/**
 * SpendChart.jsx - ML Enhanced Edition
 * Visualizes transaction categories and net cash flow logic.
 */

function ProgressItem({ label, amount, percent, color }) {
  return (
    <div className="group">
      <div className="flex justify-between text-[9px] sm:text-[10px] font-black mb-2 sm:mb-3 uppercase tracking-[0.2em]">
        <span className="text-slate-500 group-hover:text-slate-300 transition-colors">{label}</span>
        <span className="text-white">{amount}</span>
      </div>
      <div className="w-full h-1.5 sm:h-2 bg-white/5 rounded-full overflow-hidden">
        <div
          className={`${color} h-full rounded-full transition-all duration-1000 ease-out`}
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  );
}

export default function SpendChart({ transactions }) {
  // Format for large numbers (e.g., 10,500 -> 10.5K)
  const fmt = (n) => `₦${n >= 1000 ? (n / 1000).toFixed(1) + 'K' : n.toFixed(0)}`;

  // Filter and compute Outflows (Debits)
  const debits = transactions.filter(t => t.tx_type === 'debit');
  const totalOut = debits.reduce((s, t) => s + t.amount, 0);

  // Filter and compute Inflows (Credits)
  const credits = transactions.filter(t => t.tx_type === 'credit');
  const totalIn = credits.reduce((s, t) => s + t.amount, 0);

  // Group by ML-generated category
  const categories = debits.reduce((acc, tx) => {
    const cat = tx.category || 'General';
    acc[cat] = (acc[cat] || 0) + tx.amount;
    return acc;
  }, {});

  // Extended Color Palette for ML Categories
  const colors = {
    Transfer: 'bg-indigo-500',
    Food: 'bg-rose-500',
    Shopping: 'bg-pink-500',
    Utilities: 'bg-orange-500',
    Transport: 'bg-cyan-500',
    Entertainment: 'bg-purple-500',
    Health: 'bg-emerald-500',
    Education: 'bg-amber-500',
    General: 'bg-slate-500',
  };

  // Sort by highest spend and take top 5
  const sorted = Object.entries(categories)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5);

  const netLogic = totalIn - totalOut;

  return (
    <div className="bg-[#0a0c10] border border-white/5 rounded-2xl sm:rounded-[2.5rem] p-4 sm:p-6 md:p-8 space-y-4 sm:space-y-6 md:space-y-8 shadow-2xl">
      {/* Category Breakdown */}
      <div className="space-y-6">
        {sorted.length === 0 ? (
          <div className="py-10 text-center">
            <p className="text-slate-600 text-[10px] font-black uppercase tracking-widest">
              No Debit Data to Map
            </p>
          </div>
        ) : (
          sorted.map(([cat, amt]) => (
            <ProgressItem
              key={cat}
              label={cat}
              amount={fmt(amt)}
              percent={totalOut > 0 ? Math.round((amt / totalOut) * 100) : 0}
              color={colors[cat] || 'bg-slate-500'}
            />
          ))
        )}
      </div>

      {/* Cash Flow Summary */}
      <div className="pt-4 sm:pt-6 border-t border-white/5 space-y-3 sm:space-y-4">
        <div className="flex justify-between items-center">
          <div className="flex items-center gap-1.5 sm:gap-2">
            <div className="w-1 h-1 sm:w-1.5 sm:h-1.5 rounded-full bg-emerald-500" />
            <span className="text-[8px] sm:text-[10px] font-black text-slate-500 uppercase tracking-widest">Total In</span>
          </div>
          <span className="text-xs sm:text-sm font-black text-white italic">
            ₦{totalIn.toLocaleString('en-NG')}
          </span>
        </div>

        <div className="flex justify-between items-center">
          <div className="flex items-center gap-1.5 sm:gap-2">
            <div className="w-1 h-1 sm:w-1.5 sm:h-1.5 rounded-full bg-rose-500" />
            <span className="text-[8px] sm:text-[10px] font-black text-slate-500 uppercase tracking-widest">Total Out</span>
          </div>
          <span className="text-xs sm:text-sm font-black text-white italic">
            ₦{totalOut.toLocaleString('en-NG')}
          </span>
        </div>

        {/* The "Net Logic" Indicator */}
        <div className={`mt-3 sm:mt-4 p-3 sm:p-4 rounded-xl sm:rounded-2xl border transition-colors ${
          netLogic >= 0 
            ? 'bg-emerald-500/5 border-emerald-500/10' 
            : 'bg-rose-500/5 border-rose-500/10'
        }`}>
          <div className="flex justify-between items-center">
            <span className="text-[8px] sm:text-[9px] font-black uppercase tracking-[0.2em] text-slate-400">
              Net Performance
            </span>
            <span className={`text-xs sm:text-sm font-black tabular-nums ${
              netLogic >= 0 ? 'text-emerald-400' : 'text-rose-400'
            }`}>
              {netLogic >= 0 ? '+' : ''}{fmt(netLogic)}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}