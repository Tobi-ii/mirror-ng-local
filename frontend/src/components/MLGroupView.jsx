/**
 * MLGroupView — ML-suggested transaction grouping panel.
 *
 * Renders transactions clustered by similarity into category cards (overview),
 * a browsable groups list, and a detail view per group.
 * Supports aliasing (immediate removal from snapshot) and flat mode.
 */

import { useState, useMemo, useRef, useEffect } from 'react';
import { ChevronLeft, Sparkles, CheckCircle2, ArrowDownLeft, Brain, List, Layers } from 'lucide-react';
import { groupSimilarTransactions } from '../utils/transactionHelpers';
import TransactionList from './TransactionRow';

// ─── Category Theme Registry ────────────────────────────────────────────────
// Each known ML cluster label gets distinct Tailwind tokens for bg, text, and border.
// New categories returned by the ML model must be added here or fall back to DEFAULT_COLOR.
const GROUP_COLORS = {
  'Airtime Purchase': { bg: 'bg-purple-500/10', text: 'text-purple-400', border: 'border-purple-500/20' },
  'Data Purchase': { bg: 'bg-violet-500/10', text: 'text-violet-400', border: 'border-violet-500/20' },
  'Bank Transfer': { bg: 'bg-indigo-500/10', text: 'text-indigo-400', border: 'border-indigo-500/20' },
  'Electricity Bill': { bg: 'bg-orange-500/10', text: 'text-orange-400', border: 'border-orange-500/20' },
  'VAT Charge': { bg: 'bg-amber-500/10', text: 'text-amber-400', border: 'border-amber-500/20' },
  'Card Fee': { bg: 'bg-rose-500/10', text: 'text-rose-400', border: 'border-rose-500/20' },
  'Food Purchase': { bg: 'bg-red-500/10', text: 'text-red-400', border: 'border-red-500/20' },
  'Transport': { bg: 'bg-cyan-500/10', text: 'text-cyan-400', border: 'border-cyan-500/20' },
  'Salary': { bg: 'bg-emerald-500/10', text: 'text-emerald-400', border: 'border-emerald-500/20' },
};

/** Fallback palette used when a group name has no matching entry in GROUP_COLORS. */
const DEFAULT_COLOR = { bg: 'bg-slate-500/10', text: 'text-slate-400', border: 'border-slate-500/20' };

/** Look up theme tokens for a named group; defaults to neutral grey. */
function getColor(name) {
  return GROUP_COLORS[name] || DEFAULT_COLOR;
}

/** Sum of all amounts in a transaction array. */
const groupTotal = (txs) => txs.reduce((s, t) => s + t.amount, 0);

/** Format a number as ₦ with a K suffix above 1 000. */
const fmtK = (n) => n >= 1000 ? `₦${(n / 1000).toFixed(0)}K` : `₦${n.toFixed(0)}`;

// ─── Main Component ─────────────────────────────────────────────────────────

export default function MLGroupView({
  transactions = [],
  userId,
  onAliasUpdate,       // Callback fired after an alias is persisted
  onViewChange,        // Notifies parent when detail view opens/closes
  userBankColors = {},
  colorOptions = []
}) {
  // View state machine: 'overview' → 'groups' → 'detail'
  const [view, setView] = useState('overview');
  // Identifies which group is open in detail view; also '__ungrouped' | '__credits'
  const [selectedGroup, setSelectedGroup] = useState(null);
  // When true, bypasses ML grouping and renders the full TransactionList
  const [flatMode, setFlatMode] = useState(false);
  // Frozen copy of the group's transactions so aliased rows can animate out of view
  const [detailSnapshot, setDetailSnapshot] = useState([]);
  // Incremented after alias saves to force useMemo to re-cluster from scratch
  const [refreshKey, setRefreshKey] = useState(0);

  const isDetail = view === 'detail';
  const prevDetail = useRef(isDetail);
  // Sync detail-state changes upward (e.g. so the parent can hide a bottom nav).
  useEffect(() => {
    if (isDetail !== prevDetail.current && onViewChange) {
      onViewChange(isDetail);
      prevDetail.current = isDetail;
    }
  }, [isDetail, onViewChange]);

  // ─── ML Grouping & Derived State ────────────────────────────────────────────
  // Only un-aliased debits are fed to the clustering algorithm.
  // refreshKey causes re-computation so newly-aliased txs disappear from groups.
  const { groups, ungrouped } = useMemo(() => {
    const pending = transactions.filter(t => t.tx_type === 'debit' && !t.aliased);
    return groupSimilarTransactions(pending);
  }, [transactions, refreshKey]);

  // Separate credit transactions for the Income card (aliased rows excluded).
  const credited = useMemo(() => {
    return transactions.filter(t => t.tx_type === 'credit' && !t.aliased);
  }, [transactions, refreshKey]);

  // Aggregate counters derived from the current grouping state.
  const aliasedCount = transactions.filter(t => t.aliased).length;
  const groupEntries = Object.entries(groups);
  const allProcessed = groupEntries.length === 0 && ungrouped.length === 0 && credited.length === 0;
  const noData = transactions.length === 0;
  const mlTotalTx = groupEntries.reduce((s, [, g]) => s + g.transactions.length, 0);
  const mlTotalAmt = groupEntries.reduce((s, [, g]) => s + groupTotal(g.transactions), 0);

  // ─── Navigation Helpers ──────────────────────────────────────────────────────

  /**
   * Step back through the view stack: detail → groups → overview.
   * Clears detailSnapshot and resets selectedGroup appropriately.
   */
  const goBack = () => {
    if (view === 'detail' && selectedGroup) {
      setDetailSnapshot([]);
      if (selectedGroup === '__ungrouped' || selectedGroup === '__credits') {
        setSelectedGroup(null);
        setView('overview');
      } else {
        setSelectedGroup(null);
        setView('groups');
      }
    } else if (view === 'groups') {
      setView('overview');
    } else {
      setView('overview');
      setSelectedGroup(null);
    }
  };

  /**
   * Navigate into the detail view for a group.
   * Captures a snapshot so that aliased rows can be removed locally
   * without mutating the source transactions array.
   */
  const openDetail = (groupName) => {
    let txs = [];
    if (groupName === '__ungrouped') txs = ungrouped;
    else if (groupName === '__credits') txs = credited;
    else if (groups[groupName]) txs = groups[groupName].transactions;

    setDetailSnapshot([...txs]);
    setSelectedGroup(groupName);
    setView('detail');
  };

  // ─── Alias Callback ──────────────────────────────────────────────────────────

  /**
   * Invoked after a successful alias operation.
   * Removes the aliased IDs from the open detail snapshot (optimistic removal),
   * then increments refreshKey to re-cluster for the overview.
   */
  const handleAliasUpdate = (aliasedIds) => {
    // Immediately remove aliased transactions from the detail snapshot
    if (aliasedIds && aliasedIds.length > 0) {
      setDetailSnapshot(prev => {
        const filtered = prev.filter(tx => !aliasedIds.includes(String(tx.id)));
        if (filtered.length === 0 && view === 'detail') {
          setView('overview');
          setSelectedGroup(null);
        }
        return filtered;
      });
    } else {
      // Fallback: filter using current transactions (slower, but works)
      setDetailSnapshot(prev => {
        const filtered = prev.filter(snapTx => {
          const current = transactions.find(t => t.id === snapTx.id);
          return current && !current.aliased;
        });
        if (filtered.length === 0 && view === 'detail') {
          setView('overview');
          setSelectedGroup(null);
        }
        return filtered;
      });
    }
    if (onAliasUpdate) {
      onAliasUpdate();
      setRefreshKey(prev => prev + 1);
    }
  };

  /** Switch to the groups-list view. */
  const openGroupList = () => setView('groups');

  // ─── Detail View ─────────────────────────────────────────────────────────────

  if (view === 'detail' && selectedGroup) {
    const txs = detailSnapshot;
    return (
      <div className="h-full flex flex-col">
        <div className="flex items-center gap-4 mb-6">
          <button onClick={goBack} className="p-2 bg-white/5 rounded-xl hover:bg-white/10 transition-colors">
            <ChevronLeft size={16} className="text-slate-400" />
          </button>
          <div>
            <h3 className="text-base font-black tracking-tight text-white">
              {selectedGroup === '__ungrouped'
                ? 'Auto-Categorized'
                : selectedGroup === '__credits'
                ? 'Income / Credits'
                : selectedGroup}
            </h3>
            <p className="text-[10px] text-slate-600 font-mono">
              {txs.length} transaction{txs.length !== 1 ? 's' : ''}
            </p>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto">
          <TransactionList
            key={refreshKey}
            transactions={txs}
            userId={userId}
            onAliasUpdate={handleAliasUpdate}
            userBankColors={userBankColors}
            colorOptions={colorOptions}
          />
        </div>
      </div>
    );
  }

  // ─── ML Groups List ──────────────────────────────────────────────────────────

  if (view === 'groups') {
    return (
      <div className="h-full flex flex-col">
        <div className="flex items-center gap-4 mb-6">
          <button onClick={goBack} className="p-2 bg-white/5 rounded-xl hover:bg-white/10 transition-colors">
            <ChevronLeft size={16} className="text-slate-400" />
          </button>
          <div>
            <h3 className="text-base font-black tracking-tight text-white">ML Suggested Groups</h3>
            <p className="text-[10px] text-slate-600">{mlTotalTx} transactions · {fmtK(mlTotalAmt)} total</p>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto space-y-2">
          {groupEntries.map(([name, group]) => {
            const c = getColor(name);
            return (
              <button
                key={name}
                onClick={() => openDetail(name)}
                className={`w-full flex items-center justify-between ${c.bg} ${c.border} border rounded-2xl px-5 py-4 text-left hover:scale-[1.01] active:scale-[0.99] transition-all cursor-pointer`}
              >
                <div className="min-w-0 flex-1 mr-4">
                  <div className="flex items-center gap-2 mb-0.5">
                    <Sparkles size={11} className={c.text} />
                    <h4 className={`text-sm font-black tracking-tight ${c.text}`}>{name}</h4>
                  </div>
                  <p className="text-[10px] text-slate-600 mt-0.5 font-mono">
                    {group.transactions.length} tx · {fmtK(groupTotal(group.transactions))}
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-xs font-black tabular-nums text-slate-400">
                    {group.transactions.length}
                  </span>
                  <ChevronLeft size={14} className="text-slate-600 -rotate-180" />
                </div>
              </button>
            );
          })}
        </div>
      </div>
    );
  }

  // ─── Flat Mode — Raw Transaction List ────────────────────────────────────────

  if (flatMode) {
    return (
      <div className="h-full flex flex-col">
        <div className="flex items-center justify-end mb-4">
          <div className="flex bg-white/5 rounded-full p-0.5 border border-white/5">
            <button onClick={() => setFlatMode(false)} className="text-[8px] font-black uppercase tracking-wider px-3 py-1 rounded-full transition-all flex items-center gap-1.5 text-slate-500 hover:text-white">
              <Layers size={10} /> Grouped
            </button>
            <button onClick={() => setFlatMode(true)} className="text-[8px] font-black uppercase tracking-wider px-3 py-1 rounded-full transition-all flex items-center gap-1.5 bg-white text-black">
              <List size={10} /> Flat
            </button>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto">
          <TransactionList
            key={refreshKey}
            transactions={transactions}
            userId={userId}
            onAliasUpdate={onAliasUpdate}
            userBankColors={userBankColors}
            colorOptions={colorOptions}
          />
        </div>
      </div>
    );
  }

  // ─── Empty State — No Transactions ───────────────────────────────────────────

  if (noData) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center px-6">
          <CheckCircle2 size={40} className="text-slate-600 mx-auto mb-4 opacity-30" />
          <p className="text-sm text-white/40 font-black uppercase tracking-wider">No Transactions Yet</p>
          <p className="text-[10px] text-white/30 mt-1">
            Set a date range above and sync your email to get started.
          </p>
        </div>
      </div>
    );
  }

  // ─── All Transactions Already Aliased — Inline List ──────────────────────────

  if (allProcessed) {
    return (
      <TransactionList
        key={refreshKey}
        transactions={transactions}
        userId={userId}
        onAliasUpdate={onAliasUpdate}
        userBankColors={userBankColors}
        colorOptions={colorOptions}
      />
    );
  }

  // ─── Overview — Three Summary Cards ──────────────────────────────────────────

  return (
    <div className="h-full flex flex-col">
      {aliasedCount > 0 && (
        <div className="bg-emerald-500/5 border border-emerald-500/10 rounded-2xl px-5 py-3 flex items-center gap-3 mb-6 shrink-0">
          <CheckCircle2 size={16} className="text-emerald-400 shrink-0" />
          <span className="text-[10px] text-emerald-400 font-black uppercase tracking-wider">
            {aliasedCount} transaction{aliasedCount !== 1 ? 's' : ''} already aliased
          </span>
        </div>
      )}

      <div className="flex items-center justify-end mb-4">
        <div className="flex bg-white/5 rounded-full p-0.5 border border-white/5">
          <button
            onClick={() => setFlatMode(false)}
            className={`text-[8px] font-black uppercase tracking-wider px-3 py-1 rounded-full transition-all flex items-center gap-1.5 ${
              !flatMode ? 'bg-white text-black' : 'text-slate-500 hover:text-white'
            }`}
          >
            <Layers size={10} /> Grouped
          </button>
          <button
            onClick={() => setFlatMode(true)}
            className={`text-[8px] font-black uppercase tracking-wider px-3 py-1 rounded-full transition-all flex items-center gap-1.5 ${
              flatMode ? 'bg-white text-black' : 'text-slate-500 hover:text-white'
            }`}
          >
            <List size={10} /> Flat
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 flex-1">
        {/* ML Groups Card */}
        <button
          onClick={openGroupList}
          className="bg-indigo-500/[0.04] border border-indigo-500/15 rounded-2xl sm:rounded-[2rem] p-4 sm:p-6 flex flex-col items-center justify-center text-center hover:bg-indigo-500/[0.08] active:scale-[0.97] transition-all cursor-pointer h-full"
        >
          <Brain size={20} className="sm:size-[24px] text-indigo-400 mb-3" />
          <span className="text-[8px] sm:text-[9px] text-indigo-400 font-black uppercase tracking-widest mb-1">
            ML Groups
          </span>
          <span className="text-xl sm:text-2xl font-black tabular-nums text-white">
            {mlTotalTx}
          </span>
          <span className="text-[8px] sm:text-[9px] text-slate-600 font-mono mt-1">
            {fmtK(mlTotalAmt)}
          </span>
        </button>

        {/* Uncategorized Card — debits the ML model could not classify */}
        {ungrouped.length > 0 ? (
          <button
            onClick={() => openDetail('__ungrouped')}
            className="bg-white/[0.02] border border-white/5 rounded-2xl sm:rounded-[2rem] p-4 sm:p-6 flex flex-col items-center justify-center text-center hover:bg-white/5 active:scale-[0.97] transition-all cursor-pointer h-full"
          >
            <div className="w-5 h-5 sm:w-6 sm:h-6 rounded-full bg-white/5 flex items-center justify-center mb-3">
              <span className="text-slate-500 text-xs sm:text-sm font-black">?</span>
            </div>
            <span className="text-[8px] sm:text-[9px] text-slate-500 font-black uppercase tracking-widest mb-1">
              Uncategorized
            </span>
            <span className="text-xl sm:text-2xl font-black tabular-nums text-white">
              {ungrouped.length}
            </span>
            <span className="text-[8px] sm:text-[9px] text-slate-600 font-mono mt-1">
              {fmtK(groupTotal(ungrouped))}
            </span>
          </button>
        ) : (
          <div className="bg-white/[0.01] border border-white/5 rounded-2xl sm:rounded-[2rem] p-4 sm:p-6 flex flex-col items-center justify-center text-center h-full">
            <CheckCircle2 size={16} className="sm:size-[18px] text-emerald-500/50 mb-3" />
            <span className="text-[8px] sm:text-[9px] text-slate-600 font-black uppercase tracking-widest">
              All Set
            </span>
          </div>
        )}

        {/* Income / Credits Card — all credit transactions */}
        {credited.length > 0 ? (
          <button
            onClick={() => openDetail('__credits')}
            className="bg-emerald-500/[0.03] border border-emerald-500/10 rounded-2xl sm:rounded-[2rem] p-4 sm:p-6 flex flex-col items-center justify-center text-center hover:bg-emerald-500/[0.06] active:scale-[0.97] transition-all cursor-pointer h-full"
          >
            <ArrowDownLeft size={18} className="sm:size-[22px] text-emerald-400 mb-3" />
            <span className="text-[8px] sm:text-[9px] text-emerald-400 font-black uppercase tracking-widest mb-1">
              Income
            </span>
            <span className="text-xl sm:text-2xl font-black tabular-nums text-white">
              {credited.length}
            </span>
            <span className="text-[8px] sm:text-[9px] text-slate-600 font-mono mt-1">
              {fmtK(groupTotal(credited))}
            </span>
          </button>
        ) : (
          <div className="bg-white/[0.01] border border-white/5 rounded-2xl sm:rounded-[2rem] p-4 sm:p-6 flex flex-col items-center justify-center text-center h-full">
            <CheckCircle2 size={16} className="sm:size-[18px] text-emerald-500/50 mb-3" />
            <span className="text-[8px] sm:text-[9px] text-slate-600 font-black uppercase tracking-widest">
              All Set
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
