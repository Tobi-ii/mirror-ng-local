import numpy as np
from typing import List, Dict, Optional
from collections import defaultdict
import logging

from sklearn.ensemble import IsolationForest

logger = logging.getLogger(__name__)


def detect_anomalies(transactions: List[Dict]) -> List[Dict]:
    """
    Scans a transaction array and overlays anomaly detection weights.
    Returns deep copies of transaction items safely appended with anomaly tracking flags.
    """
    if len(transactions) < 3:
        return [{**tx, 'is_anomaly': False, 'anomaly_reason': None} for tx in transactions]

    # Generate distinct, immutable tracking IDs based on index to prevent memory address overlapping
    indexed_transactions = [{"_tracker_id": f"tx_{idx}", **tx} for idx, tx in enumerate(transactions)]

    forest_scores = _isolation_forest_anomalies(indexed_transactions)
    z_scores = _zscore_anomalies(indexed_transactions)
    merchant_scores = _merchant_anomalies(indexed_transactions)

    result = []
    for tx in indexed_transactions:
        t_id = tx["_tracker_id"]
        reasons = []
        
        if forest_scores.get(t_id, {}).get('is_anomaly'):
            reasons.append(forest_scores[t_id]['reason'])
        if z_scores.get(t_id, {}).get('is_anomaly'):
            reasons.append(z_scores[t_id]['reason'])
        if merchant_scores.get(t_id, {}).get('is_anomaly'):
            reasons.append(merchant_scores[t_id]['reason'])

        # Clean internally used tracker key while copying output
        tx_copy = {k: v for k, v in tx.items() if k != "_tracker_id"}
        tx_copy['is_anomaly'] = len(reasons) > 0
        tx_copy['anomaly_reason'] = reasons[0] if reasons else None
        result.append(tx_copy)

    return result


def _isolation_forest_anomalies(transactions: List[Dict]) -> Dict:
    debits = [tx for tx in transactions if tx.get('tx_type') == 'debit']
    if len(debits) < 5:
        return {tx["_tracker_id"]: {'is_anomaly': False, 'reason': None} for tx in transactions}

    cat_map: Dict[str, List[int]] = defaultdict(list)
    for i, tx in enumerate(debits):
        cat_map[tx.get('category', 'General')].append(i)

    forest = IsolationForest(contamination=0.05, random_state=42, n_estimators=100)
    all_scores = {}

    for cat, indices in cat_map.items():
        if len(indices) < 5:
            for i in indices:
                all_scores[debits[i]["_tracker_id"]] = {'is_anomaly': False, 'reason': None}
            continue

        amounts = np.array([[float(debits[i]['amount'])] for i in indices])
        scores = forest.fit_predict(amounts)
        mean_amt = float(np.mean(amounts))

        for i, score in zip(indices, scores):
            t_id = debits[i]["_tracker_id"]
            if score == -1:
                amt = float(debits[i]['amount'])
                all_scores[t_id] = {
                    'is_anomaly': True,
                    'reason': f"Unusual {cat} spend — ₦{amt:,.2f} (typical ₦{mean_amt:,.2f})",
                }
            else:
                all_scores[t_id] = {'is_anomaly': False, 'reason': None}

    result = {}
    for tx in transactions:
        t_id = tx["_tracker_id"]
        result[t_id] = all_scores.get(t_id, {'is_anomaly': False, 'reason': None})
    return result


def _zscore_anomalies(transactions: List[Dict]) -> Dict:
    by_category: Dict[str, List[float]] = defaultdict(list)
    for tx in transactions:
        if tx.get('tx_type') != 'debit':
            continue
        by_category[tx.get('category', 'General')].append(float(tx['amount']))

    stats = {}
    for cat, amts in by_category.items():
        if len(amts) >= 5:
            q1, q3 = float(np.percentile(amts, 25)), float(np.percentile(amts, 75))
            iqr = q3 - q1
            mean_v = float(np.mean(amts))
            std_v = float(np.std(amts))
            
            # Use standard scaling threshold, fallback to static deviation floor if variance is zero
            threshold = max(2.5, float(np.percentile(np.abs(np.array(amts) - mean_v) / max(std_v, 1e-4), 90)))
            stats[cat] = {
                'mean': mean_v, 
                'std': std_v if std_v > 0 else 1.0, 
                'threshold': threshold, 
                'iqr_upper': q3 + 2.0 * iqr,
                'has_variance': std_v > 0
            }

    result = {}
    for tx in transactions:
        t_id = tx["_tracker_id"]
        cat = tx.get('category', 'General')
        amount = float(tx['amount'])
        
        if tx.get('tx_type') == 'debit' and cat in stats:
            s = stats[cat]
            
            # If standard deviation was perfectly flat, check flat absolute scale jumps
            if not s['has_variance']:
                if amount > s['mean'] * 1.5:
                    result[t_id] = {
                        'is_anomaly': True,
                        'reason': f"Spike in fixed {cat} payment — ₦{amount:,.2f} vs expected ₦{s['mean']:,.2f}",
                    }
                    continue
            else:
                z = abs(amount - s['mean']) / s['std']
                if z > s['threshold']:
                    result[t_id] = {
                        'is_anomaly': True,
                        'reason': f"Unusually high {cat} spend — ₦{amount:,.2f} vs avg ₦{s['mean']:,.2f}",
                    }
                    continue
                if amount > s['iqr_upper']:
                    result[t_id] = {
                        'is_anomaly': True,
                        'reason': f"Unusual {cat} spend — ₦{amount:,.2f} (above IQR threshold)",
                    }
                    continue

        result[t_id] = {'is_anomaly': False, 'reason': None}
    return result


def _merchant_anomalies(transactions: List[Dict]) -> Dict:
    by_merchant: Dict[str, List[float]] = defaultdict(list)
    for tx in transactions:
        if tx.get('tx_type') != 'debit':
            continue
        # Truncation processing matches narration cleaning hooks
        merchant = tx.get('narration', '').strip().lower()[:30]
        if merchant:
            by_merchant[merchant].append(float(tx['amount']))

    stats = {}
    for merchant, amts in by_merchant.items():
        if len(amts) >= 3:
            std_v = float(np.std(amts))
            stats[merchant] = {
                'mean': float(np.mean(amts)), 
                'std': std_v if std_v > 0 else 1.0,
                'has_variance': std_v > 0
            }

    result = {}
    for tx in transactions:
        t_id = tx["_tracker_id"]
        merchant = tx.get('narration', '').strip().lower()[:30]
        amount = float(tx['amount'])
        
        if tx.get('tx_type') == 'debit' and merchant in stats:
            m = stats[merchant]
            if not m['has_variance']:
                if amount > m['mean'] * 1.3:  # Flag abnormal deviation on historically static fixed merchants
                    result[t_id] = {
                        'is_anomaly': True,
                        'reason': f"Abnormal amount change for {tx.get('narration', '')[:20]} — ₦{amount:,.2f} vs base ₦{m['mean']:,.2f}",
                    }
                    continue
            else:
                z = abs(amount - m['mean']) / m['std']
                if z > 2.8:
                    result[t_id] = {
                        'is_anomaly': True,
                        'reason': f"Unusual amount for this merchant — ₦{amount:,.2f} vs typical ₦{m['mean']:,.2f}",
                    }
                    continue

        result[t_id] = {'is_anomaly': False, 'reason': None}
    return result
