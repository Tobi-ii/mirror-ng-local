/**
 * Mirror-NG API Service
 * Centralized HTTP + IndexedDB abstraction layer for the FastAPI backend.
 * - Cloud sync ON:  routes requests to the server with httpOnly cookie auth
 * - Cloud sync OFF: reads/writes browser IndexedDB via localData module
 * - Exports data as CSV with alias enrichment
 */
import { localData } from './localData';

// Empty string → same origin. Served from the same host as the frontend.
const API_BASE = '';

// ── Module-level state ──────────────────────────────────────────────────
// Toggled by App.jsx at login.
// * _cloudSync:  when true, all data methods hit the FastAPI backend
//                when false, they fall back to IndexedDB (localData)
// * _userId:     the active user's MongoDB ObjectId

let _cloudSync = true;   // true = use server, false = use local browser storage
let _userId = null;      // the active user's ID

// ── Module state setters ─────────────────────────────────────────────────
// These are exported so App.jsx can configure this module without passing
// everything down as props.

/**
 * Toggle between cloud-backed and local-only storage mode.
 */
export function setCloudSync(enabled) {
  _cloudSync = enabled;
}

/**
 * Returns whether cloud sync is currently enabled.
 */
export function isCloudSync() {
  return _cloudSync;
}

/**
 * Set the active user ID (called by App.jsx on login/register).
 */
export function setUserId(id) {
  _userId = id;
}

/**
 * Return _userId if set, else fall back to localStorage mirror_user.
 */
function getUserId() {
  if (_userId) return _userId;
  try {
    const user = JSON.parse(localStorage.getItem('mirror_user') || '{}');
    return user.id || null;
  } catch { return null; }
}

/**
 * Thin wrapper around fetch() that sends the httpOnly session cookie
 * and attaches the CSRF token for state-changing requests.
 * credentials: 'include' ensures the cookie is attached even cross-origin.
 */
function getCsrfToken() {
  const match = document.cookie.match(/csrf_token=([^;]+)/);
  return match ? match[1] : null;
}

async function authFetch(url, options = {}) {
  const headers = { ...(options.headers || {}) };
  const method = (options.method || 'GET').toUpperCase();
  const csrf = getCsrfToken();

  if (csrf && method !== 'GET' && method !== 'HEAD' && method !== 'OPTIONS') {
    headers['X-CSRF-Token'] = csrf;
  }

  const res = await fetch(url, { ...options, headers, credentials: 'include' });

  if (res.status === 401) {
    window.dispatchEvent(new CustomEvent('auth:expired'));
    throw new Error('Session expired');
  }

  if (!res.ok) {
    const contentType = res.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      const err = await res.json();
      throw new Error(err.detail || `HTTP ${res.status}`);
    } else {
      const text = await res.text();
      throw new Error(`Server Error ${res.status}: ${text.slice(0, 200)}`);
    }
  }

  return res;
}

// ── API methods ──────────────────────────────────────────────────────────
// Each method follows the same pattern:
//   • If cloud sync is ON  → send the request to the FastAPI backend
//   • If cloud sync is OFF → read/write directly to the browser's IndexedDB
//                             via the localData module
export const api = {
  /**
   * Health check to verify backend connectivity
   */
  health: async () => {
    const res = await authFetch(`${API_BASE}/health`);
    return res.json();
  },

  /**
   * Verify the current session cookie; returns the user object or null.
   */
  authMe: async () => {
    const res = await authFetch(`${API_BASE}/api/auth/me`);
    if (!res.ok) return null;
    return res.json();
  },

  /**
   * Invalidate the server session (POST, no auth wrapper needed).
   */
  logout: async () => {
    await fetch(`${API_BASE}/api/auth/logout`, { method: 'POST', credentials: 'include' });
  },

  /**
   * Update transaction name (cleaned narration)
   */
  updateTransactionName: async (userId, txId, newName) => {
    const res = await authFetch(`/api/transactions/${userId}/${txId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ narration: newName })
    });
    return res.json();
  },

  /**
   * Rename an entire alias group (all transactions with this display name)
   */
  renameAliasGroup: async (userId, oldName, newName, category) => {
    const res = await authFetch(`${API_BASE}/api/aliases/${String(userId)}/rename-group`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ 
        old_name: oldName, 
        new_name: newName, 
        category: category 
      })
    });
    if (!res.ok) throw new Error('Failed to rename alias group');
    return res.json();
  },

  /**
   * Sync transactions from email server; persist to local IndexedDB when offline.
   */
  syncTransactions: async (userId, body) => {
    const res = await authFetch(`${API_BASE}/api/sync`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to sync with mail server' }));
      throw new Error(JSON.stringify(err.detail) || 'Failed to sync with mail server');
    }
    const data = await res.json();
    return data;
  },

  /**
   * Start long-running background sync; returns job_id for polling.
   */
  syncBackground: async (userId, opts = {}) => {
    const res = await authFetch(`${API_BASE}/api/sync/background`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: String(userId),
        since_date: opts.since_date || undefined,
        until_date: opts.until_date || undefined,
        full_sync: opts.full_sync || false,
        opening_balances: opts.opening_balances || [],
      })
    });
    return res.json();
  },

  /**
   * Poll background sync job status by jobId.
   */
  getSyncStatus: async (jobId) => {
    const res = await authFetch(`${API_BASE}/api/sync/status/${String(jobId)}`);
    return res.json();
  },

  /**
   * Record opening balances for session-level reconciliation.
   */
  setInitialBalances: async (userId, balances) => {
    const res = await authFetch(`${API_BASE}/api/set-initial-balances`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: userId, balances })
    });
    return res.json();
  },

  /**
   * Fetch current liquidity (balances per bank account).
   */
  getBalances: async (userId) => {
    const res = await authFetch(`${API_BASE}/api/balances/${String(userId)}`);
    return res.json();
  },

  /**
   * Fetch paginated transactions, optionally filtered by bank.
   */
  getTransactions: async (userId, { limit = 300, offset = 0, bank = null } = {}) => {
    const params = new URLSearchParams({ limit, offset });
    if (bank) params.append('bank', bank);
    const res = await authFetch(`${API_BASE}/api/transactions/${String(userId)}?${params.toString()}`);
    return res.json();
  },

  /**
   * Remove a bank account and its balance from the system.
   */
  deleteBalance: async (userId, bank, accountLast4) => {
    if (!_cloudSync) {
      await localData.deleteBalance(userId, bank);
      return { success: true };
    }
    const res = await authFetch(`${API_BASE}/api/balances/${String(userId)}`, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        bank: bank,
        account_last4: accountLast4
      })
    });
    if (!res.ok) throw new Error('Failed to delete bank account');
    return res.json();
  },

  /**
   * Override a bank's current balance (manual correction or anchor).
   */
  adjustBalance: async (userId, bank, accountLast4, newBalance, reason) => {
    if (!_cloudSync) {
      await localData.adjustBalance(userId, bank, parseFloat(newBalance));
      return { success: true };
    }
    const res = await authFetch(`${API_BASE}/api/manual-adjust-balance`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: String(userId),
        bank,
        account_last4: accountLast4,
        new_balance: newBalance,
        reason
      })
    });
    return res.json();
  },

  /**
   * Detect banks that appear in transactions but have no balance anchor yet.
   */
  getOnboardingGaps: async (userId) => {
    if (!_cloudSync) {
      return { success: true, gaps: [], total_accounts: 0 };
    }
    const res = await authFetch(`${API_BASE}/api/onboarding-gaps/${String(userId)}`);
    return res.json();
  },

  /**
   * Submit anchor balances and account_last4 for banks missing them.
   */
  resolveOnboardingGaps: async (userId, resolutions) => {
    if (!_cloudSync) {
      for (const item of resolutions) {
        if (item.anchor_balance !== null && item.anchor_balance !== undefined) {
          await localData.adjustBalance(userId, item.bank, parseFloat(item.anchor_balance));
        }
      }
      return { success: true };
    }
    const res = await authFetch(`${API_BASE}/api/onboarding-gaps/${String(userId)}/resolve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ resolutions })
    });
    return res.json();
  },

  /**
   * Financial insights: anomaly detection and spending forecast.
   */
  getInsights: async (userId) => {
    if (!_cloudSync) {
      const txs = await localData.getTransactions(userId);
      if (txs.length < 2) return { success: true, anomalies: [], forecast: { forecast: [], trend: 'insufficient_data', daily_avg: 0, weekly_projection: 0 }, message: 'Insufficient data for insights' };

      // ── Local forecasting (runs in the browser, no LLM needed) ──
      // Daily debit aggregation and linear regression forecast
      const daily = {};
      txs.forEach(tx => {
        if (tx.tx_type !== 'debit') return;
        const date = tx.timestamp?.slice(0, 10);
        if (!date) return;
        daily[date] = (daily[date] || 0) + Number(tx.amount);
      });

      const dates = Object.keys(daily).sort();
      if (dates.length < 2) return { success: true, anomalies: [], forecast: { forecast: [], trend: 'insufficient_data', daily_avg: 0, weekly_projection: 0 } };

      // Simple linear regression: predict future spend based on past daily totals
      // x = days since first transaction, y = total debit amount for that day
      const base = new Date(dates[0]);
      const X = dates.map(d => (new Date(d) - base) / 86400000);
      const y = dates.map(d => daily[d]);
      const xMean = X.reduce((a, b) => a + b, 0) / X.length;
      const yMean = y.reduce((a, b) => a + b, 0) / y.length;
      const num = X.reduce((s, x, i) => s + (x - xMean) * (y[i] - yMean), 0);
      const den = X.reduce((s, x) => s + (x - xMean) ** 2, 0) + 1e-8;
      const slope = num / den;
      const intercept = yMean - slope * xMean;
      const lastX = X[X.length - 1];
      const lastDate = new Date(dates[dates.length - 1]);
      const floor = yMean * 0.1;
      const forecast = [];
      for (let i = 1; i <= 7; i++) {
        const dayX = lastX + i;
        const predicted = Math.max(floor, slope * dayX + intercept);
        const d = new Date(lastDate);
        d.setDate(d.getDate() + i);
        forecast.push({ date: d.toISOString().slice(0, 10), predicted_spend: Math.round(predicted * 100) / 100 });
      }

      const forecastObj = {
        forecast,
        trend: slope > 100 ? 'increasing' : slope < -100 ? 'decreasing' : 'stable',
        daily_avg: Math.round(yMean * 100) / 100,
        weekly_projection: Math.round(forecast.reduce((s, f) => s + f.predicted_spend, 0) * 100) / 100,
      };

      // ── Anomaly detection via Z-score ──
      // For each category, calculate how many standard deviations a transaction
      // is from the mean. If Z > 2.0, flag it as unusual.
      const byCategory = {};
      txs.forEach(tx => {
        if (tx.tx_type !== 'debit') return;
        const cat = tx.category || 'General';
        if (!byCategory[cat]) byCategory[cat] = [];
        byCategory[cat].push(Number(tx.amount));
      });
      const stats = {};
      Object.keys(byCategory).forEach(cat => {
        const amts = byCategory[cat];
        if (amts.length < 2) return;
        const mean = amts.reduce((a, b) => a + b, 0) / amts.length;
        const std = Math.sqrt(amts.reduce((s, a) => s + (a - mean) ** 2, 0) / amts.length);
        stats[cat] = { mean, std };
      });
      const anomalies = [];
      txs.forEach(tx => {
        if (tx.tx_type !== 'debit') return;
        const cat = tx.category || 'General';
        if (!stats[cat] || stats[cat].std === 0) return;
        const amount = Number(tx.amount);
        const z = Math.abs(amount - stats[cat].mean) / stats[cat].std;
        if (z > 2.0) {
          anomalies.push({ ...tx, is_anomaly: true, anomaly_reason: `Unusually high ${cat} spend — ₦${amount.toLocaleString('en-NG')} vs avg ₦${Math.round(stats[cat].mean).toLocaleString('en-NG')}` });
        }
      });

      return { success: true, anomalies, forecast: forecastObj, stats: { total_anomalies: anomalies.length, total_analyzed: txs.length } };
    }
    const res = await authFetch(`${API_BASE}/api/insights/${String(userId)}`);
    if (!res.ok) throw new Error('Failed to fetch insights');
    return res.json();
  },

  /**
   * Agent v1: tool-based LLM chat with transaction context.
   */
  chat: async (userId, message, history = [], sinceDate, untilDate) => {
    const body = { user_id: String(userId), message, history };
    if (sinceDate) body.since_date = sinceDate;
    if (untilDate) body.until_date = untilDate;
    if (!_cloudSync) {
      const txs = await localData.getTransactions(userId);
      body.local_transactions = txs;
    }
    const res = await authFetch(`${API_BASE}/api/agent/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    if (!res.ok) throw new Error('Agent failed to respond');
    return res.json();
  },

  /**
   * Agent v2: structured intent routing — reduces hallucination risk.
   */
  chatV2: async (userId, message, history = [], sinceDate, untilDate) => {
    const body = { user_id: String(userId), message, history };
    if (sinceDate) body.since_date = sinceDate;
    if (untilDate) body.until_date = untilDate;
    if (!_cloudSync) {
      const txs = await localData.getTransactions(userId);
      body.local_transactions = txs;
    }
    const res = await authFetch(`${API_BASE}/api/agent/chat-v2`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    if (!res.ok) throw new Error('Agent V2 failed to respond');
    return res.json();
  },

  /**
   * Fetch all user-defined recipient→display-name alias mappings.
   */
  getAliases: async (userId) => {
    if (!_cloudSync) {
      const aliases = await localData.getAliases(userId);
      return { success: true, aliases };
    }
    const res = await authFetch(`${API_BASE}/api/aliases/${String(userId)}`);
    return res.json();
  },

  /**
   * Create or update an alias (upsert on recipient_pattern match).
   */
  saveAlias: async (userId, data) => {
    if (!_cloudSync) {
      const aliases = await localData.getAliases(userId);
      const existingIdx = aliases.findIndex(a => a.recipient_pattern === data.recipient_pattern);
      if (existingIdx >= 0) {
        aliases[existingIdx] = { ...aliases[existingIdx], display_name: data.display_name, category: data.category || 'General' };
        if (data.exact_match !== undefined) aliases[existingIdx].exact_match = data.exact_match;
        await localData.saveAliases(userId, aliases);
        return { success: true, alias: aliases[existingIdx] };
      }
      const newAlias = { id: Date.now(), ...data };
      if (!data.exact_match) delete newAlias.exact_match;
      aliases.push(newAlias);
      await localData.saveAliases(userId, aliases);
      return { success: true, alias: newAlias };
    }
    const res = await authFetch(`${API_BASE}/api/aliases/${String(userId)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        recipient_pattern: data.recipient_pattern,
        display_name: data.display_name,
        category: data.category || 'General',
        exact_match: data.exact_match !== undefined ? data.exact_match : false
      })
    });
    if (!res.ok) throw new Error('Failed to save alias');
    return res.json();
  },

  /**
   * Delete a transaction alias by its id.
   */
  deleteAlias: async (userId, aliasId) => {
    if (!_cloudSync) {
      await localData.deleteAlias(userId, aliasId);
      return { success: true };
    }
    const res = await authFetch(`${API_BASE}/api/aliases/${String(userId)}/${aliasId}`, {
      method: 'DELETE'
    });
    if (!res.ok) throw new Error('Failed to delete alias');
    return res.json();
  },

  /**
   * Remove a single transaction from its alias (revert to original narration).
   */
  removeTransactionFromAlias: async (userId, transactionId, category) => {
    let url = `${API_BASE}/api/aliases/${String(userId)}/transaction/${transactionId}`;
    if (category) url += `?category=${encodeURIComponent(category)}`;
    const res = await authFetch(url, {
      method: 'DELETE'
    });
    if (!res.ok) throw new Error('Failed to remove transaction from alias');
    return res.json();
  },

  /**
   * Wipe all local transactions, balances, and aliases for a user.
   */
  clearUserData: async (userId) => {
    await localData.clearUser(userId);
    return { success: true };
  },

  /**
   * Request ML-generated alias suggestions from the server,
   * or fall back to local keyword grouping if offline or the request fails.
   */
  generateAliasSuggestions: async (userId, narrations) => {
    try {
      if (!_cloudSync) {
        return { success: true, suggestions: generateLocalSuggestions(narrations) };
      }
      const res = await authFetch(`${API_BASE}/api/ai/suggest-aliases`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          user_id: String(userId), 
          narrations: narrations.slice(0, 50)
        })
      });
      
      if (!res.ok) {
        console.warn('AI suggestions failed, falling back to local grouping');
        return { success: true, suggestions: generateLocalSuggestions(narrations) };
      }
      
      return await res.json();
    } catch (error) {
      console.error('AI suggestion error:', error);
      return { success: true, suggestions: generateLocalSuggestions(narrations) };
    }
  },

  /**
   * Import multiple aliases at once (migration or batch onboarding).
   */
  bulkSaveAliases: async (userId, aliases) => {
    if (!_cloudSync) {
      const existing = await localData.getAliases(userId);
      const merged = [...existing, ...aliases.map(a => ({ id: Date.now() + Math.random(), ...a }))];
      await localData.saveAliases(userId, merged);
      return { success: true };
    }
    const res = await authFetch(`${API_BASE}/api/aliases/${String(userId)}/bulk`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ aliases })
    });
    if (!res.ok) throw new Error('Failed to bulk save aliases');
    return res.json();
  },

  /**
   * Ask the ML service to categorise a batch of transaction IDs.
   */
  categorizeTransactions: async (userId, transactionIds) => {
    const res = await authFetch(`${API_BASE}/api/ai/categorize`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ 
        user_id: String(userId), 
        transaction_ids: transactionIds 
      })
    });
    if (!res.ok) throw new Error('Failed to categorize transactions');
    return res.json();
  },

  // ── Cloud sync management ──────────────────────────────────────

  /**
   * Read the user's cloud sync preference from the server.
   */
  getCloudSync: async (userId) => {
    const res = await authFetch(`${API_BASE}/api/cloud-sync/${String(userId)}`);
    return res.json();
  },

  /**
   * Update the user's cloud sync preference on the server.
   */
  setCloudSync: async (userId, enabled) => {
    const res = await authFetch(`${API_BASE}/api/cloud-sync/${String(userId)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: String(userId), cloud_sync: enabled })
    });
    return res.json();
  },

  /**
   * Export full user data as a JSON blob.
   */
  exportData: async (userId) => {
    const res = await authFetch(`${API_BASE}/api/data/export/${String(userId)}`);
    return res.json();
  },

  /**
   * Import a previously exported JSON blob to restore user data.
   */
  importData: async (userId, data) => {
    const res = await authFetch(`${API_BASE}/api/data/import/${String(userId)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: String(userId), ...data })
    });
    return res.json();
  }
};

/**
 * Export transactions as a downloadable CSV with alias enrichment.
 * Steps:
 *   1. Match each transaction's narration against alias patterns
 *   2. Build rows with raw + enriched columns
 *   3. Trigger browser download via a temporary <a> element
 * Columns: Date, Bank, Type, Amount, Balance After, Clean Narration,
 *          Original Narration, Category, Aliased Name, Aliased Category
 */
export function exportCSV(transactions, aliases, filename = 'mirror-ng.csv') {
  const esc = (s) => `"${String(s ?? '').replace(/"/g, '""')}"`;

  const rows = transactions.map(tx => {
    const narration = (tx.narration || '').trim();
    const match = aliases.find(a =>
      narration.toLowerCase().includes((a.recipient_pattern || '').toLowerCase())
    );
    return {
      date: tx.timestamp ? tx.timestamp.split('T')[0] : '',
      bank: tx.bank || '',
      tx_type: tx.tx_type || '',
      amount: tx.tx_type === 'credit' ? tx.amount : -(tx.amount || 0),
      balance_after: tx.balance_after ?? '',
      clean_narration: narration,
      original_narration: tx.original_narration || '',
      category: tx.category || '',
      aliased_name: match ? match.display_name : narration,
      aliased_category: match ? (match.category || tx.category || '') : (tx.category || '')
    };
  });

  const header = 'Date,Bank,Type,Amount,Balance After,Clean Narration,Original Narration,Category,Aliased Name,Aliased Category';
  const csv = [header, ...rows.map(r =>
    [esc(r.date), esc(r.bank), esc(r.tx_type), r.amount, r.balance_after,
     esc(r.clean_narration), esc(r.original_narration), esc(r.category),
     esc(r.aliased_name), esc(r.aliased_category)].join(',')
  )].join('\r\n');

  const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/**
 * Fallback suggestion engine that runs entirely in the browser.
 * Uses keyword-based category detection and heuristic display-name cleaning.
 *
 * Category groups: Food, Transport, Data & Airtime, Shopping, Utilities,
 *                  Entertainment, Transfer.
 * Each narration is checked against pattern.keywords; first match wins.
 * Unmatched narrations default to confidence 0.3 and "General" category.
 */
function generateLocalSuggestions(narrations) {
  const suggestions = {};
  
  const patterns = {
    'food': {
      keywords: ['mcdonald', 'kfc', 'domino', 'pizza', 'burger', 'restaurant', 'cafe', 'eatery', 'food', 'chicken'],
      category: 'Food',
      cleanName: (text) => {
        if (text.includes('MCDONALD')) return "McDonald's";
        if (text.includes('KFC')) return "KFC";
        if (text.includes('DOMINO')) return "Domino's Pizza";
        return text.split(' ').slice(0, 2).join(' ');
      }
    },
    'transport': {
      keywords: ['uber', 'bolt', 'taxi', 'transport', 'lagos bus', 'brt', 'train', 'fuel', 'petrol', 'gas station'],
      category: 'Transport',
      cleanName: (text) => {
        if (text.includes('UBER')) return "Uber";
        if (text.includes('BOLT')) return "Bolt";
        if (text.includes('FUEL') || text.includes('PETROL')) return "Fuel Purchase";
        return text.split(' ').slice(0, 2).join(' ');
      }
    },
    'data_airtime': {
      keywords: ['mtn', 'glo', 'airtel', '9mobile', 'airtime', 'data plan', 'internet', 'subscription'],
      category: 'Data & Airtime',
      cleanName: (text) => {
        if (text.includes('MTN')) return "MTN";
        if (text.includes('GLO')) return "GLO";
        if (text.includes('AIRTEL')) return "Airtel";
        return "Data & Airtime";
      }
    },
    'shopping': {
      keywords: ['jumia', 'konga', 'amazon', 'aliexpress', 'shop', 'mall', 'store', 'retail'],
      category: 'Shopping',
      cleanName: (text) => {
        if (text.includes('JUMIA')) return "Jumia";
        if (text.includes('KONGA')) return "Konga";
        return text.split(' ').slice(0, 2).join(' ');
      }
    },
    'utilities': {
      keywords: ['ikeja electric', 'eko electric', 'abuja disco', 'water', 'waste', 'bill', 'utility'],
      category: 'Utilities',
      cleanName: (text) => {
        if (text.includes('IKEJA')) return "Ikeja Electric";
        if (text.includes('WATER')) return "Water Bill";
        return "Utility Bill";
      }
    },
    'entertainment': {
      keywords: ['netflix', 'showmax', 'spotify', 'apple music', 'cinema', 'movie', 'game', 'playstation'],
      category: 'Entertainment',
      cleanName: (text) => {
        if (text.includes('NETFLIX')) return "Netflix";
        if (text.includes('SHOWMAX')) return "Showmax";
        if (text.includes('SPOTIFY')) return "Spotify";
        return text.split(' ').slice(0, 2).join(' ');
      }
    },
    'transfer': {
      keywords: ['transfer to', 'send money', 'payment to', 'credit to'],
      category: 'Transfer',
      cleanName: (text) => {
        const match = text.match(/transfer to (\w+)/i);
        if (match) return `Transfer to ${match[1]}`;
        return "Bank Transfer";
      }
    }
  };

  for (const narration of narrations) {
    const lowerNarration = narration.toLowerCase();
    let suggested = false;
    
    for (const [key, pattern] of Object.entries(patterns)) {
      if (pattern.keywords.some(keyword => lowerNarration.includes(keyword))) {
        suggestions[narration] = {
          display_name: pattern.cleanName(narration),
          category: pattern.category,
          group: pattern.category,
          confidence: 0.7
        };
        suggested = true;
        break;
      }
    }
    
    if (!suggested) {
      const words = narration.split(' ');
      const displayName = words.slice(0, 3).join(' ').substring(0, 30);
      suggestions[narration] = {
        display_name: displayName || "Transaction",
        category: "General",
        group: "General",
        confidence: 0.3
      };
    }
  }
  
  return suggestions;
}
