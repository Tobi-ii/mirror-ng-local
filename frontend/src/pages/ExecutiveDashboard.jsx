import { useState, useMemo } from 'react';

// ── Constants & Helpers ───────────────────────────────────────────────
const CATEGORY_COLORS = {
  Transfer: '#6366f1', Utilities: '#f97316', Food: '#f43f5e',
  Shopping: '#ec4899', Transport: '#06b6d4', Entertainment: '#a855f7',
  Health: '#10b981', Education: '#f59e0b', General: '#64748b',
  'Data & Airtime': '#8b5cf6', 'Bank Transfers': '#6366f1',
  'Ebill Payments': '#f97316', 'Airtime Purchases': '#a78bfa',
  'Data Purchases': '#c084fc', 'Card Maintenance': '#fb923c',
  'VAT Charges': '#fbbf24',
};

const BANK_COLORS = {
  'Sterling Bank': '#7c3aed', 'Wema (ALAT)': '#e11d48',
  'Kuda': '#10b981', 'GTBank': '#f97316', 'OPay': '#22c55e', 'default': '#64748b',
};

const fmt = (n) => `₦${Number(n).toLocaleString('en-NG', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const fmtK = (n) => n >= 1000 ? `₦${(n / 1000).toFixed(0)}K` : `₦${n.toFixed(0)}`;

// ── Extract readable title from narration ─────────────────────────────
function extractTitle(narration) {
  if (!narration) return 'Unknown';
  
  // Pattern: "OneBank Transfer from X to Y" → "Transfer to Y"
  const transferTo = narration.match(/transfer\s+(?:from\s+.+?\s+)?to\s+(.+?)(?:\s*\(|$)/i);
  if (transferTo) return `Transfer to ${transferTo[1].trim()}`;
  
  // Pattern: "Transfer from X" → "Transfer from X"
  const transferFrom = narration.match(/transfer from\s+(.+?)(?:\s*\(|$)/i);
  if (transferFrom) return `Transfer from ${transferFrom[1].trim()}`;
  
  // Pattern: "AFB NIP TRANSFER TO X FROM Y" → "Transfer to X"
  const nipTransfer = narration.match(/nip transfer to\s+(.+?)(?:\s+from|$)/i);
  if (nipTransfer) return `Transfer to ${nipTransfer[1].trim()}`;
  
  // Pattern: "Airtime purchase for 090..." → "Airtime · 090..."
  const airtime = narration.match(/airtime purchase for\s+(\d+)/i);
  if (airtime) return `Airtime · ${airtime[1]}`;
  
  // Pattern: "Data purchase for 081..." → "Data · 081..."
  const data = narration.match(/data purchase for\s+(\d+)/i);
  if (data) return `Data · ${data[1]}`;
  
  // Pattern: "ROE ... Airtime purchase for 090..." → "Airtime · 090..."
  const roeAirtime = narration.match(/roe.*airtime purchase for\s+(\d+)/i);
  if (roeAirtime) return `Airtime · ${roeAirtime[1]}`;
  
  // Pattern: "CARD MAINTENANCE FEE..." → "Card Maintenance Fee"
  const cardMaint = narration.match(/card maintenance fee/i);
  if (cardMaint) return 'Card Maintenance Fee';
  
  // Pattern: "Vat/VAT ..." → "VAT · ..."
  const vat = narration.match(/vat\s+(.+)/i);
  if (vat) return `VAT · ${vat[1].slice(0, 30).trim()}`;
  
  // Pattern: "EbillTe" → "Ebill Payment"
  const ebill = narration.match(/ebill/i);
  if (ebill) return 'Ebill Payment';
  
  // Pattern: "COMM Eb" → "Bank Commission"
  const comm = narration.match(/comm\s/i);
  if (comm) return 'Bank Commission';
  
  // Pattern: "OLORUNTO" → keep as name
  const name = narration.match(/^([A-Z]{3,})\s*$/);
  if (name) return name[1];
  
  // Pattern: "Data purchase for 081..." already handled above, but also try "purchase"
  const purchase = narration.match(/(\w+)\s+purchase/i);
  if (purchase) return `${purchase[1]} Purchase`;
  
  // Fallback: first 50 chars, cleaned
  const cleaned = narration.replace(/\s+/g, ' ').trim();
  return cleaned.length > 50 ? cleaned.slice(0, 50) + '...' : cleaned;
}

// ── UI Components ─────────────────────────────────────────────────────
function TogglePill({ value, setValue, options }) {
  return (
    <div className="flex bg-white/5 rounded-full p-1 border border-white/5">
      {options.map(o => (
        <button key={o.value} onClick={() => setValue(o.value)}
          className={`text-[9px] font-black uppercase tracking-widest px-3 py-1 rounded-full transition-all ${
            value === o.value ? 'bg-white text-black' : 'text-slate-500 hover:text-white'
          }`}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

function DonutChart({ data, size = 200, onSliceClick, selectedSlice }) {
  const [hovered, setHovered] = useState(null);
  const total = data.reduce((s, d) => s + d.value, 0);
  const cx = size / 2, cy = size / 2;
  const r = size * 0.38, innerR = size * 0.24;

  const slices = useMemo(() => {
    let cum = -Math.PI / 2;
    return data.map(d => {
      const angle = (d.value / total) * 2 * Math.PI;
      const start = cum; cum += angle; const end = cum;
      const x1 = cx + r * Math.cos(start), y1 = cy + r * Math.sin(start);
      const x2 = cx + r * Math.cos(end), y2 = cy + r * Math.sin(end);
      const ix1 = cx + innerR * Math.cos(start), iy1 = cy + innerR * Math.sin(start);
      const ix2 = cx + innerR * Math.cos(end), iy2 = cy + innerR * Math.sin(end);
      const large = angle > Math.PI ? 1 : 0;
      const path = `M ${ix1} ${iy1} L ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2} L ${ix2} ${iy2} A ${innerR} ${innerR} 0 ${large} 0 ${ix1} ${iy1} Z`;
      const mid = start + angle / 2;
      return { ...d, path, mid, percent: ((d.value / total) * 100).toFixed(1) };
    });
  }, [data, total, cx, cy, r, innerR]);

  return (
    <div className="flex flex-col items-center gap-3 sm:gap-5 w-full">
      <svg viewBox={`0 0 ${size} ${size}`} className="w-full max-w-[200px] h-auto">
        {slices.map((s, i) => (
          <path key={i} d={s.path} fill={s.color}
            opacity={selectedSlice === null || selectedSlice === i ? 1 : 0.2}
            className="cursor-pointer transition-all duration-200"
            onMouseEnter={() => setHovered(i)} onMouseLeave={() => setHovered(null)}
            onClick={() => onSliceClick?.(i === selectedSlice ? null : i, s)}
            style={{ 
              transform: (hovered === i || selectedSlice === i) ? `translate(${Math.cos(s.mid) * 6}px, ${Math.sin(s.mid) * 6}px) scale(1.05)` : 'none',
              transition: 'all 0.2s ease',
              filter: (hovered === i || selectedSlice === i) ? 'brightness(1.2)' : 'none'
            }}
          />
        ))}
        <text x={cx} y={cy - 6} textAnchor="middle" fill="white" fontSize="11" fontWeight="900" fontFamily="monospace">
          {selectedSlice !== null ? slices[selectedSlice].percent + '%' : fmtK(total)}
        </text>
        <text x={cx} y={cy + 12} textAnchor="middle" fill="#475569" fontSize="7" fontWeight="800" letterSpacing="1.5">
          {selectedSlice !== null ? slices[selectedSlice].label.toUpperCase().slice(0, 10) : 'TOTAL'}
        </text>
      </svg>
      <div className="grid grid-cols-2 gap-x-6 gap-y-2 w-full">
        {slices.map((s, i) => (
          <div key={i} className="flex items-center gap-2 cursor-pointer group"
            onMouseEnter={() => setHovered(i)} onMouseLeave={() => setHovered(null)}
            onClick={() => onSliceClick?.(i === selectedSlice ? null : i, s)}>
            <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: s.color }} />
            <span className={`text-[9px] font-black uppercase tracking-wide truncate transition-colors ${selectedSlice === i ? 'text-white' : 'text-slate-500 group-hover:text-slate-300'}`}>{s.label}</span>
            <span className="text-[9px] font-mono text-white ml-auto">{fmtK(s.value)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function TransactionBreakdown({ transactions, label, color, onClose }) {
  const sorted = [...transactions].sort((a, b) => Math.abs(b.amount) - Math.abs(a.amount));
  return (
    <div className="mt-6 pt-6 border-t border-white/5 animate-in fade-in slide-in-from-bottom-3 duration-500">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
          <h4 className="text-[10px] font-black text-white uppercase tracking-widest">{label}</h4>
          <span className="text-[9px] text-slate-500 font-mono">({sorted.length})</span>
        </div>
        <button onClick={onClose} className="text-slate-600 hover:text-white transition-colors text-[9px] font-black uppercase tracking-[0.2em]">✕</button>
      </div>
      <div className="space-y-1.5 max-h-64 overflow-y-auto pr-2 custom-scrollbar">
        {sorted.map((tx, i) => (
          <div key={i} className="flex items-center justify-between bg-white/[0.01] border border-white/[0.03] rounded-xl px-4 py-3 hover:bg-white/[0.04] transition-colors">
            <div className="min-w-0 flex-1 mr-4">
              <p className="text-[11px] text-slate-200 truncate font-medium">{tx.narration || tx.original_narration || 'Untitled Transaction'}</p>
              <p className="text-[8px] text-slate-600 mt-0.5 uppercase tracking-tighter">{tx.timestamp?.slice(0, 10)} · {tx.bank?.replace(' Bank', '')}</p>
            </div>
            <p className={`text-xs font-bold font-mono ${tx.tx_type === 'debit' ? 'text-rose-400' : 'text-emerald-400'}`}>
              {tx.tx_type === 'debit' ? '-' : '+'}{fmt(Math.abs(tx.amount))}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Trends & Visualizations ──────────────────────────────────────────
function TrendLine({ transactions }) {
  const [hoveredIdx, setHoveredIdx] = useState(null);
  const W = 560, H = 150, PAD = { top: 20, right: 16, bottom: 28, left: 50 };

  const dailyData = useMemo(() => {
    const byDate = {};
    transactions.filter(t => t.tx_type === 'debit').forEach(t => {
      const date = t.timestamp?.slice(0, 10);
      if (!date) return;
      byDate[date] = (byDate[date] || 0) + t.amount;
    });
    return Object.entries(byDate).sort((a, b) => a[0].localeCompare(b[0])).map(([date, amt]) => ({ date, amt }));
  }, [transactions]);

  if (dailyData.length < 2) return <div className="h-36 flex items-center justify-center text-slate-700 text-[10px] italic">Insufficient data points</div>;

  const maxAmt = Math.max(...dailyData.map(d => d.amt));
  const chartW = W - PAD.left - PAD.right, chartH = H - PAD.top - PAD.bottom;
  const px = (i) => PAD.left + (i / (dailyData.length - 1)) * chartW;
  const py = (v) => PAD.top + chartH - (v / maxAmt) * chartH;
  const points = dailyData.map((d, i) => `${px(i)},${py(d.amt)}`).join(' ');
  const area = [`${px(0)},${PAD.top + chartH}`, ...dailyData.map((d, i) => `${px(i)},${py(d.amt)}`), `${px(dailyData.length - 1)},${PAD.top + chartH}`].join(' ');
  const fmtDate = (s) => new Date(s).toLocaleDateString('en-NG', { day: 'numeric', month: 'short' });
  const hideLabels = dailyData.length > 15;

  return (
    <div className="relative">
      <svg width="100%" viewBox={`0 0 ${W} ${H}`} className="overflow-visible">
        <defs>
          <linearGradient id="trendGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#6366f1" stopOpacity="0.2" />
            <stop offset="100%" stopColor="#6366f1" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0, 0.5, 1].map((t, i) => (
          <g key={i}>
            <line x1={PAD.left} y1={PAD.top + chartH * (1 - t)} x2={PAD.left + chartW} y2={PAD.top + chartH * (1 - t)} stroke="rgba(255,255,255,0.04)" strokeWidth="1" />
            <text x={PAD.left - 5} y={PAD.top + chartH * (1 - t) + 4} textAnchor="end" fill="#475569" fontSize="8" fontWeight="700">{fmtK(maxAmt * t)}</text>
          </g>
        ))}
        <polygon points={area} fill="url(#trendGrad)" />
        <polyline points={points} fill="none" stroke="#6366f1" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
        {dailyData.map((d, i) => (
          <g key={i}>
            <circle cx={px(i)} cy={py(d.amt)} r={hoveredIdx === i ? 5 : 3} fill={hoveredIdx === i ? "#fff" : "#6366f1"} className="transition-all" />
            {!hideLabels && (
              <text x={px(i)} y={PAD.top + chartH + 16} textAnchor="middle" fill={hoveredIdx === i ? "#fff" : "#475569"} fontSize="7" fontWeight="700">{fmtDate(d.date)}</text>
            )}
            <rect x={px(i)-10} y={0} width={20} height={H} fill="transparent" onMouseEnter={() => setHoveredIdx(i)} onMouseLeave={() => setHoveredIdx(null)} className="cursor-crosshair" />
          </g>
        ))}
      </svg>
      {hoveredIdx !== null && (
        <div className="absolute pointer-events-none bg-[#0a0c10] border border-white/10 px-2.5 py-1.5 rounded text-[10px] font-black text-white shadow-xl -translate-x-1/2 -translate-y-full mb-2 z-10 whitespace-nowrap"
          style={{ left: `${(px(hoveredIdx)/W)*100}%`, top: `${(py(dailyData[hoveredIdx].amt)/H)*100}%` }}>
          <div className="text-[8px] text-slate-400 font-bold uppercase tracking-wider">{fmtDate(dailyData[hoveredIdx].date)}</div>
          <div className="text-white">{fmt(dailyData[hoveredIdx].amt)}</div>
        </div>
      )}
    </div>
  );
}

function CreditDebitBars({ transactions }) {
  const [hovered, setHovered] = useState(null);
  const W = 560, H = 160, PAD = { top: 25, right: 16, bottom: 28, left: 50 };

  const dailyData = useMemo(() => {
    const byDate = {};
    transactions.forEach(t => {
      const date = t.timestamp?.slice(0, 10);
      if (!date) return;
      if (!byDate[date]) byDate[date] = { credit: 0, debit: 0 };
      byDate[date][t.tx_type] += t.amount;
    });
    return Object.entries(byDate).sort((a, b) => a[0].localeCompare(b[0])).map(([date, vals]) => ({ date, ...vals }));
  }, [transactions]);

  if (dailyData.length === 0) return <div className="h-36 flex items-center justify-center text-slate-700 text-[10px] italic">No data</div>;

  const maxVal = Math.max(...dailyData.flatMap(d => [d.credit, d.debit]));
  const chartW = W - PAD.left - PAD.right, chartH = H - PAD.top - PAD.bottom;
  const slotW = chartW / dailyData.length, barW = Math.min(16, slotW * 0.3);
  const py = (v) => PAD.top + chartH - (v / maxVal) * chartH;
  const bh = (v) => (v / maxVal) * chartH;
  const fmtDate = (s) => new Date(s).toLocaleDateString('en-NG', { day: 'numeric', month: 'short' });
  const hideLabels = dailyData.length > 15;

  return (
    <div className="relative">
      <svg width="100%" viewBox={`0 0 ${W} ${H}`} className="overflow-visible">
        {[0, 0.5, 1].map((t, i) => (
          <g key={i}>
            <line x1={PAD.left} y1={PAD.top + chartH * (1 - t)} x2={PAD.left + chartW} y2={PAD.top + chartH * (1 - t)} stroke="rgba(255,255,255,0.04)" strokeWidth="1" />
            <text x={PAD.left - 5} y={PAD.top + chartH * (1 - t) + 4} textAnchor="end" fill="#475569" fontSize="8" fontWeight="700">{fmtK(maxVal * t)}</text>
          </g>
        ))}
        {dailyData.map((d, i) => {
          const cx = PAD.left + i * slotW + slotW/2;
          return (
            <g key={i}>
              <rect x={cx - barW - 2} y={py(d.credit)} width={barW} height={bh(d.credit)} fill="#10b981" rx="1.5" opacity={hovered?.idx === i && hovered?.type === 'credit' ? 1 : 0.6} className="cursor-pointer transition-opacity" onMouseEnter={() => setHovered({idx: i, type: 'credit'})} onMouseLeave={() => setHovered(null)} />
              <rect x={cx + 2} y={py(d.debit)} width={barW} height={bh(d.debit)} fill="#f43f5e" rx="1.5" opacity={hovered?.idx === i && hovered?.type === 'debit' ? 1 : 0.6} className="cursor-pointer transition-opacity" onMouseEnter={() => setHovered({idx: i, type: 'debit'})} onMouseLeave={() => setHovered(null)} />
              {!hideLabels && (
                <text x={cx} y={PAD.top + chartH + 16} textAnchor="middle" fill={hovered?.idx === i ? "#fff" : "#475569"} fontSize="7" fontWeight="700">{fmtDate(d.date)}</text>
              )}
            </g>
          );
        })}
        <g>
          <rect x={PAD.left} y={4} width={8} height={8} fill="#10b981" rx="2" />
          <text x={PAD.left + 11} y={12} fill="#475569" fontSize="8" fontWeight="700">CREDIT</text>
          <rect x={PAD.left + 55} y={4} width={8} height={8} fill="#f43f5e" rx="2" />
          <text x={PAD.left + 68} y={12} fill="#475569" fontSize="8" fontWeight="700">DEBIT</text>
        </g>
      </svg>
      {hovered && (
        <div className="absolute pointer-events-none bg-[#0a0c10] border border-white/10 px-2.5 py-1.5 rounded text-[10px] font-black text-white shadow-xl -translate-x-1/2 -translate-y-full whitespace-nowrap z-10"
          style={{ 
            left: `${((PAD.left + hovered.idx * slotW + slotW/2 + (hovered.type === 'debit' ? barW : -barW)) / W) * 100}%`, 
            top: `${(py(dailyData[hovered.idx][hovered.type]) / H) * 100 - 2}%` 
          }}>
          <div className="text-[8px] text-slate-400 font-bold uppercase tracking-wider">{fmtDate(dailyData[hovered.idx].date)}</div>
          <div className="flex items-center gap-1.5">
            <span className="inline-block w-1.5 h-1.5 rounded-full" style={{ backgroundColor: hovered.type === 'credit' ? '#10b981' : '#f43f5e' }} />
            <span className={hovered.type === 'credit' ? 'text-emerald-400' : 'text-rose-400'}>{hovered.type.toUpperCase()}</span>
            <span className="text-white">{fmt(dailyData[hovered.idx][hovered.type])}</span>
          </div>
        </div>
      )}
    </div>
  );
}

// ── DRILL-DOWN ANALYSIS ──────────────────────────────────────────────
function VolumeAnalysis({ transactions, type }) {
  const [expandedIdx, setExpandedIdx] = useState(null);

  const data = useMemo(() => {
    const map = {};
    transactions.filter(t => t.tx_type === type).forEach(t => {
      const title = t.alias_name || extractTitle(t.narration || '');
      if (!map[title]) map[title] = { title, count: 0, total: 0, items: [] };
      map[title].count++;
      map[title].total += t.amount;
      map[title].items.push(t);
    });
    return Object.values(map).sort((a, b) => b.total - a.total).slice(0, 5);
  }, [transactions, type]);

  if (data.length === 0) return <p className="text-slate-700 text-xs italic text-center py-6">No data</p>;

  return (
    <div className="space-y-3">
      {data.map((r, i) => (
        <div key={i} className="flex flex-col gap-2">
          <div 
            onClick={() => setExpandedIdx(expandedIdx === i ? null : i)}
            className={`flex items-center gap-4 p-4 bg-white/[0.02] border border-white/[0.03] rounded-2xl hover:bg-white/5 transition-all cursor-pointer group ${expandedIdx === i ? 'bg-white/[0.05] border-white/10' : ''}`}
          >
            <div className="w-8 h-8 rounded-lg bg-indigo-500/10 flex items-center justify-center text-[10px] font-black text-indigo-400 flex-shrink-0">
              {expandedIdx === i ? '−' : i + 1}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-[11px] font-bold text-white truncate">{r.title}</p>
              <p className="text-[9px] text-slate-600 uppercase tracking-tighter">
                {r.count} transaction{r.count !== 1 ? 's' : ''} {expandedIdx === i ? '· Click to collapse' : '· Click to expand'}
              </p>
            </div>
            <p className={`text-xs font-black font-mono flex-shrink-0 ${type === 'debit' ? 'text-rose-400' : 'text-emerald-400'}`}>
              {fmt(r.total)}
            </p>
          </div>

          {expandedIdx === i && (
            <div className="ml-12 space-y-1 animate-in slide-in-from-top-2 duration-300">
              {r.items.sort((a, b) => b.amount - a.amount).map((item, idx) => (
                <div key={idx} className="flex items-center justify-between py-2 px-4 bg-white/[0.01] rounded-xl border-l border-white/5">
                  <div className="flex flex-col min-w-0 flex-1 mr-3">
                    <span className="text-[10px] text-slate-300 truncate">
                      {item.narration || 'No description'}
                    </span>
                    <span className="text-[8px] text-slate-600 uppercase italic">
                      {item.timestamp?.slice(0, 10) || 'No date'} · {item.bank?.replace(' Bank', '').replace(' (ALAT)', '')}
                    </span>
                  </div>
                  <span className={`text-[10px] font-mono font-bold flex-shrink-0 ${type === 'debit' ? 'text-rose-500/80' : 'text-emerald-500/80'}`}>
                    {fmt(item.amount)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// ── Main Executive Dashboard ──────────────────────────────────────────
export default function ExecutiveDashboard({ transactions }) {
  const [pieFilter, setPieFilter] = useState('all');
  const [pieMode, setPieMode] = useState('category');
  const [flowType, setFlowType] = useState('debit');
  const [recipientType, setRecipientType] = useState('debit');
  const [selectedSlice, setSelectedSlice] = useState(null);
  const [breakdownTxs, setBreakdownTxs] = useState(null);

  const banks = [...new Set(transactions.map(t => t.bank))];
  const filteredForPie = pieFilter === 'all' ? transactions : transactions.filter(t => t.bank === pieFilter);
  const txForPie = filteredForPie.filter(t => t.tx_type === flowType);

  const pieData = useMemo(() => {
    const map = {};
    if (pieMode === 'category') {
      txForPie.forEach(t => { const cat = t.category || 'General'; map[cat] = (map[cat] || 0) + t.amount; });
      return Object.entries(map).sort((a, b) => b[1] - a[1]).map(([label, value]) => ({ label, value, color: CATEGORY_COLORS[label] || '#64748b' }));
    } else {
      transactions.filter(t => t.tx_type === flowType).forEach(t => { map[t.bank] = (map[t.bank] || 0) + t.amount; });
      return Object.entries(map).sort((a, b) => b[1] - a[1]).map(([label, value]) => ({ label, value, color: BANK_COLORS[label] || '#64748b' }));
    }
  }, [txForPie, pieMode, transactions, flowType]);

  const handleSliceClick = (index, slice) => {
    if (index === null) { setSelectedSlice(null); setBreakdownTxs(null); return; }
    setSelectedSlice(index);
    const matching = pieMode === 'category' 
      ? txForPie.filter(t => (t.category || 'General') === slice.label)
      : transactions.filter(t => t.tx_type === flowType && t.bank === slice.label);
    setBreakdownTxs(matching);
  };

  const totalIn = transactions.filter(t => t.tx_type === 'credit').reduce((s, t) => s + t.amount, 0);
  const totalOut = transactions.filter(t => t.tx_type === 'debit').reduce((s, t) => s + t.amount, 0);
  const debits = transactions.filter(t => t.tx_type === 'debit');
  const credits = transactions.filter(t => t.tx_type === 'credit');
  const creditRatio = totalIn + totalOut > 0 ? ((totalIn / (totalIn + totalOut)) * 100).toFixed(1) : 0;

  const kpis = [
    { label: 'Total Inflow', value: fmt(totalIn), color: 'text-emerald-400', sub: `${credits.length} credits` },
    { label: 'Total Outflow', value: fmt(totalOut), color: 'text-rose-400', sub: `${debits.length} debits` },
    { label: 'Avg Debit', value: fmt(debits.length ? totalOut / debits.length : 0), color: 'text-white', sub: `Net: ${fmt(totalIn - totalOut)}` },
    { label: 'Credit Ratio', value: `${creditRatio}%`, color: 'text-indigo-400', sub: `${transactions.length} tx processed` },
  ];

  return (
    <div className="space-y-10 max-w-6xl mx-auto">
      
      {/* ── STICKY HEADER & KPIs ─────────────────────────────────────── */}
      <div className="sticky top-0 z-40 bg-[#050608]/90 backdrop-blur-xl pt-3 sm:pt-6 pb-3 sm:pb-6 -mx-4 sm:-mx-6 px-4 sm:px-6 border-b border-white/5 space-y-3 sm:space-y-6">
        <div>
          <h1 className="text-2xl sm:text-3xl md:text-4xl font-black uppercase italic tracking-tighter text-white">Executive View</h1>
          <p className="text-[8px] sm:text-[10px] font-black uppercase tracking-[0.2em] sm:tracking-[0.4em] text-white/60 mt-0.5 sm:mt-1">
            Data Intelligence Layer · {transactions.length} transactions analyzed
          </p>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
          {kpis.map((kpi, i) => (
            <div key={i} className="bg-[#0a0c10] border border-white/5 rounded-xl sm:rounded-[2rem] p-3 sm:p-5 space-y-0.5 sm:space-y-1">
              <p className="text-[7px] sm:text-[9px] font-black uppercase tracking-[0.2em] sm:tracking-[0.3em] text-white/70 truncate">{kpi.label}</p>
              <p className={`text-base sm:text-xl font-black tabular-nums ${kpi.color} truncate`}>{kpi.value}</p>
              <p className="text-[7px] sm:text-[9px] text-white/50 truncate">{kpi.sub}</p>
            </div>
          ))}
        </div>
      </div>

      {/* ── DASHBOARD CONTENT ────────────────────────────── */}
      {/* Row 1: Pie + Combined Trends */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6 lg:gap-8">
        <div className="bg-[#0a0c10] border border-white/5 rounded-2xl sm:rounded-[2rem] lg:rounded-[2.5rem] p-4 sm:p-6 lg:p-8 space-y-4 sm:space-y-6">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 sm:gap-3">
            <h3 className="text-[9px] sm:text-xs font-black uppercase tracking-[0.2em] sm:tracking-[0.3em] text-white/70">Spend Breakdown</h3>
            <div className="flex items-center gap-1.5 sm:gap-2 flex-wrap">
              <TogglePill value={flowType} setValue={(v) => { setFlowType(v); setSelectedSlice(null); setBreakdownTxs(null); }}
                options={[{ value: 'debit', label: 'Out' }, { value: 'credit', label: 'In' }]} />
              <TogglePill value={pieMode} setValue={(v) => { setPieMode(v); setSelectedSlice(null); setBreakdownTxs(null); }}
                options={[{ value: 'category', label: 'Category' }, { value: 'bank', label: 'Bank' }]} />
              {pieMode === 'category' && banks.length > 1 && (
                <TogglePill value={pieFilter} setValue={(v) => { setPieFilter(v); setSelectedSlice(null); setBreakdownTxs(null); }}
                  options={[{ value: 'all', label: 'All' }, ...banks.map(b => ({
                    value: b, label: b.replace(' Bank', '').replace(' (ALAT)', '')
                  }))]} />
              )}
            </div>
          </div>
          {pieData.length > 0 ? (
            <>
              <DonutChart data={pieData} size={140} onSliceClick={handleSliceClick} selectedSlice={selectedSlice} />
              {breakdownTxs && selectedSlice !== null && (
                <TransactionBreakdown 
                  transactions={breakdownTxs} 
                  label={pieData[selectedSlice].label}
                  color={pieData[selectedSlice].color}
                  onClose={() => { setSelectedSlice(null); setBreakdownTxs(null); }}
                />
              )}
            </>
          ) : (
            <div className="flex items-center justify-center h-40 text-slate-700 text-xs italic">No data</div>
          )}
        </div>

        <div className="bg-[#0a0c10] border border-white/5 rounded-2xl sm:rounded-[2rem] lg:rounded-[2.5rem] p-4 sm:p-6 lg:p-8 space-y-4 sm:space-y-6">
          <div>
            <h3 className="text-[9px] sm:text-xs font-black uppercase tracking-[0.2em] sm:tracking-[0.3em] text-white/70 mb-3 sm:mb-4">Daily Spend Trend</h3>
            <TrendLine transactions={transactions} />
          </div>
          <div className="pt-8 border-t border-white/5">
            <h3 className="text-[9px] sm:text-xs font-black uppercase tracking-[0.2em] sm:tracking-[0.3em] text-white/70 mb-3 sm:mb-4">Daily Credit vs Debit</h3>
            <CreditDebitBars transactions={transactions} />
          </div>
        </div>
      </div>

      {/* Row 2: Volume Analysis with Drill-Down */}
      <div className="bg-[#0a0c10] border border-white/5 rounded-2xl sm:rounded-[2rem] lg:rounded-[2.5rem] p-4 sm:p-6 lg:p-8 space-y-4 sm:space-y-6 w-full">
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-[9px] sm:text-xs font-black uppercase tracking-[0.2em] sm:tracking-[0.3em] text-white/70">
            Volume Analysis
          </h3>
          <TogglePill value={recipientType} setValue={setRecipientType}
            options={[{ value: 'debit', label: 'Outflows' }, { value: 'credit', label: 'Inflows' }]} />
        </div>
        <VolumeAnalysis transactions={transactions} type={recipientType} />
      </div>
    </div>
  );
}