"""
train.py — Run this to pre-train and save the ML models.
The Flask app also auto-trains on first startup if models don't exist.

Usage:
    python train.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from src.cost_predictor import CostPredictor

if __name__ == '__main__':
    print("Training SQL optimization ML models...")
    predictor = CostPredictor()
    print(f"✅ Strategy model trained and saved to models/")
    print(f"✅ Cost model trained and saved to models/")

    # Quick sanity check
    test_query = "SELECT * FROM orders o JOIN customers c ON o.customer_id = c.id WHERE o.amount > 500 ORDER BY o.created_at"
    result = predictor.predict_strategy(test_query)
    print(f"\nTest prediction:")
    print(f"  Query: {test_query[:60]}...")
    print(f"  Recommended strategy: {result['recommended_strategy']}")
    print(f"  ML estimated cost: {result['ml_estimated_cost']}")
    print(f"  Top strategies: {[s['strategy'] for s in result['top_strategies']]}")
    print("\nDone!")
