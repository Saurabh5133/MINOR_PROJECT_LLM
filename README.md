# QueryForge — SQL Query Optimization Engine

A production-level SQL Query Optimizer with ML-based strategy prediction, rule-based transformations, real SQLite execution plans, and cloud cost analysis across AWS Redshift, GCP BigQuery, and Azure Synapse Analytics.

---

## Architecture

```
React Frontend (port 3000)
        ↓
Node.js / Express Backend (port 3001)
        ↓
Flask ML Service (port 5001)
        ↓
SQLite (in-memory, real EXPLAIN QUERY PLAN)
        ↓ (optional)
LLM API (OpenAI / Groq / Mistral)
```

---

## Features

- **ML Strategy Prediction** — Random Forest + Gradient Boosting trained on 2000 synthetic queries
- **Rule-Based Optimizer** — 8 optimization rules (SELECT *, predicate pushdown, IN→EXISTS, etc.)
- **Real Execution Plans** — SQLite `EXPLAIN QUERY PLAN` on auto-generated schema data
- **Cloud Cost Analysis** — Real pricing models for AWS Redshift, GCP BigQuery, Azure Synapse
- **LLM Rewriting** — OpenAI-compatible API support (key optional, works without it)
- **Query Comparison** — Side-by-side before/after with cost reduction percentage
- **Optimization Trace** — Step-by-step pipeline trace for debugging

---

## Quick Start

### 1. ML Service (Python)

```bash
cd ml-model
pip install -r requirements.txt
python train.py          # optional: pre-train models
python app.py            # starts on port 5001
```

### 2. Backend (Node.js)

```bash
cd backend
npm install
npm start               # starts on port 3001
```

### 3. Frontend (React)

```bash
cd frontend
npm install
npm start               # starts on port 3000, opens browser
```

---

## LLM Setup (Optional)

Edit `ml-model/.env`:

```env
OPENAI_API_KEY=sk-...your-key...
LLM_MODEL=gpt-4o-mini
```

### Free LLM Options

| Provider | Free Tier | Setup |
|----------|-----------|-------|
| **Groq** | Yes (generous) | `https://console.groq.com` → set `LLM_BASE_URL=https://api.groq.com/openai/v1` and `LLM_MODEL=llama3-8b-8192` |
| **Mistral AI** | Free tier | `https://mistral.ai` → `LLM_BASE_URL=https://api.mistral.ai/v1`, `LLM_MODEL=mistral-small-latest` |
| **Together AI** | Free credits | `https://api.together.xyz` → `LLM_BASE_URL=https://api.together.xyz/v1` |

---

## Input Format

```json
{
  "query": "SELECT * FROM orders o JOIN customers c ON o.customer_id = c.id WHERE o.amount > 500",
  "schema": {
    "orders": {
      "columns": ["id", "customer_id", "amount", "status", "created_at"],
      "row_count": 50000
    },
    "customers": {
      "columns": ["id", "name", "email", "city"],
      "row_count": 10000
    }
  },
  "use_llm": false,
  "calculate_cloud_cost": true
}
```

---

## Cloud Cost Methodology

Costs are calculated using real published pricing:

| Platform | Pricing Model | Key Cost Driver |
|----------|--------------|-----------------|
| AWS Redshift | $0.25/hr (dc2.large) + $5/TB scanned | Compute time + Spectrum scan |
| GCP BigQuery | $5/TB scanned (on-demand) + slot usage | Data scanned |
| Azure Synapse | $1.51/hr (DW100c) + $0.10/GB external | Compute DWU + data movement |

Estimates use: data volume, compression ratio, query complexity, join count, selectivity.

---

## Optimization Rules

| Rule | Description |
|------|-------------|
| `projection_optimization` | Replace SELECT * with explicit columns |
| `predicate_pushdown` | Move WHERE filters closer to table scans |
| `remove_redundant_orderby` | Remove ORDER BY in subqueries without LIMIT |
| `limit_injection` | Add LIMIT to prevent unbounded scans |
| `in_to_exists` | Convert IN (subquery) to EXISTS |
| `count_optimization` | Replace COUNT(col) with COUNT(*) |
| `remove_redundant_distinct` | Remove DISTINCT when GROUP BY guarantees uniqueness |
| `implicit_to_explicit_join` | Rewrite implicit joins to explicit JOIN syntax |

---

## Project Structure

```
QueryOptimizer/
├── frontend/              # React app
│   └── src/
│       ├── App.jsx        # Main app + routing
│       └── components/    # QueryInput, ResultPanel, CloudCostPanel, etc.
├── backend/               # Node.js / Express proxy
│   └── server.js
└── ml-model/              # Python Flask ML service
    ├── app.py             # Flask routes
    ├── train.py           # Standalone model training
    ├── requirements.txt
    └── src/
        ├── optimizer_pipeline.py   # Main orchestrator
        ├── feature_extractor.py    # SQL → feature vector
        ├── cost_predictor.py       # Random Forest + GB models
        ├── rule_optimizer.py       # 8 rule-based optimizations
        ├── sqlite_engine.py        # Real execution plans
        ├── cloud_cost.py           # AWS/GCP/Azure pricing
        ├── llm_optimizer.py        # OpenAI-compatible LLM
        ├── complexity_analyzer.py  # Query complexity scoring
        ├── validator.py            # SQL validation
        └── explanation.py          # Human-readable explanations
```
