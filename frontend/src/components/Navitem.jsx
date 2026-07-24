import React, { useRef } from 'react';

export default function FloatingNavItem({ icon, label, active, onClick, setIsBlurred, setHoverLabel }) {
  const timerRef = useRef(null);

  const handleMouseEnter = () => {
    setHoverLabel(label);
    // Start 5s countdown
    timerRef.current = setTimeout(() => {
      setIsBlurred(true);
    }, 5000); 
  };

  const handleMouseLeave = () => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
    }
    setIsBlurred(false);
    setHoverLabel('');
  };

  return (
    <div className="relative group">
      <button
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
        onClick={() => {
          if (timerRef.current) clearTimeout(timerRef.current);
          setIsBlurred(false);
          onClick();
        }}
        className={`
          p-5 rounded-full transition-all duration-500 flex items-center justify-center
          ${active 
            ? 'bg-white text-black scale-110 shadow-[0_20px_40px_-15px_rgba(255,255,255,0.3)]' 
            : 'text-slate-400 hover:text-white hover:bg-white/10 hover:-translate-y-2'
          }
        `}
      >
        {icon || <div className="w-5 h-5 bg-current rounded-sm" />}
      </button>

      <span className="absolute -top-12 left-1/2 -translate-x-1/2 px-4 py-2 bg-[#0a0c10] border border-white/10 text-white text-[10px] font-black uppercase tracking-widest rounded-lg opacity-0 group-hover:opacity-100 transition-all duration-300 pointer-events-none whitespace-nowrap shadow-2xl">
        {label}
      </span>
    </div>
  );
}