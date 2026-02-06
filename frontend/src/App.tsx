import { useState } from 'react';
import { motion } from 'framer-motion';
import { GraphCanvas } from './components/Flow/GraphCanvas';

export default function App() {
  const [view, setView] = useState<'pre' | 'post'>('post');

  return (
    <div className="relative">
      {/* Header */}
      <div
        className="absolute top-0 left-0 right-0 z-10 px-6 py-4 flex justify-between items-center"
        style={{
          background: 'linear-gradient(to bottom, var(--color-bg-page), transparent)',
        }}
      >
        <h1 className="text-[var(--color-text-primary)] text-lg font-semibold tracking-tight">
          Research Lineage
        </h1>

        {/* View Toggle */}
        <div
          className="flex rounded-lg p-1"
          style={{
            background: 'var(--color-bg-card)',
            border: '1px solid var(--color-border-default)',
            boxShadow: 'var(--shadow-inner-light)',
          }}
        >
          {(['pre', 'post'] as const).map((v) => (
            <button
              key={v}
              onClick={() => setView(v)}
              className="relative px-4 py-2 rounded-md text-sm font-medium transition-colors"
              style={{
                color: view === v
                  ? 'var(--color-text-primary)'
                  : 'var(--color-text-muted)',
              }}
            >
              {view === v && (
                <motion.div
                  layoutId="toggle-active"
                  className="absolute inset-0 rounded-md"
                  style={{ background: 'var(--color-bg-hover)' }}
                  transition={{ type: 'spring', bounce: 0.2, duration: 0.4 }}
                />
              )}
              <span className="relative z-10">
                {v === 'pre' ? '\u00AB Pre-Order' : 'Post-Order \u00BB'}
              </span>
            </button>
          ))}
        </div>
      </div>

      <GraphCanvas view={view} />
    </div>
  );
}
