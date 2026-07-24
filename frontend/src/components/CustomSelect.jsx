import React, { useState, useRef, useEffect } from 'react';
import { ChevronDown } from 'lucide-react';
import { useBlur } from '../hooks/useBlurContext';

export default function CustomSelect({ value, onChange, options, placeholder = 'Select...' }) {
  const [open, setOpen] = useState(false);
  const [hoveredIndex, setHoveredIndex] = useState(null);
  const containerRef = useRef(null);
  const listRef = useRef(null);
  const [showScrollHint, setShowScrollHint] = useState(false);
  const { setDisableBlur } = useBlur();

  // Disable blur effect when dropdown is open
  useEffect(() => {
    setDisableBlur(open);
    return () => setDisableBlur(false);
  }, [open, setDisableBlur]);

  // Close on outside click
  useEffect(() => {
    const handleClick = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  // Check if list needs scrolling
  useEffect(() => {
    if (open && listRef.current) {
      const needsScroll = listRef.current.scrollHeight > listRef.current.clientHeight;
      setShowScrollHint(needsScroll);
    }
  }, [open, options]);

  // Keyboard navigation
  const handleKeyDown = (e) => {
    if (!open) {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        setOpen(true);
        setHoveredIndex(0);
      }
      return;
    }

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        setHoveredIndex(prev => 
          prev === null ? 0 : Math.min(prev + 1, options.length - 1)
        );
        break;
      case 'ArrowUp':
        e.preventDefault();
        setHoveredIndex(prev => 
          prev === null ? options.length - 1 : Math.max(prev - 1, 0)
        );
        break;
      case 'Enter':
        e.preventDefault();
        if (hoveredIndex !== null && options[hoveredIndex]) {
          onChange(options[hoveredIndex]);
          setOpen(false);
        }
        break;
      case 'Escape':
        setOpen(false);
        break;
      default:
        break;
    }
  };

  // Scroll hovered item into view
  useEffect(() => {
    if (hoveredIndex !== null && listRef.current) {
      const items = listRef.current.children;
      if (items[hoveredIndex]) {
        items[hoveredIndex].scrollIntoView({ block: 'nearest' });
      }
    }
  }, [hoveredIndex]);

  const handleSelect = (option) => {
    onChange(option);
    setOpen(false);
  };

  const handleScroll = () => {
    if (listRef.current) {
      const { scrollTop, scrollHeight, clientHeight } = listRef.current;
      const nearBottom = scrollTop + clientHeight >= scrollHeight - 10;
      setShowScrollHint(!nearBottom);
    }
  };

  return (
    <div
      ref={containerRef}
      className="relative w-full"
      onKeyDown={handleKeyDown}
      tabIndex={0}
      role="combobox"
      aria-expanded={open}
      aria-haspopup="listbox"
    >
      {/* Trigger */}
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-white text-xs font-bold outline-none focus:border-indigo-500 transition-colors flex items-center justify-between gap-2 hover:border-white/20"
      >
        <span className={value ? 'text-white' : 'text-slate-500'}>
          {value || placeholder}
        </span>
        <ChevronDown 
          size={12} 
          className={`text-slate-500 transition-transform duration-200 ${open ? 'rotate-180' : ''}`} 
        />
      </button>

      {/* Dropdown */}
      {open && (
        <div className="absolute z-50 mt-1 w-full bg-[#111318] border border-white/10 rounded-xl shadow-2xl overflow-hidden">
          <div
            ref={listRef}
            onScroll={handleScroll}
            className="max-h-[148px] overflow-y-auto"
            style={{
              scrollbarWidth: 'thin',
              scrollbarColor: 'rgba(255, 255, 255, 0.2) transparent'
            }}
            role="listbox"
            aria-label="Select option"
          >
            <style jsx>{`
              div::-webkit-scrollbar {
                width: 4px;
              }
              div::-webkit-scrollbar-track {
                background: transparent;
              }
              div::-webkit-scrollbar-thumb {
                background: rgba(255, 255, 255, 0.2);
                border-radius: 4px;
              }
            `}</style>
            
            {options.map((option, i) => (
              <button
                key={option}
                type="button"
                onClick={() => handleSelect(option)}
                onMouseEnter={() => setHoveredIndex(i)}
                onMouseLeave={() => setHoveredIndex(null)}
                className={`w-full text-left px-3 py-2 text-xs font-bold transition-colors
                  ${option === value 
                    ? 'bg-indigo-600 text-white' 
                    : hoveredIndex === i
                      ? 'bg-white/10 text-white'
                      : 'text-slate-400 hover:text-white'
                  }
                  ${i === 0 ? 'rounded-t-lg' : ''}
                  ${i === options.length - 1 ? 'rounded-b-lg' : ''}
                `}
                role="option"
                aria-selected={option === value}
              >
                {option}
              </button>
            ))}
          </div>
          
          {/* Scroll hint */}
          {showScrollHint && (
            <div className="absolute bottom-0 left-0 right-0 h-8 bg-gradient-to-t from-[#111318] to-transparent pointer-events-none flex items-end justify-center pb-1">
              <div className="flex items-center gap-1 text-[8px] text-slate-600 font-black uppercase tracking-widest animate-pulse">
                <span>Scroll</span>
                <ChevronDown size={8} />
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}