"""
Flask ML Service - Main API Entry Point
Serves the SQL Query Optimization engine via REST API.
"""
from flask import Flask, request, jsonify
import traceback
import os
import sys
import sqlglot

sys.path.insert(0, os.path.dirname(__file__))

from src.optimizer_pipeline import OptimizerPipeline
from src.llm_optimizer import LLMOptimizer
from src.cloud_cost import CloudCostCalculator

app = Flask(__name__)

# Manual CORS (works without flask-cors package)
@app.after_request
def add_cors(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
    return response

@app.before_request
def handle_preflight():
    if request.method == 'OPTIONS':
        from flask import Response
        r = Response()
        r.headers['Access-Control-Allow-Origin'] = '*'
        r.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
        r.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
        return r, 204

# Initialize pipeline (loads ML models on startup)
print("[Startup] Initializing optimizer pipeline...")
pipeline = OptimizerPipeline()
print("[Startup] Pipeline ready.")


@app.route('/health', methods=['GET'])
def health():
    llm_status = LLMOptimizer().get_status()
    return jsonify({
        'status': 'ok',
        'service': 'SQL Query Optimizer ML Service',
        'version': '2.0.0',
        'llm': llm_status,
    })


@app.route('/optimize', methods=['POST'])
def optimize():
    """
    Main optimization endpoint.
    
    Body:
    {
        "query": "SELECT ...",
        "schema": { "table": { "columns": [...], "row_count": N } },
        "use_llm": false,
        "calculate_cloud_cost": true
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body must be JSON'}), 400

        query = data.get('query', '').strip()
        schema = data.get('schema', {})
        use_llm = data.get('use_llm', False)
        calculate_cloud_cost = data.get('calculate_cloud_cost', True)

        if not query:
            return jsonify({'error': 'Query is required'}), 400
        # SQL syntax validation
        try:
            sqlglot.parse_one(query, read="mysql")
        except Exception as e:
            return jsonify({
                'error': f'Invalid SQL syntax: {str(e)}'
            }), 400

        # Validate query starts with SELECT (read-only)
        if not query.upper().lstrip().startswith(('SELECT', 'WITH')):
            return jsonify({'error': 'Only SELECT queries are supported for optimization'}), 400

        result = pipeline.run(
            query=query,
            schema=schema,
            use_llm=use_llm,
            calculate_cloud_cost=calculate_cloud_cost,
        )

        return jsonify(result)

    except Exception as e:
        traceback.print_exc()
        return jsonify({
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500


@app.route('/cloud-cost', methods=['POST'])
def cloud_cost_only():
    """Calculate cloud costs for a query without full optimization."""
    try:
        data = request.get_json()
        query = data.get('query', '')
        schema = data.get('schema', {})
        execution_cost = data.get('execution_cost', 100)

        calculator = CloudCostCalculator()
        costs = calculator.calculate_all(query, schema, execution_cost)
        return jsonify(costs)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/llm-status', methods=['GET'])
def llm_status():
    """Check LLM configuration status."""
    return jsonify(LLMOptimizer().get_status())


@app.route('/features', methods=['POST'])
def extract_features():
    """Extract query features only (for debugging/inspection)."""
    try:
        data = request.get_json()
        from src.feature_extractor import FeatureExtractor
        extractor = FeatureExtractor()
        features = extractor.extract(data.get('query', ''), data.get('schema'))
        return jsonify({'features': features})
    except Exception as e:
        return jsonify({'error': str(e)}), 500



@app.route('/index-advice', methods=['POST'])
def index_advice():
    """
    Standalone index recommendation endpoint.
    Body: { "query": "...", "schema": {...} }
    """
    try:
        data   = request.get_json()
        query  = data.get('query', '').strip()
        schema = data.get('schema', {})
        if not query:
            return jsonify({'error': 'Query is required'}), 400
        from src.index_advisor import IndexAdvisor
        advisor = IndexAdvisor()
        result  = advisor.analyze(query, schema)
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

# if __name__ == '__main__':
#     port = int(os.getenv('PORT', 5001))
#     debug = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
#     app.run(host='0.0.0.0', port=port, debug=debug)

# ─── MySQL Routes ─────────────────────────────────────────────────────────────

_mysql_pipeline = None   # singleton — keeps connection alive

def get_mysql_pipeline():
    global _mysql_pipeline
    if _mysql_pipeline is None:
        from src.mysql_pipeline import MySQLPipeline
        _mysql_pipeline = MySQLPipeline()
    return _mysql_pipeline



@app.route('/mysql/check', methods=['GET'])
def mysql_check():
    """Check if pymysql is installed."""
    try:
        import pymysql
        return jsonify({'available': True, 'version': pymysql.__version__})
    except ImportError:
        return jsonify({
            'available': False,
            'message': 'Run: pip install pymysql cryptography'
        })

# @app.route('/mysql/connect', methods=['POST'])
# def mysql_connect():
#     """Connect to MySQL. Body: {host, port, user, password}"""
#     try:
#         # Check pymysql is installed first
#         try:
#             import pymysql
#         except ImportError:
#             return jsonify({
#                 'success': False,
#                 'message': 'pymysql not installed. Run this command in your terminal: '

# pip install pymysql cryptography

# Then restart the ML service (python app.py).'
#             }), 200  # 200 so frontend shows the message properly

#         d    = request.get_json()
#         mp   = get_mysql_pipeline()
#         res  = mp.connect(
#             host     = d.get('host', 'localhost'),
#             port     = int(d.get('port', 3306)),
#             user     = d.get('user', 'root'),
#             password = d.get('password', ''),
#         )
#         return jsonify(res)
#     except Exception as e:
#         traceback.print_exc()
#         return jsonify({'success': False, 'message': str(e)}), 500



@app.route('/mysql/connect', methods=['POST'])
def mysql_connect():
    """Connect to MySQL. Body: {host, port, user, password}"""
    try:
        # Check pymysql is installed first
        try:
            import pymysql
        except ImportError:
            return jsonify({
                'success': False,
                'message': 'pymysql not installed. Run this command in your terminal:\npip install pymysql cryptography\n\nThen restart the ML service (python app.py).'
            }), 200

        d = request.get_json()
        mp = get_mysql_pipeline()

        res = mp.connect(
            host=d.get('host', 'localhost'),
            port=int(d.get('port', 3306)),
            user=d.get('user', 'root'),
            password=d.get('password', ''),
        )

        return jsonify(res)

    except Exception as e:
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@app.route('/mysql/setup-demo', methods=['POST'])
def mysql_setup_demo():
    """Create queryforge_demo database with sample tables."""
    try:
        mp  = get_mysql_pipeline()
        if not mp.engine.connected:
            return jsonify({'success': False, 'message': 'Not connected to MySQL'}), 400
        res = mp.setup_demo()
        return jsonify(res)
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/mysql/databases', methods=['GET'])
def mysql_databases():
    """List available databases."""
    try:
        mp = get_mysql_pipeline()
        if not mp.engine.connected:
            return jsonify({'success': False, 'databases': []}), 400
        with mp.engine.conn.cursor() as cur:
            cur.execute("SHOW DATABASES")
            import pymysql.cursors
            dbs = [list(r.values())[0] for r in cur.fetchall()
                   if list(r.values())[0] not in
                   ('information_schema','performance_schema','mysql','sys')]
        return jsonify({'success': True, 'databases': dbs})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/mysql/schema/<database>', methods=['GET'])
def mysql_schema(database):
    """Read real schema from a database."""
    try:
        mp     = get_mysql_pipeline()
        schema = mp.engine.read_schema(database)
        return jsonify({'success': True, 'schema': schema, 'tables': list(schema.keys())})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/mysql/optimize', methods=['POST'])
def mysql_optimize():
    """
    Full optimization using real MySQL.
    Body: {query, database, use_llm}
    """
    try:
        d        = request.get_json()
        query    = d.get('query', '').strip()
        database = d.get('database', '')
        use_llm  = d.get('use_llm', False)

        if not query:
            return jsonify({'error': 'Query is required'}), 400

        mp = get_mysql_pipeline()
        if not mp.engine.connected:
            return jsonify({'error': 'Not connected to MySQL. Connect first.'}), 400

        result = mp.run(query=query, database=database, use_llm=use_llm)
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/mysql/drop-demo', methods=['POST'])
def mysql_drop_demo():
    """Drop the queryforge_demo database."""
    try:
        mp  = get_mysql_pipeline()
        res = mp.drop_demo()
        return jsonify(res)
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/mysql/status', methods=['GET'])
def mysql_status():
    """Check MySQL connection status."""
    try:
        mp = get_mysql_pipeline()
        if mp.engine.connected:
            return jsonify({
                'connected': True,
                'database': mp.current_db,
                'version': mp.engine._server_version(),
            })
        return jsonify({'connected': False})
    except Exception:
        return jsonify({'connected': False})


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5001))
    debug = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug)