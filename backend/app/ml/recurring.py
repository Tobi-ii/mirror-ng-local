import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)


def detect_recurring(
    transactions: List[Dict],
    amount_tolerance: float = 0.15,
    interval_tolerance_days: int = 4,
) -> List[Dict]:
    debits = [tx for tx in transactions if tx.get('tx_type') == 'debit']
    if len(debits) < 2:
        return []

    fuzzy_groups = _fuzzy_group_narrations(debits)

    recurring = []
    for group in fuzzy_groups:
        clusters = _cluster_by_amount(group, amount_tolerance)
        for amount_cluster in clusters:
            if len(amount_cluster) < 2:
                continue
            result = _analyze_timing(amount_cluster, interval_tolerance_days)
            if result:
                recurring.append(result)

    recurring.sort(key=lambda x: x['amount'], reverse=True)
    return recurring


def _fuzzy_group_narrations(debits: List[Dict]) -> List[List[Dict]]:
    texts = [d.get('narration', '').strip().lower()[:60] or 'unknown' for d in debits]

    if len(texts) < 2:
        return [debits]

    vec = TfidfVectorizer(analyzer='char', ngram_range=(2, 4), max_features=300)
    X = vec.fit_transform(texts)
    sim = cosine_similarity(X)
    dist = np.clip(1.0 - sim, 0, 1)

    from sklearn.cluster import DBSCAN
    clustering = DBSCAN(eps=0.35, min_samples=1, metric='precomputed')
    labels = clustering.fit_predict(dist)

    groups: Dict[int, List[Dict]] = defaultdict(list)
    for label, tx in zip(labels, debits):
        groups[label].append(tx)

    return list(groups.values())


def _cluster_by_amount(txs: List[Dict], tolerance: float) -> List[List[Dict]]:
    """Group transactions by similar amounts within percentage tolerance."""
    sorted_txs = sorted(txs, key=lambda t: float(t.get('amount', 0)))
    clusters: List[List[Dict]] = []

    for tx in sorted_txs:
        amt = float(tx.get('amount', 0))
        placed = False
        for cluster in clusters:
            ref = float(cluster[0].get('amount', 0))
            max_amt = max(ref, amt)
            min_amt = min(ref, amt)
            if min_amt / max(max_amt, 0.01) >= (1.0 - tolerance):
                cluster.append(tx)
                placed = True
                break
        if not placed:
            clusters.append([tx])

    return clusters


def _analyze_timing(txs: List[Dict], tolerance_days: int) -> Optional[Dict]:
    sorted_txs = sorted(txs, key=lambda t: t['timestamp'])
    timestamps = []
    for tx in sorted_txs:
        try:
            timestamps.append(datetime.fromisoformat(str(tx['timestamp'])))
        except (ValueError, TypeError):
            return None

    if len(timestamps) < 2:
        return None

    intervals = []
    for i in range(1, len(timestamps)):
        intervals.append(abs((timestamps[i] - timestamps[i - 1]).days))

    if len(intervals) < 1:
        return None

    avg_interval = float(np.mean(intervals))
    pattern = _classify_pattern(avg_interval)
    if not pattern or avg_interval < 7:
        return None

    dominant_interval = _periodogram_interval(intervals)

    interval_is_regular = all(
        abs(iv - dominant_interval) <= tolerance_days for iv in intervals
    ) if dominant_interval else all(
        abs(iv - avg_interval) <= tolerance_days for iv in intervals
    )

    if not interval_is_regular:
        return None

    amounts = [float(t.get('amount', 0)) for t in sorted_txs]
    amount = float(np.median(amounts))
    total_spent = sum(amounts)
    next_date = _next_expected(timestamps[-1], dominant_interval or avg_interval)

    return {
        'key': sorted_txs[0].get('narration', '').strip().lower()[:50],
        'merchant': sorted_txs[0].get('narration', '').strip()[:50],
        'pattern': pattern,
        'avg_interval_days': round(dominant_interval or avg_interval, 1),
        'amount': round(amount, 2),
        'amount_range': [round(min(amounts), 2), round(max(amounts), 2)],
        'count': len(sorted_txs),
        'total_spent': round(total_spent, 2),
        'last_date': sorted_txs[-1]['timestamp'],
        'next_expected': next_date,
        'confidence': _confidence(len(sorted_txs), pattern),
    }


def _periodogram_interval(intervals: List[int]) -> Optional[float]:
    if len(intervals) < 4:
        return float(np.mean(intervals))

    n = len(intervals)
    fft = np.fft.rfft(intervals - np.mean(intervals))
    freqs = np.fft.rfftfreq(n)
    psd = np.abs(fft) ** 2

    valid = freqs > 0
    if not np.any(valid):
        return float(np.mean(intervals))

    peak_idx = np.argmax(psd[valid])
    peak_period = 1.0 / freqs[valid][peak_idx] if freqs[valid][peak_idx] > 0 else n
    return float(min(peak_period, max(intervals) * 2))


def _classify_pattern(avg_days: float) -> Optional[str]:
    if 27 <= avg_days <= 33:
        return 'monthly'
    elif 6 <= avg_days <= 8:
        return 'weekly'
    elif 13 <= avg_days <= 15:
        return 'biweekly'
    elif 85 <= avg_days <= 95:
        return 'quarterly'
    elif 360 <= avg_days <= 370:
        return 'yearly'
    return None


def _next_expected(last_date: datetime, interval_days: float) -> Optional[str]:
    try:
        return (last_date + timedelta(days=interval_days)).isoformat()
    except (ValueError, TypeError):
        return None


def _confidence(count: int, pattern: str) -> str:
    if count >= 6:
        return 'high'
    elif count >= 3:
        return 'medium'
    return 'low'
