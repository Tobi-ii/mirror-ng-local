import React from 'react';

/**
 * FloatingNavItem Component
 * - Disables hover effects and "Zen" triggers if already active.
 */
export default function FloatingNavItem({ 
  icon, 
  label, 
  active, 
  onClick, 
  onMouseEnter, 
  onMouseLeave 
}) {
  return (
    <div className="relative group">
      <button
        // Only trigger the Zen blur if the item is NOT active
        onMouseEnter={!active ? onMouseEnter : undefined}
        onMouseLeave={onMouseLeave}
        onClick={onClick}
        className={`
          p-3 sm:p-5 rounded-full transition-all duration-500 flex items-center justify-center
          ${active 
            ? 'bg-white text-black scale-125 shadow-[0_15px_30px_-10px_rgba(255,255,255,0.4)] z-10 cursor-default' 
            : 'text-slate-500 hover:text-white hover:bg-white/10 hover:-translate-y-3'
          }
        `}
      >
        <div className={`transition-transform duration-300 ${active ? 'scale-110' : 'group-hover:scale-110'}`}>
          {icon}
        </div>
      </button>

      {/* Floating Tooltip Label - Only show if NOT active */}
      {!active && (
        <div className="absolute -top-12 sm:-top-14 left-1/2 -translate-x-1/2 px-3 sm:px-4 py-1.5 sm:py-2 bg-[#0a0c10] border border-white/10 text-white text-[8px] sm:text-[10px] font-black uppercase tracking-[0.15em] sm:tracking-[0.2em] rounded-xl opacity-0 group-hover:opacity-100 translate-y-2 group-hover:translate-y-0 transition-all duration-300 pointer-events-none whitespace-nowrap shadow-2xl z-20 max-w-[120px] sm:max-w-none truncate sm:truncate-none">
          {label}
          <div className="absolute -bottom-1 left-1/2 -translate-x-1/2 w-2 h-2 bg-[#0a0c10] rotate-45 border-r border-b border-white/10"></div>
        </div>
      )}

      {/* Active Indicator Pulse */}
      {active && (
        <div className="absolute -bottom-1 left-1/2 -translate-x-1/2 w-1 h-1 bg-white rounded-full animate-ping opacity-75" />
      )}
    </div>
  );
}