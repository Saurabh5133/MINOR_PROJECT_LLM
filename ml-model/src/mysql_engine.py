"""
MySQL Real Database Engine
Connects to user's local MySQL, reads real schemas,
creates demo data in isolated 'queryforge_demo' database,
runs real EXPLAIN for actual execution plans.

Requirements: pip install pymysql
"""
import re
import math
import random
import string
from datetime import datetime, timedelta

try:
    import pymysql
    import pymysql.cursors
    PYMYSQL_AVAILABLE = True
except ImportError:
    PYMYSQL_AVAILABLE = False


DEMO_DB = 'queryforge_demo'
PAGE_ROWS = 100


class MySQLEngine:
    def __init__(self):
        self.conn     = None
        self.config   = None
        self.schema   = {}
        self.connected = False

    # ─────────────────────────────────────────── connection ──

    def connect(self, host='localhost', port=3306, user='root',
                password='', database=None) -> dict:
        """Connect to MySQL. Returns {success, message, databases}"""
        if not PYMYSQL_AVAILABLE:
            return {
                'success': False,
                'message': 'pymysql not installed. Run: pip install pymysql',
                'databases': []
            }
        try:
            self.config = dict(host=host, port=int(port),
                               user=user, password=password,
                               cursorclass=pymysql.cursors.DictCursor,
                               connect_timeout=10)
            self.conn = pymysql.connect(**self.config)
            self.connected = True

            # List available databases
            with self.conn.cursor() as cur:
                cur.execute("SHOW DATABASES")
                dbs = [r['Database'] for r in cur.fetchall()
                       if r['Database'] not in
                       ('information_schema','performance_schema','mysql','sys')]

            return {'success': True,
                    'message': f'Connected to MySQL at {host}:{port}',
                    'databases': dbs,
                    'server': self._server_version()}
        except Exception as e:
            self.connected = False
            return {'success': False, 'message': str(e), 'databases': []}

    def _server_version(self):
        try:
            with self.conn.cursor() as cur:
                cur.execute("SELECT VERSION()")
                return cur.fetchone()['VERSION()']
        except Exception:
            return 'unknown'

    # ─────────────────────────────────────────── schema reading ──

    def read_schema(self, database: str) -> dict:
        """Read real schema from a MySQL database."""
        if not self.conn:
            return {}
        try:
            with self.conn.cursor() as cur:
                cur.execute(f"USE `{database}`")
                cur.execute("SHOW TABLES")
                tables = [list(r.values())[0] for r in cur.fetchall()]

            schema = {}
            for tbl in tables:
                schema[tbl] = self._read_table_info(database, tbl)
            self.schema = schema
            return schema
        except Exception as e:
            return {}

    def _read_table_info(self, database: str, table: str) -> dict:
        try:
            with self.conn.cursor() as cur:
                # Column info
                cur.execute(f"DESCRIBE `{database}`.`{table}`")
                cols = cur.fetchall()
                columns = [{'name': c['Field'], 'type': c['Type'],
                            'nullable': c['Null'] == 'YES',
                            'key': c['Key']} for c in cols]

                # Row count
                cur.execute(f"SELECT COUNT(*) as cnt FROM `{database}`.`{table}`")
                row_count = cur.fetchone()['cnt']

                # Index info
                cur.execute(f"SHOW INDEX FROM `{database}`.`{table}`")
                indexes = [{'name': i['Key_name'], 'column': i['Column_name'],
                            'unique': i['Non_unique'] == 0}
                           for i in cur.fetchall()]

            return {
                'columns': [c['name'] for c in columns],
                'column_details': columns,
                'row_count': row_count,
                'indexes': indexes,
                'indexed_columns': {i['column'] for i in indexes},
            }
        except Exception as e:
            return {'columns': [], 'row_count': 0, 'indexes': []}

    # ─────────────────────────────────────────── demo data ──

    def setup_demo_database(self) -> dict:
        """
        Create queryforge_demo database with sample tables.
        SMART: skips insertion if data already exists.
        """
        if not self.conn:
            return {'success': False, 'message': 'Not connected'}

        try:
            with self.conn.cursor() as cur:
                cur.execute(f"CREATE DATABASE IF NOT EXISTS `{DEMO_DB}`")
                cur.execute(f"USE `{DEMO_DB}`")
            self.conn.commit()

            results = {}
            for tbl_def in DEMO_TABLES:
                result = self._setup_demo_table(tbl_def)
                results[tbl_def['name']] = result

            # Read schema of demo db
            self.schema = self.read_schema(DEMO_DB)

            return {
                'success':  True,
                'database': DEMO_DB,
                'tables':   results,
                'message':  f'Demo database ready with {len(results)} tables',
            }
        except Exception as e:
            return {'success': False, 'message': str(e)}

    def _setup_demo_table(self, tbl_def: dict) -> dict:
        """Create table and insert data only if not already present."""
        name      = tbl_def['name']
        target    = tbl_def['row_count']
        create_sql = tbl_def['create_sql']

        try:
            with self.conn.cursor() as cur:
                # Create table
                cur.execute(f"USE `{DEMO_DB}`")
                cur.execute(create_sql)

                # Check existing rows
                cur.execute(f"SELECT COUNT(*) as cnt FROM `{name}`")
                existing = cur.fetchone()['cnt']

            if existing >= target * 0.9:
                return {'status': 'reused', 'rows': existing}

            # Insert data
            rows_to_insert = target - existing
            self._insert_demo_data(name, tbl_def, rows_to_insert, existing)
            self.conn.commit()
            return {'status': 'created', 'rows': target}

        except Exception as e:
            return {'status': 'error', 'error': str(e)}

    def _insert_demo_data(self, table: str, tbl_def: dict,
                          count: int, offset: int):
        """Insert realistic demo data in batches."""
        cols      = tbl_def['columns']
        generator = tbl_def['generator']
        batch_size = 500

        col_names = ', '.join(f'`{c}`' for c in cols)
        placeholders = ', '.join(['%s'] * len(cols))
        sql = f"INSERT INTO `{table}` ({col_names}) VALUES ({placeholders})"

        batch = []
        with self.conn.cursor() as cur:
            for i in range(count):
                row = generator(i + offset + 1)
                batch.append(row)
                if len(batch) >= batch_size:
                    cur.executemany(sql, batch)
                    self.conn.commit()
                    batch = []
            if batch:
                cur.executemany(sql, batch)
                self.conn.commit()

    # ─────────────────────────────────────────── EXPLAIN ──

    def get_execution_plan(self, query: str, database: str = None) -> dict:
        """Run EXPLAIN on real MySQL and return structured plan."""
        if not self.conn:
            return {'error': 'Not connected', 'steps': [], 'cost': 999}

        db = database or DEMO_DB
        try:
            with self.conn.cursor() as cur:
                cur.execute(f"USE `{db}`")
                cur.execute(f"EXPLAIN {query.strip().rstrip(';')}")
                rows = cur.fetchall()

            steps = []
            total_cost = 0
            for row in rows:
                step = self._parse_explain_row(row)
                steps.append(step)
                total_cost += step['step_cost']

            return {
                'steps': steps,
                'cost':  round(total_cost, 2),
                'raw':   rows,
                'type':  'mysql_explain',
            }
        except Exception as e:
            return {'error': str(e), 'steps': [], 'cost': 999}

    def _parse_explain_row(self, row: dict) -> dict:
        """
        Parse a MySQL EXPLAIN row into structured step.
        MySQL EXPLAIN columns:
          id, select_type, table, type, possible_keys, key,
          key_len, ref, rows, filtered, Extra
        """
        tbl       = row.get('table', '') or ''
        acc_type  = row.get('type', 'ALL') or 'ALL'    # ALL=full scan, ref/eq_ref=index
        key_used  = row.get('key') or None
        rows_est  = int(row.get('rows', 100) or 100)
        filtered  = float(row.get('filtered', 100) or 100) / 100
        extra     = row.get('Extra', '') or ''

        # Cost estimation from EXPLAIN data
        uses_index = key_used is not None
        if acc_type in ('eq_ref', 'const', 'system'):
            step_cost = 1.0                                    # single row lookup
        elif acc_type in ('ref', 'range', 'index_merge'):
            step_cost = max(1, math.log2(rows_est + 1) * 5)   # index range scan
        elif acc_type == 'index':
            step_cost = rows_est / PAGE_ROWS                   # full index scan
        else:
            # ALL = full table scan
            # Get real row count from schema
            real_rows = rows_est
            for tn, ti in self.schema.items():
                if tn.lower() == tbl.lower():
                    real_rows = ti.get('row_count', rows_est)
                    break
            step_cost = real_rows / PAGE_ROWS

        # Extra penalties
        if 'Using filesort' in extra:
            step_cost += rows_est / PAGE_ROWS * 0.3
        if 'Using temporary' in extra:
            step_cost += rows_est / PAGE_ROWS * 0.2

        return {
            'table':        tbl,
            'detail':       f"{acc_type.upper()} on {tbl}" + (f" using {key_used}" if key_used else " (full scan)"),
            'type':         'SEARCH' if uses_index else 'SCAN',
            'access_type':  acc_type,
            'key':          key_used,
            'rows_est':     rows_est,
            'filtered_pct': round(filtered * 100, 1),
            'uses_index':   uses_index,
            'extra':        extra,
            'step_cost':    round(step_cost, 2),
        }

    def get_execution_time(self, query: str, database: str = None) -> dict:
        """Run query and measure real execution time in milliseconds."""
        if not self.conn:
            return {'success': False, 'error': 'Not connected'}
        db = database or DEMO_DB
        import time
        try:
            with self.conn.cursor() as cur:
                cur.execute(f"USE `{db}`")
                # Use SELECT query safely
                safe_q = query.strip().rstrip(';')
                if not safe_q.upper().startswith('SELECT'):
                    return {'success': False, 'error': 'Only SELECT queries supported'}
                start  = time.perf_counter()
                cur.execute(safe_q)
                cur.fetchall()
                elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            return {'success': True, 'elapsed_ms': elapsed_ms}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # ─────────────────────────────────────────── cleanup ──

    def drop_demo_database(self) -> dict:
        if not self.conn:
            return {'success': False}
        try:
            with self.conn.cursor() as cur:
                cur.execute(f"DROP DATABASE IF EXISTS `{DEMO_DB}`")
            self.conn.commit()
            return {'success': True, 'message': f'Dropped {DEMO_DB}'}
        except Exception as e:
            return {'success': False, 'message': str(e)}

    def close(self):
        if self.conn:
            try: self.conn.close()
            except: pass
            self.conn = None
        self.connected = False


# ─────────────────────────────────────────── demo table definitions ──

def _random_date(start_year=2018, end_year=2025):
    start = datetime(start_year, 1, 1)
    end   = datetime(end_year, 12, 31)
    return (start + timedelta(
        seconds=random.randint(0, int((end-start).total_seconds()))
    )).strftime('%Y-%m-%d %H:%M:%S')

def _rand_str(n=8):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=n))

CITIES    = ['New York','London','Tokyo','Paris','Sydney','Dubai','Toronto',
             'Berlin','Singapore','Mumbai','São Paulo','Cairo','Seoul']
COUNTRIES = ['USA','UK','Japan','France','Australia','UAE','Canada',
             'Germany','Singapore','India','Brazil','Egypt','South Korea']
STATUSES  = ['active','inactive','pending','approved','rejected','completed','cancelled']
DEPTS     = ['Engineering','Marketing','Sales','Finance','HR','Operations',
             'Legal','Product','Design','Data Science']

DEMO_TABLES = [
    # ── 1. customers ──────────────────────────────────────────────
    {
        'name': 'customers',
        'row_count': 10000,
        'columns': ['id','first_name','last_name','email','phone',
                    'city','country','age','registered_at','is_active'],
        'create_sql': """
            CREATE TABLE IF NOT EXISTS `customers` (
                `id`            INT PRIMARY KEY AUTO_INCREMENT,
                `first_name`    VARCHAR(50),
                `last_name`     VARCHAR(50),
                `email`         VARCHAR(100) UNIQUE,
                `phone`         VARCHAR(20),
                `city`          VARCHAR(60),
                `country`       VARCHAR(60),
                `age`           INT,
                `registered_at` DATETIME,
                `is_active`     TINYINT DEFAULT 1,
                INDEX idx_country (`country`),
                INDEX idx_city    (`city`),
                INDEX idx_active  (`is_active`)
            ) ENGINE=InnoDB
        """,
        'generator': lambda i: (
            i,
            random.choice(['Alice','Bob','Carol','David','Eva','Frank',
                           'Grace','Henry','Iris','Jack','Karen','Leo']),
            random.choice(['Smith','Johnson','Williams','Brown','Jones',
                           'Garcia','Miller','Davis','Wilson','Moore']),
            f'user{i}@example.com',
            f'+{random.randint(1,99)}{random.randint(1000000000,9999999999)}',
            random.choice(CITIES),
            random.choice(COUNTRIES),
            random.randint(18, 75),
            _random_date(2018, 2024),
            random.randint(0, 1),
        ),
    },
    # ── 2. orders ─────────────────────────────────────────────────
    {
        'name': 'orders',
        'row_count': 50000,
        'columns': ['id','customer_id','amount','status',
                    'category','created_at','shipped_at','notes'],
        'create_sql': """
            CREATE TABLE IF NOT EXISTS `orders` (
                `id`          INT PRIMARY KEY AUTO_INCREMENT,
                `customer_id` INT,
                `amount`      DECIMAL(10,2),
                `status`      VARCHAR(20),
                `category`    VARCHAR(40),
                `created_at`  DATETIME,
                `shipped_at`  DATETIME,
                `notes`       TEXT,
                INDEX idx_customer (`customer_id`),
                INDEX idx_status   (`status`),
                INDEX idx_created  (`created_at`)
            ) ENGINE=InnoDB
        """,
        'generator': lambda i: (
            i,
            random.randint(1, 10000),
            round(random.uniform(10, 5000), 2),
            random.choice(['pending','processing','shipped','delivered','cancelled']),
            random.choice(['Electronics','Clothing','Food','Books',
                           'Sports','Home','Beauty','Toys']),
            _random_date(2020, 2025),
            _random_date(2020, 2025),
            f'Order note {i}',
        ),
    },
    # ── 3. products ───────────────────────────────────────────────
    {
        'name': 'products',
        'row_count': 5000,
        'columns': ['id','name','category','price','stock',
                    'supplier_id','rating','created_at','is_available'],
        'create_sql': """
            CREATE TABLE IF NOT EXISTS `products` (
                `id`           INT PRIMARY KEY AUTO_INCREMENT,
                `name`         VARCHAR(100),
                `category`     VARCHAR(50),
                `price`        DECIMAL(10,2),
                `stock`        INT,
                `supplier_id`  INT,
                `rating`       DECIMAL(3,2),
                `created_at`   DATETIME,
                `is_available` TINYINT DEFAULT 1,
                INDEX idx_category  (`category`),
                INDEX idx_price     (`price`),
                INDEX idx_available (`is_available`)
            ) ENGINE=InnoDB
        """,
        'generator': lambda i: (
            i,
            f'Product {_rand_str(5)}',
            random.choice(['Electronics','Clothing','Food','Books',
                           'Sports','Home','Beauty','Toys']),
            round(random.uniform(5, 2000), 2),
            random.randint(0, 500),
            random.randint(1, 100),
            round(random.uniform(1.0, 5.0), 2),
            _random_date(2018, 2024),
            random.randint(0, 1),
        ),
    },
    # ── 4. employees ──────────────────────────────────────────────
    {
        'name': 'employees',
        'row_count': 8000,
        'columns': ['id','first_name','last_name','email','department',
                    'salary','hire_date','manager_id','is_active','city'],
        'create_sql': """
            CREATE TABLE IF NOT EXISTS `employees` (
                `id`         INT PRIMARY KEY AUTO_INCREMENT,
                `first_name` VARCHAR(50),
                `last_name`  VARCHAR(50),
                `email`      VARCHAR(100),
                `department` VARCHAR(50),
                `salary`     DECIMAL(10,2),
                `hire_date`  DATE,
                `manager_id` INT,
                `is_active`  TINYINT DEFAULT 1,
                `city`       VARCHAR(60),
                INDEX idx_dept   (`department`),
                INDEX idx_salary (`salary`),
                INDEX idx_active (`is_active`)
            ) ENGINE=InnoDB
        """,
        'generator': lambda i: (
            i,
            random.choice(['Alice','Bob','Carol','David','Eva',
                           'Frank','Grace','Henry','Iris','Jack']),
            random.choice(['Smith','Johnson','Williams','Brown','Jones']),
            f'emp{i}@company.com',
            random.choice(DEPTS),
            round(random.uniform(30000, 150000), 2),
            _random_date(2010, 2024)[:10],
            random.randint(1, min(i, 100)) if i > 1 else None,
            random.randint(0, 1),
            random.choice(CITIES),
        ),
    },
    # ── 5. transactions ───────────────────────────────────────────
    {
        'name': 'transactions',
        'row_count': 100000,
        'columns': ['id','customer_id','order_id','amount','transaction_type',
                    'status','created_at','gateway','is_flagged'],
        'create_sql': """
            CREATE TABLE IF NOT EXISTS `transactions` (
                `id`               INT PRIMARY KEY AUTO_INCREMENT,
                `customer_id`      INT,
                `order_id`         INT,
                `amount`           DECIMAL(10,2),
                `transaction_type` VARCHAR(20),
                `status`           VARCHAR(20),
                `created_at`       DATETIME,
                `gateway`          VARCHAR(30),
                `is_flagged`       TINYINT DEFAULT 0,
                INDEX idx_customer  (`customer_id`),
                INDEX idx_order     (`order_id`),
                INDEX idx_status    (`status`),
                INDEX idx_flagged   (`is_flagged`),
                INDEX idx_created   (`created_at`)
            ) ENGINE=InnoDB
        """,
        'generator': lambda i: (
            i,
            random.randint(1, 10000),
            random.randint(1, 50000),
            round(random.uniform(1, 10000), 2),
            random.choice(['purchase','refund','transfer','withdrawal']),
            random.choice(['success','failed','pending','reversed']),
            _random_date(2020, 2025),
            random.choice(['stripe','paypal','razorpay','braintree']),
            random.randint(0, 1),
        ),
    },
    # ── 6. flights ────────────────────────────────────────────────
    {
        'name': 'flights',
        'row_count': 20000,
        'columns': ['id','flight_number','origin','destination','airline',
                    'departure_time','arrival_time','status',
                    'delay_minutes','seats_available'],
        'create_sql': """
            CREATE TABLE IF NOT EXISTS `flights` (
                `id`              INT PRIMARY KEY AUTO_INCREMENT,
                `flight_number`   VARCHAR(10),
                `origin`          VARCHAR(60),
                `destination`     VARCHAR(60),
                `airline`         VARCHAR(50),
                `departure_time`  DATETIME,
                `arrival_time`    DATETIME,
                `status`          VARCHAR(20),
                `delay_minutes`   INT DEFAULT 0,
                `seats_available` INT,
                INDEX idx_origin  (`origin`),
                INDEX idx_status  (`status`),
                INDEX idx_airline (`airline`)
            ) ENGINE=InnoDB
        """,
        'generator': lambda i: (
            i,
            f'{random.choice(["AA","UA","DL","BA","EK","SQ"])}{random.randint(100,9999)}',
            random.choice(CITIES),
            random.choice(CITIES),
            random.choice(['American','United','Delta','British Airways',
                           'Emirates','Singapore Airlines','Air France']),
            _random_date(2023, 2025),
            _random_date(2023, 2025),
            random.choice(['on_time','delayed','cancelled','boarding','landed']),
            random.randint(0, 300),
            random.randint(0, 350),
        ),
    },
    # ── 7. hospitals ──────────────────────────────────────────────
    {
        'name': 'patients',
        'row_count': 15000,
        'columns': ['id','first_name','last_name','age','gender',
                    'blood_type','city','admitted_at','diagnosis','severity'],
        'create_sql': """
            CREATE TABLE IF NOT EXISTS `patients` (
                `id`          INT PRIMARY KEY AUTO_INCREMENT,
                `first_name`  VARCHAR(50),
                `last_name`   VARCHAR(50),
                `age`         INT,
                `gender`      VARCHAR(10),
                `blood_type`  VARCHAR(5),
                `city`        VARCHAR(60),
                `admitted_at` DATETIME,
                `diagnosis`   VARCHAR(100),
                `severity`    VARCHAR(20),
                INDEX idx_city     (`city`),
                INDEX idx_severity (`severity`),
                INDEX idx_admitted (`admitted_at`)
            ) ENGINE=InnoDB
        """,
        'generator': lambda i: (
            i,
            random.choice(['Alice','Bob','Carol','David','Eva','Frank']),
            random.choice(['Smith','Johnson','Williams','Brown','Jones']),
            random.randint(1, 90),
            random.choice(['Male','Female']),
            random.choice(['A+','A-','B+','B-','O+','O-','AB+','AB-']),
            random.choice(CITIES),
            _random_date(2020, 2025),
            random.choice(['Diabetes','Hypertension','COVID-19','Fracture',
                           'Appendicitis','Pneumonia','Migraine','Asthma']),
            random.choice(['mild','moderate','severe','critical']),
        ),
    },
]
