import numpy as np
from typing import List, Dict
from datetime import datetime, timedelta
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)

SEASONAL_PERIOD = 7


def weekly_spend_forecast(transactions: List[Dict]) -> Dict:
    daily = _aggregate_daily(transactions)
    if len(daily) < 2:
        return {'forecast': [], 'trend': 'insufficient_data', 'daily_avg': 0, 'weekly_projection': 0, 'seasonal_factors': []}

    dates = sorted(daily.keys())
    y = np.array([daily[d] for d in dates], dtype=float)

    dow_factors = _compute_dow_factors(daily)
    deseasonalized = _remove_seasonality(y, dates, dow_factors)

    X = np.array([(d - dates[0]).days for d in dates], dtype=float)
    base_forecast = _linear_regression_forecast(X, deseasonalized, dates)
    smooth_forecast = _exponential_smoothing_forecast(deseasonalized, dates)

    combined = []
    for i in range(7):
        forecast_date = dates[-1] + timedelta(days=i + 1)
        dow = forecast_date.weekday()
        seasonal_mult = dow_factors.get(dow, 1.0)
        blended = (base_forecast[i]['predicted_spend'] + smooth_forecast[i]['predicted_spend']) / 2
        season_adjusted = blended * seasonal_mult

        combined.append({
            'date': forecast_date.isoformat(),
            'predicted_spend': round(max(0, season_adjusted), 2),
            'base_trend': round(blended, 2),
            'seasonal_multiplier': round(seasonal_mult, 2),
        })

    slope = float(np.polyfit(X, deseasonalized, 1)[0]) if len(X) >= 2 else 0
    trend = 'increasing' if slope > 50 else 'decreasing' if slope < -50 else 'stable'

    return {
        'forecast': combined,
        'trend': trend,
        'daily_avg': round(float(np.mean(y)), 2),
        'weekly_projection': round(sum(f['predicted_spend'] for f in combined), 2),
        'seasonal_factors': [{'day': _dow_name(d), 'multiplier': round(dow_factors.get(d, 1.0), 2)} for d in range(7)],
    }


def _dow_name(d: int) -> str:
    return ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][d]


def _aggregate_daily(transactions: List[Dict]) -> Dict:
    daily = defaultdict(float)
    for tx in transactions:
        if tx.get('tx_type') != 'debit':
            continue
        try:
            date = datetime.fromisoformat(str(tx['timestamp'])).date()
            daily[date] += float(tx['amount'])
        except (ValueError, TypeError):
            continue
    return dict(daily)


def _compute_dow_factors(daily: Dict) -> Dict[int, float]:
    dow_totals: Dict[int, List[float]] = defaultdict(list)
    for date_str, amount in daily.items():
        if isinstance(date_str, str):
            try:
                date = datetime.fromisoformat(date_str).date()
            except ValueError:
                continue
        else:
            date = date_str
        dow_totals[date.weekday()].append(amount)

    dow_avgs = {d: float(np.mean(amts)) for d, amts in dow_totals.items()}
    overall_avg = float(np.mean(list(dow_avgs.values()))) if dow_avgs else 1.0
    if overall_avg <= 0:
        return {d: 1.0 for d in range(7)}

    factors = {d: avg / overall_avg for d, avg in dow_avgs.items()}
    for d in range(7):
        factors.setdefault(d, 1.0)
    return factors


def _remove_seasonality(y: np.ndarray, dates: List, factors: Dict[int, float]) -> np.ndarray:
    result = np.copy(y)
    for i, d in enumerate(dates):
        if isinstance(d, str):
            try:
                dow = datetime.fromisoformat(d).date().weekday()
            except ValueError:
                continue
        else:
            dow = d.weekday()
        mult = factors.get(dow, 1.0)
        if mult > 0:
            result[i] = y[i] / mult
    return result


def _add_seasonality(value: float, dow: int, factors: Dict[int, float]) -> float:
    return value * factors.get(dow, 1.0)


def _linear_regression_forecast(X: np.ndarray, y: np.ndarray, dates: List) -> List[Dict]:
    if len(X) < 2:
        return [{'date': (dates[-1] + timedelta(days=i + 1)).isoformat(), 'predicted_spend': float(np.mean(y))} for i in range(7)]
    x_mean, y_mean = X.mean(), y.mean()
    slope = float(np.dot(X - x_mean, y - y_mean) / (np.dot(X - x_mean, X - x_mean) + 1e-8))
    intercept = float(y_mean - slope * x_mean)
    floor = float(y.mean()) * 0.1
    last_x = (dates[-1] - dates[0]).days
    forecast = []
    for i in range(1, 8):
        day_x = last_x + i
        predicted = max(floor, slope * day_x + intercept)
        forecast.append({
            'date': (dates[-1] + timedelta(days=i)).isoformat(),
            'predicted_spend': round(predicted, 2),
        })
    return forecast


def _exponential_smoothing_forecast(y: np.ndarray, dates: List, alpha: float = 0.3) -> List[Dict]:
    if len(y) < 1:
        return [{'date': (dates[-1] + timedelta(days=i + 1)).isoformat(), 'predicted_spend': 0} for i in range(7)]
    smoothed = np.zeros(len(y))
    smoothed[0] = y[0]
    for i in range(1, len(y)):
        smoothed[i] = alpha * y[i] + (1 - alpha) * smoothed[i - 1]

    recent_trend = float(np.mean([smoothed[-1] - smoothed[-i] for i in range(2, min(5, len(smoothed) + 1))])) if len(smoothed) >= 3 else 0

    forecast = []
    last_val = smoothed[-1]
    floor = float(y.mean()) * 0.1
    for i in range(1, 8):
        predicted = max(floor, last_val + recent_trend * i)
        forecast.append({
            'date': (dates[-1] + timedelta(days=i)).isoformat(),
            'predicted_spend': round(predicted, 2),
        })
    return forecast
