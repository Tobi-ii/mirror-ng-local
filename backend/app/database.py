"""
database.py — SQLite connection management and schema initialization
for Mirror.ng.

Assumes single-writer semantics; check_same_thread=False is used to
allow the same connection to be shared across FastAPI async handlers.
Foreign keys are enforced at the application layer rather than via
PRAGMA foreign_keys = ON (not set here) — be aware that SQLite does
not enforce FK constraints by default.

Schema migration is performed inline on every app startup via ALTER
TABLE ... ADD COLUMN wrapped in try/except for idempotency.
"""
import sqlite3
import os
import logging
from typing import Optional, List, Dict
from datetime import datetime

logger = logging.getLogger(__name__)

# Default DB lives one directory up from this file, overridable via env
DB_PATH = os.environ.get('DB_PATH', os.path.join(os.path.dirname(__file__), '..', 'mirror.db'))


def get_db() -> sqlite3.Connection:
    """Open a new SQLite connection with dict-like row access.

    Returns:
        sqlite3.Connection with Row factory enabled.

    Note:
        check_same_thread=False relaxes safety so the connection can
        be passed across async tasks.  The caller is responsible for
        ensuring only one writer accesses the connection at a time.
    """
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA cache_size=-64000;")
    conn.execute("PRAGMA temp_store=MEMORY;")
    return conn


def init_db():
    """Create all tables and indexes; apply idempotent schema migrations.

    Safe to call on every startup — all CREATE TABLE / CREATE INDEX
    statements use IF NOT EXISTS.  Post-creation migrations (ALTER TABLE)
    are wrapped in try/except OperationalError so they are no-ops when
    the column already exists.

    Tables created:
        users, transactions, account_balances, account_settings,
        user_aliases, user_prefs
    """
    conn = get_db()

    # ── Users table — Updated with OAuth support ──────────────────
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT UNIQUE,
            email TEXT UNIQUE NOT NULL,
            name TEXT,
            auth_provider TEXT DEFAULT 'yahoo',
            access_token TEXT,
            refresh_token TEXT,
            token_expiry TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_sync_at TIMESTAMP
        )
    ''')

    # Backward-compat: older schema versions may be missing some columns
    try:
        conn.execute('ALTER TABLE users ADD COLUMN auth_provider TEXT DEFAULT "yahoo"')
    except sqlite3.OperationalError:
        pass  # Column already exists

    try:
        conn.execute('ALTER TABLE users ADD COLUMN access_token TEXT')
    except sqlite3.OperationalError:
        pass

    try:
        conn.execute('ALTER TABLE users ADD COLUMN refresh_token TEXT')
    except sqlite3.OperationalError:
        pass

    try:
        conn.execute('ALTER TABLE users ADD COLUMN token_expiry TEXT')
    except sqlite3.OperationalError:
        pass

    try:
        conn.execute('ALTER TABLE users ADD COLUMN id INTEGER PRIMARY KEY AUTOINCREMENT')
    except sqlite3.OperationalError:
        pass

    # ── Transactions table ─────────────────────────────────────────
    conn.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            bank TEXT NOT NULL,
            tx_type TEXT NOT NULL,
            amount REAL NOT NULL,
            balance_after REAL,
            narration TEXT,
            original_narration TEXT,
            account_last4 TEXT,
            timestamp TEXT NOT NULL,
            email_received_at TEXT,
            category TEXT DEFAULT 'other',
            raw_email_preview TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )
    ''')

    # ── Account balances table (history of all balance changes) ────
    conn.execute('''
        CREATE TABLE IF NOT EXISTS account_balances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            bank TEXT NOT NULL,
            account_last4 TEXT NOT NULL,
            balance REAL NOT NULL,
            last_updated TEXT NOT NULL,
            transaction_id INTEGER,
            adjustment_reason TEXT,
            is_anchor BOOLEAN DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(user_id),
            FOREIGN KEY(transaction_id) REFERENCES transactions(id)
        )
    ''')

    # ── Account settings (user preferences per bank account) ──────
    conn.execute('''
        CREATE TABLE IF NOT EXISTS account_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            bank TEXT NOT NULL,
            account_last4 TEXT NOT NULL,
            nickname TEXT,
            color_preference TEXT,
            hide_from_total BOOLEAN DEFAULT 0,
            notify_on_large_transaction REAL,
            UNIQUE(user_id, bank, account_last4),
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )
    ''')

    # ── User Aliases (for transaction name mapping) ────────────────
    conn.execute('''
        CREATE TABLE IF NOT EXISTS user_aliases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            recipient_pattern TEXT NOT NULL,
            display_name TEXT NOT NULL,
            category TEXT DEFAULT 'General',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, recipient_pattern)
        )
    ''')

    # ── Token blacklist (revoked JWT on logout) ────────────────────
    conn.execute('''
        CREATE TABLE IF NOT EXISTS token_blacklist (
            jti TEXT PRIMARY KEY,
            blacklisted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL
        )
    ''')
    conn.execute('DELETE FROM token_blacklist WHERE expires_at < datetime("now")')

    # ── Easter egg prize (single-claim) ────────────────────────────
    conn.execute('''
        CREATE TABLE IF NOT EXISTS easter_egg (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            is_active BOOLEAN DEFAULT 0,
            code TEXT,
            claimed_by TEXT,
            claimed_at TIMESTAMP,
            reward_amount REAL DEFAULT 10000.00
        )
    ''')
    conn.execute('INSERT OR IGNORE INTO easter_egg (id, is_active) VALUES (1, 0)')

    # ── Indexes for common query patterns ─────────────────────────
    conn.execute('''
        CREATE INDEX IF NOT EXISTS idx_transactions_user_timestamp
        ON transactions(user_id, timestamp DESC)
    ''')

    conn.execute('''
        CREATE INDEX IF NOT EXISTS idx_transactions_user_category
        ON transactions(user_id, category)
    ''')

    conn.execute('''
        CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_transaction
        ON transactions(user_id, bank, amount, timestamp, narration)
    ''')

    # ── User preferences (cloud sync toggle, etc.) ─────────────────
    conn.execute('''
        CREATE TABLE IF NOT EXISTS user_prefs (
            user_id TEXT PRIMARY KEY,
            cloud_sync INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )
    ''')

    conn.execute('''
        CREATE INDEX IF NOT EXISTS idx_balances_user_account
        ON account_balances(user_id, bank, account_last4, last_updated DESC)
    ''')

    conn.execute('''
        CREATE INDEX IF NOT EXISTS idx_aliases_user_pattern
        ON user_aliases(user_id, recipient_pattern)
    ''')

    # ── Run schema migrations right after creating tables ──────────
    _migrate_users_table(conn)
    _drop_old_email_password_column(conn)
    _add_onboarding_dates_columns(conn)
    _add_cleaned_narration_column(conn)

    conn.commit()
    conn.close()


def _migrate_users_table(conn):
    """Migrate very old users tables that lack the 'id' column.

    Detects the old schema (has user_id but no id), renames the
    existing table, creates the current schema, and copies data.
    This is a one-shot migration for databases that predate the
    auto-increment PK change.
    """
    try:
        cursor = conn.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cursor.fetchall()]

        if 'user_id' in columns and 'id' not in columns:
            conn.execute('ALTER TABLE users RENAME TO users_old')
            conn.execute('''
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT UNIQUE,
                    email TEXT UNIQUE NOT NULL,
                    name TEXT,
                    auth_provider TEXT DEFAULT 'yahoo',
                    access_token TEXT,
                    refresh_token TEXT,
                    token_expiry TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_sync_at TIMESTAMP
                )
            ''')
            conn.execute('''
                INSERT INTO users (user_id, email, name, created_at, last_sync_at)
                SELECT user_id, email, name, created_at, last_sync_at FROM users_old
            ''')
            conn.execute('DROP TABLE users_old')
    except Exception as e:
        logger.warning(f"User table migration skipped: {e}")


def _drop_old_email_password_column(conn):
    """Remove the legacy email_password column if present.

    Credentials are now stored encrypted via Fernet (see auth.py);
    the old plaintext column is dropped to prevent accidental exposure.
    """
    try:
        conn.execute("ALTER TABLE users DROP COLUMN email_password")
    except sqlite3.OperationalError:
        pass  # Column already gone
    except Exception as e:
        logger.warning(f"Column cleanup skipped: {e}")


def _add_cleaned_narration_column(conn):
    """Add cleaned_narration column to preserve readable narration through alias cycles.

    The narration column is overwritten when an alias is applied; this column
    keeps a persistent copy of the cleaned merchant/recipient name so that
    reverting an alias restores a readable name, not the raw bank text.
    Idempotent via try/except on ALTER TABLE ADD COLUMN.
    """
    try:
        conn.execute('ALTER TABLE transactions ADD COLUMN cleaned_narration TEXT')
    except sqlite3.OperationalError:
        pass


def _add_onboarding_dates_columns(conn):
    """Add onboarding audit-window columns to the users table.

    These TEXT columns store the date range the user selected during
    onboarding so the backend knows which historical emails to fetch.
    Idempotent via try/except on ALTER TABLE ADD COLUMN.
    """
    from datetime import datetime
    for col in ['onboarding_start_date', 'onboarding_end_date']:
        try:
            conn.execute(f'ALTER TABLE users ADD COLUMN {col} TEXT')
        except sqlite3.OperationalError:
            pass
