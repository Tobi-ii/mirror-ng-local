"""
Shared alias resolution logic for both v1 and v2 agents.
Handles both new (tx:{id}) and legacy (substring) alias patterns.
"""
import logging

logger = logging.getLogger(__name__)


def _matches_composite_pattern(tx: dict, pattern: str, exact_match: bool) -> bool:
    """Check if a transaction matches an alias pattern."""
    if not pattern:
        return False
    
    tx_id = str(tx.get('id', '')).strip()
    tx_narration = (tx.get('original_narration') or tx.get('narration') or '').lower()
    
    # Format 1: "tx:{id}" (exact ID matching)
    if pattern.startswith('tx:'):
        if not exact_match:
            logger.debug(f"Pattern '{pattern}' requires exact_match but exact_match={exact_match}")
            return False
        pattern_id = pattern[3:].strip()
        matches = tx_id == pattern_id
        if matches:
            logger.info(f"✅ TX {tx_id} matched pattern '{pattern}' (tx:id format)")
        return matches
    
    # Format 2: "YYYY-MM-DD|narration" (legacy date+narration)
    if '|' in pattern:
        parts = pattern.split('|', 1)
        if len(parts) == 2:
            pattern_date, pattern_narration = parts[0].strip(), parts[1].strip()
            tx_timestamp = tx.get('timestamp', '') or ''
            tx_date = tx_timestamp.split('T')[0] if 'T' in tx_timestamp else tx_timestamp[:10]
            tx_narration_full = (tx.get('narration') or '').strip()
            matches = tx_date == pattern_date and tx_narration_full == pattern_narration
            if matches:
                logger.info(f"✅ TX {tx_id} matched pattern '{pattern}' (date|narration format)")
            return matches
    
    # Format 3: Simple substring match (fallback)
    matches = pattern.lower().strip() in tx_narration
    if matches:
        logger.info(f"✅ TX {tx_id} matched pattern '{pattern}' (substring)")
    return matches


def resolve_alias_for_transaction(tx: dict, aliases: list) -> dict:
    """
    Resolve the effective alias for a transaction.
    Returns: {'display_name': str, 'category': str, 'is_aliased': bool}
    """
    tx_id = tx.get('id', 'unknown')
    
    # Fast path: if transaction already has alias fields (from backend API)
    if tx.get('aliased') and tx.get('alias_name'):
        logger.debug(f"TX {tx_id}: Fast path - using pre-resolved alias '{tx['alias_name']}'")
        return {
            'display_name': tx['alias_name'],
            'category': tx.get('alias_category') or tx.get('category') or 'General',
            'is_aliased': True
        }
    
    # Slow path: match against aliases list
    for alias in aliases:
        pattern = alias.get('recipient_pattern') or ''
        exact_match = bool(alias.get('exact_match', 0))
        
        if _matches_composite_pattern(tx, pattern, exact_match):
            result = {
                'display_name': alias.get('display_name') or tx.get('narration', 'Unknown'),
                'category': alias.get('category') or tx.get('category') or 'General',
                'is_aliased': True
            }
            logger.info(f"TX {tx_id}: Resolved to alias '{result['display_name']}' (category: {result['category']})")
            return result
    
    # No alias found
    logger.debug(f"TX {tx_id}: No alias found, using narration '{tx.get('narration', 'Unknown')}'")
    return {
        'display_name': tx.get('narration') or 'Unknown',
        'category': tx.get('category') or 'General',
        'is_aliased': False
    }


def load_aliases(db_conn, user_id: str) -> list:
    """Load all aliases for a user."""
    try:
        cursor = db_conn.execute(
            'SELECT recipient_pattern, display_name, category, exact_match FROM user_aliases WHERE user_id = ?',
            (user_id,)
        )
        aliases = [dict(r) for r in cursor.fetchall()]
        logger.info(f"Loaded {len(aliases)} aliases for user {user_id}")
        for alias in aliases:
            logger.debug(f"  Alias: pattern='{alias['recipient_pattern']}', display='{alias['display_name']}', category='{alias['category']}', exact={alias['exact_match']}")
        return aliases
    except Exception as e:
        logger.error(f"Failed to load aliases: {e}")
        return []
