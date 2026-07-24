"""
models.py — Pydantic models for Mirror.ng API
Defines request/response schemas for FastAPI endpoints.
"""

from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import List, Optional, Literal
from datetime import datetime


# ─────────────────────────────────────────────────────────────────────
# Transaction — normalized transaction model (for API responses)
# ─────────────────────────────────────────────────────────────────────

class Transaction(BaseModel):
    """
    Normalized transaction returned by API endpoints.
    """
    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    bank: str = Field(..., min_length=1)
    tx_type: Literal["credit", "debit", "unknown"]
    amount: float = Field(..., ge=0)  # Core Rust-tier validation replaces manual Python-tier hooks
    balance: Optional[float] = None
    narration: str
    account_last4: Optional[str] = Field(None, min_length=4, max_length=4)
    timestamp: Optional[datetime] = None
    category: str = "other"


class AgentTransactionContext(Transaction):
    """
    Extends the standard Transaction model to ensure the AI agent 
    natively parses anomaly metrics passed from the client or state machine.
    """
    is_anomaly: bool = False
    anomaly_reason: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────
# AccountBalance — for balance endpoints
# ─────────────────────────────────────────────────────────────────────

class AccountBalance(BaseModel):
    """
    Current balance for a single bank account.
    """
    model_config = ConfigDict(from_attributes=True)

    bank: str = Field(..., min_length=1)
    account_last4: str = Field(..., min_length=4, max_length=4)
    balance: float
    last_updated: Optional[datetime] = None
    is_anchor: bool = True


# ─────────────────────────────────────────────────────────────────────
# Request Models — what the API accepts
# ─────────────────────────────────────────────────────────────────────

class OpeningBalanceItem(BaseModel):
    """Single opening balance entry submitted during session audit"""
    bank: str = Field(..., min_length=1)
    account_last4: str = Field(..., min_length=1, max_length=4)
    balance: float = Field(..., ge=0)


class SyncRequest(BaseModel):
    """Request body for POST /api/sync"""
    user_id: str = Field(..., min_length=1, max_length=100)
    password: Optional[str] = None
    since_date: Optional[str] = None
    until_date: Optional[str] = None
    full_sync: bool = False
    opening_balances: List[OpeningBalanceItem] = []
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_id": "user_12345",
                "since_date": "2026-04-04",
                "until_date": "2026-05-04"
            }
        }
    )


class InitialBalanceItem(BaseModel):
    """
    Sub-model providing isolation, validation, and truncation 
    for accounts inside InitialBalanceRequest without data mutation side-effects.
    """
    bank: str = Field(..., min_length=1)
    account_last4: str
    balance: float = Field(..., ge=0)

    @field_validator('account_last4', mode='before')
    @classmethod
    def truncate_to_last_four(cls, v):
        if v is None:
            raise ValueError('account_last4 is required')
        val_str = str(v).strip()
        if len(val_str) < 4:
            raise ValueError('account_last4 must have at least 4 characters')
        return val_str[-4:]


class InitialBalanceRequest(BaseModel):
    """
    Request body for POST /api/set-initial-balances
    """
    user_id: str = Field(..., min_length=1, max_length=100)
    balances: List[InitialBalanceItem] = Field(..., min_length=1)


class ManualAdjustRequest(BaseModel):
    """Request body for POST /api/manual-adjust-balance"""
    user_id: str = Field(..., min_length=1, max_length=100)
    bank: str = Field(..., min_length=1)
    account_last4: str = Field(..., min_length=4, max_length=4)
    new_balance: float = Field(..., ge=0)
    reason: Optional[str] = Field(None, max_length=200)


# ─────────────────────────────────────────────────────────────────────
# Response Models — what the API returns
# ─────────────────────────────────────────────────────────────────────

class SyncResponse(BaseModel):
    user_id: str
    success: bool = True
    new_transactions: List[Transaction]
    balances: List[AccountBalance]
    total_synced: int
    parse_errors: int
    synced_at: datetime


class BalanceResponse(BaseModel):
    success: bool = True
    balances: List[AccountBalance]
    total_accounts: int


class TransactionResponse(BaseModel):
    success: bool = True
    transactions: List[Transaction]
    count: int
    has_more: bool


# ─────────────────────────────────────────────────────────────────────
# Cloud Sync / Data Migration Models
# ─────────────────────────────────────────────────────────────────────

class AliasRequest(BaseModel):
    """Request body for POST /api/aliases/{user_id}"""
    recipient_pattern: str = Field(..., min_length=1, max_length=500)
    display_name: str = Field(..., min_length=1, max_length=200)
    category: str = Field(default="General", max_length=100)
    exact_match: bool = False


class CloudSyncToggle(BaseModel):
    user_id: str
    cloud_sync: bool


class DataExportResponse(BaseModel):
    success: bool = True
    transactions: List[Transaction]
    balances: List[AccountBalance]
    aliases: List[dict]


class DataImportRequest(BaseModel):
    user_id: str
    transactions: List[dict] = []
    balances: List[dict] = []
    aliases: List[dict] = []


class ErrorResponse(BaseModel):
    success: bool = False
    detail: str
    error_code: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────
# Agent / AI Models — Added for ML Insights
# ─────────────────────────────────────────────────────────────────────

class AgentChatRequest(BaseModel):
    """
    Request body for AI-driven financial insights chat.
    """
    user_id: str
    message: str = Field(..., min_length=1, max_length=4000)
    history: List[dict] = []
    local_transactions: List[AgentTransactionContext] = []  # Hardened typing tracks anomaly layer structures
    since_date: Optional[str] = None
    until_date: Optional[str] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_id": "user_12345",
                "message": "What is my biggest expense this month?",
                "history": []
            }
        }
    )


class OnboardingDatesRequest(BaseModel):
    """
    Request body for setting the user's onboarding audit window.
    These dates serve as the fallback temporal anchor for the AI agent
    whenever explicit viewport dates are not provided.
    """
    user_id: str
    start_date: str  # YYYY-MM-DD
    end_date: str    # YYYY-MM-DD
