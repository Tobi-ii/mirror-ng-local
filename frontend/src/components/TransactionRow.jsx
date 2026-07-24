// components/TransactionRow.jsx
import { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { 
  ArrowDownLeft, ArrowUpRight, Pencil, Check, X, Brain, Sparkles, 
  ChevronDown, ChevronRight, CheckCircle2, Layers, Tags, FolderOpen 
} from 'lucide-react';
import { api } from '../services/api';
import { BANK_COLORS, COLOR_OPTIONS } from './BankCard';
import { getMLSuggestion, groupSimilarTransactions } from '../utils/transactionHelpers';

// ==========================================
// UTILITIES & CONFIGURATIONS
// ==========================================

const CATEGORIES = [
  'Transfer', 'Utilities', 'Food', 'Transport', 'Shopping',
  'Entertainment', 'Health', 'Education', 'Fuel', 'Data & Airtime',
  'Family', 'Business', 'General', 'Salary'
];

const CATEGORY_COLORS = {
  Transfer: 'text-indigo-400 bg-indigo-500/10',
  Utilities: 'text-orange-400 bg-orange-500/10',
  Food: 'text-rose-400 bg-rose-500/10',
  Shopping: 'text-pink-400 bg-pink-500/10',
  Salary: 'text-emerald-400 bg-emerald-500/10',
  Transport: 'text-cyan-400 bg-cyan-500/10',
  Entertainment: 'text-purple-400 bg-purple-500/10',
  Health: 'text-red-400 bg-red-500/10',
  Education: 'text-blue-400 bg-blue-500/10',
  Fuel: 'text-yellow-400 bg-yellow-500/10',
  'Data & Airtime': 'text-teal-400 bg-teal-500/10',
  Family: 'text-pink-400 bg-pink-500/10',
  Business: 'text-indigo-400 bg-indigo-500/10',
  General: 'text-slate-500 bg-slate-500/10',
};

const getTxUniqueId = (tx) => {
  if (!tx) return null;
  if (tx.id) return String(tx.id);
  if (tx._id) return String(tx._id);
  if (tx.transaction_id) return String(tx.transaction_id);
  
  const parts = [
    tx.timestamp || '',
    tx.bank || '',
    tx.amount || '',
    tx.tx_type || '',
    tx.account_last4 || '',
    (tx.narration || '').substring(0, 50)
  ];
  return parts.join('|');
};

// FIX: Changed order to use original_narration first
const getUniquePattern = (tx) => {
  if (!tx) return '';
  // Use transaction ID for 100% unique matching (prevents collisions)
  return `tx:${tx.id}`;
};

const getTransactionKey = (tx, idx) => {
  const id = getTxUniqueId(tx);
  if (id) return String(id).replace(/[^a-zA-Z0-9]/g, '-');
  return `tx-${idx}`;
};

// ==========================================
// CUSTOM SELECT DROPDOWN
// ==========================================
function CustomSelect({ value, onChange }) {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef(null);
  useEffect(() => {
    function handleClickOutside(event) {
      if (containerRef.current && !containerRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);
  const currentStyle = CATEGORY_COLORS[value] || CATEGORY_COLORS.General;
  return (
    <div className="relative w-full" ref={containerRef}>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-1.5 text-white text-xs flex items-center justify-between outline-none focus:border-indigo-500 min-h-[32px]"
      >
        <span className={`text-[9px] px-2 py-0.5 rounded-full font-black uppercase tracking-wide ${currentStyle}`}>
          {value}
        </span>
        <ChevronDown size={12} className={`text-slate-400 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>
      {isOpen && (
        <div className="absolute z-50 left-0 right-0 mt-1 bg-zinc-950 border border-white/10 rounded-xl shadow-2xl p-1 max-h-48 overflow-y-auto custom-scrollbar animate-in fade-in slide-in-from-top-1 duration-100">
          {CATEGORIES.map((cat) => {
            const catStyle = CATEGORY_COLORS[cat] || CATEGORY_COLORS.General;
            return (
              <button
                key={cat}
                type="button"
                onClick={() => { onChange(cat); setIsOpen(false); }}
                className={`w-full text-left px-3 py-2 rounded-lg text-xs hover:bg-white/5 transition-colors flex items-center ${
                  value === cat ? 'bg-white/5' : ''
                }`}
              >
                <span className={`text-[8px] px-2 py-0.5 rounded-full font-black uppercase tracking-wide ${catStyle}`}>
                  {cat}
                </span>
                {value === cat && <Check size={10} className="text-indigo-400 ml-auto" />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ==========================================
// TRANSACTION ITEM
// ==========================================
function TransactionItem({ 
  tx, userId, onAliasUpdate, isAliased: initialIsAliased, index, 
  userBankColors = {}, colorOptions = [],
  isBatchMode = false,
  isSelected = false,
  selectionCount = 0,
  onToggleSelect = null,
}) {
  const [isEditing, setIsEditing] = useState(false);
  const [aliasName, setAliasName] = useState(tx?.narration || '');
  const [category, setCategory] = useState(tx?.category || 'General');
  const [isSaving, setIsSaving] = useState(false);
  const [isAliased, setIsAliased] = useState(initialIsAliased);
  const [isHovered, setIsHovered] = useState(false);
  const [saveError, setSaveError] = useState('');

  const txId = getTxUniqueId(tx);

  useEffect(() => {
    if (isSelected && selectionCount === 1 && !isBatchMode) {
      setIsEditing(true);
      setAliasName(tx?.narration || '');
      setCategory(tx?.category || 'General');
    } else {
      setIsEditing(false);
    }
  }, [isSelected, selectionCount, isBatchMode, tx?.narration, tx?.category]);

  useEffect(() => {
    setIsAliased(initialIsAliased);
  }, [initialIsAliased]);

  if (!tx) return null;
  
  const mlSuggestion = !isAliased && tx.tx_type === 'debit' ? getMLSuggestion(tx.original_narration || tx.narration) : null;
  const isCredit = tx.tx_type === 'credit';
  
  const defaultBankTheme = BANK_COLORS[tx.bank] || BANK_COLORS.default;
  const defaultHex = defaultBankTheme.defaultHex;
  const chosenColorIdx = userBankColors?.[tx.bank];
  let activeColor = defaultHex;
  if (chosenColorIdx !== undefined && colorOptions?.[chosenColorIdx]?.hex) {
    activeColor = colorOptions[chosenColorIdx].hex;
  }

  const originalNarration = tx.original_narration || tx.narration;
  const fmt = (n) => new Intl.NumberFormat('en-NG', {
    style: 'currency', currency: 'NGN', minimumFractionDigits: 2
  }).format(Math.abs(n));
  const fmtDate = (s) => {
    if (!s) return '';
    try { return new Date(s).toLocaleDateString('en-NG', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }); } 
    catch (e) { return ''; }
  };
  const catStyle = CATEGORY_COLORS[category] || CATEGORY_COLORS.General;

  const doSaveAlias = async (id, name, cat) => {
    if (!id) {
      console.error('Cannot save alias: no transaction ID', tx);
      setSaveError('Cannot save: no unique identifier');
      setTimeout(() => setSaveError(''), 3000);
      return;
    }
    setIsSaving(true);
    setSaveError('');
    try {
      const pattern = getUniquePattern(tx);
      if (!pattern) {
        setSaveError('Cannot save: no narration');
        setTimeout(() => setSaveError(''), 3000);
        setIsSaving(false);
        return;
      }
      await api.saveAlias(userId, {
        recipient_pattern: pattern,
        display_name: name,
        category: cat,
        exact_match: true
      });
      setIsAliased(true);
      setIsEditing(false);
      if (onAliasUpdate) onAliasUpdate([id]);
    } catch (error) { 
      console.error('Failed to save alias:', error);
      setSaveError('Failed to save alias');
      setTimeout(() => setSaveError(''), 3000);
    } 
    finally { setIsSaving(false); }
  };

  const handleSaveAlias = async (overrideName = null, overrideCat = null) => {
    const name = (overrideName || aliasName).trim();
    const cat = overrideCat || category;
    if (!name) return;
    doSaveAlias(txId, name, cat);
  };

  const handleAcceptSuggestion = () => {
    if (mlSuggestion) {
      setAliasName(mlSuggestion.display_name);
      setCategory(mlSuggestion.category);
      handleSaveAlias(mlSuggestion.display_name, mlSuggestion.category);
    }
  };

  const handleCancelEdit = () => {
    setIsEditing(false);
    setAliasName(tx.narration || '');
    setCategory(tx.category || 'General');
    if (onToggleSelect) onToggleSelect(txId);
  };

  const handlePencilClick = () => {
    if (!isAliased && onToggleSelect) {
      onToggleSelect(txId);
    }
  };

  const hoverBg = `${activeColor}20`;
  
  let rowBg = 'transparent';
  if (isBatchMode && isSelected) {
    rowBg = 'rgba(16, 185, 129, 0.15)';
  } else if (isHovered && !isEditing && !isBatchMode) {
    rowBg = hoverBg;
  }

  const borderColor = (isBatchMode && isSelected) ? '#10b981' : activeColor;
  const dotColor = (isBatchMode && isSelected) ? '#10b981' : activeColor;

  const selectionControl = isBatchMode ? (
    <button
      onClick={() => onToggleSelect && onToggleSelect(txId)}
      className={`p-1.5 rounded-lg transition-all ${isSelected ? 'bg-emerald-500/20' : 'opacity-0 group-hover:opacity-100 hover:bg-white/10'}`}
    >
      {isSelected ? <Check size={12} className="text-emerald-400" /> : <div className="w-3 h-3 border border-emerald-400 rounded-sm" />}
    </button>
  ) : (
    !isAliased && (
      <button onClick={handlePencilClick} className="p-1.5 rounded-lg transition-all opacity-0 group-hover:opacity-100 hover:bg-white/10">
        <Pencil size={12} className="text-slate-400" />
      </button>
    )
  );

  return (
    <div
      className={`flex items-center justify-between px-5 py-5 rounded-r-2xl transition-all group mb-1.5`}
      style={{ 
        animationDelay: `${(index || 0) * 30}ms`,
        borderLeft: `2px solid ${borderColor}`,
        backgroundColor: rowBg
      }}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {isEditing ? (
        <div className="flex-1 flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
          <div className="flex-1 min-w-0">
            <input
              type="text"
              value={aliasName}
              onChange={(e) => { setAliasName(e.target.value); setSaveError(''); }}
              placeholder="Display name..."
              className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-1.5 text-white text-xs outline-none focus:border-indigo-500 min-h-[32px]"
              autoFocus
            />
            <p className="text-[8px] text-slate-600 mt-0.5 truncate font-mono">Original: {originalNarration.slice(0, 40)}...</p>
            {saveError && <p className="text-[9px] text-rose-400 font-bold mt-1 uppercase tracking-wider">{saveError}</p>}
          </div>
          <div className="w-full sm:w-44"><CustomSelect value={category} onChange={setCategory} /></div>
          <div className="flex items-center gap-2 self-end sm:self-auto shrink-0">
            <button onClick={() => handleSaveAlias()} disabled={isSaving || !aliasName.trim()} className="p-1.5 bg-indigo-600 rounded-lg text-white hover:bg-indigo-700 transition-colors disabled:opacity-50"><Check size={12} /></button>
            <button onClick={handleCancelEdit} className="p-1.5 bg-white/5 rounded-lg text-slate-400 hover:bg-white/10 transition-colors"><X size={12} /></button>
          </div>
        </div>
      ) : (
        <>
          <div className="flex items-center gap-3 min-w-0 flex-1">
            <div className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ backgroundColor: dotColor }} />
            <div className={`w-7 h-7 rounded-lg flex-shrink-0 flex items-center justify-center ${isCredit ? defaultBankTheme.creditIcon : defaultBankTheme.debitIcon}`}>
              {isCredit ? <ArrowDownLeft size={14} /> : <ArrowUpRight size={14} />}
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 flex-wrap">
                <p className={`text-xs font-bold truncate ${isAliased ? 'text-indigo-300' : 'text-white'}`}>{tx.narration}</p>
                {isAliased && <span className="text-[7px] px-1 py-0.5 bg-indigo-500/20 text-indigo-400 rounded-full font-black uppercase">aliased</span>}
                {!isAliased && !isEditing && !isBatchMode && tx.category && tx.category !== 'General' && (
                  <span className="text-[7px] px-1 py-0.5 bg-indigo-500/15 text-indigo-400 rounded-full font-black uppercase">
                    ML: {tx.category}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
                <span className={`text-[8px] px-1.5 py-0.5 rounded-full font-black uppercase tracking-wide ${catStyle}`}>{category}</span>
                <span className="text-[8px] text-slate-600 font-mono">{tx.bank} •••• {tx.account_last4}</span>
                <span className="text-[8px] text-slate-700">{fmtDate(tx.timestamp)}</span>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <div className="text-right flex-shrink-0">
              <p className={`font-black text-xs tabular-nums ${isCredit ? 'text-emerald-400' : 'text-white'}`}>{isCredit ? '+' : '-'}{fmt(tx.amount)}</p>
            </div>
            {selectionControl}
          </div>
        </>
      )}
    </div>
  );
}

// ==========================================
// ALIASED CATEGORY GROUP
// ==========================================
function AliasedCategoryGroup({ category, transactions, userId, onAliasUpdate, isExpanded, onToggle, userBankColors, colorOptions }) {
  const [expanded, setExpanded] = useState(isExpanded);
  const toggleExpand = () => { setExpanded(!expanded); if (onToggle) onToggle(!expanded); };
  const catColor = CATEGORY_COLORS[category]?.split(' ')[0] || 'text-slate-400';
  const bgColor = CATEGORY_COLORS[category]?.split(' ')[1] || 'bg-white/5';
  const total = transactions.reduce((sum, tx) => sum + (tx.amount || 0), 0);
  const fmtTotal = (n) => new Intl.NumberFormat('en-NG', {
    style: 'currency', currency: 'NGN', minimumFractionDigits: 0,
  }).format(Math.abs(n));
  const sign = total < 0 ? '-' : '';

  return (
    <div className="mb-4 border border-white/5 rounded-xl overflow-hidden">
      <div className={`px-4 py-2 ${bgColor.replace('bg-', 'bg-opacity-20 bg-') || 'bg-white/5'}`}>
        <button onClick={toggleExpand} className="flex items-center gap-2 w-full text-left">
          {expanded ? <ChevronDown size={14} className="text-slate-400 shrink-0" /> : <ChevronRight size={14} className="text-slate-400 shrink-0" />}
          <FolderOpen size={14} className={`${catColor} shrink-0`} />
          <span className={`text-xs font-black uppercase tracking-wider ${catColor} truncate`}>{category}</span>
          <span className="text-[8px] px-1.5 py-0.5 bg-white/10 rounded-full shrink-0 ml-auto">
            {transactions.length} items · {sign}{fmtTotal(total)}
          </span>
        </button>
      </div>
      {expanded && (
        <div className="p-2 space-y-1">
          {transactions.map((tx, idx) => (
            <TransactionItem
              key={getTransactionKey(tx, idx)}
              tx={tx}
              userId={userId}
              onAliasUpdate={onAliasUpdate}
              isAliased={true}
              index={idx}
              userBankColors={userBankColors}
              colorOptions={colorOptions}
              isBatchMode={false}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ==========================================
// ML GROUPED TRANSACTIONS
// ==========================================
function GroupedTransactionGroup({ group, groupName, userId, onAliasUpdate, isExpanded, onToggle, userBankColors, colorOptions }) {
  const [batchName, setBatchName] = useState(group?.display_name || '');
  const [batchCategory, setBatchCategory] = useState(group?.category || 'General');
  const [isSaving, setIsSaving] = useState(false);
  const [expanded, setExpanded] = useState(isExpanded);
  const [showForm, setShowForm] = useState(false);
  const [batchError, setBatchError] = useState('');
  
  const [selectedIds, setSelectedIds] = useState(new Set());
  const toggleSelection = useCallback((id) => {
    const strId = String(id);
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(strId)) next.delete(strId);
      else next.add(strId);
      return next;
    });
  }, []);

  useEffect(() => {
    const size = selectedIds.size;
    if (size >= 2) setShowForm(true);
    else if (size === 0) setShowForm(false);
  }, [selectedIds]);

  const handleAliasAll = () => {
    if (group.transactions.length === 1) return;
    const allIds = group.transactions.map(tx => String(getTxUniqueId(tx))).filter(Boolean);
    setSelectedIds(new Set(allIds));
    setBatchName(group.display_name || groupName);
    setBatchCategory(group.category || 'General');
    setShowForm(true);
  };

  const handleSaveBatch = async () => {
    if (!batchName.trim()) {
      setBatchError('Please enter a batch name');
      setTimeout(() => setBatchError(''), 3000);
      return;
    }
    setIsSaving(true);
    try {
      const selectedTxs = group.transactions.filter(tx => selectedIds.has(String(getTxUniqueId(tx))));
      if (selectedTxs.length === 0) {
        alert('No transactions selected.');
        setShowForm(false);
        return;
      }

      const results = await Promise.allSettled(
        selectedTxs.map(tx => {
          const pattern = getUniquePattern(tx);
          if (!pattern) return Promise.reject(new Error('No narration'));
          return api.saveAlias(userId, {
            recipient_pattern: pattern,
            display_name: batchName.trim(),
            category: batchCategory,
            exact_match: true
          });
        })
      );

      const savedIds = [];
      results.forEach((result, index) => {
        if (result.status === 'fulfilled') {
          savedIds.push(getTxUniqueId(selectedTxs[index]));
        }
      });

      setShowForm(false);
      setSelectedIds(new Set());
      if (onAliasUpdate && savedIds.length > 0) {
        onAliasUpdate(savedIds);
      }
    } catch (error) {
      console.error('Batch alias error:', error);
      alert('Failed to save batch.');
      setShowForm(false);
    } finally {
      setIsSaving(false);
    }
  };

  const cancelBatch = () => {
    setShowForm(false);
    setSelectedIds(new Set());
  };

  const selectedCount = selectedIds.size;
  const headerButtonLabel = selectedCount > 0 ? `Alias Selected (${selectedCount})` : 'Alias All';

  const handleHeaderButtonClick = () => {
    if (selectedCount > 0) handleSaveBatch();
    else handleAliasAll();
  };

  return (
    <div className="mb-4 border border-white/5 rounded-xl overflow-hidden">
      <div className="bg-gradient-to-r from-indigo-500/10 to-purple-500/10 px-4 py-2 flex items-center justify-between">
        <button onClick={() => setExpanded(!expanded)} className="flex items-center gap-2 flex-1 text-left min-w-0">
          {expanded ? <ChevronDown size={14} className="text-slate-400" /> : <ChevronRight size={14} className="text-slate-400" />}
          <Layers size={14} className="text-indigo-400" />
          <span className="text-xs font-black uppercase tracking-wider text-white truncate">{groupName}</span>
          <span className="text-[8px] px-1.5 py-0.5 bg-white/10 rounded-full">{group.transactions.length} items</span>
        </button>
        <button 
          onClick={handleHeaderButtonClick} 
          className={`text-[8px] px-2 py-1 rounded-lg font-black uppercase transition-colors ${
            selectedCount > 0 ? 'bg-emerald-600/80 text-white hover:bg-emerald-600' : 'bg-indigo-600/60 text-white hover:bg-indigo-600/80'
          }`}
        >
          {headerButtonLabel}
        </button>
      </div>
      {expanded && (
        <div className="p-2 space-y-1">
          {showForm && group.transactions.length > 1 && (
            <div className="flex items-center gap-2 mb-2 bg-zinc-900/60 p-3 rounded-xl border border-white/5 animate-in fade-in duration-100">
              <div className="flex-1 min-w-0">
                <input
                  type="text"
                  value={batchName}
                  onChange={(e) => { setBatchName(e.target.value); setBatchError(''); }}
                  placeholder="Batch Display Name..."
                  className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-1.5 text-white text-xs min-h-[32px] outline-none focus:border-indigo-500"
                />
                {batchError && <p className="text-[9px] text-rose-400 font-bold mt-1.5 uppercase tracking-wider block">{batchError}</p>}
              </div>
              <div className="w-44 shrink-0"><CustomSelect value={batchCategory} onChange={setBatchCategory} /></div>
              <button 
                onClick={handleSaveBatch} 
                disabled={isSaving || selectedCount === 0} 
                className="text-xs px-4 py-1.5 bg-emerald-600 text-white font-black rounded-lg hover:bg-emerald-700 transition-colors shrink-0 disabled:opacity-50"
              >
                {isSaving ? 'Saving...' : 'Save'}
              </button>
              <button 
                onClick={cancelBatch} 
                className="text-xs px-3 py-1.5 bg-white/10 text-slate-300 font-black rounded-lg hover:bg-white/20 transition-colors shrink-0"
              >
                Cancel
              </button>
            </div>
          )}
          {group.transactions.map((tx, idx) => {
            const txId = getTxUniqueId(tx);
            return (
              <TransactionItem
                key={getTransactionKey(tx, idx)}
                tx={tx}
                userId={userId}
                onAliasUpdate={onAliasUpdate}
                isAliased={tx.aliased}
                index={idx}
                userBankColors={userBankColors}
                colorOptions={colorOptions}
                isBatchMode={selectedIds.size >= 2}
                isSelected={txId ? selectedIds.has(String(txId)) : false}
                selectionCount={selectedCount}
                onToggleSelect={toggleSelection}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}

// ==========================================
// MAIN EXPORT – TransactionList
// ==========================================
export default function TransactionList({ 
  transactions = [], userId, onAliasUpdate,
  userBankColors = {}, colorOptions = []    
}) {
  const [expandedGroups, setExpandedGroups] = useState({ aliasedCategories: {}, mlGroups: true, pending: true, credits: true });
  const [flatBatchIds, setFlatBatchIds] = useState(new Set());
  const [flatBatchName, setFlatBatchName] = useState('');
  const [flatBatchCategory, setFlatBatchCategory] = useState('General');
  const [flatBatchError, setFlatBatchError] = useState('');
  const [flatBatchSaving, setFlatBatchSaving] = useState(false);
  const [flatShowForm, setFlatShowForm] = useState(false);
  const [flatSection, setFlatSection] = useState(null);
  
  const [selectedAlias, setSelectedAlias] = useState(null);
  const [editingAliasId, setEditingAliasId] = useState(null);
  const [editAliasName, setEditAliasName] = useState('');
  const [deletingPattern, setDeletingPattern] = useState(null);
  const [editingGroupId, setEditingGroupId] = useState(null);

  useEffect(() => {
    const size = flatBatchIds.size;
    if (size >= 2 && !flatShowForm) {
      const firstId = [...flatBatchIds][0];
      const tx = transactions.find(t => String(getTxUniqueId(t)) === firstId);
      if (tx) {
        setFlatSection(tx.tx_type === 'credit' ? 'credits' : 'pending');
        setFlatShowForm(true);
      }
    } else if (size === 0) {
      setFlatShowForm(false);
      setFlatSection(null);
    }
  }, [flatBatchIds, transactions, flatShowForm]);

  const aliasedByCategory = useMemo(() => {
    const aliased = transactions.filter(tx => tx.aliased === true);
    const grouped = {};
    aliased.forEach(tx => {
      const cat = tx.category || 'General';
      if (!grouped[cat]) grouped[cat] = [];
      grouped[cat].push(tx);
    });
    return grouped;
  }, [transactions]);

  const pendingTransactions = useMemo(() => {
    return transactions.filter(tx => tx.tx_type === 'debit' && !tx.aliased);
  }, [transactions]);

  const mlGroups = useMemo(() => {
    return groupSimilarTransactions(pendingTransactions);
  }, [pendingTransactions]);

  const ungroupedPendingTransactions = useMemo(() => {
    if (!mlGroups.groups || Object.keys(mlGroups.groups).length === 0) {
      return pendingTransactions;
    }
    
    const mlGroupTxIds = new Set();
    Object.values(mlGroups.groups).forEach(group => {
      group.transactions.forEach(tx => {
        const txId = getTxUniqueId(tx);
        if (txId) mlGroupTxIds.add(txId);
      });
    });
    
    return pendingTransactions.filter(tx => {
      const txId = getTxUniqueId(tx);
      return !mlGroupTxIds.has(txId);
    });
  }, [pendingTransactions, mlGroups]);

  const creditTransactions = useMemo(() => {
    return transactions.filter(tx => tx.tx_type === 'credit' && !tx.aliased);
  }, [transactions]);

  const toggleFlatSelection = useCallback((id) => {
    const strId = String(id);
    setFlatBatchIds(prev => {
      const next = new Set(prev);
      if (next.has(strId)) next.delete(strId);
      else next.add(strId);
      return next;
    });
  }, []);

  const handleFlatAliasAll = useCallback((section) => {
    const txs = section === 'pending' ? ungroupedPendingTransactions : creditTransactions;
    const allIds = txs.map(tx => String(getTxUniqueId(tx))).filter(Boolean);
    setFlatBatchIds(new Set(allIds));
    setFlatSection(section);
    setFlatShowForm(true);
  }, [ungroupedPendingTransactions, creditTransactions]);

  const cancelFlatBatch = useCallback(() => {
    setFlatShowForm(false);
    setFlatBatchIds(new Set());
    setFlatSection(null);
  }, []);

  const handleFlatAliasSubmit = useCallback(async () => {
    if (!flatBatchName.trim()) {
      setFlatBatchError('Please enter a batch name');
      setTimeout(() => setFlatBatchError(''), 3000);
      return;
    }
    const txs = flatSection === 'pending' ? ungroupedPendingTransactions : creditTransactions;
    setFlatBatchSaving(true);
    try {
      const selectedTxs = txs.filter(tx => flatBatchIds.has(String(getTxUniqueId(tx))));
      if (selectedTxs.length === 0) {
        alert('No transactions selected.');
        setFlatShowForm(false);
        return;
      }

      const results = await Promise.allSettled(
        selectedTxs.map(tx => {
          const pattern = getUniquePattern(tx);
          if (!pattern) return Promise.reject(new Error('No narration'));
          return api.saveAlias(userId, {
            recipient_pattern: pattern,
            display_name: flatBatchName.trim(),
            category: flatBatchCategory,
            exact_match: true
          });
        })
      );

      const savedIds = [];
      results.forEach((result, index) => {
        if (result.status === 'fulfilled') {
          savedIds.push(getTxUniqueId(selectedTxs[index]));
        }
      });

      setFlatShowForm(false);
      setFlatBatchIds(new Set());
      setFlatSection(null);
      if (onAliasUpdate && savedIds.length > 0) {
        onAliasUpdate(savedIds);
      }
    } catch (error) {
      console.error('Batch alias error:', error);
      alert('Failed to save batch.');
    } finally {
      setFlatBatchSaving(false);
    }
  }, [flatBatchName, flatBatchCategory, flatSection, flatBatchIds, ungroupedPendingTransactions, creditTransactions, userId, onAliasUpdate]);

  const handleFlatHeaderClick = useCallback((section) => {
    if (flatBatchIds.size > 0 && flatSection === section) {
      handleFlatAliasSubmit();
    } else {
      handleFlatAliasAll(section);
    }
  }, [flatBatchIds, flatSection, handleFlatAliasSubmit, handleFlatAliasAll]);

  // LEFT COLUMN: Renames the entire Alias Group
  const handleRenameGroup = async (oldName, newName, category) => {
    if (!newName.trim()) return;
    setEditingGroupId(null);
    try {
      await api.renameAliasGroup(userId, oldName, newName, category);
      if (onAliasUpdate) onAliasUpdate([]);
      setSelectedAlias(newName.trim());
    } catch (err) { 
      console.error(err);
      alert('Failed to rename alias group');
    }
  };

  // RIGHT COLUMN: Renames only the specific transaction
  const handleRenameTransaction = async (tx, newName) => {
    if (!newName.trim()) return;
    setEditingAliasId(null);
    try {
      await api.updateTransactionName(userId, tx.id, newName.trim());
      if (onAliasUpdate) onAliasUpdate([]);
    } catch (err) { 
      console.error(err);
      alert('Failed to rename transaction');
    }
  };

  const handleDeleteAlias = async (pattern) => {
    if (!window.confirm('Delete this alias?')) return;
    setDeletingPattern(pattern);
    try {
      await api.deleteAliasByPattern?.(userId, pattern);
      if (onAliasUpdate) onAliasUpdate([]);
      setSelectedAlias(null);
    } catch (err) { 
      console.error(err);
      alert('Failed to delete alias');
    } finally { setDeletingPattern(null); }
  };

  const toggleGroup = (key) => setExpandedGroups(prev => ({ ...prev, [key]: !prev[key] }));

  const allPendingAliased = ungroupedPendingTransactions.length === 0 && Object.keys(mlGroups.groups || {}).length === 0;
  const isFullyCategorized = allPendingAliased && creditTransactions.length === 0 && Object.keys(aliasedByCategory).length > 0;

  const fmtTotal = (n) => new Intl.NumberFormat('en-NG', {
    style: 'currency', currency: 'NGN', minimumFractionDigits: 0,
  }).format(Math.abs(n));

  if (!transactions || transactions.length === 0) {
    return <div className="py-20 text-center opacity-10 italic text-sm">No movements detected.</div>;
  }

  if (isFullyCategorized) {
    const totalAliasedList = transactions.filter(tx => tx.aliased);
    const getDisplayName = (tx) => tx.alias_name || tx.narration;
    const allUniqueAliasNames = Array.from(new Set(totalAliasedList.map(getDisplayName).filter(Boolean)));
    const selectedTransactions = selectedAlias
      ? totalAliasedList.filter(tx => getDisplayName(tx) === selectedAlias)
      : [];

    const selectedTotal = selectedTransactions.reduce((sum, tx) => sum + (tx.amount || 0), 0);
    const signSelected = selectedTotal < 0 ? '-' : '';

    return (
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start animate-in fade-in duration-300">
        <div className="lg:col-span-4 bg-zinc-950/40 border border-white/5 rounded-2xl p-5 space-y-4 sticky top-6">
          <div>
            <h4 className="text-xs font-black text-white uppercase tracking-wider">Alias Registries</h4>
            <p className="text-[9px] text-slate-500 font-mono mt-0.5">Click any alias to see its transactions</p>
          </div>
          <div className="space-y-2 max-h-[65vh] overflow-y-auto pr-1 custom-scrollbar">
            {allUniqueAliasNames.map((name, idx) => {
              const occurrences = totalAliasedList.filter(t => getDisplayName(t) === name);
              const total = occurrences.reduce((sum, tx) => sum + (tx.amount || 0), 0);
              const sign = total < 0 ? '-' : '';
              const catType = occurrences[0]?.alias_category || occurrences[0]?.category || 'General';
              const isActive = selectedAlias === name;
              return (
                <div
                  key={`alias-${name}-${idx}`}
                  className={`w-full px-4 py-3 text-left flex items-center justify-between text-xs font-bold rounded-xl transition-all ${
                    isActive ? 'bg-indigo-600/20 border border-indigo-500/30 text-white' : 'bg-white/5 hover:bg-white/10 text-slate-300'
                  }`}
                >
                  {editingGroupId === name ? (
                    <div className="flex items-center gap-2 w-full" onClick={(e) => e.stopPropagation()}>
                      <input
                        type="text"
                        defaultValue={name}
                        id={`rename-group-${idx}`}
                        className="bg-black/40 border border-white/10 rounded px-2 py-1 text-white text-xs flex-1 outline-none focus:border-indigo-500"
                        autoFocus
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') {
                            const newName = e.target.value.trim();
                            if (newName && newName !== name) handleRenameGroup(name, newName, catType);
                            else setEditingGroupId(null);
                          }
                        }}
                      />
                      <button onClick={() => {
                        const input = document.getElementById(`rename-group-${idx}`);
                        const newName = input.value.trim();
                        if (newName && newName !== name) handleRenameGroup(name, newName, catType);
                        else setEditingGroupId(null);
                      }} className="p-1 bg-indigo-600 rounded text-white hover:bg-indigo-700"><Check size={12} /></button>
                      <button onClick={() => setEditingGroupId(null)} className="p-1 bg-white/5 rounded hover:bg-white/10"><X size={12} /></button>
                    </div>
                  ) : (
                    <>
                      <div className="min-w-0 flex-1 cursor-pointer" onClick={() => setSelectedAlias(name)}>
                        <p className="truncate font-bold">{name}</p>
                        <span className={`text-[7px] px-1.5 py-0.2 rounded-full font-black uppercase mt-1 inline-block ${CATEGORY_COLORS[catType] || CATEGORY_COLORS.General}`}>
                          {catType}
                        </span>
                      </div>
                      <div className="flex items-center gap-2 shrink-0 ml-2">
                        <div className="flex flex-col items-end">
                          <span className="text-[8px] bg-black/40 px-2 py-0.5 rounded-full font-mono text-indigo-400">{occurrences.length} txs</span>
                          <span className="text-[8px] font-mono text-slate-400 mt-0.5">{sign}{fmtTotal(total)}</span>
                        </div>
                        <button 
                          onClick={(e) => { e.stopPropagation(); setEditingGroupId(name); }} 
                          className="p-1.5 hover:bg-white/10 rounded transition-colors"
                          title="Rename alias group"
                        >
                          <Pencil size={12} className="text-slate-400" />
                        </button>
                      </div>
                    </>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        <div className="lg:col-span-8 space-y-4 max-h-[85vh] overflow-y-auto pr-2 custom-scrollbar">
          <div className="flex items-center justify-between pb-2 border-b border-white/5">
            <div className="flex items-center gap-2">
              <CheckCircle2 size={14} className="text-emerald-400" />
              <h3 className="text-xs font-black uppercase tracking-wider text-white">
                {selectedAlias ? `Transactions: ${selectedAlias}` : 'Select an alias from the left'}
              </h3>
            </div>
            <span className="text-[8px] bg-emerald-500/10 text-emerald-400 px-2 py-0.5 rounded-full uppercase font-black tracking-widest">
              {selectedAlias ? `${selectedTransactions.length} items · ${signSelected}${fmtTotal(selectedTotal)}` : 'All Cleaned'}
            </span>
          </div>

          {selectedAlias ? (
            <div className="space-y-2">
              {selectedTransactions.map((tx, idx) => {
                const txId = getTxUniqueId(tx);
                const pattern = getUniquePattern(tx);
                const isDeleting = deletingPattern === pattern;
                const isEditing = editingAliasId === txId;
                return (
                  <div key={getTransactionKey(tx, idx)} className="bg-black/30 border border-white/5 rounded-xl p-3 hover:bg-white/5 transition-colors">
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        {isEditing ? (
                          <div className="flex items-center gap-2">
                            <input
                              type="text"
                              value={editAliasName}
                              onChange={(e) => setEditAliasName(e.target.value)}
                              className="bg-black/40 border border-white/10 rounded px-2 py-1 text-white text-xs flex-1"
                              autoFocus
                            />
                            <button onClick={() => handleRenameTransaction(tx, editAliasName)} className="p-1 bg-indigo-600 rounded text-white"><Check size={12} /></button>
                            <button onClick={() => setEditingAliasId(null)} className="p-1 bg-white/5 rounded"><X size={12} /></button>
                          </div>
                        ) : (
                          <div>
                            <p className="text-sm font-bold text-white truncate">{tx.narration}</p>
                            <div className="flex flex-wrap items-center gap-3 mt-1 text-[10px]">
                              <span className="text-slate-600">{tx.bank} •••• {tx.account_last4}</span>
                              <span className="text-slate-700">{new Date(tx.timestamp).toLocaleDateString()}</span>
                              <span className={`font-black ${tx.tx_type === 'credit' ? 'text-emerald-400' : 'text-white'}`}>
                                {tx.tx_type === 'credit' ? '+' : '-'}₦{Math.abs(tx.amount).toLocaleString('en-NG', { minimumFractionDigits: 2 })}
                              </span>
                            </div>
                          </div>
                        )}
                      </div>
                      <div className="flex items-center gap-1 shrink-0">
                        {!isEditing && (
                          <button
                            onClick={() => { setEditingAliasId(txId); setEditAliasName(tx.narration); }}
                            className="p-1.5 hover:bg-white/10 rounded transition-colors"
                            title="Rename transaction name"
                          >
                            <Pencil size={12} className="text-slate-400" />
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="py-12 text-center text-slate-500 text-xs">Click any alias on the left to see its transactions.</div>
          )}
        </div>
      </div>
    );
  }

  const pendingHeaderLabel = (flatSection === 'pending' && flatBatchIds.size > 0) ? `Alias Selected (${flatBatchIds.size})` : 'Alias All';
  const creditsHeaderLabel = (flatSection === 'credits' && flatBatchIds.size > 0) ? `Alias Selected (${flatBatchIds.size})` : 'Alias All';

  return (
    <div className="space-y-6">
      {Object.keys(aliasedByCategory).length > 0 && (
        <div className="mb-6">
          <div className="flex items-center gap-2 mb-3 px-1"><Check size={12} className="text-emerald-400" /><span className="text-[10px] font-black uppercase tracking-wider text-slate-400">Aliased Transactions</span></div>
          {Object.entries(aliasedByCategory).map(([category, txs]) => (
            <AliasedCategoryGroup key={`cat-${category}`} category={category} transactions={txs} userId={userId} onAliasUpdate={onAliasUpdate} isExpanded={expandedGroups.aliasedCategories[category] ?? true} userBankColors={userBankColors} colorOptions={colorOptions} />
          ))}
        </div>
      )}

      {mlGroups.groups && Object.keys(mlGroups.groups).length > 0 && (
        <div className="mb-6">
          <button onClick={() => toggleGroup('mlGroups')} className="w-full flex items-center justify-between px-4 py-2 bg-amber-500/5 rounded-xl hover:bg-amber-500/10 text-left mb-2">
            <div className="flex items-center gap-2">{expandedGroups.mlGroups ? <ChevronDown size={14} className="text-amber-400" /> : <ChevronRight size={14} className="text-amber-400" />}<Brain size={12} className="text-amber-400" /><span className="text-[10px] font-black uppercase tracking-wider text-white">ML Suggested Groups</span></div>
          </button>
          {expandedGroups.mlGroups && (
            <div className="space-y-3">
              {Object.entries(mlGroups.groups).map(([groupName, groupData]) => (
                <GroupedTransactionGroup
                  key={`ml-${groupName}`}
                  group={groupData}
                  groupName={groupName}
                  userId={userId}
                  onAliasUpdate={onAliasUpdate}
                  isExpanded={true}
                  userBankColors={userBankColors}
                  colorOptions={colorOptions}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {(ungroupedPendingTransactions.length > 0 || flatSection === 'pending') && (
        <div className="mb-6">
          <div className="flex items-center justify-between w-full px-4 py-2 bg-white/5 rounded-xl text-left mb-2">
            <button onClick={() => setExpandedGroups(p => ({ ...p, pending: !p.pending }))} className="flex items-center gap-2 text-left min-w-0 flex-1">
              {expandedGroups.pending ? <ChevronDown size={14} className="text-slate-400" /> : <ChevronRight size={14} className="text-slate-400" />}
              <Tags size={12} className="text-slate-400" /><span className="text-[10px] font-black uppercase tracking-wider text-white">Unassigned Inflows & Outflows</span>
              <span className="text-[8px] px-1.5 py-0.5 bg-white/10 rounded-full font-mono">{ungroupedPendingTransactions.length} items</span>
            </button>
            <button 
              onClick={() => handleFlatHeaderClick('pending')} 
              className={`text-[8px] px-2 py-1 rounded-lg font-black uppercase tracking-wider transition-colors ${
                flatSection === 'pending' && flatBatchIds.size > 0 ? 'bg-emerald-600/80 text-white hover:bg-emerald-600' : 'bg-white/5 hover:bg-white/10 text-slate-300'
              }`}
            >
              {pendingHeaderLabel}
            </button>
          </div>
          {expandedGroups.pending && ungroupedPendingTransactions.length > 0 && (
            <div className="space-y-1">
              {flatShowForm && flatSection === 'pending' && ungroupedPendingTransactions.length > 1 && (
                <div className="flex items-center gap-2 mb-2 bg-zinc-900/60 p-3 rounded-xl border border-white/5 animate-in fade-in duration-100">
                  <div className="flex-1 min-w-0">
                    <input type="text" value={flatBatchName} onChange={(e) => { setFlatBatchName(e.target.value); setFlatBatchError(''); }} placeholder="Batch Display Name..." className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-1.5 text-white text-xs min-h-[32px] outline-none focus:border-indigo-500" />
                    {flatBatchError && <p className="text-[9px] text-rose-400 font-bold mt-1.5 uppercase tracking-wider">{flatBatchError}</p>}
                  </div>
                  <div className="w-44"><CustomSelect value={flatBatchCategory} onChange={setFlatBatchCategory} /></div>
                  <button onClick={handleFlatAliasSubmit} disabled={flatBatchSaving || flatBatchIds.size === 0} className="text-xs px-4 py-1.5 bg-emerald-600 text-white font-black rounded-lg hover:bg-emerald-700 transition-colors shrink-0 disabled:opacity-50">
                    {flatBatchSaving ? 'Saving...' : 'Save'}
                  </button>
                  <button onClick={cancelFlatBatch} className="text-xs px-3 py-1.5 bg-white/10 text-slate-300 font-black rounded-lg hover:bg-white/20 transition-colors shrink-0">Cancel</button>
                </div>
              )}

              {ungroupedPendingTransactions.map((tx, idx) => {
                const txId = getTxUniqueId(tx);
                return (
                  <TransactionItem
                    key={getTransactionKey(tx, idx)}
                    tx={tx}
                    userId={userId}
                    onAliasUpdate={onAliasUpdate}
                    isAliased={false}
                    index={idx}
                    userBankColors={userBankColors}
                    colorOptions={colorOptions}
                    isBatchMode={flatBatchIds.size >= 2}
                    isSelected={txId ? flatBatchIds.has(String(txId)) : false}
                    selectionCount={flatBatchIds.size}
                    onToggleSelect={toggleFlatSelection}
                  />
                );
              })}
            </div>
          )}
        </div>
      )}

      {creditTransactions.length > 0 && (
        <div className="mb-6">
          <div className="flex items-center justify-between w-full px-4 py-2 bg-white/5 rounded-xl mb-2">
            <button onClick={() => setExpandedGroups(p => ({ ...p, credits: !p.credits }))} className="flex items-center gap-2 text-left min-w-0 flex-1">
              {expandedGroups.credits ? <ChevronDown size={14} className="text-slate-400" /> : <ChevronRight size={14} className="text-slate-400" />}
              <CheckCircle2 size={12} className="text-emerald-400" /><span className="text-[10px] font-black uppercase tracking-wider text-white">Inflow Credits</span>
              <span className="text-[8px] px-1.5 py-0.5 bg-emerald-500/10 text-emerald-400 rounded-full font-mono">{creditTransactions.length} items</span>
            </button>
            <button 
              onClick={() => handleFlatHeaderClick('credits')} 
              className={`text-[8px] px-2 py-1 rounded-lg font-black uppercase tracking-wider transition-colors ${
                flatSection === 'credits' && flatBatchIds.size > 0 ? 'bg-emerald-600/80 text-white hover:bg-emerald-600' : 'bg-white/5 hover:bg-white/10 text-slate-300'
              }`}
            >
              {creditsHeaderLabel}
            </button>
          </div>
          {expandedGroups.credits && (
            <div className="space-y-1">
              {flatShowForm && flatSection === 'credits' && creditTransactions.length > 1 && (
                <div className="flex items-center gap-2 mb-2 bg-zinc-900/60 p-3 rounded-xl border border-white/5 animate-in fade-in duration-100">
                  <div className="flex-1 min-w-0">
                    <input type="text" value={flatBatchName} onChange={(e) => { setFlatBatchName(e.target.value); setFlatBatchError(''); }} placeholder="Batch Display Name..." className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-1.5 text-white text-xs min-h-[32px] outline-none focus:border-indigo-500" />
                    {flatBatchError && <p className="text-[9px] text-rose-400 font-bold mt-1.5 uppercase tracking-wider">{flatBatchError}</p>}
                  </div>
                  <div className="w-44"><CustomSelect value={flatBatchCategory} onChange={setFlatBatchCategory} /></div>
                  <button onClick={handleFlatAliasSubmit} disabled={flatBatchSaving || flatBatchIds.size === 0} className="text-xs px-4 py-1.5 bg-emerald-600 text-white font-black rounded-lg hover:bg-emerald-700 transition-colors shrink-0 disabled:opacity-50">
                    {flatBatchSaving ? 'Saving...' : 'Save'}
                  </button>
                  <button onClick={cancelFlatBatch} className="text-xs px-3 py-1.5 bg-white/10 text-slate-300 font-black rounded-lg hover:bg-white/20 transition-colors shrink-0">Cancel</button>
                </div>
              )}
              {creditTransactions.map((tx, idx) => {
                const txId = getTxUniqueId(tx);
                return (
                  <TransactionItem
                    key={getTransactionKey(tx, idx)}
                    tx={tx}
                    userId={userId}
                    onAliasUpdate={onAliasUpdate}
                    isAliased={false}
                    index={idx}
                    userBankColors={userBankColors}
                    colorOptions={colorOptions}
                    isBatchMode={flatBatchIds.size >= 2}
                    isSelected={txId ? flatBatchIds.has(String(txId)) : false}
                    selectionCount={flatBatchIds.size}
                    onToggleSelect={toggleFlatSelection}
                  />
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}