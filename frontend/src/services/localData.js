// localData.js — Reads and writes user data (transactions, balances, aliases)
// using the browser's built-in IndexedDB. Used when cloud sync is OFF.
// Think of it like a pocket database that lives in your browser.

const DB_NAME = 'mirror-ng';
const DB_VERSION = 1;

// Opens (or creates) the IndexedDB database.
// This is the low-level setup — it runs once when the app first needs storage.
function openDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = (e) => {
      // First visit? Create the "data" store (like a table).
      const db = e.target.result;
      if (!db.objectStoreNames.contains('data')) {
        db.createObjectStore('data');
      }
    };
    req.onsuccess = (e) => resolve(e.target.result);
    req.onerror = (e) => reject(e.target.error);
  });
}

// Read a value from IndexedDB by its key
async function get(key) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction('data', 'readonly');
    const req = tx.objectStore('data').get(key);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

// Write (upsert) a value to IndexedDB
async function set(key, value) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction('data', 'readwrite');
    tx.objectStore('data').put(value, key);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

// Delete a single entry from IndexedDB by key
async function del(key) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction('data', 'readwrite');
    tx.objectStore('data').delete(key);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

// Build a namespaced key like "txn_42" so different users' data doesn't collide
function pfx(userId, type) {
  return `${type}_${userId}`;
}

export const localData = {
  // Save transactions for a user, avoiding duplicates
  // A "duplicate" means same bank, amount, and timestamp
  async saveTransactions(userId, txs) {
    const existing = await this.getTransactions(userId) || [];
    const merged = [...existing];
    for (const tx of txs) {
      const idx = merged.findIndex(
        e => e.bank === tx.bank && e.amount === tx.amount && e.timestamp === tx.timestamp
      );
      if (idx >= 0) merged[idx] = tx;
      else merged.push(tx);
    }
    await set(pfx(userId, 'txn'), merged);
    return merged;
  },

  // Get all transactions for a user (returns empty array if none)
  async getTransactions(userId) {
    return (await get(pfx(userId, 'txn'))) || [];
  },

  // Save or update balances. If a bank already exists, update it; otherwise add a new entry.
  async saveBalances(userId, bals) {
    const existing = await this.getBalances(userId) || [];
    for (const b of bals) {
      const idx = existing.findIndex(e => e.bank === b.bank);
      if (idx >= 0) existing[idx] = b;
      else existing.push(b);
    }
    await set(pfx(userId, 'bal'), existing);
    return existing;
  },

  // Get all saved balances for a user
  async getBalances(userId) {
    return (await get(pfx(userId, 'bal'))) || [];
  },

  // Remove a balance entry for a specific bank
  async deleteBalance(userId, bank) {
    const bals = await this.getBalances(userId);
    const filtered = bals.filter(b => b.bank !== bank);
    await set(pfx(userId, 'bal'), filtered);
    return filtered;
  },

  // Manually set a bank's balance. Creates a new entry if it doesn't exist yet.
  async adjustBalance(userId, bank, newBalance) {
    const bals = await this.getBalances(userId);
    const idx = bals.findIndex(b => b.bank === bank);
    if (idx >= 0) bals[idx].balance = newBalance;
    else bals.push({ bank, account_last4: '0000', balance: newBalance, last_updated: new Date().toISOString(), is_anchor: true });
    await set(pfx(userId, 'bal'), bals);
    return bals;
  },

  // Overwrite all aliases for a user
  async saveAliases(userId, aliases) {
    await set(pfx(userId, 'alias'), aliases);
    return aliases;
  },

  // Get all saved aliases for a user
  async getAliases(userId) {
    return (await get(pfx(userId, 'alias'))) || [];
  },

  // Remove a single alias by its unique ID
  async deleteAlias(userId, aliasId) {
    const aliases = await this.getAliases(userId);
    const filtered = aliases.filter(a => a.id !== aliasId);
    await set(pfx(userId, 'alias'), filtered);
    return filtered;
  },

  // Export all user data (transactions + balances + aliases) as one object
  async getExport(userId) {
    const transactions = await this.getTransactions(userId);
    const balances = await this.getBalances(userId);
    const aliases = await this.getAliases(userId);
    return { transactions, balances, aliases };
  },

  // Bulk-import data. Used when migrating from cloud to local storage.
  async importData(userId, { transactions, balances, aliases }) {
    if (transactions) await set(pfx(userId, 'txn'), transactions);
    if (balances) await set(pfx(userId, 'bal'), balances);
    if (aliases) await set(pfx(userId, 'alias'), aliases);
  },

  // Wipe all of a user's data from IndexedDB (used before importing fresh data)
  async clearUser(userId) {
    await del(pfx(userId, 'txn'));
    await del(pfx(userId, 'bal'));
    await del(pfx(userId, 'alias'));
  }
};
