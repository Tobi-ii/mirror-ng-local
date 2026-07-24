import re
import logging
from typing import List, Dict, Optional, Tuple
from collections import Counter, defaultdict

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import DBSCAN
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)

MERCHANT_PATTERNS = [
    (r'POS(?:\s+-\s+)?(?:\w+\s*)?(.+)', 1),
    (r'(?:PAYMENT TO|PAYMENT FOR|PURCHASE AT|PAID TO|PAY\s+)(.+)', 1),
    (r'(?:TRANSFER TO|TRF TO|TO:)\s*(.+)', 1),
    (r'(?:ATM\s+(?:WITHDRAWAL|WITHDRAW))(?:\s*[-–]\s*)?(.+)?', 1),
    (r'BILL PAYMENT\s*[:\-]?\s*(.+)', 1),
    (r'(UBER|BOLT|NETFLIX|SPOTIFY|SHOWMAX|DSTV|GOTV)(?:\s|$)', 0),
    (r'(MTN|GLO|AIRTEL|9MOBILE)\s*(?:DATA|AIRTIME)?', 0),
]

STOP_WORDS = {'the', 'a', 'an', 'and', 'or', 'for', 'to', 'of', 'in', 'at', 'by', 'with', 'from'}


def clean_merchant_name(name: str) -> str:
    name = re.sub(r'[^a-zA-Z0-9\s]', ' ', name).strip()
    name = re.sub(r'\s+', ' ', name)
    parts = [w.capitalize() for w in name.split() if w.lower() not in STOP_WORDS]
    return ' '.join(parts) if parts else name.capitalize()


def extract_merchant(narration: str) -> Optional[str]:
    if not narration:
        return None
    text = narration.strip()
    for pattern, group_idx in MERCHANT_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            raw = m.group(group_idx)
            if raw and raw.strip():
                return clean_merchant_name(raw.strip())
    if ' ' in text and len(text.split()) <= 5:
        return clean_merchant_name(text)
    return None


def _make_cluster_name(names: List[str]) -> str:
    name_groups: Dict[str, List[str]] = defaultdict(list)
    for n in names:
        prefix = n.split()[0] if n.split() else n
        name_groups[prefix].append(n)
    longest_group = max(name_groups.values(), key=len)
    return max(longest_group, key=len)


def fuzzy_cluster_merchants(
    transactions: List[Dict],
    eps: float = 0.4,
    min_samples: int = 1,
) -> Dict[str, List[Dict]]:
    raw_names: List[Tuple[str, Dict]] = []
    for tx in transactions:
        merchant = extract_merchant(tx.get('narration', ''))
        if merchant:
            raw_names.append((merchant, tx))

    if len(raw_names) < 2:
        clusters: Dict[str, List[Dict]] = {}
        for name, tx in raw_names:
            clusters.setdefault(name, []).append(tx)
        return clusters

    names = [r[0] for r in raw_names]
    vec = TfidfVectorizer(
        analyzer='char',
        ngram_range=(2, 4),
        max_features=500,
        lowercase=True,
    )
    X = vec.fit_transform(names)
    sim = cosine_similarity(X)
    dist = np.clip(1.0 - sim, 0, 1)

    clustering = DBSCAN(eps=eps, min_samples=min_samples, metric='precomputed')
    labels = clustering.fit_predict(dist)

    cluster_map: Dict[int, List[Tuple[str, Dict]]] = defaultdict(list)
    for label, name, tx in zip(labels, names, [r[1] for r in raw_names]):
        cluster_map[label].append((name, tx))

    result: Dict[str, List[Dict]] = {}
    for label, items in cluster_map.items():
        cluster_names = [it[0] for it in items]
        cluster_name = _make_cluster_name(cluster_names)
        result[cluster_name] = [it[1] for it in items]

    return result


def get_top_merchants(
    transactions: List[Dict],
    min_count: int = 2,
    limit: int = 20,
) -> List[Dict]:
    clusters = fuzzy_cluster_merchants(transactions)
    results = []
    for merchant, txs in clusters.items():
        if len(txs) < min_count:
            continue
        total = sum(float(t.get('amount', 0)) for t in txs if t.get('tx_type') == 'debit')
        results.append({
            'merchant': merchant,
            'count': len(txs),
            'total_spent': round(total, 2),
            'avg_amount': round(total / len(txs), 2) if txs else 0,
            'category': Counter(t.get('category', 'General') for t in txs).most_common(1)[0][0],
        })
    results.sort(key=lambda x: x['total_spent'], reverse=True)
    return results[:limit]
