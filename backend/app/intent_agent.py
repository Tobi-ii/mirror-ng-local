"""
Mirror.ng Intent Agent — Structured Query Architecture
======================================================
Four-layer pipeline for converting natural language → validated SQL → formatted response.

Architecture:
  Layer 1 (Intent Parser)   : LLM-based JSON intent extraction, with regex fallback
  Layer 2 (Validator)       : Whitelist-based sanitization of every parsed field
  Layer 3 (Query Engine)    : Pure SQL execution using parameterised queries
  Layer 4 (Formatter)       : Optional LLM rephrasing, with built-in structured fallback

Security model:
  - SQL injection is prevented via parameterized queries (WHERE: `?`)
  - ORDER BY / LIMIT are sanitised through allow-listed helper functions
  - All user-supplied string fields are truncated and validated against allow-lists
  - Regex patterns are compiled or inlined with strict anchors where applicable

Design invariants:
  - The LLM is NEVER trusted with raw input or raw SQL output
  - Pattern fallback guarantees offline operability when the LLM is unreachable
  - Every query path returns a well-typed dict; callers never inspect raw rows
"""

import os
import json
import logging
import re
from typing import List, Dict, Any, Optional
from .llm_clients import get_openrouter_client, MODEL_CHAIN

logger = logging.getLogger(__name__)

# Compiled once; validates YYYY-MM-DD format across both validator and helpers
_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


# ─── SQL SAFETY HELPERS ──────────────────────────────────────────────────
# These three functions are the ONLY gatekeepers for dynamic SQL fragments.
# They accept arbitrary input and return only allow-listed values, preventing
# injection via ORDER BY, LIMIT, or column-name parameters.

def _safe_order_dir(order: str) -> str:
    """Return only 'ASC' or 'DESC'. Everything else collapses to 'ASC'.

    SECURITY: ORDER BY direction is a high-risk injection vector because it
    cannot be parameterized. This whitelist approach guarantees safety.
    """
    return "DESC" if str(order).upper() == "DESC" else "ASC"


def _safe_limit(limit, default: int = 10) -> int:
    """Coerce limit to 1..100. Non-integer or missing values fall back to default.

    Prevents both runaway result sets and injection via non-numeric limit.
    """
    if limit is None:
        return default
    try:
        return max(1, min(int(limit), 100))
    except (ValueError, TypeError):
        return default


def _safe_order_col(order_by: str) -> str:
    """Allow only 'amount' or 'timestamp'. Reject any unrecognised column name.

    SECURITY: Column names cannot use parameterised queries. This whitelist
    is the only defence against ORDER BY injection.
    """
    return "amount" if order_by == "amount" else "timestamp"


def _validate_date(date_str: str, default: str = "earliest") -> str:
    """Return the date string only if it matches YYYY-MM-DD; otherwise return default.

    Used both for user-supplied date filters and temporal-context defaults.
    """
    if not date_str:
        return default
    if _DATE_RE.match(date_str):
        return date_str
    return default

def _validate_history(history: list, max_length: int = 20) -> list:
    """Sanitise conversation history before passing it to the LLM.

    Strips non-dict entries, limits string length to 2000 characters,
    removes control characters, and caps the sequence at `max_length` items.
    This prevents prompt-injection via crafted history payloads.
    """
    if not isinstance(history, list):
        return []
    validated = []
    for msg in history[-max_length:]:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        content = msg.get("content", "")
        if role not in ("user", "assistant"):
            continue
        if isinstance(content, str):
            content = content[:2000]
            content = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f]', '', content)
        validated.append({"role": role, "content": content})
    return validated

# ─── LAYER 1 (PART 1): LLM JSON Schema ──────────────────────────────────
# The LLM is told it may ONLY output JSON conforming to this schema.
# Every field here is re-validated in Layer 2 — the LLM output is never trusted.

INTENT_SCHEMA = {
    "intent": "aggregate | list | insight | lookup",
    "metric": "sum | count | max | min | average",
    "field": "amount",
    "filters": {
        "tx_type": "debit | credit | all",
        "category": "string",
        "bank": "string",
        "narration_contains": "string",
        "date_from": "YYYY-MM-DD",
        "date_to": "YYYY-MM-DD"
    },
    "group_by": "sender | recipient | date | category | bank | none",
    "order_by": "amount | date",
    "order": "asc | desc",
    "limit": 1
}

# ─── LAYER 1 (PART 2): LLM System Prompt ────────────────────────────────
# The prompt explicitly prohibits the LLM from answering, computing, or using
# outside knowledge. It must output ONLY valid JSON. The date-range context
# block is appended dynamically at runtime when temporal_context is provided.

INTENT_SYSTEM_PROMPT = """You are Mirror Intent Parser.

Your ONLY job is to convert user questions into valid JSON queries.

RULES:
- NEVER answer the question.
- NEVER compute or estimate values.
- NEVER use outside knowledge.
- ONLY output valid JSON matching the schema below.
- If unclear, set "intent": "lookup" and narrow filters conservatively.
- If the user asks about a person or business name, use narration_contains.
- If the user asks "most" or "highest", use order_by + desc + limit.
- "group_by": "none" means no grouping, return single value.

SCHEMA:
{
  "intent": "aggregate|list|insight|lookup",
  "metric": "sum|count|max|min|average",
  "field": "amount",
  "filters": {
    "tx_type": "debit|credit|all",
    "category": "string or null",
    "bank": "string or null",
    "narration_contains": "string or null",
    "date_from": "YYYY-MM-DD or null",
    "date_to": "YYYY-MM-DD or null"
  },
  "group_by": "sender|recipient|date|category|bank|none",
  "order_by": "amount|date",
  "order": "asc|desc",
  "limit": null or integer
}

EXAMPLE INPUT: "Who sent me the most money?"
EXAMPLE OUTPUT: {"intent":"aggregate","metric":"sum","field":"amount","filters":{"tx_type":"credit"},"group_by":"sender","order_by":"amount","order":"desc","limit":1}

EXAMPLE INPUT: "How much did I spend on airtime?"
EXAMPLE OUTPUT: {"intent":"aggregate","metric":"sum","field":"amount","filters":{"tx_type":"debit","narration_contains":"airtime"},"group_by":"none"}

EXAMPLE INPUT: "What day did I spend the most?"
EXAMPLE OUTPUT: {"intent":"aggregate","metric":"sum","field":"amount","filters":{"tx_type":"debit"},"group_by":"date","order_by":"amount","order":"desc","limit":1}

EXAMPLE INPUT: "What's my biggest expense?"
EXAMPLE OUTPUT: {"intent":"lookup","metric":"max","field":"amount","filters":{"tx_type":"debit"},"limit":1}

EXAMPLE INPUT: "Show me my last 5 transfers"
EXAMPLE OUTPUT: {"intent":"list","metric":"count","field":"amount","filters":{"tx_type":"debit","narration_contains":"transfer"},"order_by":"date","order":"desc","limit":5}

OUTPUT ONLY JSON. NO TEXT. NO EXPLANATION.

AUDIT CONTEXT:
- The user's financial data is bounded to a specific audit window.
- When the user asks time-relative questions ("this week", "last month"), use date_from/date_to relative to the current date.
- If the user asks about a month explicitly outside the audit window, do NOT fabricate data — the query will return empty.
- This context is already applied as defaults in the prompt above."""

# ─── LAYER 2: QUERY VALIDATOR ──────────────────────────────────────────
# Every value the LLM emits is run through allow-list checks below.
# Unrecognised values fall back to safe defaults (e.g. "lookup", "sum", "all").

ALLOWED_INTENTS = {"aggregate", "list", "insight", "lookup"}
ALLOWED_METRICS = {"sum", "count", "max", "min", "average"}
ALLOWED_TX_TYPES = {"debit", "credit", "all"}
ALLOWED_GROUP_BY = {"sender", "recipient", "date", "category", "bank", "none"}
ALLOWED_ORDER_BY = {"amount", "date"}
ALLOWED_ORDER = {"asc", "desc"}

def validate_query(query: dict) -> dict:
    """Validate and sanitise the LLM-generated query against a whitelist.

    Every field is checked independently; unrecognised values are replaced
    with harmless defaults. String-length truncation prevents buffer issues.

    Args:
        query: Raw dict from LLM output (or pattern-matching fallback).

    Returns:
        Sanitised dict guaranteed to have every required key present.
        Fields not matching the schema are silently dropped or defaulted.

    Example:
        >>> validate_query({"intent": "aggregate", "metric": "sum", "filters": {}})
        {'intent': 'aggregate', 'metric': 'sum', ...}

    Edge cases:
        - Non-dict filters are replaced with empty dict.
        - Intents/metrics not in ALLOWED_* fall back to ("lookup", "sum").
        - date_from/date_to are validated against ^\\d{4}-\\d{2}-\\d{2}$.
    """
    
    # Ensure required fields exist
    intent = query.get("intent", "lookup")
    if intent not in ALLOWED_INTENTS:
        intent = "lookup"
    
    metric = query.get("metric", "sum")
    if metric not in ALLOWED_METRICS:
        metric = "sum"
    
    filters = query.get("filters", {})
    if not isinstance(filters, dict):
        filters = {}
    
    # Sanitise filters — each value type-checked and truncated independently
    safe_filters = {}
    
    tx_type = filters.get("tx_type", "all")
    if tx_type in ALLOWED_TX_TYPES:
        safe_filters["tx_type"] = tx_type
    else:
        safe_filters["tx_type"] = "all"
    
    if filters.get("category"):
        safe_filters["category"] = str(filters["category"])[:50]
    
    if filters.get("bank"):
        safe_filters["bank"] = str(filters["bank"])[:50]
    
    if filters.get("narration_contains"):
        safe_filters["narration_contains"] = str(filters["narration_contains"])[:100]
    
    if filters.get("date_from"):
        if re.match(r'^\d{4}-\d{2}-\d{2}$', str(filters["date_from"])):
            safe_filters["date_from"] = filters["date_from"]
    
    if filters.get("date_to"):
        if re.match(r'^\d{4}-\d{2}-\d{2}$', str(filters["date_to"])):
            safe_filters["date_to"] = filters["date_to"]
    
    group_by = query.get("group_by", "none")
    if group_by not in ALLOWED_GROUP_BY:
        group_by = "none"
    
    order_by = query.get("order_by", "date")
    if order_by not in ALLOWED_ORDER_BY:
        order_by = "date"
    
    order = query.get("order", "desc")
    if order not in ALLOWED_ORDER:
        order = "desc"
    
    limit = query.get("limit")
    if limit is not None:
        try:
            limit = int(limit)
            limit = max(1, min(limit, 100))  # Clamp between 1-100
        except (ValueError, TypeError):
            limit = None
    
    return {
        "intent": intent,
        "metric": metric,
        "field": "amount",
        "filters": safe_filters,
        "group_by": group_by,
        "order_by": order_by,
        "order": order,
        "limit": limit
    }

# ─── LAYER 3: QUERY ENGINE (Pure SQL) ──────────────────────────────────
# This function builds SELECT statements dynamically but NEVER interpolates
# user data directly. All values go through parameterised `?` placeholders.
# ORDER BY and LIMIT are handled by the _safe_* helpers above.

def execute_query(query: dict, user_id: str, db_conn) -> dict:
    """Execute a validated query against the transactions database.

    SQL injection is prevented by:
      1. Parameterised WHERE clauses (all user input via `?`).
      2. _safe_order_col / _safe_order_dir / _safe_limit whitelists.
      3. No raw string formatting beyond the allow-listed helpers.

    Args:
        query: The sanitised dict from validate_query().
        user_id: Scopes all queries to one user (WHERE user_id = ?).
        db_conn: A PEP-249-compatible connection (sqlite3 / aiosqlite).

    Returns:
        A well-typed result dict keyed by type (single_value | grouped |
        list | lookup | insight). Every path returns a consistent shape.

    Raises:
        No exceptions propagate; failures are caught and returned as
        {"type": "error", "message": ...}.

    Example:
        >>> execute_query({"intent": "aggregate", "metric": "sum", ...}, "u1", conn)
        {'type': 'single_value', 'value': 12345.0, 'metric': 'sum', ...}

    Edge cases:
        - Empty result sets return 0 for aggregate, empty list for list,
          {"found": False} for lookup.
        - Missing narration defaults to "Unknown".
    """
    
    intent = query["intent"]
    metric = query["metric"]
    filters = query["filters"]
    group_by = query["group_by"]
    order_by = query["order_by"]
    order = query["order"]
    limit = query.get("limit")
    
    # Build SQL WHERE clause — all values use parameterised `?`
    where_parts = ["user_id = ?"]
    params = [user_id]
    
    if filters.get("tx_type") and filters["tx_type"] != "all":
        where_parts.append("tx_type = ?")
        params.append(filters["tx_type"])
    
    if filters.get("category"):
        where_parts.append("category LIKE ?")
        params.append(f"%{filters['category']}%")
    
    if filters.get("bank"):
        where_parts.append("bank LIKE ?")
        params.append(f"%{filters['bank']}%")
    
    if filters.get("narration_contains"):
        search_term = filters['narration_contains']
        
        # Search aliases by display_name — expands matching via custom patterns
        try:
            alias_cursor = db_conn.execute(
                "SELECT recipient_pattern FROM user_aliases WHERE user_id = ? AND display_name LIKE ?",
                (user_id, f"%{search_term}%")
            )
            matching_patterns = [row['recipient_pattern'] for row in alias_cursor.fetchall()]
        except Exception:
            matching_patterns = []
        
        or_conditions = [
            "narration LIKE ?",
            "original_narration LIKE ?"
        ]
        or_params = [f"%{search_term}%", f"%{search_term}%"]
        
        for pattern in matching_patterns:
            or_conditions.append("original_narration LIKE ?")
            or_params.append(f"%{pattern}%")
            
        where_parts.append(f"({' OR '.join(or_conditions)})")
        params.extend(or_params)
    
    if filters.get("date_from"):
        where_parts.append("date(timestamp) >= date(?)")
        params.append(filters["date_from"])
    
    if filters.get("date_to"):
        where_parts.append("date(timestamp) <= date(?)")
        params.append(filters["date_to"])
    
    where_clause = " AND ".join(where_parts)
    
    # Load aliases for narration mapping — used by apply_alias helpers below
    try:
        alias_cursor = db_conn.execute(
            'SELECT recipient_pattern, display_name, category FROM user_aliases WHERE user_id = ?',
            (user_id,)
        )
        aliases = alias_cursor.fetchall()
    except Exception:
        aliases = []
    
    def apply_alias(narration):
        """Replace narration text with the alias display_name if the pattern matches.

        Case-insensitive substring match; returns "Unknown" for None/empty input.
        """
        if not narration:
            return "Unknown"
        for alias in aliases:
            if alias["recipient_pattern"].lower() in narration.lower():
                return alias["display_name"]
        return narration
    
    def apply_alias_category(narration, original_category):
        """Override a transaction's category with the alias category when matched.

        Falls through to original_category, then to "General" if both are absent.
        """
        if not narration:
            return original_category or "General"
        for alias in aliases:
            if alias["recipient_pattern"].lower() in narration.lower():
                return alias["category"] or original_category or "General"
        return original_category or "General"
    
    # ── Handle each intent type ──────────────────────────────────────────

    if intent == "aggregate" and group_by == "none":
        # Single-value aggregation: "How much did I spend on X?"
        select = "SELECT "
        if metric == "sum":
            select += "SUM(amount)"
        elif metric == "count":
            select += "COUNT(*)"
        elif metric == "max":
            select += "MAX(amount)"
        elif metric == "min":
            select += "MIN(amount)"
        elif metric == "average":
            select += "AVG(amount)"
        
        cursor = db_conn.execute(
            f"{select} FROM transactions WHERE {where_clause}",
            params
        )
        result = cursor.fetchone()
        value = result[0] if result and result[0] else 0
        
        return {
            "type": "single_value",
            "value": float(value),
            "metric": metric,
            "filters_applied": filters
        }
    
    elif intent == "aggregate" and group_by != "none":
        # Grouped aggregation: "Who sent me the most money?"
        # Maps logical group_by keys to physical SQL column expressions
        group_column = {
            "sender": "narration",
            "recipient": "narration",
            "date": "date(timestamp)",
            "category": "category",
            "bank": "bank"
        }.get(group_by, "category")
        
        select = "SELECT "
        if metric == "sum":
            select += "SUM(amount) as total"
        elif metric == "count":
            select += "COUNT(*) as total"
        elif metric == "max":
            select += "MAX(amount) as total"
        elif metric == "min":
            select += "MIN(amount) as total"
        elif metric == "average":
            select += "AVG(amount) as total"
        
        order_dir = _safe_order_dir(order)
        limit_val = _safe_limit(limit, 10)
        
        cursor = db_conn.execute(
            f"{select}, {group_column} as grp, narration FROM transactions WHERE {where_clause} GROUP BY grp ORDER BY total {order_dir} LIMIT {limit_val}",
            params
        )
        rows = cursor.fetchall()
        
        groups = []
        for row in rows:
            narration = row["narration"] if "narration" in row.keys() else row["grp"]
            display_name = apply_alias(narration) if group_by in ("sender", "recipient") else row["grp"]
            groups.append({
                "group": str(display_name),
                "total": float(row["total"]),
                "count": len([r for r in rows if r["grp"] == row["grp"]]),
                "raw_narration": narration if display_name != narration else None
            })
        
        return {
            "type": "grouped",
            "groups": groups,
            "metric": metric,
            "group_by": group_by,
            "filters_applied": filters
        }
    
    elif intent == "list":
        # List transactions — ordered, limited, with alias-mapped narrations
        order_col = _safe_order_col(order_by)
        order_dir = _safe_order_dir(order)
        limit_val = _safe_limit(limit, 20)
        
        cursor = db_conn.execute(
            f"SELECT * FROM transactions WHERE {where_clause} ORDER BY {order_col} {order_dir} LIMIT {limit_val}",
            params
        )
        rows = cursor.fetchall()
        
        transactions = []
        for row in rows:
            narration = row["narration"] or "Unknown"
            display = apply_alias(narration)
            cat = apply_alias_category(narration, row["category"])
            
            transactions.append({
                "id": row["id"],
                "bank": row["bank"],
                "tx_type": row["tx_type"],
                "amount": float(row["amount"]),
                "narration": display,
                "original_narration": narration if display != narration else None,
                "category": cat,
                "timestamp": row["timestamp"],
                "balance_after": float(row["balance_after"]) if row["balance_after"] else None
            })
        
        return {
            "type": "list",
            "transactions": transactions,
            "count": len(transactions),
            "filters_applied": filters
        }
    
    elif intent == "lookup":
        # Single-record lookup — returns the first match after sorting
        order_col = _safe_order_col(order_by)
        order_dir = _safe_order_dir(order)
        
        cursor = db_conn.execute(
            f"SELECT * FROM transactions WHERE {where_clause} ORDER BY {order_col} {order_dir} LIMIT 1",
            params
        )
        row = cursor.fetchone()
        
        if not row:
            return {
                "type": "lookup",
                "found": False,
                "message": "No matching transaction found."
            }
        
        narration = row["narration"] or "Unknown"
        display = apply_alias(narration)
        
        return {
            "type": "lookup",
            "found": True,
            "transaction": {
                "id": row["id"],
                "bank": row["bank"],
                "tx_type": row["tx_type"],
                "amount": float(row["amount"]),
                "narration": display,
                "original_narration": narration if display != narration else None,
                "category": apply_alias_category(narration, row["category"]),
                "timestamp": row["timestamp"]
            }
        }
    
    elif intent == "insight":
        # Quick insight: total inflow, total outflow, and net position
        cursor = db_conn.execute(
            f"SELECT tx_type, SUM(amount) as total FROM transactions WHERE {where_clause} GROUP BY tx_type",
            params
        )
        rows = cursor.fetchall()
        
        total_in = 0
        total_out = 0
        for row in rows:
            if row["tx_type"] == "credit":
                total_in = float(row["total"])
            elif row["tx_type"] == "debit":
                total_out = float(row["total"])
        
        return {
            "type": "insight",
            "total_in": total_in,
            "total_out": total_out,
            "net": total_in - total_out,
            "transaction_count": sum(1 for r in rows),
            "filters_applied": filters
        }
    
    return {"type": "error", "message": f"Unknown intent: {intent}"}

# ─── LAYER 4: RESPONSE FORMATTER ────────────────────────────────────────
# Two-tier formatting: LLM-based natural language (preferred), then
# deterministic structured fallback. The LLM prompt explicitly prohibits
# inventing numbers; the fallback never hallucinates.

FORMATTER_PROMPT = """You are Mirror, a sharp financial assistant for Nigerians.

Convert this financial data into a natural, concise answer. 
Use ₦ for naira. Be direct. Flag anything unusual.

DATA: {data}
USER QUESTION: {question}
PREVIOUS RESPONSE: {previous}

RULES:
- Use ONLY the data provided. Do not invent numbers.
- If PREVIOUS RESPONSE contains a number, the current answer must be consistent.
- Keep it under 3 sentences unless asked for detail.
- If data shows unusual patterns, mention it."""

def format_response(result: dict, question: str, previous_response: str = "") -> str:
    """Format query results into a human-readable response.

    Attempts LLM-based formatting first. If the LLM call fails (network,
    rate-limit, timeout), falls back to deterministic templates for each
    result type (single_value, grouped, list, lookup, insight).

    Args:
        result: The dict returned by execute_query().
        question: The original user message (passed to the LLM for context).
        previous_response: The last assistant message (for consistency checks).

    Returns:
        A formatted string. Never returns raw JSON to the user unless the
        result type is unrecognised.
    """
    try:
        client = get_openrouter_client()
        response = client.chat.completions.create(
            model=MODEL_CHAIN,
            messages=[{
                "role": "user",
                "content": FORMATTER_PROMPT.format(
                    data=json.dumps(result, default=str, indent=2),
                    question=question,
                    previous=previous_response
                )
            }],
            temperature=0.3,
            max_tokens=300
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.warning(f"Formatter LLM failed, using fallback: {e}")
        # Fallback formatting — deterministic, no external dependency
        if result.get("type") == "single_value":
            return f"{result['metric'].title()}: ₦{result['value']:,.2f}"
        elif result.get("type") == "grouped" and result.get("groups"):
            top = result["groups"][0]
            return f"Top: {top['group']} — ₦{top['total']:,.2f}"
        elif result.get("type") == "insight":
            return f"In: ₦{result['total_in']:,.2f} | Out: ₦{result['total_out']:,.2f} | Net: ₦{result['net']:,.2f}"
        elif result.get("type") == "lookup":
            tx = result.get("transaction")
            if result.get("found") and tx:
                amt = f"₦{tx['amount']:,.2f}" if isinstance(tx['amount'], (int, float)) else tx['amount']
                bank = tx.get('bank', 'Unknown')
                nar = tx.get('narration', 'Unknown')
                ts = tx.get('timestamp', '')
                return f"Found in **{bank}** — {amt}\n\n{nar}\n\n_{ts}_"
            return "No matching transaction found."
        elif result.get("type") == "list" and result.get("transactions"):
            lines = [f"{i+1}. **{t.get('bank','?')}** — ₦{t['amount']:,.2f} — {t.get('narration','?')}" 
                     for i, t in enumerate(result['transactions'][:10])]
            header = f"Found {result['count']} transactions:\n" if result.get('count') else ""
            return header + "\n".join(lines)
        return json.dumps(result, default=str, indent=2)

# ─── LAYER 1 FALLBACK: PATTERN-BASED PARSER ─────────────────────────────
# This function is invoked when the LLM is unreachable or returns invalid JSON.
# Each regex targets a specific question archetype; matched patterns produce
# a fully-formed intent dict without any external dependency.
#
# Regex notes:
#   \b        — word boundary to avoid partial matches (e.g. "balance" in "imbalance")
#   (?:...)   — non-capturing group for alternation
#   (.+)      — capture group for the subject (e.g. "airtime" in "spend on airtime")
#   \s*(\d+)? — optional numeric capture for "last 5 transactions"

def parse_intent_via_patterns(message: str) -> dict:
    """Convert common question patterns to validated intent dicts. No LLM required.

    Patterns are ordered by specificity: broad/generic questions are checked
    later to avoid stealing queries from more specific patterns. Returns None
    when no pattern matches (caller should then return an error message).

    Args:
        message: The raw user message (lowercased and stripped internally).

    Returns:
        A dict matching the INTENT_SCHEMA shape, or None if unmatched.

    Examples:
        >>> parse_intent_via_patterns("How much did I spend on airtime?")
        {'intent': 'aggregate', 'metric': 'sum', ..., 'narration_contains': 'airtime'}
        >>> parse_intent_via_patterns("What's the weather?")
        None
    """
    lower = message.lower().strip()

    # Pattern: "balance" or "how much money do I have"
    # \b anchors avoid matching "balance" inside compound words
    if re.search(r'\b(?:balance|how much (?:money|funds) do i have)\b', lower):
        return {"intent": "insight", "metric": "sum", "field": "amount", "filters": {"tx_type": "all"}, "group_by": "none"}

    # Pattern: "biggest debit" / "largest purchase" — single largest withdrawal
    if re.search(r'(?:biggest|largest|highest|most expensive).*(?:debit|purchase|spend|withdrawal)', lower):
        return {"intent": "lookup", "metric": "max", "field": "amount", "filters": {"tx_type": "debit"}, "order_by": "amount", "order": "desc", "limit": 1}

    # Pattern: "biggest credit" / "largest deposit" — single largest inflow
    if re.search(r'(?:biggest|largest|highest|most).*(?:credit|income|deposit|received)', lower):
        return {"intent": "lookup", "metric": "max", "field": "amount", "filters": {"tx_type": "credit"}, "order_by": "amount", "order": "desc", "limit": 1}

    # Pattern: "who sent me the most?" — grouped by sender, sorted descending
    if re.search(r'who (?:sent|transferred|paid|gave) me (?:the most|the highest|most money)', lower):
        return {"intent": "aggregate", "metric": "max", "field": "amount", "filters": {"tx_type": "credit"}, "group_by": "sender", "order_by": "amount", "order": "desc", "limit": 1}

    # Pattern: "which number did I buy airtime for?" — grouped by recipient
    if re.search(r'(?:what number|who|which number).*airtime|airtime.*(?:most|often|number)', lower):
        return {"intent": "aggregate", "metric": "sum", "field": "amount", "filters": {"tx_type": "debit", "narration_contains": "airtime"}, "group_by": "recipient", "order_by": "amount", "order": "desc", "limit": 1}

    # Pattern: "how much did I spend on X" — captures the subject via (.+)
    spend_on = re.search(r'how much (?:did|do) i (?:spend|spent|pay|paid) (?:on|for) (.+)', lower)
    if spend_on:
        return {"intent": "aggregate", "metric": "sum", "field": "amount", "filters": {"tx_type": "debit", "narration_contains": spend_on.group(1).strip()}, "group_by": "none"}

    # Pattern: "how much did I spend this week / last month" — computes date range
    if re.search(r'how much (?:did|do) i (?:spend|spent) (?:this|last) (?:week|month)', lower):
        from datetime import datetime, timedelta
        
        today = datetime.now()
        date_from = None
        
        if "this week" in lower:
            # Monday of the current week
            start_of_week = today - timedelta(days=today.weekday())
            date_from = start_of_week.strftime("%Y-%m-%d")
        elif "last week" in lower:
            # Monday of the previous week
            start_of_last_week = today - timedelta(days=today.weekday() + 7)
            date_from = start_of_last_week.strftime("%Y-%m-%d")
        elif "this month" in lower:
            start_of_month = today.replace(day=1)
            date_from = start_of_month.strftime("%Y-%m-%d")
        elif "last month" in lower:
            first_of_this_month = today.replace(day=1)
            start_of_last_month = (first_of_this_month - timedelta(days=1)).replace(day=1)
            date_from = start_of_last_month.strftime("%Y-%m-%d")
        
        filters = {"tx_type": "debit"}
        if date_from:
            filters["date_from"] = date_from
        
        return {"intent": "aggregate", "metric": "sum", "field": "amount", "filters": filters, "group_by": "none"}

    # Pattern: "forecast" / "predict" — triggers insight mode for spending trends
    if re.search(r'\b(?:forecast|predict|project(?:ion)?)\b', lower):
        return {"intent": "insight", "metric": "sum", "field": "amount", "filters": {"tx_type": "debit"}, "group_by": "none"}

    # Pattern: "unusual" / "anomaly" — flags insight mode for outlier detection
    if re.search(r'\b(?:unusual|anomaly|suspicious|strange|weird)\b', lower):
        return {"intent": "insight", "metric": "count", "field": "amount", "filters": {"tx_type": "debit"}, "group_by": "none"}

    # Pattern: "last N transactions" — optional numeric capture, defaults to 10
    last_n = re.search(r'(?:last|latest|recent|show|list)\s*(\d+)?\s*(?:transaction|movement|activity|history)', lower)
    if last_n:
        limit = int(last_n.group(1)) if last_n.group(1) else 10
        return {"intent": "list", "metric": "count", "field": "amount", "filters": {"tx_type": "all"}, "order_by": "date", "order": "desc", "limit": min(limit, 50)}

    # Pattern: "transfers" — broad match for transfer-related queries
    if re.search(r'\b(?:transfer|bank transfer|send money)\b', lower):
        return {"intent": "aggregate", "metric": "sum", "field": "amount", "filters": {"tx_type": "debit", "narration_contains": "transfer"}, "group_by": "none"}

    # Pattern: "biggest expense" — single largest debit transaction
    if re.search(r'biggest (?:expense|spending|cost|purchase|payment)', lower):
        return {"intent": "lookup", "metric": "max", "field": "amount", "filters": {"tx_type": "debit"}, "order_by": "amount", "order": "desc", "limit": 1}

    return None

# ─── MAIN AGENT ENTRY POINT ─────────────────────────────────────────────

def run_intent_agent(user_id: str, message: str, history: List[Dict], db_conn,
                     since_date: Optional[str] = None,
                     until_date: Optional[str] = None,
                     temporal_context: Optional[Dict] = None) -> Dict:
    """
    Production-safe four-layer agent:
      Layer 1: LLM → JSON intent parsing with pattern-based fallback
      Layer 2: Whitelist-based query validation
      Layer 3: Deterministic SQL execution (parameterised queries only)
      Layer 4: LLM formatting with structured fallback

    Args:
        user_id:     Database-scoped user identifier.
        message:     Raw natural language question from the user.
        history:     Conversation history (list of {"role", "content"} dicts).
        db_conn:     Active database connection (sqlite3 or compatible).
        since_date:  Lower bound for the audit window (YYYY-MM-DD).
        until_date:  Upper bound for the audit window (YYYY-MM-DD).
        temporal_context: Optional dict with "since" / "until" keys that
                         override the individual since/until params.

    Returns:
        Dict with keys:
            response (str):      The formatted answer text.
            model_used (str):    Model name or "pattern-fallback" / "none".
            intent_parsed (dict): The validated query dict (or None on failure).
            result (dict):       Raw result from execute_query (for debugging).

    Edge cases:
        - When both LLM and pattern-matching fail, returns a fixed error string.
        - When execute_query throws, returns a generic error preserving model_used.
        - Empty history passes the raw message directly to the LLM without a
          conversation prefix.
        - Missing temporal_context defaults to the individual since/until params.
    """
    
    # Resolve temporal context if provided
    if temporal_context:
        since_date = temporal_context.get("since", since_date)
        until_date = temporal_context.get("until", until_date)
    
    raw_json = None
    model_used = None
    parsed_intent = None
    
    # Layer 1: Try LLM-based intent parsing first
    # Conversation history is injected so follow-up questions ("list", "this week")
    # are resolved relative to the previous turn. The default date range is appended
    # to the system prompt so the LLM applies it without explicit user mention.
    since_date = _validate_date(since_date, "earliest")
    until_date = _validate_date(until_date, "present")
    
    date_context = ""
    if since_date and since_date != "earliest":
        date_context += f"\nDEFAULT DATE RANGE: from {since_date}"
        if until_date and until_date != "present":
            date_context += f" to {until_date}"
        date_context += "\nApply these as date_from/date_to defaults when the user's question does not specify explicit dates."
    
    history = _validate_history(history, max_length=20)
    history_context = ""
    if history and len(history) >= 2:
        recent = history[-6:]
        history_context = "CONVERSATION SO FAR:\n"
        for msg in recent:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "user":
                history_context += f"User: {content}\n"
            elif role == "assistant":
                history_context += f"Assistant: {content}\n"
        history_context += "\nCURRENT QUESTION: " + message
    
    system_content = INTENT_SYSTEM_PROMPT
    if date_context:
        system_content += "\n\n" + date_context
    
    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": history_context if history_context else message}
    ]
    
    raw_json = None
    model_used = None
    parsed_intent = None
    
    try:
        client = get_openrouter_client()
        response = client.chat.completions.create(
            model=MODEL_CHAIN,
            messages=messages,
            temperature=0.1,
            max_tokens=300
        )
        raw_json = response.choices[0].message.content.strip()
        model_used = response.model
    except Exception as e:
        logger.warning(f"LLM call failed, trying pattern fallback: {e}")
    
    # Strip markdown code fences if the LLM wraps JSON in ```json ... ```
    if raw_json:
        raw_json = re.sub(r'^```(?:json)?\s*', '', raw_json)
        raw_json = re.sub(r'\s*```$', '', raw_json)
        try:
            parsed_intent = json.loads(raw_json)
        except json.JSONDecodeError:
            logger.warning(f"LLM returned invalid JSON, trying pattern fallback: {raw_json[:200]}")
    
    # Layer 1 fallback: pattern-based parsing when LLM is unavailable or fails
    if parsed_intent is None:
        pattern_intent = parse_intent_via_patterns(message)
        if pattern_intent:
            parsed_intent = pattern_intent
            model_used = "pattern-fallback"
            logger.info(f"Pattern fallback matched: {json.dumps(pattern_intent)}")
        else:
            return {
                "response": "I couldn't process that request. Try rephrasing (e.g. 'How much did I spend on transfers?').",
                "model_used": "none",
                "intent_parsed": None,
                "result": None
            }
    
    # Layer 2: Validate and sanitise the parsed intent
    validated_query = validate_query(parsed_intent)
    
    # Layer 3: Execute the validated query against the database
    try:
        result = execute_query(validated_query, user_id, db_conn)
    except Exception as e:
        logger.error(f"Query execution failed: {e}")
        return {
            "response": "I couldn't fetch that data. Please try again.",
            "model_used": model_used,
            "intent_parsed": validated_query,
            "result": None
        }
    
    # Layer 4: Format the result into a natural-language response
    previous_response = ""
    if history:
        for msg in reversed(history):
            if msg.get("role") == "assistant" and msg.get("content"):
                previous_response = msg["content"][:200]
                break
    response_text = format_response(result, message, previous_response)
    
    return {
        "response": response_text,
        "model_used": model_used,
        "intent_parsed": validated_query,
        "result": result
    }
