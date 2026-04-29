"""
Anomaly Detection Tool for CityGrid AI Agent.

Detects anomalies in data using Isolation Forest, LOF, or Z-Score methods.
Data is injected by the graph from the last execute_sql result.
"""

import json
from typing import Any, Union

import numpy as np
import pandas as pd
from langchain_core.tools import tool
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor


MAX_SAMPLE_ROWS = 20
MAX_ANOMALY_INDICES = 100


def _parse_data(data: Union[str, list[dict]]) -> pd.DataFrame:
    if isinstance(data, str):
        data = json.loads(data)
    if not data:
        raise ValueError("No data provided. Call execute_sql first to get data.")
    return pd.DataFrame(data)


def _validate_feature_columns(df: pd.DataFrame, feature_columns: list[str]) -> pd.DataFrame:
    missing = [c for c in feature_columns if c not in df.columns]
    if missing:
        raise ValueError(
            f"Columns not found: {missing}. Available: {list(df.columns)}"
        )
    sub = df[feature_columns].copy()
    for col in feature_columns:
        sub[col] = pd.to_numeric(sub[col], errors="coerce")
    sub = sub.dropna()
    if sub.empty:
        raise ValueError(
            "No valid numeric data after converting feature_columns. "
            "Ensure the selected columns contain numbers."
        )
    return sub


def _build_summary(
    df_original: pd.DataFrame,
    feature_df: pd.DataFrame,
    labels: np.ndarray,
    scores: np.ndarray | None,
    method: str,
) -> dict[str, Any]:
    anomaly_mask = labels == -1
    anomaly_indices = feature_df.index[anomaly_mask].tolist()
    n_anomalies = int(anomaly_mask.sum())

    sample_rows = df_original.loc[anomaly_indices[:MAX_SAMPLE_ROWS]].copy()
    if scores is not None:
        sample_rows = sample_rows.copy()
        sample_rows["anomaly_score"] = scores[anomaly_mask][:MAX_SAMPLE_ROWS]

    return {
        "success": True,
        "method": method,
        "n_total": len(feature_df),
        "n_anomalies": n_anomalies,
        "anomaly_ratio": round(n_anomalies / len(feature_df), 4) if len(feature_df) else 0,
        "anomaly_indices": anomaly_indices[:MAX_ANOMALY_INDICES],
        "sample_anomaly_rows": sample_rows.to_dict(orient="records"),
    }


@tool
def detect_anomalies(
    feature_columns: list[str],
    data: Union[str, list[dict]] = "",
    method: str = "isolation_forest",
    contamination: float = 0.1,
    z_threshold: float = 3.0,
) -> dict[str, Any]:
    """
    Detect anomalies in data using statistical / ML methods.

    Data is automatically provided from the last execute_sql result.
    Call execute_sql first, then call this tool specifying numeric columns to analyze.

    Args:
        feature_columns: List of numeric column names to analyze for anomalies.
        data: Data as JSON string or list of dicts. Automatically injected by the system
              from the last execute_sql result — you do NOT need to pass it.
        method: Detection method — "isolation_forest" (default), "lof", or "zscore".
        contamination: Expected proportion of anomalies (0..0.5). Used by isolation_forest and lof. Default 0.1.
        z_threshold: Z-score threshold for zscore method. Default 3.0.

    Returns:
        Summary with anomaly count, indices, and sample anomaly rows.
    """
    try:
        df = _parse_data(data)
        feature_df = _validate_feature_columns(df, feature_columns)
        X = feature_df.values

        if method == "isolation_forest":
            cont = max(0.001, min(contamination, 0.5))
            model = IsolationForest(contamination=cont, random_state=42, n_jobs=-1)
            labels = model.fit_predict(X)
            scores = model.decision_function(X)
            return _build_summary(df, feature_df, labels, scores, method)

        if method == "lof":
            cont = max(0.001, min(contamination, 0.5))
            model = LocalOutlierFactor(contamination=cont, n_jobs=-1)
            labels = model.fit_predict(X)
            scores = model.negative_outlier_factor_
            return _build_summary(df, feature_df, labels, scores, method)

        if method == "zscore":
            means = np.mean(X, axis=0)
            stds = np.std(X, axis=0)
            stds[stds == 0] = 1.0
            z = np.abs((X - means) / stds)
            max_z = np.max(z, axis=1)
            labels = np.where(max_z > z_threshold, -1, 1)
            return _build_summary(df, feature_df, labels, max_z, method)

        return {
            "success": False,
            "error": f"Unknown method: {method}. Use: isolation_forest, lof, zscore",
        }

    except json.JSONDecodeError as e:
        return {"success": False, "error": f"Invalid JSON data: {e}"}
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"Anomaly detection failed: {e}"}


ANOMALY_TOOLS = [detect_anomalies]
