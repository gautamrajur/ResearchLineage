import { useState } from 'react';
import { GraphCanvas } from './components/Flow/GraphCanvas';

export default function App() {
  const [view, setView] = useState<'pre' | 'post'>('post');

  return (
    <div className="relative">
      <div className="absolute top-0 left-0 right-0 z-10 px-5 py-4 flex justify-between items-center"
        style={{ background: 'linear-gradient(to bottom, #43362A 0%, rgba(67,54,42,0.85) 70%, transparent 100%)' }}>
        <h1 className="text-[#E8DFC8] text-lg font-semibold tracking-tight">
          Research Lineage
        </h1>

        <div className="flex rounded-lg p-1"
          style={{ background: '#3A2E21', border: '1px solid rgba(200,178,114,0.25)' }}>
          {(['pre', 'post'] as const).map((v) => (
            <button
              key={v}
              onClick={() => setView(v)}
              className={`
                px-4 py-1.5 rounded-md text-[13px] font-medium
                transition-all duration-200
                ${view === v
                  ? 'text-[#E8DFC8]'
                  : 'text-[#697153] hover:text-[#A0A584]'
                }
              `}
              style={view === v ? { background: '#2E2518' } : {}}
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
