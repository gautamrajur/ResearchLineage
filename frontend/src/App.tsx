import { useState } from 'react';
import { GraphCanvas } from './components/Flow/GraphCanvas';

export default function App() {
  const [view, setView] = useState<'pre' | 'post'>('post');

  return (
    <div className="relative">
      <div className="absolute top-0 left-0 right-0 z-10 px-5 py-4 flex justify-between items-center bg-gradient-to-b from-[#F5F0E8] via-[#F5F0E8]/80 to-transparent">
        <h1 className="text-[#1C1510] text-lg font-semibold tracking-tight">
          Research Lineage
        </h1>

        <div className="flex bg-[#EDE6D8] rounded-lg p-1 border border-[#D0C4AD]">
          {(['pre', 'post'] as const).map((v) => (
            <button
              key={v}
              onClick={() => setView(v)}
              className={`
                px-4 py-1.5 rounded-md text-[13px] font-medium
                transition-all duration-200
                ${view === v
                  ? 'bg-[#FDFAF6] text-[#1C1510] shadow-sm'
                  : 'text-[#9B8B77] hover:text-[#1C1510]'
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
