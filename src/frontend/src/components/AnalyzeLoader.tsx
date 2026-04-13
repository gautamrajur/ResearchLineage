import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import type { Theme } from '../lib/theme';

interface AnalyzeLoaderProps {
  paperId: string;
  title?: string;
  year?: number | null;
  onCancel: () => void;
  theme: Theme;
}

const STAGES = [
  { label: 'Resolving paper', sub: 'Fetching metadata from Semantic Scholar' },
  { label: 'Building citation tree', sub: 'Walking ancestors and descendants' },
  { label: 'Extracting key innovations', sub: 'Reading full text where available' },
  { label: 'Tracing lineage with Gemini', sub: 'Picking predecessors step by step' },
  { label: 'Assembling timeline', sub: 'Comparing each paper to the next' },
] as const;

export function AnalyzeLoader({ paperId, title, year, onCancel, theme }: AnalyzeLoaderProps) {
  const [stage, setStage] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const isDark = theme.id === 'dark';

  useEffect(() => {
    const t0 = Date.now();
    const tick = setInterval(() => setElapsed(Math.floor((Date.now() - t0) / 1000)), 250);
    return () => clearInterval(tick);
  }, []);

  useEffect(() => {
    const intervals = [4000, 8000, 10000, 14000, 12000];
    const timer = setTimeout(
      () => setStage((s) => Math.min(s + 1, STAGES.length - 1)),
      intervals[stage] ?? 10000,
    );
    return () => clearTimeout(timer);
  }, [stage]);

  return (
    <section className="min-h-screen flex flex-col items-center justify-center px-6 pt-24 pb-16">
      <motion.div
        initial={{ opacity: 0, scale: 0.96 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
        className="relative w-full max-w-[600px]"
      >
        {/* Orb */}
        <div className="flex justify-center mb-10">
          <div className="relative w-28 h-28">
            {[0, 1, 2].map((i) => (
              <motion.div
                key={i}
                className="absolute inset-0 rounded-full"
                style={{ background: `radial-gradient(circle, ${theme.accent}${40 - i * 10 < 10 ? '0' : ''}${(40 - i * 10).toString(16)} 0%, transparent 70%)` }}
                animate={{ scale: [1, 1.9, 1], opacity: [0.7, 0, 0.7] }}
                transition={{ duration: 2.8, delay: i * 0.55, repeat: Infinity, ease: 'easeOut' }}
              />
            ))}
            <motion.div
              animate={{ rotate: 360 }}
              transition={{ duration: 6, repeat: Infinity, ease: 'linear' }}
              className="absolute inset-5 rounded-full"
              style={{ border: `1.5px solid ${theme.accent}50`, borderTopColor: theme.accent, borderRightColor: 'transparent' }}
            />
            <motion.div
              animate={{ rotate: -360 }}
              transition={{ duration: 10, repeat: Infinity, ease: 'linear' }}
              className="absolute inset-9 rounded-full"
              style={{ border: `1.5px solid ${theme.seed}40`, borderRightColor: theme.seed, borderTopColor: 'transparent' }}
            />
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="w-3 h-3 rounded-full" style={{ background: theme.seed, boxShadow: `0 0 30px ${theme.seed}cc` }} />
            </div>
          </div>
        </div>

        {/* Title */}
        <div className="text-center mb-8">
          <p className="text-[10px] uppercase tracking-[0.18em] font-bold mb-2" style={{ color: theme.accent }}>
            Analyzing
          </p>
          <h2 className="text-[22px] sm:text-[26px] font-semibold leading-tight max-w-[520px] mx-auto" style={{ color: theme.textPrimary }}>
            {title || paperId}
          </h2>
          {year && <p className="mt-1 text-[13px] tabular-nums" style={{ color: theme.textSecondary }}>{year}</p>}
        </div>

        {/* Stages */}
        <ol className="space-y-2.5">
          {STAGES.map((s, i) => {
            const state = i < stage ? 'done' : i === stage ? 'active' : 'pending';
            return (
              <motion.li
                key={s.label}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.3 + i * 0.07, duration: 0.4 }}
                className="flex items-start gap-4 px-4 py-3 rounded-xl"
                style={{
                  background: isDark ? 'rgba(18,20,26,0.55)' : 'rgba(255,255,255,0.70)',
                  border: `1px solid ${theme.border}`,
                  backdropFilter: 'blur(12px)',
                }}
              >
                <StageDot state={state} accent={theme.accent} />
                <div className="flex-1 min-w-0">
                  <div className="text-[13px]" style={{
                    color: state === 'pending' ? theme.textMuted : state === 'active' ? theme.accent : theme.textSecondary,
                    fontWeight: state === 'active' ? 600 : 400,
                  }}>
                    {s.label}
                  </div>
                  <div className="text-[11px] mt-0.5" style={{ color: theme.textMuted }}>{s.sub}</div>
                </div>
                {state === 'done' && (
                  <motion.span initial={{ scale: 0 }} animate={{ scale: 1 }} className="text-[13px] shrink-0" style={{ color: '#4ADE80' }}>✓</motion.span>
                )}
              </motion.li>
            );
          })}
        </ol>

        {/* Footer */}
        <div className="mt-6 flex items-center justify-between text-[11px]" style={{ color: theme.textMuted }}>
          <span className="tabular-nums">
            {Math.floor(elapsed / 60)}:{(elapsed % 60).toString().padStart(2, '0')} · fresh analyses can take 2–4 min
          </span>
          <button
            onClick={onCancel}
            className="px-3 py-1 rounded-md transition-colors"
            style={{ color: theme.textSecondary }}
            onMouseEnter={(e) => (e.currentTarget.style.background = isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.05)')}
            onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
          >
            Cancel
          </button>
        </div>
      </motion.div>
    </section>
  );
}

function StageDot({ state, accent }: { state: 'pending' | 'active' | 'done'; accent: string }) {
  return (
    <div className="relative w-5 h-5 shrink-0 mt-0.5">
      {state === 'active' ? (
        <>
          <motion.div className="absolute inset-0 rounded-full" style={{ background: `${accent}25` }}
            animate={{ scale: [1, 1.7, 1], opacity: [0.8, 0, 0.8] }} transition={{ duration: 1.4, repeat: Infinity }} />
          <div className="absolute inset-[4px] rounded-full" style={{ background: accent, boxShadow: `0 0 12px ${accent}88` }} />
        </>
      ) : state === 'done' ? (
        <div className="absolute inset-[3px] rounded-full" style={{ background: '#4ADE8022', border: '1.5px solid #4ADE8080' }} />
      ) : (
        <div className="absolute inset-[5px] rounded-full bg-gray-300/50" />
      )}
    </div>
  );
}
