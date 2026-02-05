import { motion } from 'framer-motion';
import type { ViewMode } from '../../types/paper';

interface ViewToggleProps {
  view: ViewMode;
  onChange: (view: ViewMode) => void;
}

export function ViewToggle({ view, onChange }: ViewToggleProps) {
  return (
    <div className="flex bg-white/5 rounded-xl p-1 border border-white/10">
      <button
        onClick={() => onChange('pre')}
        className={`
          relative px-4 py-2 rounded-lg text-sm font-medium
          transition-colors duration-200
          ${view === 'pre' ? 'text-white' : 'text-gray-400 hover:text-gray-200'}
        `}
      >
        {view === 'pre' && (
          <motion.div
            layoutId="toggle-bg"
            className="absolute inset-0 bg-indigo-600 rounded-lg"
            transition={{ type: 'spring', bounce: 0.2, duration: 0.4 }}
          />
        )}
        <span className="relative z-10 flex items-center gap-2">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
          </svg>
          Pre-Order
        </span>
      </button>

      <button
        onClick={() => onChange('post')}
        className={`
          relative px-4 py-2 rounded-lg text-sm font-medium
          transition-colors duration-200
          ${view === 'post' ? 'text-white' : 'text-gray-400 hover:text-gray-200'}
        `}
      >
        {view === 'post' && (
          <motion.div
            layoutId="toggle-bg"
            className="absolute inset-0 bg-indigo-600 rounded-lg"
            transition={{ type: 'spring', bounce: 0.2, duration: 0.4 }}
          />
        )}
        <span className="relative z-10 flex items-center gap-2">
          Post-Order
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 5l7 7-7 7M5 5l7 7-7 7" />
          </svg>
        </span>
      </button>
    </div>
  );
}
