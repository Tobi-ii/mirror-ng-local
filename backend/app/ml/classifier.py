import pickle, os, logging, re
from typing import Optional

logger = logging.getLogger(__name__)
MODEL_PATH = os.environ.get('MODEL_PATH', os.path.join(os.path.dirname(__file__), 'category_model.pkl'))

# Business keywords that indicate commercial transactions
BUSINESS_KEYWORDS = [
    'LIMITED', 'LTD', 'ENTERPRISES', 'VENTURES', 'GLOBAL', 'MULTIVENTURES',
    'COMPANY', 'CORPORATION', 'STORE', 'SHOP', 'MART', 'PLAZA',
    'SOLUTIONS', 'TECH', 'SERVICES', 'INVESTMENT', 'TRADING'
]

# Utility/service keywords
UTILITY_KEYWORDS = [
    'AIRTIME', 'DATA', 'ELECTRICITY', 'WATER', 'CABLE', 'DSTV', 'GOTV',
    'NETFLIX', 'SPOTIFY', 'SHOWMAX', 'MTN', 'GLO', 'AIRTEL', '9MOBILE',
    'UTILITY', 'BILL PAYMENT', 'EBILL'
]

# Seed training data — expanded with more patterns
TRAINING_DATA = [
    # Utilities
    ("data purchase", "Utilities"), ("airtime", "Utilities"), ("mtn", "Utilities"),
    ("glo", "Utilities"), ("airtel", "Utilities"), ("9mobile", "Utilities"),
    ("electricity", "Utilities"), ("dstv", "Utilities"), ("gotv", "Utilities"),
    ("netflix", "Entertainment"), ("spotify", "Entertainment"), ("showmax", "Entertainment"),
    ("bill payment", "Utilities"), ("ebill", "Utilities"),

    # Transfers
    ("transfer from", "Transfer"), ("transfer to", "Transfer"), ("onebank transfer", "Transfer"),
    ("nip transfer", "Transfer"), ("alat nip transfer", "Transfer"),
    ("nip", "Transfer"), ("banknip", "Transfer"), ("afb nip", "Transfer"),
    ("comm alat nip transfer", "Transfer"), ("vat alat nip transfer", "Transfer"),

    # Income
    ("salary", "Income"), ("payroll", "Income"), ("wage", "Income"),

    # Transport
    ("uber", "Transport"), ("bolt", "Transport"), ("taxify", "Transport"), ("fuel", "Transport"),

    # Shopping
    ("pos", "Shopping"), ("jumia", "Shopping"), ("konga", "Shopping"), ("market", "Shopping"),
    ("buycard", "Shopping"), ("card purchase", "Shopping"),

    # Food
    ("restaurant", "Food"), ("food", "Food"), ("eatery", "Food"), ("cafe", "Food"),
]

def _is_person_name(narration: str) -> bool:
    """Detect if narration looks like a person's name (2-4 capitalized words)."""
    if not narration:
        return False

    # Remove common prefixes
    cleaned = re.sub(r'^(transfer to|from|nip|onebank)\s+', '', narration, flags=re.IGNORECASE).strip()

    # Split into words
    words = cleaned.split()

    # Person names typically have 2-4 words, all capitalized
    if 2 <= len(words) <= 5:
        # Check if most words are capitalized (allowing for small words like "of", "the")
        capitalized_count = sum(1 for w in words if w[0].isupper() and len(w) > 1)
        # If 70%+ of words are capitalized and no business keywords, likely a person
        if capitalized_count / len(words) >= 0.7:
            # Check it's not a business
            upper_narration = narration.upper()
            if not any(keyword in upper_narration for keyword in BUSINESS_KEYWORDS):
                return True

    return False

def _is_business(narration: str) -> bool:
    """Detect if narration contains business keywords (word-boundary match)."""
    if not narration:
        return False
    upper = narration.upper()
    return any(re.search(r'\b' + re.escape(kw) + r'\b', upper) for kw in BUSINESS_KEYWORDS)

def _is_utility(narration: str) -> bool:
    """Detect if narration contains utility/service keywords (word-boundary match)."""
    if not narration:
        return False
    upper = narration.upper()
    return any(re.search(r'\b' + re.escape(kw) + r'\b', upper) for kw in UTILITY_KEYWORDS)

def predict_category(narration: str) -> str:
    """
    Predict category using pattern-based detection first, then ML classifier as fallback.
    """
    try:
        if not narration:
            return "General"

        # Step 1: Pattern-based detection (fast, accurate for common patterns)
        if _is_utility(narration):
            return "Utilities"

        if _is_business(narration):
            return "Shopping"

        if _is_person_name(narration):
            return "Transfer"

        # Step 2: ML classifier for everything else
        clf = load_classifier()
        prediction = clf.predict([narration.lower()])[0]
        return prediction

    except Exception as e:
        logger.error(f"Classifier error: {e}")
        return "General"

def train_classifier():
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline

    texts = [t[0] for t in TRAINING_DATA]
    labels = [t[1] for t in TRAINING_DATA]

    pipeline = Pipeline([
        ('tfidf', TfidfVectorizer(analyzer='word', ngram_range=(1, 2), max_features=2000)),
        ('clf', LogisticRegression(max_iter=500, class_weight='balanced'))
    ])
    pipeline.fit(texts, labels)

    with open(MODEL_PATH, 'wb') as f:
        pickle.dump(pipeline, f)

    logger.info(f"NLP Classifier trained on {len(texts)} samples")
    return pipeline

def load_classifier():
    if os.path.exists(MODEL_PATH):
        with open(MODEL_PATH, 'rb') as f:
            return pickle.load(f)
    return train_classifier()

def retrain_with_feedback(narration: str, correct_category: str):
    """Call this when user corrects a category — incremental learning hook."""
    TRAINING_DATA.append((narration.lower(), correct_category))
    train_classifier()
    logger.info(f"Retrained with: '{narration}' -> {correct_category}")
