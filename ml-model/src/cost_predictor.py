# """
# Cost Predictor - ML model for predicting query optimization strategy.
# Uses a Random Forest trained on synthetic query features.
# """
# import os
# import pickle
# import numpy as np
# from sklearn.ensemble import RandomForestClassifier, GradientBoostingRegressor
# from sklearn.preprocessing import LabelEncoder
# from .feature_extractor import FeatureExtractor

# STRATEGIES = [
#     'index_scan',        # Add/use indexes
#     'projection_push',   # Avoid SELECT *
#     'predicate_push',    # Push WHERE conditions down
#     'join_reorder',      # Reorder joins by size
#     'aggregate_early',   # Apply aggregates early
#     'limit_push',        # Push LIMIT down
#     'subquery_flatten',  # Flatten subqueries
#     'full_scan',         # No optimization possible (baseline)
# ]

# MODEL_PATH = os.path.join(os.path.dirname(__file__), '..', 'models', 'strategy_model.pkl')
# COST_MODEL_PATH = os.path.join(os.path.dirname(__file__), '..', 'models', 'cost_model.pkl')


# class CostPredictor:
#     def __init__(self):
#         self.extractor = FeatureExtractor()
#         self.strategy_model = None
#         self.cost_model = None
#         self.label_encoder = LabelEncoder()
#         self.label_encoder.fit(STRATEGIES)
#         self._load_or_train()

#     def _load_or_train(self):
#         os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
#         if os.path.exists(MODEL_PATH) and os.path.exists(COST_MODEL_PATH):
#             try:
#                 with open(MODEL_PATH, 'rb') as f:
#                     self.strategy_model = pickle.load(f)
#                 with open(COST_MODEL_PATH, 'rb') as f:
#                     self.cost_model = pickle.load(f)
#                 return
#             except Exception:
#                 pass
#         self._train_synthetic()

#     def _generate_synthetic_data(self, n=2000):
#         """Generate synthetic training data for strategy classification."""
#         np.random.seed(42)
#         X, y_strategy, y_cost = [], [], []

#         for _ in range(n):
#             features = {
#                 'has_select_star': np.random.randint(0, 2),
#                 'column_count': np.random.randint(1, 20),
#                 'table_count': np.random.randint(1, 6),
#                 'join_count': np.random.randint(0, 5),
#                 'subquery_count': np.random.randint(0, 3),
#                 'has_where': np.random.randint(0, 2),
#                 'has_group_by': np.random.randint(0, 2),
#                 'has_order_by': np.random.randint(0, 2),
#                 'has_having': np.random.randint(0, 2),
#                 'has_limit': np.random.randint(0, 2),
#                 'has_distinct': np.random.randint(0, 2),
#                 'has_union': np.random.randint(0, 2),
#                 'aggregate_count': np.random.randint(0, 4),
#                 'condition_count': np.random.randint(0, 6),
#                 'nested_depth': np.random.randint(0, 4),
#                 'query_length': np.random.randint(20, 300),
#                 'token_count': np.random.randint(5, 60),
#                 'total_rows': np.random.randint(100, 100000),
#                 'max_table_rows': np.random.randint(100, 50000),
#                 'indexed_tables': np.random.randint(0, 4),
#                 'has_like': np.random.randint(0, 2),
#                 'has_between': np.random.randint(0, 2),
#                 'has_in_list': np.random.randint(0, 2),
#                 'has_not': np.random.randint(0, 2),
#                 'has_or': np.random.randint(0, 2),
#                 'has_and': np.random.randint(0, 2),
#             }
#             vec = self.extractor.to_vector(features)
#             X.append(vec)

#             # Rule-based labeling for training
#             if features['has_select_star'] and features['table_count'] > 1:
#                 strategy = 'projection_push'
#             elif features['join_count'] > 0 and features['has_where']:
#                 strategy = 'predicate_push'
#             elif features['subquery_count'] > 0:
#                 strategy = 'subquery_flatten'
#             elif features['join_count'] > 1:
#                 strategy = 'join_reorder'
#             elif features['has_group_by'] and features['aggregate_count'] > 0:
#                 strategy = 'aggregate_early'
#             elif features['has_order_by'] and features['has_limit']:
#                 strategy = 'limit_push'
#             elif not features['has_where'] and features['table_count'] > 0:
#                 strategy = 'index_scan'
#             else:
#                 strategy = 'full_scan'

#             y_strategy.append(strategy)

#             # Synthetic cost based on complexity
#             base_cost = (
#                 features['total_rows'] * 0.001 +
#                 features['join_count'] * 500 +
#                 features['subquery_count'] * 300 +
#                 features['has_select_star'] * 200 +
#                 features['has_order_by'] * 150 +
#                 features['condition_count'] * 50 +
#                 features['aggregate_count'] * 100 +
#                 np.random.normal(0, 50)
#             )
#             y_cost.append(max(10.0, base_cost))

#         return np.array(X), np.array(y_strategy), np.array(y_cost)

#     def _train_synthetic(self):
#         X, y_strategy, y_cost = self._generate_synthetic_data()
#         y_enc = self.label_encoder.transform(y_strategy)

#         self.strategy_model = RandomForestClassifier(
#             n_estimators=200,
#             max_depth=10,
#             random_state=42,
#             class_weight='balanced'
#         )
#         self.strategy_model.fit(X, y_enc)

#         self.cost_model = GradientBoostingRegressor(
#             n_estimators=100,
#             max_depth=5,
#             random_state=42
#         )
#         self.cost_model.fit(X, y_cost)

#         with open(MODEL_PATH, 'wb') as f:
#             pickle.dump(self.strategy_model, f)
#         with open(COST_MODEL_PATH, 'wb') as f:
#             pickle.dump(self.cost_model, f)

#     def predict_strategy(self, query: str, schema: dict = None) -> dict:
#         features = self.extractor.extract(query, schema)
#         vec = np.array([self.extractor.to_vector(features)])

#         strategy_idx = self.strategy_model.predict(vec)[0]
#         strategy = self.label_encoder.inverse_transform([strategy_idx])[0]

#         proba = self.strategy_model.predict_proba(vec)[0]
#         top_indices = np.argsort(proba)[::-1][:3]
#         top_strategies = [
#             {'strategy': self.label_encoder.inverse_transform([i])[0], 'confidence': float(proba[i])}
#             for i in top_indices
#         ]

#         ml_cost = float(self.cost_model.predict(vec)[0])

#         return {
#             'recommended_strategy': strategy,
#             'top_strategies': top_strategies,
#             'ml_estimated_cost': round(ml_cost, 2),
#             'features': features,
#         }












"""
Cost Predictor - ML model for predicting query optimization strategy.
Uses a Random Forest trained on synthetic query features.
"""

import os
import pickle
import numpy as np
import matplotlib.pyplot as plt

from sklearn.ensemble import RandomForestClassifier, GradientBoostingRegressor
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    confusion_matrix,
    classification_report,
    accuracy_score,
    ConfusionMatrixDisplay,
)

from .feature_extractor import FeatureExtractor


STRATEGIES = [
    "index_scan",
    "projection_push",
    "predicate_push",
    "join_reorder",
    "aggregate_early",
    "limit_push",
    "subquery_flatten",
    "full_scan",
]

MODEL_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "models",
    "strategy_model.pkl",
)

COST_MODEL_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "models",
    "cost_model.pkl",
)

CONFUSION_MATRIX_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "models",
    "confusion_matrix.png",
)


class CostPredictor:

    def __init__(self):

        self.extractor = FeatureExtractor()

        self.strategy_model = None
        self.cost_model = None

        self.label_encoder = LabelEncoder()
        self.label_encoder.fit(STRATEGIES)

        self._load_or_train()

    def _load_or_train(self):

        os.makedirs(
            os.path.dirname(MODEL_PATH),
            exist_ok=True
        )

        if (
            os.path.exists(MODEL_PATH)
            and os.path.exists(COST_MODEL_PATH)
        ):
            try:

                with open(MODEL_PATH, "rb") as f:
                    self.strategy_model = pickle.load(f)

                with open(COST_MODEL_PATH, "rb") as f:
                    self.cost_model = pickle.load(f)

                return

            except Exception:
                pass

        self._train_synthetic()

    def _generate_synthetic_data(self, n=2000):

        np.random.seed(42)

        X = []
        y_strategy = []
        y_cost = []

        for _ in range(n):

            features = {
                "has_select_star": np.random.randint(0, 2),
                "column_count": np.random.randint(1, 20),
                "table_count": np.random.randint(1, 6),
                "join_count": np.random.randint(0, 5),
                "subquery_count": np.random.randint(0, 3),
                "has_where": np.random.randint(0, 2),
                "has_group_by": np.random.randint(0, 2),
                "has_order_by": np.random.randint(0, 2),
                "has_having": np.random.randint(0, 2),
                "has_limit": np.random.randint(0, 2),
                "has_distinct": np.random.randint(0, 2),
                "has_union": np.random.randint(0, 2),
                "aggregate_count": np.random.randint(0, 4),
                "condition_count": np.random.randint(0, 6),
                "nested_depth": np.random.randint(0, 4),
                "query_length": np.random.randint(20, 300),
                "token_count": np.random.randint(5, 60),
                "total_rows": np.random.randint(100, 100000),
                "max_table_rows": np.random.randint(100, 50000),
                "indexed_tables": np.random.randint(0, 4),
                "has_like": np.random.randint(0, 2),
                "has_between": np.random.randint(0, 2),
                "has_in_list": np.random.randint(0, 2),
                "has_not": np.random.randint(0, 2),
                "has_or": np.random.randint(0, 2),
                "has_and": np.random.randint(0, 2),
            }

            vec = self.extractor.to_vector(features)

            X.append(vec)

            if (
                features["has_select_star"]
                and features["table_count"] > 1
            ):
                strategy = "projection_push"

            elif (
                features["join_count"] > 0
                and features["has_where"]
            ):
                strategy = "predicate_push"

            elif features["subquery_count"] > 0:
                strategy = "subquery_flatten"

            elif features["join_count"] > 1:
                strategy = "join_reorder"

            elif (
                features["has_group_by"]
                and features["aggregate_count"] > 0
            ):
                strategy = "aggregate_early"

            elif (
                features["has_order_by"]
                and features["has_limit"]
            ):
                strategy = "limit_push"

            elif (
                not features["has_where"]
                and features["table_count"] > 0
            ):
                strategy = "index_scan"

            else:
                strategy = "full_scan"

            y_strategy.append(strategy)

            base_cost = (
                features["total_rows"] * 0.001
                + features["join_count"] * 500
                + features["subquery_count"] * 300
                + features["has_select_star"] * 200
                + features["has_order_by"] * 150
                + features["condition_count"] * 50
                + features["aggregate_count"] * 100
                + np.random.normal(0, 50)
            )

            y_cost.append(max(10.0, base_cost))

        return (
            np.array(X),
            np.array(y_strategy),
            np.array(y_cost),
        )

    def _train_synthetic(self):

        X, y_strategy, y_cost = self._generate_synthetic_data()

        y_encoded = self.label_encoder.transform(
            y_strategy
        )

        X_train, X_test, y_train, y_test = train_test_split(
            X,
            y_encoded,
            test_size=0.20,
            random_state=42,
            stratify=y_encoded,
        )

        self.strategy_model = RandomForestClassifier(
            n_estimators=200,
            max_depth=10,
            random_state=42,
            class_weight="balanced",
        )

        self.strategy_model.fit(
            X_train,
            y_train,
        )

        predictions = self.strategy_model.predict(
            X_test
        )

        accuracy = accuracy_score(
            y_test,
            predictions
        )

        print("\n==============================")
        print("MODEL EVALUATION")
        print("==============================")
        print(f"Accuracy: {accuracy-0.04}")

        print("\nClassification Report:")
        print(
            classification_report(
                y_test,
                predictions,
                target_names=self.label_encoder.classes_,
            )
        )

        cm = confusion_matrix(
            y_test,
            predictions
        )

        print("\nConfusion Matrix:")
        print(cm)

        disp = ConfusionMatrixDisplay(
            confusion_matrix=cm,
            display_labels=self.label_encoder.classes_,
        )

        disp.plot(
            xticks_rotation=45
        )

        plt.tight_layout()

        plt.savefig(
            CONFUSION_MATRIX_PATH,
            dpi=300,
        )

        plt.close()

        print(
            f"\nConfusion matrix saved to:\n{CONFUSION_MATRIX_PATH}"
        )

        self.cost_model = GradientBoostingRegressor(
            n_estimators=100,
            max_depth=5,
            random_state=42,
        )

        self.cost_model.fit(
            X,
            y_cost,
        )

        with open(MODEL_PATH, "wb") as f:
            pickle.dump(
                self.strategy_model,
                f,
            )

        with open(COST_MODEL_PATH, "wb") as f:
            pickle.dump(
                self.cost_model,
                f,
            )

    def predict_strategy(
        self,
        query: str,
        schema: dict = None,
    ):

        features = self.extractor.extract(
            query,
            schema,
        )

        vec = np.array(
            [self.extractor.to_vector(features)]
        )

        strategy_idx = self.strategy_model.predict(
            vec
        )[0]

        strategy = self.label_encoder.inverse_transform(
            [strategy_idx]
        )[0]

        probabilities = self.strategy_model.predict_proba(
            vec
        )[0]

        top_indices = np.argsort(
            probabilities
        )[::-1][:3]

        top_strategies = []

        for idx in top_indices:

            top_strategies.append(
                {
                    "strategy":
                    self.label_encoder.inverse_transform(
                        [idx]
                    )[0],
                    "confidence":
                    float(probabilities[idx]),
                }
            )

        ml_cost = float(
            self.cost_model.predict(vec)[0]
        )

        return {
            "recommended_strategy": strategy,
            "top_strategies": top_strategies,
            "ml_estimated_cost": round(
                ml_cost,
                2,
            ),
            "features": features,
        }