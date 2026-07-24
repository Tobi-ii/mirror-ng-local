/**
 * SessionOnboarding — full-screen modal wizard for initializing a mirror session.
 *
 * Props:
 *   userId        — target user for the background sync job
 *   sinceDate     — (optional) externally controlled audit start date
 *   setSinceDate  — callback to sync sinceDate upstream
 *   untilDate     — (optional) externally controlled audit end date
 *   setUntilDate  — callback to sync untilDate upstream
 *   onExecute(skip, accounts, result) — fires on completion / skip
 *   syncing       — (optional) external syncing flag (parent-driven)
 *
 * Key local state:
 *   accounts[i] — { bank, account_last4, balance }  (max 4)
 *   syncing     — true while background sync is in progress
 *   progress    — 0–100 from the sync job status API
 *   progressMsg — human-readable message from the job
 *
 * Renders:
 *   A dark, centered modal with date-range pickers, opening-balance
 *   account rows, a progress bar (during sync), and two action buttons.
 */

import React, { useState, useEffect, useRef } from 'react';
import { Plus, Trash2, Calendar, Loader2 } from 'lucide-react';
import CustomSelect from './CustomSelect';
import { api } from '../services/api';

// ─── SUPPORTED FINANCIAL INSTITUTIONS ───
// Used in the bank dropdown for each opening-balance row.
const SUPPORTED_BANKS = [
  'Sterling Bank', 'Wema (ALAT)', 'GTBank', 'Access Bank',
  'First Bank', 'Kuda', 'OPay', 'Moniepoint', 'PalmPay',
  'Piggyvest', 'Cowrywise', 'Other',
];

const getTodayDate = () => {
  const today = new Date();
  return today.toISOString().split('T')[0];
};

const getThirtyDaysAgo = () => {
  const date = new Date();
  date.setDate(date.getDate() - 30);
  return date.toISOString().split('T')[0];
};

export default function SessionOnboarding({
  userId,
  sinceDate: externalSinceDate,
  setSinceDate: externalSetSinceDate,
  untilDate: externalUntilDate,
  setUntilDate: externalSetUntilDate,
  onExecute,
  syncing: externalSyncing,
}) {
  const [sinceDate, setSinceDate] = useState(externalSinceDate || getThirtyDaysAgo());
  const [untilDate, setUntilDate] = useState(getTodayDate());
  const [accounts, setAccounts] = useState([
    { bank: 'Sterling Bank', account_last4: '', balance: '' }
  ]);

  // ─── BACKGROUND SYNC POLLING STATE ───
  // pollRef holds the setInterval handle so it can be cleared on unmount.
  // isSyncing merges local + external flags to keep the UI in sync.
  const [syncing, setSyncing] = useState(false);
  const [progress, setProgress] = useState(0);
  const [progressMsg, setProgressMsg] = useState('');
  const pollRef = useRef(null);

  const isSyncing = syncing || externalSyncing;

  // Initialise untilDate to today on mount, and push it upstream so the
  // parent calendar view also respects the same boundary.
  useEffect(() => {
    const today = getTodayDate();
    setUntilDate(today);
    if (externalSetUntilDate) externalSetUntilDate(today);
  }, []);

  // Sync local sinceDate changes back to the parent component.
  useEffect(() => {
    if (externalSetSinceDate) externalSetSinceDate(sinceDate);
  }, [sinceDate, externalSetSinceDate]);

  // Sync local untilDate changes back to the parent component.
  useEffect(() => {
    if (externalSetUntilDate) externalSetUntilDate(untilDate);
  }, [untilDate, externalSetUntilDate]);

  // Teardown: clear the polling interval if the component unmounts mid-sync.
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  // ─── ACCOUNT ROW MANAGEMENT ───

  /** Append a new blank account row (cap of 4). */
  const addAccount = () => {
    if (accounts.length >= 4) return;
    setAccounts(prev => [...prev, { bank: 'Sterling Bank', account_last4: '', balance: '' }]);
  };

  /** Remove the account row at index i. */
  const removeAccount = (i) => {
    setAccounts(prev => prev.filter((_, idx) => idx !== i));
  };

  /** Update a single field on the account row at index i. */
  const updateAccount = (i, field, value) => {
    setAccounts(prev => prev.map((a, idx) => idx === i ? { ...a, [field]: value } : a));
  };

  // ─── ONBOARDING FLOW: EXECUTE / SKIP ───
  //
  // Two entry points:
  //   1. "Skip to Stateless Audit" — calls onExecute(true, []) immediately.
  //   2. "Execute Session Audit"   — validates accounts, fires a background
  //      sync job, then polls for completion via setInterval (2 s).
  //
  // The polling loop drives the progress bar and fires onExecute once the
  // job reaches a terminal state (completed / failed).

  /**
   * Kick off the onboarding flow.
   * @param {boolean} isSkip — if true, bypass sync entirely.
   * @param {Array}   accts  — raw account rows to validate and send.
   */
  const handleExecute = async (isSkip, accts) => {
    if (isSkip) {
      onExecute(true, []);
      return;
    }

    // Filter out accounts with zero or empty balance; default last4 to '0000'.
    const validAccounts = accts
      .filter(a => a.balance && parseFloat(a.balance) > 0)
      .map(a => ({ bank: a.bank, account_last4: a.account_last4 || '0000', balance: parseFloat(a.balance) }));

    setSyncing(true);
    setProgress(5);
    setProgressMsg('Starting sync...');

    try {
      const res = await api.syncBackground(userId, {
        since_date: sinceDate,
        until_date: untilDate,
        opening_balances: validAccounts,
      });

      if (!res?.job_id) {
        console.error('Failed to start background sync:', res);
        setSyncing(false);
        return;
      }

      const jobId = res.job_id;

      // Poll every 2 seconds until the job completes or fails.
      pollRef.current = setInterval(async () => {
        try {
          const status = await api.getSyncStatus(jobId);
          setProgress(status.progress || 0);
          setProgressMsg(status.message || '');

          if (status.status === 'completed') {
            clearInterval(pollRef.current);
            pollRef.current = null;
            setSyncing(false);
            onExecute(false, [], status.result);
          } else if (status.status === 'failed') {
            clearInterval(pollRef.current);
            pollRef.current = null;
            setSyncing(false);
            console.error('Background sync failed:', status.message);
            onExecute(false, []);
          }
        } catch (e) {
          console.error('Error polling sync status:', e);
        }
      }, 2000);
    } catch (e) {
      console.error('Error starting background sync:', e);
      setSyncing(false);
    }
  };

  // ─── DATE CHANGE HANDLERS ───
  // Enforce constraint: sinceDate cannot exceed untilDate, and untilDate
  // cannot exceed today.  If the user drags sinceDate past untilDate, the
  // untilDate resets to today to keep the range valid.

  const handleSinceDateChange = (e) => {
    const newDate = e.target.value;
    setSinceDate(newDate);
    if (newDate > untilDate) {
      const today = getTodayDate();
      setUntilDate(today);
    }
  };

  const handleUntilDateChange = (e) => {
    const newDate = e.target.value;
    const today = getTodayDate();
    if (newDate > today) {
      setUntilDate(today);
    } else {
      setUntilDate(newDate);
    }
  };

  // ─── DERIVED DISPLAY VALUES ───
  // Compute total opening balance for the header summary, and format it
  // in Nigerian Naira with the en-NG locale.

  const totalOpening = accounts.reduce((s, a) => s + (parseFloat(a.balance) || 0), 0);
  const fmt = (n) => `₦${Number(n).toLocaleString('en-NG', { minimumFractionDigits: 2 })}`;
  const todayDate = getTodayDate();

  return (
    <div className="fixed inset-0 z-[110] bg-[#050608] flex items-center justify-center p-4 sm:p-6 overflow-y-auto">
      <div className="max-w-3xl w-full my-4">

        {/* ─── HEADER: TITLE + OPENING BALANCE SUMMARY ─── */}
        <div className="text-center mb-6 sm:mb-8">
          <h2 className="text-3xl sm:text-5xl font-black italic tracking-tighter uppercase">Initialize Mirror</h2>
          <p className="text-slate-500 text-[8px] sm:text-[10px] font-black uppercase tracking-[0.3em] sm:tracking-[0.5em] mt-2">
            Frame your financial reality
          </p>
          {totalOpening > 0 && (
            <p className="text-2xl sm:text-3xl font-black italic text-white tabular-nums mt-3">{fmt(totalOpening)}</p>
          )}
        </div>

        <div className="bg-[#0a0c10] border border-white/10 p-4 sm:p-8 rounded-2xl sm:rounded-[3rem] shadow-2xl space-y-5 sm:space-y-6">

          {/* ─── DATE RANGE PICKERS ─── */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4">
            <div className="space-y-1 sm:space-y-2">
              <label className="text-[8px] sm:text-[9px] font-black uppercase text-white tracking-widest ml-2">Audit Start</label>
              <div className="relative">
                <input
                  type="date"
                  value={sinceDate}
                  onChange={handleSinceDateChange}
                  max={untilDate}
                  disabled={isSyncing}
                  className="w-full bg-white/5 border border-white/10 px-3 sm:px-4 py-2.5 sm:py-3 rounded-xl sm:rounded-2xl text-white outline-none font-bold text-xs sm:text-sm appearance-none [color-scheme:dark] transition-all disabled:opacity-40"
                />
                <Calendar size={12} className="sm:size-[14px] absolute right-3 sm:right-4 top-1/2 -translate-y-1/2 text-purple-400/60 pointer-events-none" />
              </div>
            </div>
            <div className="space-y-1 sm:space-y-2">
              <label className="text-[8px] sm:text-[9px] font-black uppercase text-white tracking-widest ml-2">
                Audit End
                <span className="text-purple-400 ml-1">· Today</span>
              </label>
              <div className="relative">
                <input
                  type="date"
                  value={untilDate}
                  onChange={handleUntilDateChange}
                  min={sinceDate}
                  max={todayDate}
                  disabled={isSyncing}
                  className="w-full bg-white/5 border border-white/10 px-3 sm:px-4 py-2.5 sm:py-3 rounded-xl sm:rounded-2xl text-white outline-none font-bold text-xs sm:text-sm appearance-none [color-scheme:dark] transition-all disabled:opacity-40"
                />
                <Calendar size={12} className="sm:size-[14px] absolute right-3 sm:right-4 top-1/2 -translate-y-1/2 text-purple-400/60 pointer-events-none" />
              </div>
              <p className="text-[7px] sm:text-[8px] text-slate-600 text-right mt-0.5 sm:mt-1">Max: {todayDate} (today)</p>
            </div>
          </div>

          {/* ─── OPENING BALANCE ACCOUNT ROWS ─── */}
          {/* Each row: bank dropdown | last-4 digits | balance input | delete.
              New rows can be added up to a max of 4 via the "Add Another Account" button. */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <label className="text-[9px] font-black uppercase text-white tracking-widest">Opening Balances</label>
              <span className="text-[9px] text-slate-700 italic">Max 4 accounts</span>
            </div>

            {accounts.map((account, i) => (
              <div key={i} className="grid grid-cols-12 gap-3 items-center mb-3">
                <div className="col-span-5">
                  <CustomSelect
                    value={account.bank}
                    onChange={(val) => updateAccount(i, 'bank', val)}
                    options={SUPPORTED_BANKS}
                    placeholder="Select bank"
                  />
                </div>
                <div className="col-span-3">
                  <input
                    type="text"
                    maxLength="4"
                    placeholder="Last 4"
                    value={account.account_last4}
                    onChange={(e) => updateAccount(i, 'account_last4', e.target.value.replace(/\D/g,'').slice(-4))}
                    disabled={isSyncing}
                    className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500 focus:border-indigo-500 outline-none text-center disabled:opacity-40"
                  />
                </div>
                <div className="col-span-3 relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 text-sm">₦</span>
                  <input
                    type="number"
                    placeholder="0.00"
                    value={account.balance}
                    onChange={(e) => updateAccount(i, 'balance', parseFloat(e.target.value) || '')}
                    disabled={isSyncing}
                    className="w-full bg-white/5 border border-white/10 rounded-lg pl-7 pr-3 py-2 text-sm text-white placeholder-slate-500 focus:border-indigo-500 outline-none disabled:opacity-40"
                  />
                </div>
                <div className="col-span-1 flex justify-center">
                  {accounts.length > 1 ? (
                    <button onClick={() => removeAccount(i)}
                      disabled={isSyncing}
                      className="text-slate-500 hover:text-red-400 transition-colors disabled:opacity-30">
                      <Trash2 size={16} />
                    </button>
                  ) : <div />}
                </div>
              </div>
            ))}

            {accounts.length < 4 && (
              <button onClick={addAccount} disabled={isSyncing}
                className="flex items-center gap-2 text-[9px] font-black uppercase tracking-widest text-purple-400 hover:text-purple-300 transition-colors mt-2 disabled:opacity-30">
                <Plus size={12} /> Add Another Account
              </button>
            )}
          </div>

          {/* ─── SYNC PROGRESS BAR ─── */}
          {/* Visible only while isSyncing is true. Driven by the 2-second
              poll loop in handleExecute reading getSyncStatus(jobId). */}
          {isSyncing && (
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-purple-400">
                <Loader2 size={14} className="animate-spin" />
                <span className="text-[9px] font-black uppercase tracking-widest">Syncing</span>
              </div>
              <div className="w-full bg-white/5 rounded-full h-2 overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-purple-500 to-indigo-500 rounded-full transition-all duration-500 ease-out"
                  style={{ width: `${Math.min(progress, 100)}%` }}
                />
              </div>
              <p className="text-[8px] text-slate-500 font-mono">
                {progressMsg || `${Math.round(progress)}%`}
              </p>
            </div>
          )}

          {/* ─── ACTION BUTTONS ─── */}
          {/* Primary: "Execute Session Audit"  — validates accounts & starts sync.
              Secondary: "Skip to Stateless Audit" — bypasses balance collection. */}
          <div className="flex flex-col gap-2 sm:gap-3 pt-2">
            <button
              onClick={() => handleExecute(false, accounts)}
              disabled={isSyncing}
              className="w-full py-4 sm:py-5 bg-white text-black font-black rounded-full uppercase italic text-sm sm:text-base hover:bg-purple-600 hover:text-white transition-all active:scale-[0.98] disabled:opacity-50"
            >
              {isSyncing ? 'Reconstructing Feed...' : 'Execute Session Audit'}
            </button>
            <button
              onClick={() => handleExecute(true, [])}
              disabled={isSyncing}
              className="w-full py-2.5 sm:py-3 text-slate-500 font-black rounded-full uppercase text-[8px] sm:text-[9px] tracking-[0.2em] sm:tracking-[0.3em] hover:text-white transition-all disabled:opacity-50"
            >
              Skip to Stateless Audit
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
