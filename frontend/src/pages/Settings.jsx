// Settings.jsx — The settings panel where users can:
//   • View/edit bank account balances
//   • Manage transaction aliases (name patterns)
//   • Toggle cloud sync on/off
//   • Export/import data
//   • Log out
import { useState, useEffect, useMemo } from 'react';
import { ArrowLeft, Trash2, LogOut, Pencil, Check, X, Cloud, CloudOff, Download, ChevronDown, ChevronRight } from 'lucide-react';
import { api, setCloudSync, isCloudSync, exportCSV } from '../services/api';
import { localData } from '../services/localData';

export function Settings({ userId, onBack, onLogout, transactions, onDataChanged, onCloudSyncChange, onAliasesChanged }) {
  // ── State ─────────────────────────────────────────────────────────────
  const [balances, setBalances] = useState([]);           // bank accounts with their balances
  const [aliases, setAliases] = useState([]);             // user-defined transaction name aliases
  const [loading, setLoading] = useState(true);            // loading data from API
  const [editingBal, setEditingBal] = useState(null);      // index of the balance being edited (or null)
  const [editValue, setEditValue] = useState('');           // new balance value during editing
  const [editLast4, setEditLast4] = useState('');           // last 4 digits during editing
  const [deletingAlias, setDeletingAlias] = useState(null); // alias ID being deleted
  const [clearingAliases, setClearingAliases] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);  // confirm "clear all aliases" dialog
  const [expandedAliasGroups, setExpandedAliasGroups] = useState({}); // which alias groups are expanded
  const toggleAliasExpand = (name) => {
    setExpandedAliasGroups(prev => ({ ...prev, [name]: !prev[name] }));
  };
  const [localTransactions, setLocalTransactions] = useState([]);
  const [removedTxIds, setRemovedTxIds] = useState(new Set());
  const [cloudSync, setCloudSyncLocal] = useState(true);    // current cloud sync state
  const [migrating, setMigrating] = useState(false);        // true during data migration
  const [showMigrateConfirm, setShowMigrateConfirm] = useState(false); // show migration confirmation dialog
  const [migrateDirection, setMigrateDirection] = useState(null); // 'to-local' or 'to-cloud'

  // Helper to format pattern for display in Settings
  const formatPatternForDisplay = (pattern) => {
    if (!pattern) return '';
    if (pattern.startsWith('tx:')) {
      const txId = pattern.substring(3).trim();
      const tx = transactions?.find(t => String(t.id) === txId);
      if (tx) {
        const date = tx.timestamp ? tx.timestamp.split('T')[0] : '';
        const narration = tx.original_narration || tx.narration || '';
        return `${date}|${narration}`;
      }
      return pattern;
    }
    if (pattern.includes('|')) return pattern;
    return pattern;
  };

  // ── Helper function to match alias patterns ─────────────────────
  const matchesCompositePattern = (tx, pattern) => {
    if (!pattern) return false;
    
    // Format 1: "tx:{id}" (Primary - 100% unique)
    if (pattern.startsWith('tx:')) {
      const patternId = pattern.substring(3).trim();
      const txId = String(tx.id || '').trim();
      return txId === patternId;
    }
    
    // Format 2: "YYYY-MM-DD|narration" (Legacy support)
    if (pattern.includes('|')) {
      const pipeIndex = pattern.indexOf('|');
      const patternDate = pattern.substring(0, pipeIndex).trim();
      const patternNarration = pattern.substring(pipeIndex + 1).trim();
      
      const txDate = (tx.timestamp || '').split('T')[0];
      const txNarration = (tx.original_narration || tx.narration || '').trim();
      
      return txDate === patternDate && txNarration === patternNarration;
    }
    
    // Legacy: simple substring match (fallback)
    return (tx.original_narration || tx.narration || '').toLowerCase().includes(pattern.toLowerCase().trim());
  };

  // On mount: fetch all data from the API (balances, aliases, cloud sync preference)
  useEffect(() => {
    Promise.all([
      api.getBalances(userId),
      api.getAliases(userId),
      api.getTransactions(userId, { limit: 1000 }),
      api.getCloudSync(userId)
    ]).then(([balRes, aliasRes, txRes, syncRes]) => {
      setCloudSyncLocal(syncRes?.success ? syncRes.cloud_sync : true);
      let loadedBals = balRes?.success ? balRes.balances : [];

      // ── DEDUPLICATION FIX: Group by bank name, keep only one entry per bank ──
      // If a bank has multiple entries (e.g., OPay with empty last4 AND OPay with 3456),
      // prefer the one with a valid last4 (not empty/0000)
      const bankMap = new Map();
      
      loadedBals.forEach(b => {
        const bank = b.bank;
        const last4 = b.account_last4 || '';
        const isValidLast4 = last4 && last4 !== '0000' && last4.trim() !== '';
        
        if (!bankMap.has(bank)) {
          // First entry for this bank
          bankMap.set(bank, b);
        } else {
          // Bank already exists - check if this entry is better
          const existing = bankMap.get(bank);
          const existingLast4 = existing.account_last4 || '';
          const existingIsValid = existingLast4 && existingLast4 !== '0000' && existingLast4.trim() !== '';
          
          // Prefer entry with valid last4, or higher balance, or more recent timestamp
          if (isValidLast4 && !existingIsValid) {
            bankMap.set(bank, b);
          } else if (isValidLast4 === existingIsValid) {
            // Both have valid (or invalid) last4 - keep the one with higher balance or more recent
            if ((b.balance || 0) > (existing.balance || 0)) {
              bankMap.set(bank, b);
            } else if ((b.balance || 0) === (existing.balance || 0) && 
                       (b.last_updated || '') > (existing.last_updated || '')) {
              bankMap.set(bank, b);
            }
          }
        }
      });
      
      loadedBals = Array.from(bankMap.values());

      // Include banks that have transactions but still need a balance anchor set
      const normLast4 = (v) => (v || '0000');
      const balBankKeys = new Set(loadedBals.map(b => b.bank));
      const latestTxPerBank = {};
      (transactions || []).forEach(t => {
        const bank = t.bank;
        if (!latestTxPerBank[bank] || (t.timestamp || '') > (latestTxPerBank[bank].timestamp || '')) {
          latestTxPerBank[bank] = t;
        }
      });
      Object.values(latestTxPerBank).forEach(tx => {
        const bank = tx.bank;
        if (!balBankKeys.has(bank)) {
          loadedBals.push({
            bank: tx.bank,
            account_last4: normLast4(tx.account_last4),
            balance: 0,
            last_updated: tx.timestamp,
            is_anchor: false,
            provides_balance: false,
            _isUnanchored: true
          });
          balBankKeys.add(bank);
        }
      });

      setBalances(loadedBals);
      if (aliasRes?.success) setAliases(aliasRes.aliases);
      if (txRes?.success) setLocalTransactions(txRes.transactions);
    }).finally(() => setLoading(false));
  }, [userId]);

  // Delete a manually-added bank account balance
  const handleDeleteBalance = async (bank, last4) => {
    await api.deleteBalance(userId, bank, last4);
    const balRes = await api.getBalances(userId);
    if (balRes?.success) setBalances(balRes.balances);
    if (onDataChanged) onDataChanged();
  };

  // Manually adjust a bank's balance (opens an inline input)
  const handleAdjustBalance = async (bank, last4) => {
    await api.adjustBalance(userId, bank, last4 || '0000', parseFloat(editValue), 'user_manual_adjustment');
    const balRes = await api.getBalances(userId);
    if (balRes?.success) setBalances(balRes.balances);
    setEditingBal(null);
    if (onDataChanged) onDataChanged();
  };

  // Delete a single transaction alias
  const handleDeleteAlias = async (aliasId) => {
    await api.deleteAlias(userId, aliasId);
    const aliasRes = await api.getAliases(userId);
    if (aliasRes?.success) setAliases(aliasRes.aliases);
    setDeletingAlias(null);
    if (onDataChanged) onDataChanged();
    // ── FIX: Also refresh transactions so Audit Feed updates immediately ──
    if (onAliasesChanged) onAliasesChanged();
  };

  // Delete every single alias (used after user confirms "Clear All")
  const handleClearAllAliases = async () => {
    setClearingAliases(true);
    for (const a of aliases) {
      try { await api.deleteAlias(userId, a.id); } catch (e) { console.error(e); }
    }
    setAliases([]);
    setClearingAliases(false);
    setConfirmClear(false);
    if (onDataChanged) onDataChanged();
    // ── FIX: Also refresh transactions so Audit Feed updates immediately ──
    if (onAliasesChanged) onAliasesChanged();
  };

  const handleClearAliasGroup = async (aliasName) => {
    if (!confirm(`Clear all ${aliasTxCounts[aliasName] || 0} transactions from "${aliasName}"? This will revert them to their original narration and restore their original category.`)) return;
    const items = aliases.filter(a => (a.display_name || 'Unnamed') === aliasName);
    const txsToClear = (transactions || []).filter(tx => {
      const txNarration = (tx.original_narration || tx.narration || '').toLowerCase();
      return items.some(a => {
        const pattern = (a.recipient_pattern || '').toLowerCase();
        if (!pattern) return false;
        if (a.exact_match === true || a.exact_match === 1) return matchesCompositePattern(tx, a.recipient_pattern);
        return txNarration.includes(pattern);
      });
    });
    for (const alias of items) {
      await api.deleteAlias(userId, alias.id);
    }
    for (const tx of txsToClear) {
      const originalCategory = tx.category || 'Uncategorized';
      await api.removeTransactionFromAlias(userId, tx.id, originalCategory);
    }
    const [txRes, aliasRes] = await Promise.all([
      api.getTransactions(userId, { limit: 1000 }),
      api.getAliases(userId)
    ]);
    if (txRes?.success) setLocalTransactions(txRes.transactions);
    if (aliasRes?.success) setAliases(aliasRes.aliases);
    if (onDataChanged) onDataChanged();
    if (onAliasesChanged) onAliasesChanged();
    setExpandedAliasGroups(prev => ({ ...prev, [aliasName]: false }));
  };

  const handleRemoveTransactionFromAlias = async (transactionId, groupAliases) => {
    const tx = localTransactions.find(t => String(t.id) === String(transactionId));
    const matchingAliases = (groupAliases || []).filter(a => {
      const pattern = (a.recipient_pattern || '').toLowerCase();
      if (!pattern) return false;
      if (a.exact_match === true || a.exact_match === 1) {
        return matchesCompositePattern(tx || { id: transactionId }, a.recipient_pattern);
      }
      const txNarration = (tx?.original_narration || tx?.narration || '').toLowerCase();
      return txNarration.includes(pattern);
    });
    for (const alias of matchingAliases) {
      try { await api.deleteAlias(userId, alias.id); } catch (e) { console.error(e); }
    }
    const res = await api.removeTransactionFromAlias(userId, transactionId);
    if (res.success) {
      setRemovedTxIds(prev => new Set(prev).add(String(transactionId)));
      const [txRes, aliasRes] = await Promise.all([
        api.getTransactions(userId, { limit: 1000 }),
        api.getAliases(userId)
      ]);
      if (txRes?.success) setLocalTransactions(txRes.transactions);
      if (aliasRes?.success) setAliases(aliasRes.aliases);
      if (onDataChanged) onDataChanged();
      if (onAliasesChanged) onAliasesChanged();
    }
  };

  // Toggle cloud sync. Shows a confirmation dialog that explains the migration.
  const handleToggleCloudSync = async () => {
    const newVal = !cloudSync;
    if (newVal) {
      // OFF → ON: upload local data to cloud
      setMigrateDirection('to-cloud');
    } else {
      // ON → OFF: download cloud data to local
      setMigrateDirection('to-local');
    }
    setShowMigrateConfirm(true);
  };

  // Actually perform the data migration after the user confirms.
  // 'to-local'  = download from server → save in IndexedDB
  // 'to-cloud'  = upload from IndexedDB → save on server
  const confirmMigration = async () => {
    setShowMigrateConfirm(false);
    setMigrating(true);
    try {
      if (migrateDirection === 'to-local') {
        // Download from server, then save everything in the browser's IndexedDB
        const exportRes = await api.exportData(userId);
        if (exportRes?.success) {
          await localData.clearUser(userId);
          await localData.importData(userId, {
            transactions: exportRes.transactions || [],
            balances: exportRes.balances || [],
            aliases: exportRes.aliases || []
          });
        }
      } else {
        // Export from local to server
        const localExport = await localData.getExport(userId);
        await api.importData(userId, localExport);
      }

      // Toggle on server
      const res = await api.setCloudSync(userId, migrateDirection === 'to-cloud');
      if (res?.success) {
        setCloudSyncLocal(migrateDirection === 'to-cloud');
        setCloudSync(migrateDirection === 'to-cloud');
        if (onCloudSyncChange) onCloudSyncChange(migrateDirection === 'to-cloud');
      }
    } catch (e) {
      console.error('Migration failed:', e);
    } finally {
      setMigrating(false);
      setMigrateDirection(null);
      // Refresh data
      const [balRes, aliasRes] = await Promise.all([
        api.getBalances(userId),
        api.getAliases(userId)
      ]);
      if (balRes?.success) setBalances(balRes.balances);
      if (aliasRes?.success) setAliases(aliasRes.aliases);
      if (onDataChanged) onDataChanged();
      if (onAliasesChanged) onAliasesChanged();
    }
  };

  const syncedBanks = new Set((transactions || []).map(t => t.bank));
  const _isUnanchored = (b) => b._isUnanchored === true;

  // Categorize a bank account status:
  //   'auto_tracked'  — bank sends balances with every alert (no manual input needed)
  //   'anchor_needed' — bank has transactions but no anchor balance set yet
  //   'manual'        — user added this manually
  const getCategory = (b) => {
    // Check if we actually have email transactions for this bank
    const hasTransactions = syncedBanks.has(b.bank);

    // Only auto-tracked if the bank supports it AND we actually have email transactions for it
    if (b.provides_balance && hasTransactions) return 'auto_tracked';

    // If it already has a balance anchor set, treat as manual
    if (b.is_anchor) return 'manual';

    // If it has transactions but no balance anchor set yet
    if (_isUnanchored(b) || hasTransactions) return 'anchor_needed';

    // Otherwise, it's a manually added account (like your GTBank)
    return 'manual';
  };

  const getBadge = (b) => {
    const cat = getCategory(b);
    if (cat === 'auto_tracked')
      return <span className="text-[8px] px-2 py-0.5 bg-emerald-500/10 text-emerald-400 rounded-full font-black uppercase tracking-wider">Balance auto-tracked</span>;
    if (cat === 'anchor_needed')
      return <span className="text-[8px] px-2 py-0.5 bg-amber-500/10 text-amber-400 rounded-full font-black uppercase tracking-wider">Anchor not set</span>;
    return <span className="text-[8px] px-2 py-0.5 bg-indigo-500/10 text-indigo-400 rounded-full font-black uppercase tracking-wider">Manual</span>;
  };

  const fmt = (n) => `₦${Number(n).toLocaleString('en-NG', { minimumFractionDigits: 2 })}`;

  // Count real transaction matches per alias display_name
  // Uses composite pattern matching and respects exact_match flag
  const aliasTxCounts = useMemo(() => {
    const counts = {};
    
    if (!transactions || !aliases) return counts;
    
    // Initialize counts for all aliases
    aliases.forEach(a => {
      const key = a.display_name || 'Unnamed';
      if (!counts[key]) counts[key] = 0;
    });
    
    // Count matching transactions
    transactions.forEach(tx => {
      if (removedTxIds.has(String(tx.id))) return;
      for (const a of aliases) {
        const pattern = a.recipient_pattern || '';
        if (!pattern) continue;
        
        const exactMatch = a.exact_match === true || a.exact_match === 1;
        let matches = false;
        
        if (exactMatch) {
          // Use composite pattern matching
          matches = matchesCompositePattern(tx, pattern);
        } else {
          // Legacy substring match
          const txNarration = (tx.original_narration || tx.narration || '').toLowerCase();
          matches = txNarration.includes(pattern.toLowerCase());
        }
        
        if (matches) {
          const key = a.display_name || 'Unnamed';
          counts[key] = (counts[key] || 0) + 1;
          break; // Only count each transaction once
        }
      }
    });
    
    return counts;
  }, [transactions, aliases]);

  // Show a loader while balances, aliases, and sync preference are loading
  if (loading) {
    return (
      <div className="min-h-screen bg-[#050608] flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-indigo-500/20 border-t-indigo-500 rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#050608] text-white">
      <div className="max-w-4xl mx-auto px-4 sm:px-8 py-6 sm:py-10 space-y-8 sm:space-y-12 pb-40">
        {/* Header: back button, title, logout */}
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 sm:gap-6 min-w-0">
            <button onClick={onBack} className="p-2 sm:p-3 bg-white/5 rounded-xl sm:rounded-2xl hover:bg-white/10 transition-colors shrink-0">
              <ArrowLeft size={18} className="sm:size-[20px] text-slate-400" />
            </button>
            <div className="min-w-0">
              <h1 className="text-xl sm:text-3xl font-black tracking-tighter italic uppercase truncate">Settings</h1>
              <p className="text-[8px] sm:text-[10px] text-slate-500 font-black uppercase tracking-[0.2em] sm:tracking-[0.3em]">Manage your financial mirror</p>
            </div>
          </div>
          <button onClick={onLogout} className="flex items-center gap-1.5 sm:gap-2 px-3 sm:px-6 py-2 sm:py-3 bg-rose-500/10 border border-rose-500/20 rounded-xl sm:rounded-2xl text-rose-400 hover:bg-rose-500/20 transition-all text-[8px] sm:text-[10px] font-black uppercase tracking-widest shrink-0">
            <LogOut size={12} className="sm:size-[14px]" /> <span className="hidden sm:inline">Logout</span><span className="sm:hidden">Out</span>
          </button>
        </div>

        {/* Cloud Sync Toggle: switch between server storage and browser-only storage */}
        <section className="space-y-4">
          <h2 className="text-[10px] font-black uppercase tracking-[0.3em] text-slate-500">Data Sync</h2>
          <div className="bg-[#0a0c10] border border-white/5 rounded-2xl px-4 sm:px-6 py-4 sm:py-5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                {cloudSync ? (
                  <Cloud size={18} className="text-indigo-400" />
                ) : (
                  <CloudOff size={18} className="text-amber-400" />
                )}
                <div>
                  <p className="text-xs sm:text-sm font-bold">{cloudSync ? 'Cloud Sync' : 'Local Only'}</p>
                  <p className="text-[8px] sm:text-[10px] text-slate-500 mt-0.5">
                    {cloudSync
                      ? 'Your data is stored on the server. Accessible from any device.'
                      : 'Your data stays in this browser. Not synced across devices.'}
                  </p>
                </div>
              </div>
              <button
                onClick={handleToggleCloudSync}
                disabled={migrating}
                className={`relative w-12 h-7 sm:w-14 sm:h-8 rounded-full transition-all ${
                  cloudSync ? 'bg-indigo-600' : 'bg-white/10'
                } ${migrating ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
              >
                <div className={`absolute top-0.5 sm:top-1 w-5 h-5 sm:w-6 sm:h-6 bg-white rounded-full shadow-lg transition-all ${
                  cloudSync ? 'left-6 sm:left-7' : 'left-1'
                }`} />
              </button>
            </div>
            {migrating && (
              <div className="mt-3 flex items-center gap-2 text-amber-400 text-[10px] font-black uppercase tracking-wider">
                <div className="w-3 h-3 border-2 border-amber-400/20 border-t-amber-400 rounded-full animate-spin" />
                Migrating data...
              </div>
            )}
          </div>
        </section>

        {/* CSV Export */}
        <div className="bg-[#0a0c10] border border-white/5 rounded-2xl px-4 sm:px-6 py-4 sm:py-5 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Download size={18} className="text-indigo-400" />
            <div>
              <p className="text-xs sm:text-sm font-bold">Export CSV</p>
              <p className="text-[8px] sm:text-[10px] text-slate-500 mt-0.5">
                Download all transactions with alias categories
              </p>
            </div>
          </div>
          <button
            onClick={() => exportCSV(transactions || [], aliases)}
            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-[10px] font-black rounded-xl transition-all uppercase tracking-wider"
          >
            Download
          </button>
        </div>

        {/* Migration Confirmation Modal */}
        {showMigrateConfirm && (
          <div className="fixed inset-0 z-[99] bg-black/80 flex items-center justify-center p-4">
            <div className="bg-[#0a0c10] border border-white/10 rounded-[2rem] p-6 sm:p-8 max-w-md w-full space-y-4">
              <h3 className="text-base sm:text-lg font-black uppercase tracking-wider">
                {migrateDirection === 'to-local' ? 'Download Data?' : 'Upload Data?'}
              </h3>
              <p className="text-xs sm:text-sm text-slate-400 leading-relaxed">
                {migrateDirection === 'to-local'
                  ? 'All your data will be downloaded from the cloud to this device. Server data will be deleted.'
                  : 'All local data on this device will be uploaded to the cloud, replacing any existing server data.'}
              </p>
              <div className="flex gap-3 pt-2">
                <button onClick={() => setShowMigrateConfirm(false)}
                  className="flex-1 py-3 bg-white/5 text-slate-400 text-[10px] font-black rounded-xl hover:bg-white/10 transition-all uppercase tracking-wider">
                  Cancel
                </button>
                <button onClick={confirmMigration}
                  className="flex-1 py-3 bg-indigo-600 text-white text-[10px] font-black rounded-xl hover:bg-indigo-700 transition-all uppercase tracking-wider">
                  Confirm
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Balances: list of all bank accounts with edit/delete controls */}
        <section className="space-y-4">
          <h2 className="text-[10px] font-black uppercase tracking-[0.3em] text-slate-500">Bank Accounts ({balances.length})</h2>
          <div className="space-y-2">
            {balances.length === 0 ? (
              <p className="text-slate-600 text-sm italic py-8 text-center">No accounts configured.</p>
            ) : balances.map((b, i) => {
              const cat = getCategory(b);
              const isAutoTracked = cat === 'auto_tracked';
              const isManual = cat === 'manual';
              return (
              <div key={i} className="flex flex-col sm:flex-row sm:items-center justify-between bg-[#0a0c10] border border-white/5 rounded-2xl px-4 sm:px-6 py-3 sm:py-4 group hover:border-white/10 transition-all gap-2 sm:gap-0">
                <div className="flex items-center gap-3 sm:gap-4 min-w-0">
                  <div className="w-8 h-8 sm:w-10 sm:h-10 rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center shrink-0">
                    <span className="text-indigo-400 font-black text-xs sm:text-sm">{b.bank.charAt(0)}</span>
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5 sm:gap-2 flex-wrap">
                      <p className="text-xs sm:text-sm font-bold truncate">{b.bank}</p>
                      {getBadge(b)}
                    </div>
                    <p className="text-[8px] sm:text-[10px] text-slate-600 font-mono">•••• {b.account_last4}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2 sm:gap-3 ml-11 sm:ml-0">
                  {editingBal === i ? (
                    <div className="flex items-center gap-1.5 sm:gap-2">
                      <input type="text" value={editLast4}
                        onChange={e => setEditLast4(e.target.value.slice(-4))}
                        placeholder="Last 4"
                        maxLength={4}
                        className="w-12 sm:w-14 bg-white/5 border border-white/10 px-2 py-1.5 sm:py-2 rounded-xl text-white text-[10px] sm:text-xs font-mono text-center outline-none focus:border-indigo-500"
                      />
                      <div className="relative">
                        <span className="absolute left-2 sm:left-3 top-1/2 -translate-y-1/2 text-slate-500 text-[10px] sm:text-xs">₦</span>
                        <input type="number" value={editValue}
                          onChange={e => setEditValue(e.target.value)}
                          className="w-20 sm:w-28 bg-white/5 border border-white/10 pl-5 sm:pl-6 pr-2 sm:pr-3 py-1.5 sm:py-2 rounded-xl text-white text-[10px] sm:text-xs font-black outline-none focus:border-indigo-500"
                          autoFocus
                        />
                      </div>
                      <button onClick={() => handleAdjustBalance(b.bank, editLast4 || '0000')}
                        className="p-1.5 sm:p-2 bg-indigo-600 rounded-lg hover:bg-indigo-700 transition-colors">
                        <Check size={10} className="sm:size-[12px]" />
                      </button>
                      <button onClick={() => setEditingBal(null)}
                        className="p-1.5 sm:p-2 bg-white/5 rounded-lg hover:bg-white/10 transition-colors">
                        <X size={10} className="sm:size-[12px]" />
                      </button>
                    </div>
                  ) : (
                    <span className="text-xs sm:text-sm font-black tabular-nums font-mono">{fmt(b.balance)}</span>
                  )}
                  {!isAutoTracked && (
                    <button onClick={() => { setEditingBal(i); setEditValue(b.balance); setEditLast4(b.account_last4 || ''); }}
                      className="opacity-0 group-hover:opacity-100 p-1.5 sm:p-2 hover:bg-white/10 rounded-lg transition-all">
                      <Pencil size={10} className="sm:size-[12px] text-slate-500" />
                    </button>
                  )}
                  {isManual && (
                    <button onClick={() => handleDeleteBalance(b.bank, b.account_last4)}
                      className="opacity-0 group-hover:opacity-100 p-1.5 sm:p-2 hover:bg-rose-500/10 rounded-lg transition-all">
                      <Trash2 size={10} className="sm:size-[12px] text-rose-400" />
                    </button>
                  )}
                </div>
              </div>
              );
            })}
          </div>
        </section>

        {/* Aliases: user-defined names that replace raw bank narration text */}
        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-[10px] font-black uppercase tracking-[0.3em] text-slate-500">
              Transaction Aliases ({aliases.length})
            </h2>
            {aliases.length > 0 && !confirmClear && (
              <button onClick={() => setConfirmClear(true)}
                className="text-[9px] px-3 py-1.5 bg-rose-500/10 border border-rose-500/20 text-rose-400 rounded-lg font-black uppercase tracking-wider hover:bg-rose-500/20 transition-all flex items-center gap-1.5">
                <Trash2 size={10} /> Clear All
              </button>
            )}
            {confirmClear && (
              <div className="flex items-center gap-2">
                <span className="text-[9px] text-rose-400 font-black uppercase tracking-wider">Clear all {aliases.length} aliases?</span>
                <button onClick={handleClearAllAliases} disabled={clearingAliases}
                  className="text-[9px] px-3 py-1.5 bg-rose-600 text-white rounded-lg font-black uppercase tracking-wider hover:bg-rose-700 transition-all">
                  {clearingAliases ? 'Clearing...' : 'Yes'}
                </button>
                <button onClick={() => setConfirmClear(false)}
                  className="p-1.5 hover:bg-white/10 rounded-lg transition-all">
                  <X size={12} className="text-slate-500" />
                </button>
              </div>
            )}
          </div>
          <div className="space-y-2">
            {aliases.length === 0 ? (
              <p className="text-slate-600 text-sm italic py-8 text-center">No aliases defined.</p>
            ) : Object.entries(aliases.reduce((g, a) => {
              const key = a.display_name || 'Unnamed';
              (g[key] = g[key] || []).push(a);
              return g;
            }, {})).map(([name, items]) => {
              const isOpen = expandedAliasGroups[name] ?? false;
              // Find original transactions matching any alias pattern in this group
              const matchedTxs = (localTransactions || []).filter(tx => {
                if (removedTxIds.has(String(tx.id))) return false;
                const txNarration = (tx.original_narration || tx.narration || '').toLowerCase();
                return items.some(a => {
                  const pattern = (a.recipient_pattern || '').toLowerCase();
                  if (!pattern) return false;
                  if (a.exact_match === true || a.exact_match === 1) {
                    return matchesCompositePattern(tx, a.recipient_pattern);
                  }
                  return txNarration.includes(pattern);
                });
              });
              return (
                <div key={name} className="bg-[#0a0c10] border border-white/5 rounded-2xl overflow-hidden">
                  <div
                    onClick={() => toggleAliasExpand(name)}
                    className="flex items-center justify-between px-4 sm:px-6 py-3 sm:py-4 cursor-pointer hover:bg-white/[0.02] transition-colors"
                  >
                    <div className="flex items-center gap-3">
                      <ChevronDown size={16} className={`text-slate-500 transition-transform ${isOpen ? 'rotate-0' : '-rotate-90'}`} />
                      <div>
                        <h3 className="text-white font-bold text-lg">{name}</h3>
                        <div className="flex items-center gap-2 mt-1">
                          <span className="text-sm text-slate-400 font-medium">{aliasTxCounts[name] || 0}</span>
                          <span className="text-slate-600">·</span>
                          <span className="text-xs px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300">
                            {items[0].category || 'General'}
                          </span>
                        </div>
                      </div>
                    </div>
                    <button onClick={(e) => { e.stopPropagation(); handleClearAliasGroup(name); }}
                      className="text-red-400 hover:text-red-300 text-xs px-3 py-1 rounded-lg hover:bg-red-500/10 transition-colors">
                      Clear All
                    </button>
                  </div>
                  {/* Expanded Content */}
                  {isOpen && (
                    <div className="px-4 sm:px-6 pb-3 sm:pb-4 space-y-2">
                      {matchedTxs.length > 0 ? matchedTxs.map((tx, tidx) => (
                        <div key={tidx} className="flex items-center justify-between group/tx p-3 rounded-lg bg-gray-900/50 hover:bg-gray-800/50 transition-colors">
                          <div className="flex-1 min-w-0 mr-3">
                            <p className="text-xs text-gray-300 font-mono truncate">
                              {tx.timestamp?.split('T')[0]} | {tx.original_narration || tx.narration}
                            </p>
                            <div className="flex items-center gap-2 mt-1">
                              <span className="text-xs text-gray-500">
                                ₦{Math.abs(tx.amount || 0).toLocaleString()}
                              </span>
                              <span className="text-xs px-2 py-0.5 rounded bg-gray-700 text-gray-300">
                                {tx.category || 'Uncategorized'}
                              </span>
                            </div>
                          </div>
                          <button
                            onClick={(e) => { e.stopPropagation(); handleRemoveTransactionFromAlias(tx.id, items); }}
                            className="opacity-0 group-hover/tx:opacity-100 transition-opacity p-2 hover:bg-rose-500/20 rounded-lg flex-shrink-0"
                            title="Remove from alias (revert to original)"
                          >
                            <Trash2 size={16} className="text-rose-400 hover:text-rose-300" />
                          </button>
                        </div>
                      )) : (
                        <p className="text-sm text-slate-500 text-center py-4">No transactions currently match this alias</p>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </section>

        {/* Footer */}
        <div className="pt-6 border-t border-white/5 text-center">
          <p className="text-[9px] text-slate-700 font-black uppercase tracking-[0.3em]">
            mirror.ng · Your Financial Mirror
          </p>
        </div>
      </div>
    </div>
  );
}