// components/BankCard.jsx
import { useState, useRef, useEffect } from 'react';
import { CreditCard, TrendingUp, TrendingDown } from 'lucide-react';

export const BANK_COLORS = {
  'Sterling Bank': {
    gradient: 'from-red-900 to-red-800',     // Wine / Burgundy
    bg: 'hover:bg-red-950/20',
    creditIcon: 'bg-emerald-500/10 text-emerald-400',
    debitIcon: 'bg-red-500/10 text-red-400',
    defaultHex: '#991B1B'
  },
  'Wema (ALAT)': {
    gradient: 'from-rose-600 to-pink-700',   // Red / Rose
    bg: 'hover:bg-rose-950/20',
    creditIcon: 'bg-emerald-500/10 text-emerald-400',
    debitIcon: 'bg-rose-500/10 text-rose-400',
    defaultHex: '#E11D48'
  },
  'Wema Bank': {
    gradient: 'from-rose-600 to-pink-700',
    bg: 'hover:bg-rose-950/20',
    creditIcon: 'bg-emerald-500/10 text-emerald-400',
    debitIcon: 'bg-rose-500/10 text-rose-400',
    defaultHex: '#E11D48'
  },
  'Kuda': {
    gradient: 'from-purple-600 to-indigo-800', // Purple
    bg: 'hover:bg-purple-950/20',
    creditIcon: 'bg-emerald-500/10 text-emerald-400',
    debitIcon: 'bg-purple-500/10 text-purple-400',
    defaultHex: '#9333EA'
  },
  'GTBank': {
    gradient: 'from-orange-500 to-amber-600',
    bg: 'hover:bg-orange-950/20',
    creditIcon: 'bg-emerald-500/10 text-emerald-400',
    debitIcon: 'bg-orange-500/10 text-orange-400',
    defaultHex: '#F97316'
  },
  'Access Bank': {
    gradient: 'from-blue-700 to-blue-900',
    bg: 'hover:bg-blue-950/20',
    creditIcon: 'bg-emerald-500/10 text-emerald-400',
    debitIcon: 'bg-blue-500/10 text-blue-400',
    defaultHex: '#1D4ED8'
  },
  'OPay': {
    gradient: 'from-emerald-500 to-teal-600', // Green
    bg: 'hover:bg-emerald-950/20',
    creditIcon: 'bg-emerald-500/10 text-emerald-400',
    debitIcon: 'bg-emerald-500/10 text-emerald-400',
    defaultHex: '#10B981'
  },
  'Moniepoint': {
    gradient: 'from-sky-500 to-blue-600',
    bg: 'hover:bg-sky-950/20',
    creditIcon: 'bg-emerald-500/10 text-emerald-400',
    debitIcon: 'bg-sky-500/10 text-sky-400',
    defaultHex: '#0EA5E9'
  },
  'Piggyvest': {
    gradient: 'from-violet-600 to-purple-800',
    bg: 'hover:bg-violet-950/20',
    creditIcon: 'bg-emerald-500/10 text-emerald-400',
    debitIcon: 'bg-violet-500/10 text-violet-400',
    defaultHex: '#7C3AED'
  },
  'Cowrywise': {
    gradient: 'from-fuchsia-600 to-pink-700',
    bg: 'hover:bg-fuchsia-950/20',
    creditIcon: 'bg-emerald-500/10 text-emerald-400',
    debitIcon: 'bg-fuchsia-500/10 text-fuchsia-400',
    defaultHex: '#C026D3'
  },
  'PalmPay': {
    gradient: 'from-cyan-500 to-blue-600',
    bg: 'hover:bg-cyan-950/20',
    creditIcon: 'bg-emerald-500/10 text-emerald-400',
    debitIcon: 'bg-cyan-500/10 text-cyan-400',
    defaultHex: '#06B6D4'
  },
  'First Bank': {
    gradient: 'from-slate-600 to-slate-800',
    bg: 'hover:bg-slate-800/20',
    creditIcon: 'bg-emerald-500/10 text-emerald-400',
    debitIcon: 'bg-slate-500/10 text-slate-400',
    defaultHex: '#475569'
  },
  'default': {
    gradient: 'from-slate-700 to-slate-900',
    bg: 'hover:bg-slate-900/20',
    creditIcon: 'bg-emerald-500/10 text-emerald-400',
    debitIcon: 'bg-slate-500/10 text-slate-400',
    defaultHex: '#475569'
  }
};

export const COLOR_OPTIONS = [
  { gradient: 'from-emerald-500 to-teal-600', bg: 'bg-emerald-500', hex: '#10b981' },
  { gradient: 'from-purple-600 to-indigo-800', bg: 'bg-purple-600', hex: '#9333ea' },
  { gradient: 'from-orange-500 to-amber-600', bg: 'bg-orange-500', hex: '#f97316' },
  { gradient: 'from-rose-600 to-pink-700', bg: 'bg-rose-500', hex: '#e11d48' },
  { gradient: 'from-blue-700 to-blue-900', bg: 'bg-blue-700', hex: '#1d4ed8' },
  { gradient: 'from-red-900 to-red-800', bg: 'bg-red-900', hex: '#991b1b' },
  { gradient: 'from-sky-500 to-blue-600', bg: 'bg-sky-500', hex: '#0ea5e9' },
  { gradient: 'from-violet-600 to-purple-800', bg: 'bg-violet-600', hex: '#7c3aed' },
  { gradient: 'from-fuchsia-600 to-pink-700', bg: 'bg-fuchsia-600', hex: '#c026d3' },
  { gradient: 'from-cyan-500 to-blue-600', bg: 'bg-cyan-500', hex: '#06b6d4' },
  { gradient: 'from-slate-600 to-slate-800', bg: 'bg-slate-600', hex: '#475569' },
];

export default function BankCard({
  bank,
  balance,
  account_last4,
  last_updated,
  totalCredit = 0,
  totalDebit = 0,
  onClick,
  colorIndex,
  allBankColors = {},
  onColorChange,
  usedColorIndices = new Set(),
}) {
  const theme = BANK_COLORS[bank] || BANK_COLORS.default;
  const defaultGradient = theme.gradient;
  const defaultIdx = COLOR_OPTIONS.findIndex(o => o.gradient === defaultGradient);
  const effectiveIdx = colorIndex !== undefined ? colorIndex : (defaultIdx >= 0 ? defaultIdx : 0);

  const [showPicker, setShowPicker] = useState(false);
  const pickerRef = useRef(null);

  useEffect(() => {
    function handleClickOutside(event) {
      if (pickerRef.current && !pickerRef.current.contains(event.target)) {
        setShowPicker(false);
      }
    }
    if (showPicker) document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showPicker]);

  const togglePicker = (e) => {
    e.stopPropagation();
    setShowPicker(!showPicker);
  };

  const handleColorSelect = (e, idx) => {
    e.stopPropagation();
    if (usedColorIndices.has(idx) && idx !== effectiveIdx) return;
    if (onColorChange) onColorChange(bank, idx);
    setShowPicker(false);
  };

  const fmt = (n) => new Intl.NumberFormat('en-NG', {
    style: 'currency', currency: 'NGN', minimumFractionDigits: 2,
  }).format(n);
  const fmtFlow = (v) => new Intl.NumberFormat('en-NG', {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  }).format(Math.abs(v));
  const fmtDate = (s) => s ? new Date(s).toLocaleDateString('en-NG', {
    day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit',
  }) : '';

  const gradientClass = `bg-gradient-to-br ${COLOR_OPTIONS[effectiveIdx]?.gradient || defaultGradient}`;

  return (
    <div className="relative group w-[220px] sm:w-[260px] md:w-[300px] lg:w-[340px] shrink-0">
      <div
        onClick={onClick}
        className={`rounded-2xl sm:rounded-[2.5rem] ${gradientClass} text-white shadow-2xl flex relative overflow-hidden transition-all duration-500 ease-in-out group-hover:-translate-y-2 group-hover:shadow-indigo-500/20 active:scale-[0.97] cursor-pointer h-40 sm:h-44 md:h-48 lg:h-52`}
      >
        <div className="absolute top-0 right-0 w-40 h-40 bg-white/10 rounded-full -mr-20 -mt-20 blur-3xl group-hover:bg-white/20 transition-all pointer-events-none" />
        <div className="flex-[1.6] p-4 sm:p-5 md:p-6 lg:p-7 flex flex-col justify-between z-10 min-w-0">
          <div className="flex justify-between items-start relative">
            <div ref={pickerRef} className="flex items-center relative">
              <button
                onClick={togglePicker}
                type="button"
                title="Change card colour"
                className={`w-11 h-11 rounded-2xl backdrop-blur-xl flex items-center justify-center border shadow-inner shrink-0 transition-all duration-200 z-30 ${
                  showPicker
                    ? 'bg-white/30 border-white/40 scale-105'
                    : 'bg-white/15 border-white/20 hover:bg-white/25 hover:scale-110 active:scale-95'
                }`}
              >
                <CreditCard size={22} className="opacity-90" />
              </button>
              {showPicker && (
                <div className="absolute left-14 top-0 flex items-center gap-1.5 bg-black/50 backdrop-blur-xl border border-white/10 px-3 py-2 rounded-2xl shadow-2xl animate-in fade-in slide-in-from-left-2 duration-200 z-40 max-w-[130px] sm:max-w-[170px] md:max-w-[210px] overflow-x-auto scrollbar-none">
                  {COLOR_OPTIONS.map((option, idx) => {
                    const isUsed = usedColorIndices.has(idx);
                    const isCurrent = idx === effectiveIdx;
                    const disabled = isUsed && !isCurrent;
                    return (
                      <button
                        key={idx}
                        onClick={(e) => { if (!disabled) handleColorSelect(e, idx); }}
                        type="button"
                        disabled={disabled}
                        title={disabled ? "Already used by another bank" : `Set colour to ${option.gradient}`}
                        className={`w-5 h-5 rounded-full shrink-0 transition-all duration-150 hover:scale-125 active:scale-90 border ${
                          isCurrent
                            ? 'border-white scale-110 shadow-md ring-2 ring-white/30'
                            : 'border-white/20'
                        } ${option.bg} ${disabled ? 'opacity-20 cursor-not-allowed hover:scale-100' : ''}`}
                      />
                    );
                  })}
                </div>
              )}
            </div>
            <span className="font-mono text-[10px] font-bold opacity-60 tracking-widest mt-1">•••• {account_last4}</span>
          </div>
          <div className="overflow-hidden mt-4">
            <p className="text-[9px] font-black uppercase tracking-[0.25em] opacity-90 mb-1.5 truncate">{bank}</p>
            <h3 className="text-[1.4rem] font-black tracking-tighter tabular-nums leading-none whitespace-nowrap">{fmt(balance)}</h3>
            <p className="text-[8px] opacity-70 mt-2 font-mono tracking-tight italic uppercase">{fmtDate(last_updated)}</p>
          </div>
        </div>
        <div
          className={`w-0 opacity-0 transition-all duration-500 ease-in-out border-l border-white/10 bg-black/10 backdrop-blur-md flex flex-col justify-center px-0 gap-3 overflow-hidden z-10 ${
            showPicker ? 'hidden' : 'group-hover:w-full group-hover:flex-1 group-hover:opacity-100 group-hover:px-5'
          }`}
        >
          <div className="py-1 whitespace-nowrap">
            <div className="flex items-center gap-1.5 opacity-40 mb-1">
              <TrendingUp size={11} className="text-emerald-400" />
              <span className="text-[7px] font-black uppercase tracking-widest">Inflow</span>
            </div>
            <p className="text-xs font-black text-emerald-400 tabular-nums">+{fmtFlow(totalCredit)}</p>
          </div>
          <div className="h-[1px] bg-white/5 w-full shrink-0" />
          <div className="py-1 whitespace-nowrap">
            <div className="flex items-center gap-1.5 opacity-40 mb-1">
              <TrendingDown size={11} className="text-rose-400" />
              <span className="text-[7px] font-black uppercase tracking-widest">Outflow</span>
            </div>
            <p className="text-xs font-black text-rose-400 tabular-nums">-{fmtFlow(totalDebit)}</p>
          </div>
        </div>
      </div>
    </div>
  );
}