import { useState } from 'react';
import { GraphCanvas } from './components/Flow/GraphBackend';

export default function App() {
  const [view, setView] = useState<'pre' | 'post'>('post');

  return (
    <div className="relative">
      <div className="absolute top-0 left-0 right-0 z-10 px-5 py-4 flex justify-between items-center bg-gradient-to-b from-[#0B0D11] via-[#0B0D11]/80 to-transparent">
        <h1 className="text-[#EAEDF2] text-lg font-semibold tracking-tight">
          Research Lineage
        </h1>

        <div className="flex bg-[#12141A] rounded-lg p-1 border border-white/[0.06]">
          {(['pre', 'post'] as const).map((v) => (
            <button
              key={v}
              onClick={() => setView(v)}
              className={`
                px-4 py-1.5 rounded-md text-[13px] font-medium
                transition-all duration-200
                ${view === v
                  ? 'bg-[#1A1D25] text-[#EAEDF2] shadow-sm'
                  : 'text-[#8B95A5] hover:text-[#EAEDF2]'
                }
              `}
            >
              {v === 'pre' ? '\u2190 References' : 'Citations \u2192'}
            </button>
          ))}
        </div>
      </div>

      <GraphCanvas view={view} />
    </div>
  );
}
