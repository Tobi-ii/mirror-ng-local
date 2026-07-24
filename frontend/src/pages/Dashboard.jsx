// ──────────────────────────────────────────────────────────────────────────────
// Dashboard — primary financial overview page for Mirror
// Renders: account cards, audit trail, spend chart, alias summary coverflow,
//          executive summary, agent chat, insights, and history views
// State: transactions, balances, aliases, syncing, navigation tabs, filters,
//        onboarding flow, gaps detection
// ──────────────────────────────────────────────────────────────────────────────

import { useState, useRef, useEffect, useMemo } from 'react';
import { 
  LayoutDashboard, History, LogOut, Brain, MessageSquare, Settings as LucideSettings,
  CheckCircle2, FolderOpen, ChevronRight
} from 'lucide-react';
import { api } from '../services/api';

import FloatingNavItem from "../components/FloatingNavItem";
import BankCard, { BANK_COLORS, COLOR_OPTIONS } from "../components/BankCard";
import SpendChart from "../components/SpendChart";
import InsightsPanel from "./InsightsPanel";
import AgentChat from "./AgentChat";
import SessionOnboarding from "../components/SessionOnboarding";
import DashboardHeader from "../components/DashboardHeader";
import ExecutiveDashboard from "./ExecutiveDashboard";
import { Settings } from "./Settings";
import CustomSelect from "../components/CustomSelect";
import MLGroupView from "../components/MLGroupView";
import OnboardingGapsModal from '../components/OnboardingGapsModal';

// ─── Supported financial institutions for manual account entry ──────────────
const SUPPORTED_BANKS = [
  'Sterling Bank', 'Wema (ALAT)', 'GTBank', 'Access Bank',
  'First Bank', 'Kuda', 'OPay', 'Moniepoint', 'PalmPay',
  'Piggyvest', 'Cowrywise', 'Other',
];

// ─── Category-to-Tailwind mappings for transaction display ──────────────────
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

// ────────────────────────────────────────────────────────────────────────────
// AddManualCard – inline form for manually adding a bank account + balance
// Props:  onAdd(bank, last4, balance) — callback after user confirms
// State:  open, bank, last4, balance — local form fields
// ────────────────────────────────────────────────────────────────────────────
function AddManualCard({ onAdd }) {
  const [open, setOpen] = useState(false);
  const [bank, setBank] = useState('Piggyvest');
  const [last4, setLast4] = useState('');
  const [balance, setBalance] = useState('');

  // Validate and submit the manual account entry, then reset form
  const handleAdd = () => {
    if (!balance) return;
    onAdd(bank, last4 || '0000', balance);
    setOpen(false);
    setBank('Piggyvest');
    setLast4('');
    setBalance('');
  };

  // Closed state — render a dashed placeholder card with a "+" button
  if (!open) return (
    <div onClick={() => setOpen(true)}
      className="h-44 w-32 flex-shrink-0 rounded-[2.5rem] border-2 border-dashed border-white/10 flex flex-col items-center justify-center gap-4 cursor-pointer hover:border-indigo-500/50 hover:bg-white/5 transition-all group">
      <div className="w-10 h-10 rounded-2xl bg-white/5 border border-white/10 flex items-center justify-center group-hover:bg-indigo-500/20 transition-all">
        <span className="text-xl text-slate-500 group-hover:text-indigo-400 font-light">+</span>
      </div>
      <p className="text-[9px] font-black uppercase tracking-[0.2em] text-slate-600 group-hover:text-slate-400 text-center leading-relaxed">Add<br/>Account</p>
    </div>
  );

  // Open state — show bank selector, last-4 digits input, balance input, and action buttons
  return (
    <div className="h-44 w-[280px] flex-shrink-0 rounded-[2.5rem] bg-[#0a0c10] border border-white/10 p-5 flex flex-col justify-between shadow-2xl animate-in fade-in zoom-in-95 duration-300">
      <CustomSelect
        value={bank}
        onChange={setBank}
        options={SUPPORTED_BANKS}
        placeholder="Select bank"
      />
      <div className="flex gap-2">
        <input 
          type="text" 
          value={last4} 
          // Enforce max 4 digits by slicing input value
          onChange={e => setLast4(e.target.value.slice(-4))}
          placeholder="Last 4" 
          maxLength={4}
          className="w-1/3 bg-white/5 border border-white/10 px-2 py-2 rounded-xl text-white text-[10px] font-mono outline-none text-center focus:border-indigo-500 transition-colors" 
        />
        <div className="relative flex-1">
          <span className="absolute left-2 top-1/2 -translate-y-1/2 text-slate-500 text-[10px] font-black">₦</span>
          <input 
            type="number" 
            value={balance} 
            onChange={e => setBalance(e.target.value)}
            placeholder="Balance"
            className="w-full bg-white/5 border border-white/10 pl-5 pr-2 py-2 rounded-xl text-white text-[10px] font-black outline-none focus:border-indigo-500 transition-colors" 
          />
        </div>
      </div>
      <div className="flex gap-2">
        <button 
          onClick={handleAdd} 
          className="flex-1 py-2 bg-indigo-600 text-white text-[10px] font-black rounded-xl hover:bg-indigo-700 transition-colors"
        >
          Add
        </button>
        <button 
          onClick={() => setOpen(false)} 
          className="flex-1 py-2 bg-white/5 text-slate-400 text-[10px] font-black rounded-xl hover:bg-white/10 transition-colors"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────────
// Dashboard — root page component
// Props:  userId (string|number), onLogout (fn)
// State:  transactions[], balances[], aliases[], syncing, onboarding-flow,
//         navigation (activeTab), filters (bankFilter, dates), execMode,
//         blurred overlay, gaps modal, carousel index, per-bank color overrides
// ────────────────────────────────────────────────────────────────────────────
export default function Dashboard({ userId, onLogout }) {
  const [transactions, setTransactions] = useState([]);
  const [balances, setBalances] = useState([]);
  const [aliases, setAliases] = useState([]);
  const [syncing, setSyncing] = useState(false);
  const [auditExpanded, setAuditExpanded] = useState(false);
  const [showOnboarding, setShowOnboarding] = useState(true);
  const [showSettings, setShowSettings] = useState(false);
  const [showGaps, setShowGaps] = useState(false);
  const [gapsData, setGapsData] = useState(null);
  const [totalAccountsData, setTotalAccountsData] = useState(0);
  const [activeTab, setActiveTab] = useState('dashboard');
  const [isBlurred, setIsBlurred] = useState(false);
  const [hoverLabel, setHoverLabel] = useState('');
  const [bankFilter, setBankFilter] = useState('all');
  const [execMode, setExecMode] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const timerRef = useRef(null);
  const mainRef = useRef(null);
  const scrollRef = useRef(null);
  const [activeCardIndex, setActiveCardIndex] = useState(0);
  const [wrappedCards, setWrappedCards] = useState({});
  const wrappedMeasuredRef = useRef({});

  // ─── Per-bank color overrides (persisted locally in-memory) ──────────────
  const [allBankColors, setAllBankColors] = useState({});

  // Update a single bank's color index while preserving others
  const handleBankColorChange = (bank, colorIdx) => {
    setAllBankColors(prev => ({ ...prev, [bank]: colorIdx }));
  };

  // ─── Responsive: track mobile breakpoint ────────────────────────────────
  // Dependencies intentionally empty — runs once on mount; cleanup removes listener
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 767px)');
    setIsMobile(mq.matches);
    const handler = (e) => setIsMobile(e.matches);
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);

  const [sinceDate, setSinceDate] = useState('2026-01-01');
  const [untilDate, setUntilDate] = useState(null);

  // ── Audit window filter ──────────────────────────────────────────────
  // Restrict displayed transactions to the selected date range
  const auditFilteredTransactions = transactions.filter(tx => {
    if (!tx.timestamp) return false;
    const txDate = tx.timestamp.split('T')[0];
    return untilDate
      ? txDate >= sinceDate && txDate <= untilDate
      : txDate >= sinceDate;
  });

  // ── Alias application – respects backend aliased flag ────────────────
  // Where tx.aliased is truthy, substitute narration/category with the
  // matching alias record's display fields (supports exact or substring match)
  const applyAliases = (txList) => {
    if (!aliases.length) return txList;
    return txList.map(tx => {
      if (tx.aliased) {
        const match = aliases.find(a => {
          const pattern = (a.recipient_pattern || '').toLowerCase();
          const narration = (tx.original_narration || tx.narration || '').toLowerCase();
          const exactMatch = a.exact_match === true || a.exact_match === 1;
          
          if (exactMatch) {
            return narration === pattern;
          } else {
            return pattern && narration.includes(pattern);
          }
        });
        
        if (match) {
          return {
            ...tx,
            narration: match.display_name,
            category: match.category,
            original_narration: tx.original_narration || tx.narration
          };
        }
      }
      return tx;
    });
  };

  const aliasedTransactions = applyAliases(auditFilteredTransactions);

  // Apply active bank filter; "all" shows every bank
  const filteredTx = bankFilter === 'all'
    ? aliasedTransactions
    : aliasedTransactions.filter(t => t.bank === bankFilter);

  // ── Check if ALL transactions are aliased ────────────────────────────
  // Drives the "cover flow" alias summary UI vs. normal audit trail
  const allTransactionsAliased = useMemo(() => {
    if (filteredTx.length === 0) return false;
    return filteredTx.every(tx => tx.aliased === true);
  }, [filteredTx]);

  // ── Group aliased transactions by alias name ─────────────────────────
  // Computes per-group totals (credit - debit) and transaction count;
  // sorted by magnitude descending for cover-flow card ordering
  const aliasSummaryGroups = useMemo(() => {
    if (!allTransactionsAliased) return [];
    
    const groups = {};
    filteredTx.forEach(tx => {
      const name = tx.alias_name || tx.narration || 'Unnamed';
      const cat = tx.alias_category || tx.category || 'General';
      const key = `${name}|||${cat}`;
      
      if (!groups[key]) {
        groups[key] = {
          name,
          category: cat,
          count: 0,
          total: 0,
          transactions: []
        };
      }
      groups[key].count += 1;
      groups[key].total += tx.tx_type === 'credit' ? tx.amount : -tx.amount;
      groups[key].transactions.push(tx);
    });
    
    return Object.values(groups).sort((a, b) => Math.abs(b.total) - Math.abs(a.total));
  }, [filteredTx, allTransactionsAliased]);

  // Handle scroll to find center card (no infinite loop)
  // Scans carousel children to determine which card is visually centered
  const handleCarouselScroll = () => {
    if (!scrollRef.current) return;
    const container = scrollRef.current;
    const center = container.scrollLeft + container.offsetWidth / 2;

    const cards = container.children;
    let closest = 0;
    let minDiff = Infinity;

    for (let i = 0; i < cards.length; i++) {
      const card = cards[i];
      const cardCenter = card.offsetLeft + card.offsetWidth / 2;
      const diff = Math.abs(center - cardCenter);
      if (diff < minDiff) {
        minDiff = diff;
        closest = i;
      }
    }
    setActiveCardIndex(closest);
  };

  // ── Balance display logic ────────────────────────────────────────────
  // Derive synced bank balances from transactions + API balances; merge
  // with manually-entered banks. Synced banks appear first in the list.
  const syncedBanks = [...new Set(auditFilteredTransactions.map(t => t.bank))].map(bank => {
    const bankTxs = auditFilteredTransactions.filter(t => t.bank === bank);
    const existingBal = balances.find(b => b.bank === bank);
    const net = bankTxs.reduce((s, t) => t.tx_type === 'credit' ? s + t.amount : s - t.amount, 0);
    return {
      bank,
      account_last4: existingBal?.account_last4 || bankTxs[0]?.account_last4 || '????',
      balance: existingBal ? existingBal.balance : net,
      last_updated: existingBal?.last_updated || bankTxs[0]?.timestamp,
      isSynced: true
    };
  });

  // Banks present in /balances but missing from synced set → manual entries
  const manualBanks = balances
    .filter(b => !syncedBanks.find(s => s.bank === b.bank))
    .map(b => ({ ...b, isSynced: false }));

  // Synced banks first, then manual; preserves order within each group
  const displayBalances = [...syncedBanks, ...manualBanks]
    .sort((a, b) => a.isSynced === b.isSynced ? 0 : a.isSynced ? -1 : 1);

  // ── Compute which colour indices are already used ──
  // Prevents duplicate gradient assignments across visible bank cards
  const usedColorIndices = useMemo(() => {
    const used = new Set();
    displayBalances.forEach(b => {
      const bankName = b.bank;
      const overrideIdx = allBankColors[bankName];
      if (overrideIdx !== undefined) {
        used.add(overrideIdx);
      } else {
        const theme = BANK_COLORS[bankName] || BANK_COLORS.default;
        const defaultGradient = theme.gradient;
        const defaultIdx = COLOR_OPTIONS.findIndex(o => o.gradient === defaultGradient);
        if (defaultIdx !== -1) used.add(defaultIdx);
      }
    });
    return used;
  }, [displayBalances, allBankColors]);

  // ── Derived stats ────────────────────────────────────────────────────
  // Aggregate liquidity, total inflow, total outflow, and unique banks list
  const aggregateLiquidity = displayBalances.reduce((s, b) => s + (b.balance || 0), 0);
  const totalIn = aliasedTransactions.filter(t => t.tx_type === 'credit').reduce((s, t) => s + t.amount, 0);
  const totalOut = aliasedTransactions.filter(t => t.tx_type === 'debit').reduce((s, t) => s + t.amount, 0);
  const banks = [...new Set(auditFilteredTransactions.map(t => t.bank))];

  // ── API helpers ──────────────────────────────────────────────────────

  // Fetch user-defined aliases from backend
  const loadAliases = async () => {
    try {
      const res = await api.getAliases(userId);
      if (res?.success) setAliases(res.aliases || []);
    } catch (e) {
      console.error('Failed to load aliases:', e);
    }
  };

  // Refresh balances then aliases (aliases depend on latest transaction data)
  const refreshBalances = async () => {
    try {
      const balRes = await api.getBalances(userId);
      if (balRes?.success) setBalances(balRes.balances);
      await loadAliases();
    } catch (e) {
      console.error('Failed to refresh:', e);
    }
  };

  // Refresh transactions then aliases; limits to 1000 most recent records
  const refreshTransactions = async () => {
    try {
      const txRes = await api.getTransactions(userId, { limit: 1000 });
      if (txRes?.success) setTransactions(txRes.transactions);
      await loadAliases();
    } catch (e) {
      console.error('Failed to refresh transactions:', e);
    }
  };

  // Listen for AI bulk updates or settings changes to refresh data globally
  useEffect(() => {
    const handleDataUpdate = () => {
      refreshTransactions();
      refreshBalances();
    };

    window.addEventListener('mirror-data-updated', handleDataUpdate);
    return () => window.removeEventListener('mirror-data-updated', handleDataUpdate);
  }, [userId]);

  // Close settings panel and re-fetch balances to reflect any changes
  const closeSettings = () => {
    setShowSettings(false);
    refreshBalances();
  };

  // Create a manual account via API, then refresh balances from server
  const handleAddAccount = async (bank, last4, balance) => {
    try {
      const res = await api.setInitialBalances(userId, [{
        bank, account_last4: last4 || '0000', balance: parseFloat(balance)
      }]);
      if (!res?.success) {
        console.error('Failed to add account:', res);
        return;
      }
      const balRes = await api.getBalances(userId);
      if (balRes?.success) setBalances(balRes.balances);
    } catch (e) {
      console.error('Failed to add account:', e);
    }
  };

  // Track scroll position to toggle nav opacity after 30px threshold
  const handleScroll = () => {
    if (mainRef.current) setScrolled(mainRef.current.scrollTop > 30);
  };

  // ── Onboarding initializer (branching logic) ─────────────────────────
  // If skipping, dismiss onboarding and fetch transactions directly.
  // Otherwise perform a sync (either from background result or inline),
  // then fetch transactions + balances + aliases, and show gaps if any.
  const handleInitialize = async (isSkip, accounts = [], syncResult = null) => {
    if (isSkip) { setShowOnboarding(false); refreshTransactions(); return; }
    setSyncing(true);
    try {
      let res = syncResult;

      // Fallback to direct sync if no background result provided
      if (!res) {
        const validAccounts = accounts
          .filter(a => a.balance && parseFloat(a.balance) > 0)
          .map(a => ({ bank: a.bank, account_last4: a.account_last4 || '0000', balance: parseFloat(a.balance) }));

        res = await api.syncTransactions(userId, {
          user_id: String(userId),
          since_date: sinceDate,
          full_sync: false,
          opening_balances: validAccounts
        });
      }
      console.log('🕵️ SYNC RESPONSE:', res);

      if (res?.success) {
        const [txRes, balRes] = await Promise.all([
          api.getTransactions(userId, { limit: 1000 }),
          api.getBalances(userId)
        ]);
        if (txRes?.success) setTransactions(txRes.transactions);
        if (balRes?.success) setBalances(balRes.balances);
        await loadAliases();
        
        // Only show modal if there are actual missing gaps
        if (res.gaps && res.gaps.length > 0) {
          setGapsData(res.gaps);
          setTotalAccountsData(res.total_accounts || 0);
          setShowGaps(true);
        }
      }
      setShowOnboarding(false);
    } catch (e) {
      console.error('Sync failed:', e);
      setShowOnboarding(false);
      await refreshTransactions();
    } finally {
      setSyncing(false);
    }
  };

  // ── Manual sync trigger ──────────────────────────────────────────────
  // Fires a sync request with current date window, then refreshes data
  const handleSync = async () => {
    setSyncing(true);
    try {
      const res = await api.syncTransactions(userId, {
        user_id: String(userId),
        since_date: sinceDate,
        full_sync: false
      });
      console.log('🕵️ SYNC RESPONSE:', res);
      if (res?.success) {
        const [txRes, balRes] = await Promise.all([
          api.getTransactions(userId, { limit: 1000 }),
          api.getBalances(userId)
        ]);
        if (txRes?.success) setTransactions(txRes.transactions);
        if (balRes?.success) setBalances(balRes.balances);
        await loadAliases();
      }
    } catch (e) {
      console.error('Sync failed:', e);
    } finally {
      setSyncing(false);
    }
  };

  // ── Hover blur effect handlers ───────────────────────────────────────
  // On desktop, 800ms hover triggers a full-screen blurred overlay with
  // the nav item label as a hero title (dramatic reveal effect)
  const handleMouseEnter = (label) => {
    if (isMobile) return;
    if (timerRef.current) clearTimeout(timerRef.current);
    setHoverLabel(label);
    timerRef.current = setTimeout(() => setIsBlurred(true), 800);
  };

  const handleMouseLeave = () => {
    if (timerRef.current) clearTimeout(timerRef.current);
    setIsBlurred(false);
    setHoverLabel('');
  };

  // Format a number as Nigerian Naira with 2 decimal places
  const fmt = (n) => `₦${Number(n).toLocaleString('en-NG', { minimumFractionDigits: 2 })}`;

  // ── Bank filter pill bar ─────────────────────────────────────────────
  // Only rendered when more than one unique bank exists in the dataset
  const BankFilterBar = () => (
    banks.length > 1 ? (
      <div className="flex items-center gap-2 flex-wrap">
        <button onClick={() => setBankFilter('all')}
          className={`text-[10px] font-black uppercase tracking-widest px-3 py-1.5 rounded-full transition-all ${bankFilter === 'all' ? 'bg-white text-black' : 'text-slate-500 hover:text-white'}`}>
          All
        </button>
        {banks.map(b => (
          <button key={b} onClick={() => setBankFilter(b)}
            className={`text-[10px] font-black uppercase tracking-widest px-3 py-1.5 rounded-full transition-all ${bankFilter === b ? 'bg-white text-black' : 'text-slate-500 hover:text-white'}`}>
            {b.replace(' Bank', '').replace(' (ALAT)', '')}
          </button>
        ))}
      </div>
    ) : null
  );

  return (
    <div className="relative min-h-screen bg-[#050608] text-white overflow-hidden">
      {/* ── Full-screen blur overlay (triggered by nav hover) ───────────── */}
      <div className={`fixed inset-0 z-[95] transition-all duration-700 pointer-events-none ${isBlurred ? 'backdrop-blur-[64px] bg-black/80 opacity-100' : 'backdrop-blur-0 opacity-0'}`} />
      
      {isBlurred && (
        <div className="fixed inset-0 flex items-center justify-center z-[96] pointer-events-none text-center px-6">
          <h2 className="text-[12vw] font-black italic uppercase tracking-tighter text-white animate-in zoom-in-95 duration-700 leading-none">{hoverLabel}</h2>
        </div>
      )}

      {/* ── Missing-transaction gaps modal ──────────────────────────────── */}
      <OnboardingGapsModal
        userId={userId}
        isOpen={showGaps}
        onClose={() => setShowGaps(false)}
        onComplete={() => { 
          setShowGaps(false); 
          refreshTransactions();
          refreshBalances();
        }}
        inlineGaps={gapsData}
        inlineTotalAccounts={totalAccountsData}
      />

      {/* ── Session onboarding (first-run or manual trigger) ────────────── */}
      {showOnboarding && (
        <SessionOnboarding
          userId={userId}
          sinceDate={sinceDate} setSinceDate={setSinceDate}
          untilDate={untilDate} setUntilDate={setUntilDate}
          onExecute={handleInitialize} syncing={syncing}
        />
      )}

      {/* ── Settings panel (full-screen overlay) ────────────────────────── */}
      {showSettings && (
        <div className="fixed inset-0 z-[90] overflow-y-auto pointer-events-auto bg-[#050608]">
          <Settings
            userId={userId}
            onBack={closeSettings}
            onLogout={onLogout}
            transactions={transactions}
            onDataChanged={refreshBalances}
            onAliasesChanged={refreshTransactions}
          />
        </div>
      )}

      {/* ─── Main scrollable content ──────────────────────────────────── */}
      <main 
        ref={mainRef} 
        onScroll={handleScroll}
        className={`h-screen overflow-y-auto will-change-transform pb-24 ${
          isBlurred ? 'scale-[0.92] opacity-5 transition-all duration-700' : 'scale-100 opacity-100'
        }`}
        style={{ backfaceVisibility: 'hidden' }}
      >
        {/* Top bar with audit controls, sync, exec toggle */}
        <DashboardHeader
          sinceDate={sinceDate} untilDate={untilDate}
          onNewAudit={() => setShowOnboarding(true)}
          execMode={execMode}
          onToggleExec={() => setExecMode(prev => !prev)}
          onSync={handleSync}
          syncing={syncing}
        />

        <div className="p-4 sm:p-8 max-w-[1700px] mx-auto space-y-6 sm:space-y-10">

          {/* ─── Hero section ─────────────────────────────────────────── */}
          {/* Shows aggregate liquidity, total inflow, account count, total outflow */}
          <section className="space-y-4 text-center flex flex-col items-center w-full">
            <div className="flex items-center gap-3">
              <div className="w-2 h-2 bg-indigo-500 rounded-full animate-pulse" />
              <p className="text-[11px] font-black uppercase tracking-[0.5em] text-white/50">
                {execMode && activeTab === 'dashboard' ? 'Executive View' : 'The Mirror'}
              </p>
            </div>
            {activeTab === 'dashboard' && (
              <>
                <h1 className="text-[10vw] sm:text-[7.5vw] font-black tracking-tighter italic tabular-nums leading-none text-center w-full max-w-[90vw] sm:max-w-none break-all truncate sm:truncate-none px-2">
                  {fmt(aggregateLiquidity)}
                </h1>
                <div className="flex flex-col sm:flex-row items-center justify-center gap-3 sm:gap-12 text-sm pt-2 w-full sm:w-auto">
                  <div className="flex flex-col items-center gap-1">
                    <span className="text-[10px] font-black uppercase tracking-widest text-white">Inflow</span>
                    <span className="text-emerald-400 font-black font-mono text-lg sm:text-xl">+{fmt(totalIn)}</span>
                  </div>
                  <div className="w-12 sm:w-[1px] h-[1px] sm:h-12 bg-white/5" />
                  <div className="flex flex-col items-center gap-1">
                    <span className="text-[10px] font-black uppercase tracking-widest text-white">Accounts</span>
                    <span className="text-indigo-400 font-black font-mono text-lg sm:text-xl">{displayBalances.length}</span>
                  </div>
                  <div className="w-12 sm:w-[1px] h-[1px] sm:h-12 bg-white/5" />
                  <div className="flex flex-col items-center gap-1">
                    <span className="text-[10px] font-black uppercase tracking-widest text-white">Outflow</span>
                    <span className="text-rose-400 font-black font-mono text-lg sm:text-xl">-{fmt(totalOut)}</span>
                  </div>
                </div>
              </>
            )}
          </section>

          {/* ─── Executive dashboard (high-level summary charts) ─────────── */}
          {activeTab === 'dashboard' && execMode && (
            <ExecutiveDashboard transactions={aliasedTransactions} />
          )}

          {activeTab === 'dashboard' && !execMode && (
            <>
              {/* ─── Bank card carousel ───────────────────────────────── */}
              <div className="relative group/scroll">
                <div className="flex gap-6 overflow-x-auto pb-8 scrollbar-hide px-2 items-center">
                  {/* Show inline "Add Account" card only when there are >3 cards to keep UI clean */}
                  {displayBalances.length > 3 && <AddManualCard onAdd={handleAddAccount} />}
                  {displayBalances.map((b, i) => (
                    <BankCard
                      key={i}
                      bank={b.bank}
                      account_last4={b.account_last4}
                      balance={b.balance}
                      last_updated={b.last_updated}
                      // Toggle bank filter on click; clicking active bank resets to "all"
                      onClick={() => setBankFilter(prev => prev === b.bank ? 'all' : b.bank)}
                      totalCredit={aliasedTransactions.filter(t => t.bank === b.bank && t.tx_type === 'credit').reduce((s, t) => s + t.amount, 0)}
                      totalDebit={aliasedTransactions.filter(t => t.bank === b.bank && t.tx_type === 'debit').reduce((s, t) => s + t.amount, 0)}
                      colorIndex={allBankColors[b.bank]}
                      allBankColors={allBankColors}
                      onColorChange={handleBankColorChange}
                      usedColorIndices={usedColorIndices}
                    />
                  ))}
                  <AddManualCard onAdd={handleAddAccount} />
                  {/* Spacer to allow last card to scroll past viewport edge */}
                  <div className="w-64 shrink-0" />
                </div>
                {/* Right fade overlay for visual polish on overflow */}
                <div className="absolute top-0 right-0 h-full w-48 bg-gradient-to-l from-[#050608] via-[#050608]/80 to-transparent pointer-events-none z-20" />
              </div>

              {/* ═══ ALL ALIASED VIEW (COVER FLOW) ═══ */}
              {/* When every visible transaction has been aliased, show an
                  interactive cover-flow grouped by alias instead of the raw audit trail */}
              {allTransactionsAliased && aliasSummaryGroups.length > 0 ? (
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 sm:gap-10 lg:gap-16 pt-4 items-start">
                  {/* Left Column: Infinite Carousel */}
                  <div className="lg:col-span-2 flex flex-col">
                    <div className="flex items-center justify-between flex-wrap gap-4 mb-6">
                      <div className="flex items-center gap-3">
                        <CheckCircle2 size={16} className="text-emerald-400" />
                        <div>
                          <h3 className="text-[10px] font-black uppercase tracking-[0.3em] text-emerald-400">All Transactions Categorized</h3>
                          <p className="text-[8px] text-slate-500 font-black uppercase tracking-wider mt-0.5">
                            {aliasedTransactions.length} transactions · {aliasSummaryGroups.length} categories
                          </p>
                        </div>
                      </div>
                    </div>

                    <div className="relative group/scroll w-full overflow-hidden">
                      <div 
                        ref={scrollRef}
                        onScroll={handleCarouselScroll}
                        className="flex gap-6 overflow-x-auto scrollbar-hide px-[calc(50%-100px)] py-10 snap-x snap-mandatory"
                      >
                        {aliasSummaryGroups.map((group, idx) => {
                          const isActive = idx === activeCardIndex;
                          const catStyle = CATEGORY_COLORS[group.category] || CATEGORY_COLORS.General;

                          // Compute hover background tint based on category
                          const bgTint = group.category === 'Transfer' ? 'hover:bg-indigo-500/20' : 
                                         group.category === 'Utilities' ? 'hover:bg-orange-500/20' :
                                         group.category === 'Food' ? 'hover:bg-rose-500/20' :
                                         group.category === 'Shopping' ? 'hover:bg-pink-500/20' :
                                         group.category === 'Salary' ? 'hover:bg-emerald-500/20' :
                                         group.category === 'Transport' ? 'hover:bg-cyan-500/20' :
                                         group.category === 'Entertainment' ? 'hover:bg-purple-500/20' :
                                         group.category === 'Health' ? 'hover:bg-red-500/20' :
                                         group.category === 'Education' ? 'hover:bg-blue-500/20' :
                                         group.category === 'Fuel' ? 'hover:bg-yellow-500/20' :
                                         group.category === 'Data & Airtime' ? 'hover:bg-teal-500/20' :
                                         group.category === 'Family' ? 'hover:bg-pink-500/20' :
                                         group.category === 'Business' ? 'hover:bg-indigo-500/20' : 'hover:bg-slate-500/20';

                          // Compute text color based on category
                          const textColor = group.category === 'Transfer' ? 'text-indigo-400' : 
                                            group.category === 'Utilities' ? 'text-orange-400' :
                                            group.category === 'Food' ? 'text-rose-400' :
                                            group.category === 'Shopping' ? 'text-pink-400' :
                                            group.category === 'Salary' ? 'text-emerald-400' :
                                            group.category === 'Transport' ? 'text-cyan-400' :
                                            group.category === 'Entertainment' ? 'text-purple-400' :
                                            group.category === 'Health' ? 'text-red-400' :
                                            group.category === 'Education' ? 'text-blue-400' :
                                            group.category === 'Fuel' ? 'text-yellow-400' :
                                            group.category === 'Data & Airtime' ? 'text-teal-400' :
                                            group.category === 'Family' ? 'text-pink-400' :
                                            group.category === 'Business' ? 'text-indigo-400' : 'text-slate-400';

                          return (
                            <button
                              key={`${group.name}-${idx}`}
                              onClick={() => setActiveTab('history')}
                              className={`flex-shrink-0 w-[200px] h-[250px] rounded-[2.5rem] bg-[#0a0c10] border border-white/5 flex flex-col items-center justify-center gap-6 cursor-pointer transition-all duration-500 ease-out snap-center ${bgTint} ${
                                isActive 
                                  ? 'scale-110 z-10 opacity-100 shadow-2xl border-white/20' 
                                  : 'scale-90 z-0 opacity-40 hover:scale-100 hover:opacity-80'
                              }`}
                            >
                              <div className={`w-9 h-9 rounded-2xl flex items-center justify-center ${catStyle}`}>
                                <FolderOpen size={16} />
                              </div>
                              <div className="text-center px-4 space-y-2 w-full">
                                <h4
                                  // Detect text overflow to reduce font size on wrapped alias names
                                  ref={(el) => {
                                    if (!el || wrappedMeasuredRef.current[idx] !== undefined) return;
                                    wrappedMeasuredRef.current[idx] = true;
                                    if (el.scrollHeight > el.clientHeight) {
                                      setWrappedCards(prev => ({ ...prev, [idx]: true }));
                                    }
                                  }}
                                  className={`${wrappedCards[idx] ? 'text-[11px]' : 'text-sm'} font-black text-white leading-tight break-words line-clamp-3`}
                                >
                                  {group.name}
                                </h4>
                                <p className={`text-[7px] font-black uppercase tracking-widest ${textColor} truncate w-full`}>
                                  {group.category}
                                </p>
                              </div>
                              <div className="mt-4 text-center space-y-1">
                                <p className="text-base font-black tabular-nums text-white">{fmt(Math.abs(group.total))}</p>
                                <p className="text-[6px] text-slate-500 font-black uppercase tracking-wider">
                                  {group.count} tx{group.count !== 1 ? 's' : ''}
                                </p>
                              </div>
                            </button>
                          );
                        })}
                      </div>
                      {/* Edge fade gradients for carousel overflow */}
                      <div className="absolute top-0 left-0 h-full w-24 bg-gradient-to-r from-[#050608] to-transparent pointer-events-none z-20" />
                      <div className="absolute top-0 right-0 h-full w-24 bg-gradient-to-l from-[#050608] to-transparent pointer-events-none z-20" />
                    </div>
                  </div>

                  {/* Right Column: Volume Logic (Always Visible) */}
                  <div className="flex flex-col h-full">
                    <h3 className="text-[10px] font-black uppercase tracking-[0.3em] opacity-80 text-white mb-6">Volume Logic</h3>
                    <div className="flex-1 h-full">
                      <SpendChart transactions={aliasedTransactions} />
                    </div>
                  </div>
                </div>
              ) : (
                /* ═══ NORMAL VIEW ═══ */
                <div className={`grid grid-cols-1 lg:grid-cols-3 gap-6 sm:gap-10 lg:gap-16 pt-4 ${auditExpanded ? 'items-start' : 'items-stretch'}`}>
                  <div className={`lg:col-span-2 flex flex-col ${auditExpanded ? '' : 'h-full'}`}>
                    <div className="flex items-center justify-between flex-wrap gap-4 mb-6">
                      <h3 className="text-[10px] font-black uppercase tracking-[0.3em] opacity-80 text-white">Audit Trail</h3>
                      <BankFilterBar />
                    </div>
                    <div className={`bg-[#0a0c10]/40 rounded-2xl sm:rounded-[3.5rem] border border-white/5 p-4 sm:p-8 ${auditExpanded ? '' : 'flex-1 h-full'}`}>
                      <MLGroupView 
                        transactions={filteredTx}
                        userId={userId}
                        onAliasUpdate={refreshTransactions}
                        onViewChange={setAuditExpanded}
                        userBankColors={allBankColors}
                        colorOptions={COLOR_OPTIONS}
                      />
                    </div>
                  </div>
                  <div className={`flex flex-col ${auditExpanded ? '' : 'h-full'}`}>
                    <h3 className="text-[10px] font-black uppercase tracking-[0.3em] opacity-80 text-white mb-6">Volume Logic</h3>
                    <div className="flex-1 h-full">
                      <SpendChart transactions={aliasedTransactions} />
                    </div>
                  </div>
                </div>
              )}
            </>
          )}

          {/* ─── Tab-based sub-views ───────────────────────────────────── */}
          <div className={activeTab === 'ask' ? '' : 'hidden'}>
            <AgentChat userId={userId} />
          </div>
          {activeTab === 'insights' && <InsightsPanel userId={userId} />}

          {/* ─── History / audit-feed tab ──────────────────────────────── */}
          {activeTab === 'history' && (
            <div className="space-y-6">
              <div className="flex items-center justify-between flex-wrap gap-4">
                <h3 className="text-xs font-black uppercase tracking-[0.3em] opacity-20 text-white">Audit Feed</h3>
                <BankFilterBar />
              </div>
              <div className="bg-[#0a0c10]/40 border border-white/5 rounded-2xl sm:rounded-[3.5rem] p-4 sm:p-8 max-w-5xl mx-auto min-h-[420px]">
                <MLGroupView 
                  transactions={filteredTx}
                  userId={userId}
                  onAliasUpdate={refreshTransactions}
                  userBankColors={allBankColors}
                  colorOptions={COLOR_OPTIONS}
                />
              </div>
            </div>
          )}
        </div>
      </main>

      {/* ─── Fixed bottom navigation bar ───────────────────────────────── */}
      {/* Becomes fully opaque once user has scrolled past 30px threshold */}
      <nav className={`fixed bottom-3 sm:bottom-6 left-1/2 -translate-x-1/2 z-[100] flex items-center gap-0.5 sm:gap-3 p-1.5 sm:p-4 bg-[#0a0c10]/80 backdrop-blur-3xl border border-white/10 rounded-full shadow-2xl transition-all duration-500 ${scrolled ? 'opacity-100' : 'opacity-20 hover:opacity-100'}`}>
        <FloatingNavItem 
          icon={<LayoutDashboard size={18} />} 
          label="The Mirror"
          active={activeTab === 'dashboard' && !showSettings}
          onMouseEnter={() => handleMouseEnter('The Mirror')}
          onMouseLeave={handleMouseLeave}
          onClick={() => { setActiveTab('dashboard'); setShowSettings(false); handleMouseLeave(); }} 
        />
        <FloatingNavItem 
          icon={<MessageSquare size={18} />} 
          label="Ask Mirror"
          active={activeTab === 'ask' && !showSettings}
          onMouseEnter={() => handleMouseEnter('Ask Mirror')}
          onMouseLeave={handleMouseLeave}
          onClick={() => { setActiveTab('ask'); setShowSettings(false); handleMouseLeave(); }} 
        />
        <FloatingNavItem 
          icon={<Brain size={18} />} 
          label="Insights"
          active={activeTab === 'insights' && !showSettings}
          onMouseEnter={() => handleMouseEnter('Insights')}
          onMouseLeave={handleMouseLeave}
          onClick={() => { setActiveTab('insights'); setShowSettings(false); handleMouseLeave(); }} 
        />
        <FloatingNavItem 
          icon={<History size={18} />} 
          label="Audit Feed"
          active={activeTab === 'history' && !showSettings}
          onMouseEnter={() => handleMouseEnter('Audit Feed')}
          onMouseLeave={handleMouseLeave}
          onClick={() => { setActiveTab('history'); setShowSettings(false); handleMouseLeave(); }} 
        />
        <FloatingNavItem 
          icon={<LucideSettings size={18} />} 
          label="Settings"
          active={showSettings}
          onMouseEnter={() => handleMouseEnter('Settings')}
          onMouseLeave={handleMouseLeave}
          onClick={() => { setShowSettings(true); handleMouseLeave(); }} 
        />
        <div className="w-[1px] h-6 sm:h-8 bg-white/10 mx-1 sm:mx-2" />
        <button onClick={onLogout} className="p-3 sm:p-5 text-red-500/40 hover:text-red-500 transition-all rounded-full">
          <LogOut size={18} />
        </button>
      </nav>
    </div>
  );
}
