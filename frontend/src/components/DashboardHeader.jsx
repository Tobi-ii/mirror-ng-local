import React from 'react';
import { Calendar, RefreshCw, RotateCw } from 'lucide-react';

export default function DashboardHeader({ sinceDate, untilDate, onNewAudit, execMode, onToggleExec, onSync, syncing }) {
  return (
    <header className="sticky top-0 z-40 bg-[#050608]/40 backdrop-blur-2xl px-4 sm:px-12 py-3 sm:py-4 flex justify-between items-center border-b border-white/5">
      <div className="flex items-center gap-2 sm:gap-4 min-w-0">
        <div className="w-8 h-8 sm:w-10 sm:h-10 bg-white rounded-xl flex items-center justify-center font-black italic text-black shrink-0">M</div>
        <span className="font-black text-lg sm:text-2xl tracking-tighter italic uppercase truncate">Mirror.ng</span>
      </div>

      <div className="flex items-center gap-2 sm:gap-4">
        <div className="hidden md:flex items-center gap-3 px-6 py-3 bg-white/5 rounded-full border border-white/10">
          <Calendar size={14} className="text-indigo-500" />
          <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">
            {sinceDate} — {untilDate || 'PRESENT'}
          </span>
        </div>

        <button
          onClick={onToggleExec}
          className={`text-[8px] sm:text-[10px] font-black uppercase tracking-widest px-3 sm:px-4 py-2 sm:py-2.5 rounded-full border transition-all whitespace-nowrap ${
            execMode
              ? 'bg-indigo-600 border-indigo-600 text-white shadow-lg shadow-indigo-600/20'
              : 'border-white/10 text-slate-500 hover:text-white hover:border-white/30'
          }`}
        >
          {execMode ? '✦ Executive' : 'Executive'}
        </button>

        <button
          onClick={onSync}
          disabled={syncing}
          className="text-slate-500 hover:text-white text-[8px] sm:text-[10px] font-black uppercase tracking-[0.2em] sm:tracking-[0.3em] flex items-center gap-1 sm:gap-2 transition-all whitespace-nowrap"
        >
          <RotateCw size={12} className={`sm:size-[14px] ${syncing ? 'animate-spin' : ''}`} /> Sync
        </button>
        <button
          onClick={onNewAudit}
          className="text-slate-500 hover:text-white text-[8px] sm:text-[10px] font-black uppercase tracking-[0.2em] sm:tracking-[0.3em] flex items-center gap-1 sm:gap-2 transition-all whitespace-nowrap"
        >
          <RefreshCw size={12} className="sm:size-[14px]" /> <span className="hidden sm:inline">New </span>Audit
        </button>
      </div>
    </header>
  );
}