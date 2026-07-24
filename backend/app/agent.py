"""
Mirror.ng Agent — LLM-powered financial assistant

Architecture:
- Primary LLM: Gemini 2.0 Flash (via OpenRouter)
- Fallback LLM: Groq (Llama 3.3 70B)
- Last resort: DeepSeek
- Pattern-based fallback for common queries (avoids LLM call entirely)

Orchestrates tool execution, alias resolution, bulk updates, and
response formatting. Designed for Nigerian bank data (Sterling, Wema/ALAT,
Kuda, OPay, etc.).
"""

import os
import json
import logging
import re
import random
import asyncio
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime
from .llm_clients import get_openrouter_client, get_nvidia_client, MODEL_CHAIN
from .alias_utils import resolve_alias_for_transaction, load_aliases as load_aliases_full

ALLOWED_CATEGORIES = [
    "Transfer", "Utilities", "Food", "Transport", "Shopping",
    "Entertainment", "Health", "Education", "Fuel", "Data & Airtime",
    "Family", "Business", "General", "Salary"
]

logger = logging.getLogger(__name__)

# In-memory store for bulk update previews awaiting user confirmation
# Keyed by UUID, holds transaction IDs and target narration/category
_pending_bulk_updates: Dict[str, Dict] = {}

# Precompiled regex for date validation (YYYY-MM-DD format)
_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def sanitize_user_input(text: str) -> str:
    """Strip control characters and wrap input in XML-style tags for LLM context isolation."""
    text = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]', '', text)
    return f"[USER_INPUT]\n{text}\n[/USER_INPUT]"


def _validate_date(date_str: str, default: str = "earliest") -> str:
    """Return date_str if it matches YYYY-MM-DD, otherwise return default.

    Args:
        date_str: The date string to validate. May be None or empty.
        default: Fallback value when validation fails ('earliest' or 'present').

    Returns:
        Validated date string or the provided default.

    Example:
        >>> _validate_date('2024-03-15', 'earliest')
        '2024-03-15'
        >>> _validate_date('not-a-date', 'present')
        'present'
    """
    if not date_str:
        return default
    if _DATE_RE.match(date_str):
        return date_str
    return default


def _validate_history(history: list, max_length: int = 20) -> list:
    """Sanitize and truncate conversation history before sending to the LLM.

    Args:
        history: Raw conversation history from the client.
        max_length: Maximum number of messages to keep (oldest trimmed).

    Returns:
        Cleaned list of messages with validated roles, truncated content,
        and control characters stripped.

    Edge cases:
        - Non-list input returns empty list
        - Non-dict messages are silently dropped
        - Content strings are capped at 2000 characters
        - Control characters (0x00-0x1F) are stripped from content
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
            # SECURITY: Cap content length to prevent prompt injection via large payloads
            content = content[:2000]
            content = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f]', '', content)
        validated.append({"role": role, "content": content})
    return validated


# ─── TOOL DEFINITIONS ──────────────────────────────────────────────────
# Each tool is defined as an OpenAI-compatible function-calling schema.
# The LLM chooses which tool to call based on the user's query.
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_balance",
            "description": "Get current account balances for all the user's bank accounts",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_transactions",
            "description": "Get transaction history. Can filter by date or bank.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Number of transactions to fetch (default 20)"
                    },
                    "since_date": {
                        "type": "string",
                        "description": "Filter from this date onward. Format: YYYY-MM-DD"
                    },
                    "bank": {
                        "type": "string",
                        "description": "Filter by bank name e.g. 'Sterling Bank'"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_insights",
            "description": "Get ML insights: 7-day spend forecast, anomaly detection, spending trends",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_narrations",
            "description": "Search and analyze transaction narrations. Use for questions like 'what number did I top up most', 'who sent me money', 'which recipient got the most transfers'. Extracts patterns from narration text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tx_type": {
                        "type": "string",
                        "enum": ["debit", "credit", "all"],
                        "description": "Filter by transaction type"
                    },
                    "keyword": {
                        "type": "string",
                        "description": "Optional keyword to filter narrations e.g. 'airtime', 'transfer', 'data'"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_largest_transactions",
            "description": "Get the largest transactions by amount, useful for 'what was my biggest spend'",
            "parameters": {
                "type": "object",
                "properties": {
                    "tx_type": {
                        "type": "string",
                        "enum": ["debit", "credit", "all"],
                        "description": "Filter by transaction type"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "How many to return (default 5)"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "preview_bulk_update",
            "description": "Preview renaming and recategorizing transactions matching a narration pattern. DOES NOT execute. Returns a preview_id the user must confirm.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Substring to search narrations (e.g. 'EBILLPAY')"},
                    "new_narration": {"type": "string", "description": "New narration to apply"},
                    "new_category": {
                        "type": "string",
                        "description": "The new category for matched transactions",
                        "enum": ALLOWED_CATEGORIES
                    }
                },
                "required": ["query", "new_narration", "new_category"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_bulk_update",
            "description": "Execute a previously previewed bulk update using its preview_id. Only call when the user has confirmed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "preview_id": {"type": "string", "description": "The preview_id from preview_bulk_update"}
                },
                "required": ["preview_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_categories",
            "description": "Get the list of all valid transaction categories currently in the database. Use this before suggesting or applying a category change to ensure it exists.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    }
]

def clean_llm_json(text: str) -> str:
    """Remove tool result markers and JSON blocks that smaller LLMs sometimes echo."""
    text = re.sub(r'Tool result:\s*', '', text)
    result = []
    i = 0
    while i < len(text):
        if text[i] == '{':
            snippet = text[i:i+200]
            tool_keys = [
                '"success"', '"preview_id"', '"error"', '"total_matched"',
                '"transactions"', '"alias_breakdown"', '"matched_count"',
                '"count"', '"new_narration"', '"new_category"', '"matches"'
            ]
            if any(key in snippet for key in tool_keys):
                brace_count = 0
                j = i
                while j < len(text):
                    if text[j] == '{': brace_count += 1
                    elif text[j] == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            i = j + 1
                            break
                    j += 1
                else:
                    result.append(text[i])
                    i += 1
                continue
        result.append(text[i])
        i += 1
    cleaned = "".join(result)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned).strip()
    cleaned = re.sub(r'^(?:\s*\n)+', '', cleaned)
    json_chars = sum(1 for c in cleaned if c in '{}[],":')
    if len(cleaned) > 0 and (json_chars / len(cleaned)) > 0.8:
        return "I found the data but couldn't format it properly. Please try rephrasing your question."
    return cleaned


# The system prompt defines the assistant's personality, rules, and behavioral constraints.
# Key design decisions:
# - Explicit query→tool mappings to reduce LLM reasoning errors
# - Naira (₦) formatting enforced at the prompt level
# - Bulk update guardrails require preview→confirm flow
# - Category validation enforced via get_categories tool
# - Financial advice disclaimer triggered by specific topics
# - Temporal audit context injected at runtime via format() placeholders
SYSTEM_PROMPT = """You are Mirror — a Nigerian financial intelligence assistant. You help users understand their spending, track transactions, and manage their money.

## YOUR PERSONALITY & TONE
- Speak in Nigerian English — warm, direct, and conversational.
- Be professional but friendly. You're a financial assistant, not a robot.
- Use phrases like "Let me check that for you", "I see you've spent X on Y", "Here's what I found".
- Keep responses concise and actionable.
- Use emojis sparingly but effectively (✅, 💰, 📊, etc.).
- Be confident and clear. Don't over-explain or hedge unnecessarily.
- When something goes wrong, be direct: "That didn't work. Let me try again."
- Celebrate wins briefly: "Done! 3 transactions updated."

## WHAT YOU CAN HELP WITH
✅ Tracking and analyzing transactions.
✅ Categorizing spending and finding patterns.
✅ Identifying unusual transactions or spikes.
✅ Answering questions about past spending and balances.
✅ Bulk renaming/recategorizing transactions.

## WHAT YOU CANNOT DO
❌ Give investment advice or tell users how to make money.
❌ Predict future earnings or recommend specific financial products.
❌ Encourage get-rich-quick schemes.

## FINANCIAL ADVICE GUARDRAILS
When users ask about making money, investments, or financial advice:
1. Acknowledge their question briefly.
2. Redirect to what you CAN help with.
3. Suggest they consult a licensed financial advisor.
4. DO NOT engage in brainstorming or planning for making money.

Example response to "How do I make 30 million?":
"I'm not a financial advisor, so I can't help with that. What I can do is help you track where your money goes, see your spending patterns, and categorize your transactions. Would you like me to show you your spending summary?"

## RESPONSE FORMATTING RULES

### RESPONSE FORMATTING RULES:
1. NEVER use bullet points (•) for lists of balances or transactions.
2. NEVER include raw tool output or JSON in your response. Always summarize or tabulate.
3. ALWAYS use markdown tables for structured data:

**For balances:**
| Bank | Account | Balance |
|------|---------|---------|
| Sterling Bank | ••••5156 | ₦5,695.00 |
| **Total** | | **₦21,742.01** |

**For transactions:**
| Date | Description | Amount | Category |
|------|-------------|--------|----------|
| 02 Jul | EbillTech | -₦2,000 | Utilities |

### CATEGORY ENFORCEMENT:
When categorizing transactions, the category MUST be one of these 14 options:
{ALLOWED_CATEGORIES}

If the user requests a category not in this list (e.g., "Groceries"), map it to the closest match (e.g., "Food") or ask them to choose from the list.

### Bulk Editing Rules
- When a user asks to rename/recategorize multiple transactions, call `preview_bulk_update` first.
- Tell the user how many matches you found and ask them to confirm.
- Only call `execute_bulk_update` after the user explicitly confirms.

## BULK UPDATE EXECUTION FLOW
When you show a bulk update preview:
1. Wait for the user to click "Apply" on the UI card.
2. The system will send you a confirmation message like "✅ Bulk update completed successfully..."
3. Acknowledge the success briefly: "✅ Done! N transactions updated. I've also saved this as a rule in your Settings, so future transactions will be categorized automatically."
4. DO NOT show another preview. DO NOT ask for confirmation again. Move on.
5. If you receive "❌ Bulk update failed", explain the error and offer to try again.

## ERROR HANDLING
If a tool call fails or returns an error:
1. Acknowledge the failure clearly.
2. Explain what went wrong in simple terms.
3. Offer alternatives or next steps.
4. DO NOT hallucinate that the operation succeeded.
5. NEVER say "Now answer my original question" — this causes confusion.

AUDIT CONTEXT (current view window):
- Period: {since_date} to {until_date}
- Period source: {since_date_source}
- Current actual date: {current_date}
- When asked about spend, transfers, or any time-bounded question, use this period automatically. Do NOT ask the user to specify a date range — the audit window is already set.
- Relative time keywords like "today", "this week", "this month", "last month" should be resolved against the current actual date ({current_date}).
- If the user asks about a month that falls outside the period above, note that it is outside your active audit scope."""


def load_aliases(db_conn, user_id: str) -> List[Dict]:
    """Load user aliases for narration cleaning.

    Args:
        db_conn: Database connection (sqlite3 or similar).
        user_id: The user's unique identifier.

    Returns:
        List of alias dicts with 'recipient_pattern' and 'display_name' keys.
        Returns empty list on any database error — aliases are non-critical.
    """
    try:
        cursor = db_conn.execute(
            'SELECT recipient_pattern, display_name FROM user_aliases WHERE user_id = ?',
            (user_id,)
        )
        return [dict(r) for r in cursor.fetchall()]
    except Exception:
        # SECURITY: Silently swallow DB errors — alias resolution is a UX enhancement,
        # not a critical path. Failing here should not block the user's request.
        return []


def apply_aliases_to_narration(narration: str, aliases: List[Dict]) -> str:
    """Replace narration with alias display_name if pattern matches.

    Args:
        narration: Raw transaction narration text.
        aliases: List of alias dicts with 'recipient_pattern' and 'display_name'.

    Returns:
        The alias display_name if matched, else the original narration.

    Matching is case-insensitive substring-based (not regex) for performance.
    First matching alias wins (priority by alias list order).
    """
    for a in aliases:
        pattern = a['recipient_pattern'].lower()
        if pattern and pattern in narration.lower():
            return a['display_name']
    return narration


def clean_tx_narration(tx: Dict, aliases: List[Dict]) -> Dict:
    """Apply aliases and shorten common prefixes on a transaction dict.

    Normalizes bank-originated narration formats (e.g. Nigerian bank NIP
    references, OneBank transfer syntax) into human-readable form.

    Args:
        tx: Raw transaction dict with at least a 'narration' key.
        aliases: User-defined alias patterns.

    Returns:
        New dict with cleaned narration. Original is not mutated.

    Transformation pipeline:
        1. Alias substitution (user-defined)
        2. Strip leading reference numbers ("00000... | text")
        3. Insert spaces between concatenated CamelCase words
        4. Parse OneBank "Transfer from X to Y" → "Transfer to Y"
        5. Strip common bank prefixes (BANKNIP, NIP:, etc.)
    """
    tx = dict(tx)
    raw = tx.get('narration', '') or ''
    aliased = apply_aliases_to_narration(raw, aliases)
    cleaned = aliased

    # Regex: strip leading numeric reference followed by pipe and space
    # Common in Nigerian bank SMS: "000001260515072215138153450611 | Description"
    # ^\d+     — one or more digits (reference number)
    # \s*\|\s* — optional whitespace, pipe, optional whitespace
    cleaned = re.sub(r'^\d+\s*\|\s*', '', cleaned).strip()

    # If first 20 chars have no whitespace, the narration is likely
    # concatenated CamelCase (e.g. "POSWithdrawalAirtime"). Insert spaces
    # to make it readable: "POS Withdrawal Airtime"
    if not any(c.isspace() for c in cleaned[:20]):
        # Insert space between lowercase+uppercase boundary: "aA" → "a A"
        cleaned = re.sub(r'([a-z])([A-Z])', r'\1 \2', cleaned)
        # Insert space between uppercase sequence and title case: "ABCDef" → "ABC Def"
        cleaned = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1 \2', cleaned)

    # Normalize "OneBank Transfer from <Sender> to <Recipient>" format
    # Capture group 1: everything after "to "
    m = re.search(r'OneBank\s+Transfer\s+from\s+.*?\s+to\s+(.+)', cleaned, re.IGNORECASE)
    if m:
        to_part = m.group(1).strip()
        # Strip parenthetical suffixes like "Name(ExtraInfo)" → "Name"
        to_part = re.sub(r'\(.*?\)', '', to_part).strip()
        cleaned = f"Transfer to {to_part}"
    else:
        # Strip known prefixes from other bank formats
        for prefix in ['BANKNIP From', 'NIP:', 'OneBank Transfer from', '00000']:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
                break

    tx['narration'] = cleaned or aliased
    return tx


# ─── TOOL EXECUTOR ─────────────────────────────────────────────────────
def execute_tool(tool_name: str, tool_args: Dict, user_id: str, db_conn, is_local: bool = False) -> str:
    """Dispatch to the appropriate backend function based on tool_name.

    Args:
        tool_name: The name of the tool to execute (must match a TOOLS entry).
        tool_args: Arguments dictionary from the LLM's function call.
        user_id: The requesting user's identifier.
        db_conn: Active database connection.
        is_local: If True, certain operations (bulk updates) are blocked
                  because data hasn't been synced to the cloud.

    Returns:
        JSON string of the result, or an error message string.

    Raises:
        No exceptions propagate to caller — all errors are caught and
        returned as user-facing error messages.
    """
    # SECURITY: LLMs sometimes emit string values for integer fields.
    # Normalize to prevent SQLite type mismatches or crashes.
    if "limit" in tool_args and isinstance(tool_args["limit"], str):
        try:
            tool_args["limit"] = int(tool_args["limit"])
        except (ValueError, TypeError):
            tool_args["limit"] = 5

    try:
        aliases = load_aliases_full(db_conn, user_id)

        if tool_name == "get_balance":
            from .balance_manager import BalanceManager
            balances = []
            try:
                bm = BalanceManager(db_conn)
                balances = bm.get_all_current_balances(user_id)
            except Exception:
                balances = []

            cursor = db_conn.execute(
                'SELECT bank, account_last4, tx_type, amount FROM transactions WHERE user_id = ?',
                (user_id,)
            )
            txs = cursor.fetchall()

            if txs:
                banks_in_txs = set(t['bank'] for t in txs)
                banks_with_anchor = set(b['bank'] for b in balances)

                for bank in banks_in_txs - banks_with_anchor:
                    bank_txs = [t for t in txs if t['bank'] == bank]
                    last4 = next((t['account_last4'] for t in bank_txs if t['account_last4']), '????')
                    net = sum(t['amount'] if t['tx_type'] == 'credit' else -t['amount'] for t in bank_txs)
                    balances.append({
                        'bank': bank,
                        'account_last4': last4,
                        'balance': net,
                        'note': 'computed from transactions (no anchor set)'
                    })

            if not balances:
                return json.dumps({"success": True, "balances": [], "total": 0})

            total = sum(b['balance'] or 0 for b in balances)
            return json.dumps({
                "success": True,
                "balances": balances,
                "total": total
            }, default=str)

        elif tool_name == "get_transactions":
            limit = tool_args.get("limit", 20)
            since_date = tool_args.get("since_date")
            bank = tool_args.get("bank")

            query = "SELECT * FROM transactions WHERE user_id = ?"
            params = [user_id]
            if since_date:
                query += " AND timestamp >= ?"
                params.append(since_date)
            if bank:
                # SECURITY: Using LIKE with user-provided bank name.
                # Parameterized query prevents SQL injection.
                query += " AND bank LIKE ?"
                params.append(f"%{bank}%")

            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)

            cursor = db_conn.execute(query, params)
            txs = [clean_tx_narration(dict(row), aliases) for row in cursor.fetchall()]
            return json.dumps(txs, default=str) if txs else "No transactions found."

        elif tool_name == "get_insights":
            from .ml.anomaly import detect_anomalies
            from .ml.forecaster import weekly_spend_forecast

            cursor = db_conn.execute(
                "SELECT * FROM transactions WHERE user_id = ? ORDER BY timestamp ASC",
                (user_id,)
            )
            txs = [dict(row) for row in cursor.fetchall()]
            # ML pipeline: anomaly detection uses isolation forest / z-score;
            # forecast uses exponential smoothing or linear regression.
            anomalies = [t for t in detect_anomalies(txs) if t.get("is_anomaly")]
            forecast = weekly_spend_forecast(txs)
            return json.dumps({
                "forecast": forecast,
                "anomalies": anomalies,
                "total_transactions": len(txs)
            }, default=str)

        elif tool_name == "search_narrations":
            tx_type = tool_args.get("tx_type", "all")
            keyword = tool_args.get("keyword", "")

            query = "SELECT * FROM transactions WHERE user_id = ?"
            params = [user_id]
            if tx_type != "all":
                query += " AND tx_type = ?"
                params.append(tx_type)
            if keyword:
                # Search both narration and original_narration to catch
                # transactions that were aliased/cleaned after import.
                query += " AND (narration LIKE ? OR original_narration LIKE ?)"
                params.extend([f"%{keyword}%", f"%{keyword}%"])

            query += " ORDER BY timestamp DESC"
            cursor = db_conn.execute(query, params)
            txs = [dict(row) for row in cursor.fetchall()]

            resolved_txs = []
            phone_counts: Dict[str, Dict] = {}
            alias_counts: Dict[str, Dict] = {}

            for tx in txs:
                resolved = resolve_alias_for_transaction(tx, aliases)

                if resolved['is_aliased']:
                    name = resolved['display_name']
                    if name not in alias_counts:
                        alias_counts[name] = {"count": 0, "total_amount": 0, "category": resolved['category']}
                    alias_counts[name]["count"] += 1
                    alias_counts[name]["total_amount"] += float(tx["amount"])

                narration = tx.get("original_narration") or tx.get("narration", "")
                # Regex: Nigerian mobile numbers starting with 07, 08, or 09
                # (0[789]) — match country prefix variants
                # \d{9}   — exactly 9 remaining digits
                phones = re.findall(r'0[789]\d{9}', narration)
                for phone in phones:
                    if phone not in phone_counts:
                        phone_counts[phone] = {"count": 0, "total_amount": 0}
                    phone_counts[phone]["count"] += 1
                    phone_counts[phone]["total_amount"] += float(tx["amount"])

                resolved_txs.append({
                    "display_name": resolved['display_name'],
                    "original_narration": tx.get("narration"),
                    "amount": float(tx["amount"]),
                    "tx_type": tx["tx_type"],
                    "category": resolved['category'],
                    "date": tx["timestamp"],
                    "bank": tx["bank"]
                })

            return json.dumps({
                "total_matched": len(txs),
                "alias_breakdown": alias_counts,
                "phone_number_breakdown": phone_counts,
                "transactions": resolved_txs[:30]
            }, default=str)

        elif tool_name == "get_largest_transactions":
            tx_type = tool_args.get("tx_type", "all")
            limit = tool_args.get("limit", 5)
            query = "SELECT * FROM transactions WHERE user_id = ?"
            params = [user_id]
            if tx_type != "all":
                query += " AND tx_type = ?"
                params.append(tx_type)
            query += " ORDER BY amount DESC LIMIT ?"
            params.append(limit)
            cursor = db_conn.execute(query, params)
            txs = [dict(row) for row in cursor.fetchall()]
            results = []
            for tx in txs:
                resolved = resolve_alias_for_transaction(tx, aliases)
                results.append({
                    "bank": tx.get('bank', ''),
                    "amount": float(tx.get('amount', 0)),
                    "display_name": resolved['display_name'],
                    "original_narration": tx.get('narration', ''),
                    "category": resolved['category'],
                    "date": tx.get('timestamp', ''),
                    "tx_type": tx.get('tx_type', '')
                })
            return json.dumps(results, default=str)

        elif tool_name == "preview_bulk_update":
            # SECURITY: Block bulk edits for local-only (non-synced) sessions.
            # Without cloud sync, there's no persistent DB to update.
            if is_local:
                return json.dumps({"success": False, "error": "Bulk editing is only available when Cloud Sync is enabled. These transactions are only in your local session and haven't been saved to the database yet."})
            query = tool_args.get("query", "")
            new_narration = tool_args.get("new_narration", "")
            new_category = tool_args.get("new_category", "")
            if not query or not new_narration:
                return json.dumps({"success": False, "error": "query and new_narration required"})
            cursor = db_conn.execute(
                'SELECT id, narration, amount, tx_type FROM transactions WHERE user_id = ? AND LOWER(narration) LIKE ?',
                (user_id, f"%{query.lower()}%")
            )
            matches = [dict(r) for r in cursor.fetchall()]
            if not matches:
                return json.dumps({"success": False, "message": f"No transactions found matching '{query}'."})
            preview_id = str(uuid.uuid4())
            # Store preview in memory — expires on server restart or 24h TTL
            _pending_bulk_updates[preview_id] = {
                "user_id": user_id,
                "transaction_ids": [m["id"] for m in matches],
                "new_narration": new_narration,
                "new_category": new_category,
                "query": query,
                "count": len(matches),
            }
            return json.dumps({
                "success": True, "preview_id": preview_id, "count": len(matches),
                "new_narration": new_narration, "new_category": new_category,
                "matches": [{"narration": m["narration"], "amount": m["amount"], "id": m["id"]} for m in matches[:5]],
                "matched_count": len(matches)
            }, default=str)

        elif tool_name == "execute_bulk_update":
            preview_id = tool_args.get("preview_id", "")
            if not preview_id or preview_id not in _pending_bulk_updates:
                return json.dumps({"success": False, "error": "Invalid or expired preview_id. Run preview_bulk_update first."})
            data = _pending_bulk_updates[preview_id]
            # SECURITY: Verify the preview belongs to the requesting user
            # to prevent user A from executing user B's preview.
            if data["user_id"] != user_id:
                return json.dumps({"success": False, "error": "Preview does not belong to this user."})
            updated_count = len(data["transaction_ids"])
            query_pattern = data.get("query", "")
            # Only create/update the alias rule — do NOT overwrite transactions
            if query_pattern and updated_count > 0:
                cursor = db_conn.execute(
                    'SELECT id FROM user_aliases WHERE user_id = ? AND recipient_pattern = ?',
                    (user_id, query_pattern)
                )
                existing_alias = cursor.fetchone()
                if existing_alias:
                    db_conn.execute('''
                        UPDATE user_aliases
                        SET display_name = ?, category = ?
                        WHERE id = ?
                    ''', (data["new_narration"], data["new_category"], existing_alias['id']))
                else:
                    db_conn.execute('''
                        INSERT INTO user_aliases (user_id, recipient_pattern, display_name, category, exact_match)
                        VALUES (?, ?, ?, ?, 0)
                    ''', (user_id, query_pattern, data["new_narration"], data["new_category"]))
            db_conn.commit()
            # Clean up preview to prevent replay attacks
            del _pending_bulk_updates[preview_id]
            return json.dumps({"success": True, "updated_count": updated_count, "message": f"Rule created for {updated_count} transactions."})

        elif tool_name == "get_categories":
            cursor = db_conn.execute(
                "SELECT DISTINCT category FROM transactions WHERE user_id = ? AND category IS NOT NULL ORDER BY category",
                (user_id,)
            )
            categories = [row[0] for row in cursor.fetchall()]
            return json.dumps({"success": True, "categories": categories})

        return f"Unknown tool: {tool_name}"

    except Exception as e:
        # Catch-all: prevents unhandled exceptions from crashing the agent loop.
        # Logged server-side; user sees a generic message (no stack trace leak).
        logger.error(f"Tool error ({tool_name}): {e}")
        return f"An error occurred while processing that request."


# ─── FALLBACK FORMATTER (NO LLM NEEDED) ───────────────────────────────
def format_tool_result_fallback(tool_name: str, tool_result: str) -> str:
    """Format tool results without calling the LLM again.

    Used when the LLM fails after a tool call (rate limit, timeout, empty response).
    Produces human-readable Markdown from structured JSON data.

    Args:
        tool_name: Name of the tool that produced the result.
        tool_result: JSON string returned by execute_tool().

    Returns:
        Formatted string with Markdown formatting for the UI.

    Supported tools:
        - get_insights: Shows forecast trend + anomaly highlights
        - get_transactions: Tabular list with bank, amount, narration
        - get_balance: Per-account + total balance summary
        - All others: Raw JSON in code block

    Edge cases:
        - Empty data arrays produce "No X found." messages
        - Parsing errors return a descriptive error string (not a crash)
    """
    try:
        data = json.loads(tool_result)

        if tool_name == "get_insights":
            forecast = data.get("forecast", {})
            anomalies = data.get("anomalies", [])
            total_txs = data.get("total_transactions", 0)

            response = f"📊 **Financial Insights**\n\n"
            response += f"Total transactions analyzed: {total_txs}\n\n"

            if forecast:
                response += f"**7-Day Forecast:**\n"
                response += f"- Trend: {forecast.get('trend', 'unknown')}\n"
                response += f"- Daily average: ₦{forecast.get('daily_avg', 0):,.2f}\n"
                response += f"- Weekly projection: ₦{forecast.get('weekly_projection', 0):,.2f}\n\n"

            if anomalies:
                response += f"⚠️ **Unusual Transactions ({len(anomalies)}):**\n"
                for anomaly in anomalies[:5]:
                    amount = anomaly.get('amount', 0)
                    cat = anomaly.get('category', 'Unknown')
                    response += f"- ₦{amount:,.2f} in {cat}\n"
            else:
                response += "✅ No unusual transactions detected.\n"

            return response

        elif tool_name == "get_transactions":
            txs = data if isinstance(data, list) else []
            if not txs:
                return "No transactions found."

            response = f"Found {len(txs)} transactions:\n\n"
            for i, tx in enumerate(txs[:10], 1):
                bank = tx.get('bank', 'Unknown')
                amount = tx.get('amount', 0)
                narration = tx.get('narration', 'Unknown')
                tx_type = tx.get('tx_type', '')
                symbol = "+" if tx_type == "credit" else "-"
                response += f"{i}. {bank}: {symbol}₦{amount:,.2f} - {narration}\n"

            if len(txs) > 10:
                response += f"\n... and {len(txs) - 10} more transactions"

            return response

        elif tool_name == "get_balance":
            balances = data.get("balances", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            if not balances:
                return "No account balances found."

            response = "💰 **Current Balances:**\n\n"
            total = 0
            for bal in balances:
                bank = bal.get('bank', 'Unknown')
                last4 = bal.get('account_last4', '????')
                amount = bal.get('balance', 0)
                total += amount
                response += f"- {bank} ••••{last4}: ₦{amount:,.2f}\n"

            response += f"\n**Total: ₦{total:,.2f}**"
            return response

        return f"Tool result:\n```json\n{json.dumps(data, indent=2)}\n```"

    except Exception as e:
        logger.error(f"Fallback formatter failed: {e}")
        return f"Tool executed but formatting failed: {str(e)}"


def try_pattern_fallback(message: str, user_id: str, db_conn) -> Optional[Dict]:
    """Handle common queries without LLM — works even when rate limited.

    Pattern-matches the user's message against known query templates and
    returns a structured response directly from the database. This is the
    first line of defense before any LLM call is attempted.

    Args:
        message: Raw user message string.
        user_id: The user's unique identifier.
        db_conn: Active database connection.

    Returns:
        Dict with 'success', 'response', 'tool_calls_made', and 'model_used'
        keys if a pattern matched, or None to proceed to the LLM.

    Supported patterns (in priority order):
        - Alias/category count queries
        - Category listing with transaction counts
        - Balance queries
        - Recent transaction listing ("last N transactions")
        - Time-bounded spend totals ("this week/month")
        - Spend-on-category queries ("how much did I spend on X")
        - Total spend queries
    """
    lower = message.lower().strip()

    # Pattern: "How many aliases" / "Do I have aliases?"
    # Captures count queries about user-defined aliases or categories
    if re.search(r'(how many|do i have|do you have).*(aliases|categories|groups|alias)', lower):
        cursor = db_conn.execute(
            'SELECT COUNT(DISTINCT display_name) FROM user_aliases WHERE user_id = ?',
            (user_id,)
        )
        count = cursor.fetchone()[0]

        if count == 0:
            response = "You don't have any aliases yet. You can create them in the Audit Feed by clicking on transactions."
        else:
            cursor = db_conn.execute(
                '''SELECT display_name, category, COUNT(*) as count
                   FROM user_aliases WHERE user_id = ?
                   GROUP BY display_name ORDER BY count DESC LIMIT 5''',
                (user_id,)
            )
            examples = cursor.fetchall()
            response = f"You have {count} alias groups:\n\n"
            for ex in examples:
                response += f"• {ex['display_name']} ({ex['category']}): {ex['count']} transactions\n"
            if count > 5:
                response += f"\n... and {count - 5} more"

        return {
            "success": True,
            "response": response,
            "tool_calls_made": [{"tool": "count_aliases", "args": {}}],
            "model_used": "pattern-fallback"
        }

    # Pattern: "What categories do I have?"
    if re.search(r'(what|show|list).*(categories|groups)', lower):
        cursor = db_conn.execute(
            '''SELECT category, display_name, COUNT(*) as tx_count
               FROM user_aliases WHERE user_id = ?
               GROUP BY category, display_name ORDER BY category, tx_count DESC''',
            (user_id,)
        )
        rows = cursor.fetchall()

        if not rows:
            return {
                "success": True,
                "response": "You don't have any categories yet. Create aliases in the Audit Feed to get started.",
                "tool_calls_made": [],
                "model_used": "pattern-fallback"
            }

        # Group aliases under their parent categories for structured display
        categories = {}
        for row in rows:
            cat = row['category']
            if cat not in categories:
                categories[cat] = {"aliases": [], "total_tx": 0}
            categories[cat]["aliases"].append(f"{row['display_name']} — {row['tx_count']} txns")
            categories[cat]["total_tx"] += row['tx_count']

        lines = ["Your categories:\n"]
        for cat, data in sorted(categories.items(), key=lambda x: x[1]["total_tx"], reverse=True):
            lines.append(f"• {cat}: ({data['total_tx']} Transactions)")
            for alias in data["aliases"]:
                lines.append(f"    {alias}")

        return {
            "success": True,
            "response": "\n".join(lines),
            "tool_calls_made": [{"tool": "list_categories", "args": {}}],
            "model_used": "pattern-fallback"
        }

    # Pattern: "What's my balance" / "show balance"
    if re.search(r"(what(?:'s| is) my|show|current)\s*(balance|funds)", lower):
        from .balance_manager import BalanceManager
        bm = BalanceManager(db_conn)
        balances = bm.get_all_current_balances(user_id)

        if not balances:
            return {
                "success": True,
                "response": "No account balances found.",
                "tool_calls_made": [{"tool": "get_balance", "args": {}}],
                "model_used": "pattern-fallback"
            }

        logger.info(f"Pattern fallback: user_id={user_id}, bm={bm}")

        balances = bm.get_all_current_balances(user_id)
        logger.info(f"Balances retrieved: {balances}")

        response = "| Bank | Account | Balance |\n|------|---------|---------|\n"
        total = 0.0
        for bal in balances:
            last4 = bal.get('account_last4') or 'N/A'
            amount = bal.get('balance') or 0.0
            logger.info(f"Processing balance: bank={bal.get('bank')}, last4={last4}, amount={amount}")
            response += f"| {bal['bank']} | ••••{last4} | ₦{amount:,.2f} |\n"
            total += amount
        response += f"| **Total** | | **₦{total:,.2f}** |"

        return {
            "success": True,
            "response": response,
            "tool_calls_made": [{"tool": "get_balance", "args": {}}],
            "model_used": "pattern-fallback"
        }

    # Pattern: "Show last N transactions"
    # (\d+)?  — optional digit group for the count (defaults to 5)
    # (?:show|list|last) — action verb
    # (?:transactions?|activity) — noun, accepts singular/plural
    match = re.search(r'(?:show|list|last)\s*(\d+)?\s*(?:transactions?|activity)', lower)
    if match:
        limit = int(match.group(1)) if match.group(1) else 5
        cursor = db_conn.execute(
            '''SELECT bank, narration, amount, tx_type, timestamp
               FROM transactions WHERE user_id = ?
               ORDER BY timestamp DESC LIMIT ?''',
            (user_id, limit)
        )
        txs = cursor.fetchall()

        if not txs:
            return {
                "success": True,
                "response": "No transactions found.",
                "tool_calls_made": [{"tool": "get_transactions", "args": {}}],
                "model_used": "pattern-fallback"
            }

        response = f"Last {len(txs)} transactions:\n\n"
        for i, tx in enumerate(txs, 1):
            symbol = "+" if tx['tx_type'] == "credit" else "-"
            narration = tx['narration'] or ''
            # Same CamelCase splitting logic as clean_tx_narration
            if not any(c.isspace() for c in narration[:20]):
                narration = re.sub(r'([a-z])([A-Z])', r'\1 \2', narration)
                narration = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1 \2', narration)
            response += f"{i}. {tx['bank']}: {symbol}₦{tx['amount']:,.2f} - {narration}\n"

        return {
            "success": True,
            "response": response,
            "tool_calls_made": [{"tool": "get_transactions", "args": {"limit": limit}}],
            "model_used": "pattern-fallback"
        }

    # Pattern: "How much did I spend this week / month?"
    # Calculates start-of-period based on relative keywords and sums debits
    if re.search(r'how much (?:did|do) i (?:spend|spent) (?:this|last) (?:week|month)', lower):
        from datetime import datetime, timedelta

        today = datetime.now()

        if "this week" in lower:
            # Monday of current week (weekday() = 0 for Monday)
            start_of_week = today - timedelta(days=today.weekday())
            since_date = start_of_week.strftime("%Y-%m-%d")
            period_label = "this week"
        elif "last week" in lower:
            # Monday of previous week
            start_of_last_week = today - timedelta(days=today.weekday() + 7)
            since_date = start_of_last_week.strftime("%Y-%m-%d")
            period_label = "last week"
        elif "this month" in lower:
            start_of_month = today.replace(day=1)
            since_date = start_of_month.strftime("%Y-%m-%d")
            period_label = "this month"
        elif "last month" in lower:
            # First day of previous month by going back 1 day from first of this month
            first_of_this_month = today.replace(day=1)
            start_of_last_month = (first_of_this_month - timedelta(days=1)).replace(day=1)
            since_date = start_of_last_month.strftime("%Y-%m-%d")
            period_label = "last month"
        else:
            since_date = None
            period_label = "total"

        query = 'SELECT SUM(amount) FROM transactions WHERE user_id = ? AND tx_type = ?'
        params = [user_id, 'debit']

        if since_date:
            query += ' AND timestamp >= ?'
            params.append(since_date)

        cursor = db_conn.execute(query, params)
        total = cursor.fetchone()[0] or 0

        return {
            "success": True,
            "response": f"You've spent ₦{total:,.2f} {period_label}.",
            "tool_calls_made": [{"tool": "pattern_spend_on", "args": {"since_date": since_date} if since_date else {}}],
            "model_used": "pattern-fallback"
        }

    # Pattern: "How much did I spend on [X]?"
    # Matches any text after "on" or "for" as the category/keyword
    spend_on = re.search(r'how much (?:did|do) i (?:spend|spent) (?:on|for) (.+?)(?:\?|$)', lower)
    if spend_on:
        keyword = spend_on.group(1).strip()

        aliases = load_aliases_full(db_conn, user_id)

        cursor = db_conn.execute(
            'SELECT * FROM transactions WHERE user_id = ? AND tx_type = ?',
            (user_id, 'debit')
        )
        txs = [dict(row) for row in cursor.fetchall()]

        # Match across three dimensions: category, alias display name, and raw narration
        total = 0.0
        count = 0
        keyword_lower = keyword.lower()

        for tx in txs:
            resolved = resolve_alias_for_transaction(tx, aliases)
            cat = resolved['category'].lower()
            alias_name = resolved['display_name'].lower()
            narration = (tx.get('original_narration') or tx.get('narration') or '').lower()

            if keyword_lower in cat or keyword_lower in alias_name or keyword_lower in narration:
                total += float(tx['amount'])
                count += 1

        if count == 0:
            return {
                "success": True,
                "response": f"I couldn't find any spending matching '{keyword}'. Try checking your categories or aliases.",
                "tool_calls_made": [],
                "model_used": "pattern-fallback"
            }

        return {
            "success": True,
            "response": f"You've spent ₦{total:,.2f} on {keyword} across {count} transaction{'s' if count != 1 else ''}.",
            "tool_calls_made": [{"tool": "pattern_spend_on", "args": {"keyword": keyword}}],
            "model_used": "pattern-fallback"
        }

    # Pattern: "How much did I spend" (total, no time period or category)
    if re.search(r'how much (?:did|do) i (?:spend|spent)', lower) and not re.search(r'on|for', lower):
        cursor = db_conn.execute(
            'SELECT SUM(amount) FROM transactions WHERE user_id = ? AND tx_type = ?',
            (user_id, 'debit')
        )
        total = cursor.fetchone()[0] or 0
        return {
            "success": True,
            "response": f"You've spent a total of ₦{total:,.2f}.",
            "tool_calls_made": [{"tool": "pattern_spend_on", "args": {}}],
            "model_used": "pattern-fallback"
        }

    return None


# ─── AGENT LOOP ────────────────────────────────────────────────────────
async def run_agent(user_id: str, message: str, history: List[Dict], db_conn, since_date: Optional[str] = None, until_date: Optional[str] = None, temporal_context: Optional[Dict] = None, is_local: bool = False) -> Dict:
    """Main agent entry point — orchestrates the LLM conversation loop.

    Flow:
        1. Try pattern fallback (fast, no LLM call)
        2. Inject temporal audit context into system prompt
        3. Validate/clean conversation history
        4. Call LLM with tools available
        5. Process tool calls (up to 5 iterations max)
        6. If LLM fails after tool calls, use fallback formatter
        7. Return final response or fallback

    Args:
        user_id: The user's unique identifier.
        message: The user's current message.
        history: Previous conversation messages.
        db_conn: Active database connection.
        since_date: Start of audit window (YYYY-MM-DD).
        until_date: End of audit window (YYYY-MM-DD).
        temporal_context: Dict with 'since', 'until', 'source' keys
                         from the frontend's audit state.
        is_local: Whether the session is local-only (no cloud sync).

    Returns:
        Dict with 'response' (str), 'tool_calls_made' (list), 'model_used' (str).

    Raises:
        No exceptions propagate — all errors are caught and returned
        as user-facing messages or fallback responses.
    """
    pattern_result = try_pattern_fallback(message, user_id, db_conn)
    if pattern_result:
        logger.info(f"Pattern fallback matched for: {message[:50]}")
        # Simulate human-like typing delay for UX consistency
        delay = random.uniform(5, 15)
        logger.info(f"Adding {delay:.1f}s delay for UX consistency")
        await asyncio.sleep(delay)
        return pattern_result

    # Merge temporal context from frontend audit state with existing params
    if temporal_context:
        since_date = _validate_date(temporal_context.get("since", since_date), "earliest")
        until_date = _validate_date(temporal_context.get("until", until_date), "present")
        since_date_source = temporal_context.get("source", "system")
        until_date_source = temporal_context.get("source", "system")
    else:
        since_date = _validate_date(since_date, "earliest")
        until_date = _validate_date(until_date, "present")
        since_date_source = "system default"
        until_date_source = "system default"

    history = _validate_history(history, max_length=20)

    # Inject current date and audit window into the system prompt
    current_date = datetime.utcnow().strftime("%Y-%m-%d")
    prompt = SYSTEM_PROMPT.replace('{ALLOWED_CATEGORIES}', str(ALLOWED_CATEGORIES)).format(
        since_date=since_date,
        until_date=until_date,
        since_date_source=since_date_source,
        until_date_source=until_date_source,
        current_date=current_date
    )
    messages = [{"role": "system", "content": prompt}, *history, {"role": "user", "content": sanitize_user_input(message)}]
    tool_calls_made = []
    last_tool_result = None
    last_tool_name = None
    preview_metadata = None

    def call_llm(client, model, msgs):
        """Thin wrapper around chat completions with fixed params."""
        return client.chat.completions.create(
            model=model, messages=msgs, tools=TOOLS, tool_choice="auto",
            temperature=0.3, max_tokens=1024
        )

    nvidia_fallback = os.getenv("NVIDIA_API_KEY")
    response = None

    try:
        client = get_openrouter_client()
        response = call_llm(client, MODEL_CHAIN, messages)
    except Exception as e:
        logger.warning(f"OpenRouter failed: {e}")
        if nvidia_fallback:
            nvidia_models = [
                "meta/llama-3.1-8b-instruct",       # Fast, reliable, free
                "meta/llama-3.1-70b-instruct",      # Smarter, slightly slower
                "mistralai/mistral-7b-instruct-v0.3" # Good backup
            ]
            
            client = get_nvidia_client()
            response = None # Reset response for the fallback loop
            
            for model in nvidia_models:
                try:
                    response = call_llm(client, model, messages)
                    model_used = f"nvidia:{model}"
                    logger.info(f"Successfully used NVIDIA model: {model}")
                    break # Stop trying if one works
                except Exception as e2:
                    logger.warning(f"NVIDIA model {model} failed: {e2}")
                    response = None
                    continue
            
            if response is None:
                logger.error("All NVIDIA fallback models failed.")

    if response is None:
        return {
            "response": "I'm experiencing technical difficulties. Please try again in a moment.",
            "tool_calls_made": [],
            "model_used": "error"
        }
    model_used = response.model

    # Iterative tool-calling loop: max 5 rounds to prevent runaway tool loops
    for _ in range(5):
        if response.choices[0].finish_reason != "tool_calls":
            break

        assistant_msg = response.choices[0].message
        messages.append({"role": "assistant", "content": assistant_msg.content or "", "tool_calls": assistant_msg.tool_calls})

        for tool_call in assistant_msg.tool_calls:
            tool_name = tool_call.function.name
            tool_args = json.loads(tool_call.function.arguments or "{}")
            tool_calls_made.append({"tool": tool_name, "args": tool_args})

            result = execute_tool(tool_name, tool_args, user_id, db_conn, is_local)
            last_tool_result = result
            last_tool_name = tool_name

            if tool_name == "preview_bulk_update":
                try:
                    preview_data = json.loads(result)
                    if preview_data.get("success") and preview_data.get("preview_id"):
                        preview_metadata = {
                            "preview_id": preview_data["preview_id"],
                            "query": tool_args.get("query", ""),
                            "new_narration": tool_args.get("new_narration", ""),
                            "new_category": tool_args.get("new_category", ""),
                            "count": preview_data.get("count", 0),
                            "matched_count": preview_data.get("matched_count", 0),
                            "matches": preview_data.get("matches", [])
                        }
                except json.JSONDecodeError:
                    pass

            # SECURITY: Prevent context window overflow from massive tool results
            if len(result) > 8000:
                logger.warning(f"Tool {tool_name} result too large ({len(result)} chars), truncating")
                result = result[:8000] + "\n... [truncated]"

            messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": result})

        try:
            response = call_llm(client, MODEL_CHAIN, messages)
        except Exception as e:
            # LLM failed after tool calls — use fallback formatter instead of erroring out
            logger.error(f"Final LLM call failed: {e}")
            if last_tool_result:
                logger.info(f"Using fallback formatter for tool: {last_tool_name}")
                fallback_response = format_tool_result_fallback(last_tool_name, last_tool_result)
                return {
                    "response": fallback_response,
                    "tool_calls_made": tool_calls_made,
                    "model_used": f"{model_used}+fallback",
                    "preview_metadata": preview_metadata
                }
            break

    final_response = response.choices[0].message.content if response.choices else None

    # If LLM returned empty content but we have tool data, use fallback
    if not final_response and last_tool_result:
        logger.warning(f"LLM returned empty response, using fallback formatter for tool: {last_tool_name}")
        final_response = format_tool_result_fallback(last_tool_name, last_tool_result)
        model_used = f"{model_used}+fallback"
    elif not final_response:
        final_response = "I couldn't generate a response. Please try again."

    # Strip raw JSON / tool output that smaller LLMs sometimes echo
    if final_response:
        final_response = clean_llm_json(final_response)

    return {
        "response": final_response,
        "tool_calls_made": tool_calls_made,
        "model_used": model_used,
        "preview_metadata": preview_metadata
    }
