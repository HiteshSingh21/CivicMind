"""
CivicMind -- Forecasting Agent
================================
Time series prediction with confidence intervals.

Local fallback: statsmodels exponential smoothing / simple trend projection
Google Cloud swap-in: BigQuery ML ML.FORECAST with ARIMA_PLUS model
"""

import os
import json
from datetime import datetime, timedelta
from typing import Optional

from agents.utils.db_interface import get_database

try:
    import numpy as np
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False

try:
    from statsmodels.tsa.holtwinters import ExponentialSmoothing
    STATSMODELS_AVAILABLE = True
except ImportError:
    STATSMODELS_AVAILABLE = False

try:
    from google import genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False


def _get_genai_client():
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key or not GENAI_AVAILABLE:
        return None
    return genai.Client(api_key=api_key)


def _forecast_with_statsmodels(dates: list, values: list, horizon: int = 30):
    """Use exponential smoothing for time-series forecast with confidence bands."""
    if not STATSMODELS_AVAILABLE or not PANDAS_AVAILABLE:
        return _forecast_simple_trend(dates, values, horizon)

    try:
        series = pd.Series(values, index=pd.to_datetime(dates))
        series = series.asfreq('D', fill_value=series.mean())

        # Fit Holt-Winters exponential smoothing
        model = ExponentialSmoothing(
            series,
            trend='add',
            seasonal=None,  # Daily data, no clear weekly seasonality in 6mo
            initialization_method='estimated'
        )
        fitted = model.fit(optimized=True)

        # Forecast
        forecast = fitted.forecast(horizon)

        # Confidence intervals (approximate using residual std)
        residuals = fitted.resid
        std = residuals.std()

        forecast_dates = [series.index[-1] + timedelta(days=i+1) for i in range(horizon)]

        forecast_data = []
        for i, (date, value) in enumerate(zip(forecast_dates, forecast)):
            # Widen confidence band further into the future
            width = std * (1.0 + 0.05 * i) * 1.96
            forecast_data.append({
                "date": date.strftime("%Y-%m-%d"),
                "predicted": round(float(value), 1),
                "lower_bound": round(float(value - width), 1),
                "upper_bound": round(float(value + width), 1),
            })

        return forecast_data

    except Exception:
        return _forecast_simple_trend(dates, values, horizon)


def _forecast_simple_trend(dates: list, values: list, horizon: int = 30):
    """Simple linear trend projection fallback."""
    n = len(values)
    if n < 2:
        return []

    # Simple linear regression
    x = list(range(n))
    x_mean = sum(x) / n
    y_mean = sum(values) / n

    numerator = sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, values))
    denominator = sum((xi - x_mean) ** 2 for xi in x)

    slope = numerator / denominator if denominator != 0 else 0
    intercept = y_mean - slope * x_mean

    # Residual standard error
    predictions = [slope * xi + intercept for xi in x]
    residuals = [yi - pi for yi, pi in zip(values, predictions)]
    std = (sum(r**2 for r in residuals) / max(n - 2, 1)) ** 0.5

    last_date = datetime.strptime(dates[-1], "%Y-%m-%d")
    forecast_data = []
    for i in range(1, horizon + 1):
        date = last_date + timedelta(days=i)
        predicted = slope * (n + i - 1) + intercept
        width = std * (1.0 + 0.03 * i) * 1.96
        forecast_data.append({
            "date": date.strftime("%Y-%m-%d"),
            "predicted": round(max(0, predicted), 1),
            "lower_bound": round(max(0, predicted - width), 1),
            "upper_bound": round(predicted + width, 1),
        })

    return forecast_data


async def run_forecasting_agent(question: str) -> dict:
    """Run the Forecasting Agent.

    Pulls historical data, runs time-series forecast, returns predictions
    with confidence intervals.

    Returns dict with keys: agent, forecast, historical, summary, confidence_level, source
    """
    db = get_database()
    q_lower = question.lower()

    # Determine what to forecast based on the question
    if "respiratory" in q_lower or "complaint" in q_lower or "health" in q_lower:
        # Forecast respiratory complaints
        target_neighborhood = "Riverside"  # Default to our story's focus
        for hood in ["Riverside", "Downtown", "Greenfield", "Lakeside", "Hilltop"]:
            if hood.lower() in q_lower:
                target_neighborhood = hood
                break

        sql = f"""
            SELECT date, SUM(complaint_count) as value
            FROM respiratory_complaints
            WHERE neighborhood = '{target_neighborhood}'
            GROUP BY date
            ORDER BY date
        """
        metric_name = f"Respiratory Complaints in {target_neighborhood}"
        source = "Table: respiratory_complaints"

    elif "congestion" in q_lower or "delay" in q_lower or "transit" in q_lower or "route" in q_lower:
        sql = """
            SELECT date, AVG(avg_delay_minutes) as value
            FROM transit_metrics
            WHERE route_id = 'RT-14'
            GROUP BY date
            ORDER BY date
        """
        metric_name = "Route 14 Average Delay (minutes)"
        source = "Table: transit_metrics"

    elif "waste" in q_lower or "bin" in q_lower:
        sql = """
            SELECT date, AVG(fill_percentage) as value
            FROM waste_sensors
            WHERE neighborhood = 'Riverside'
            GROUP BY date
            ORDER BY date
        """
        metric_name = "Riverside Avg Bin Fill (%)"
        source = "Table: waste_sensors"

    else:
        # Default to respiratory complaints in Riverside
        sql = """
            SELECT date, SUM(complaint_count) as value
            FROM respiratory_complaints
            WHERE neighborhood = 'Riverside'
            GROUP BY date
            ORDER BY date
        """
        metric_name = "Respiratory Complaints in Riverside"
        source = "Table: respiratory_complaints"

    # Execute query
    try:
        rows = db.execute_query(sql)
    except ValueError:
        return {
            "agent": "forecasting_agent",
            "error": "Failed to retrieve historical data for forecasting.",
            "forecast": [],
            "historical": [],
            "summary": "Unable to generate forecast due to data retrieval error.",
            "confidence_level": 0,
            "source": source,
        }

    if not rows:
        return {
            "agent": "forecasting_agent",
            "forecast": [],
            "historical": [],
            "summary": "Insufficient historical data to generate a forecast.",
            "confidence_level": 0,
            "source": source,
        }

    dates = [r["date"] for r in rows]
    values = [float(r["value"]) for r in rows]

    # Generate forecast
    horizon = 30
    forecast_data = _forecast_with_statsmodels(dates, values, horizon)

    # Historical data (last 60 days for chart)
    historical = [
        {"date": d, "value": round(v, 1)}
        for d, v in zip(dates[-60:], values[-60:])
    ]

    # Generate summary
    client = _get_genai_client()
    if forecast_data:
        last_actual = values[-1]
        last_predicted = forecast_data[-1]["predicted"]
        trend = "rising" if last_predicted > last_actual else "declining"
        pct_change = ((last_predicted - last_actual) / max(last_actual, 1)) * 100

        default_summary = (
            f"{metric_name}: The trend is {trend}. "
            f"Current value: {round(last_actual, 1)}, "
            f"30-day forecast: {last_predicted} "
            f"({'+' if pct_change > 0 else ''}{round(pct_change, 1)}%). "
            f"Confidence band: [{forecast_data[-1]['lower_bound']}, {forecast_data[-1]['upper_bound']}]."
        )

        if client:
            try:
                model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
                resp = client.models.generate_content(
                    model=model,
                    contents=f"""Given this forecasting result, write a 2-sentence civic intelligence summary:
Metric: {metric_name}
Current value: {last_actual}
30-day forecast: {last_predicted} (range: {forecast_data[-1]['lower_bound']} to {forecast_data[-1]['upper_bound']})
Trend: {trend}, {round(abs(pct_change), 1)}% change

Be specific and actionable. Mention the confidence range.""",
                )
                default_summary = resp.text.strip()
            except Exception:
                pass

        confidence = 0.85 if STATSMODELS_AVAILABLE else 0.70
    else:
        default_summary = "Unable to generate a reliable forecast from the available data."
        confidence = 0.0

    return {
        "agent": "forecasting_agent",
        "metric": metric_name,
        "forecast": forecast_data,
        "historical": historical,
        "summary": default_summary,
        "confidence_level": confidence,
        "source": source,
        "method": "Exponential Smoothing (Holt-Winters)" if STATSMODELS_AVAILABLE else "Linear Trend Projection",
        "google_cloud_equivalent": "BigQuery ML ARIMA_PLUS / ML.FORECAST",
    }
