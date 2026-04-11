import { useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import type { AnalyzeResponse } from '../lib/types';
import type { Theme } from '../lib/theme';
import { formatNumber } from '../lib/utils';
import { TimelineView } from './TimelineView';
import { TreeView } from './TreeView';

type Tab = 'timeline' | 'tree' | 'raw';

interface ResultsPageProps {
  result: AnalyzeResponse;
  onBack: () => void;
  theme: Theme;
}

export function ResultsPage({ result, onBack, theme }: ResultsPageProps) {
  const { timeline, tree, elapsed } = result;
  const [tab, setTab] = useState<Tab>(() =>
    timeline ? 'timeline' : tree ? 'tree' : 'raw',
  );

  const isDark = theme.id === 'dark';
  const seed = timeline?.seed_paper
    ?? (tree ? { paper_id: tree.target.paperId, title: tree.target.title, year: tree.target.year ?? null } : null);
  const span = timeline?.year_range?.span ?? null;

  const tabs: { id: Tab; label: string; icon: string; disabled?: boolean }[] = [
    { id: 'timeline', label: 'Evolution Timeline', icon: '◐', disabled: !timeline },
    { id: 'tree', label: 'Predecessor / Successor Tree', icon: '◉', disabled: !tree },
    { id: 'raw', label: 'Raw JSON', icon: '{}' },
  ];

  return (
    <section className="pt-24 pb-24 px-6 max-w-[1400px] mx-auto">
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }} className="mb-8">

        <button onClick={onBack}
          className="inline-flex items-center gap-1.5 text-[12px] mb-4 transition-colors group"
          style={{ color: theme.textSecondary }}
          onMouseEnter={(e) => (e.currentTarget.style.color = theme.textPrimary)}
          onMouseLeave={(e) => (e.currentTarget.style.color = theme.textSecondary)}
        >
          <span className="group-hover:-translate-x-0.5 transition-transform">←</span>
          New search
        </button>

        {/* Partial-failure notice */}
        {!timeline && tree && (
          <motion.div initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}
            className="mb-6 flex items-start gap-3 px-4 py-3 rounded-xl"
            style={{ border: `1px solid ${theme.seed}44`, background: `${theme.seed}0A` }}
          >
            <span className="text-[14px] mt-px" style={{ color: theme.seed }}>⚠</span>
            <div>
              <div className="text-[12.5px] font-medium" style={{ color: theme.textPrimary }}>
                Evolution timeline unavailable for this run
              </div>
              <div className="text-[11px] mt-0.5" style={{ color: theme.textSecondary }}>
                The citation tree built successfully, but Gemini couldn't complete the lineage analysis. Usually a transient overload. Retrying in a minute or two generally works; cached papers return instantly.
              </div>
            </div>
          </motion.div>
        )}

        <div className="flex items-start justify-between gap-6 flex-wrap">
          <div className="min-w-0 flex-1">
            <p className="text-[10px] uppercase tracking-[0.14em] font-bold mb-2" style={{ color: theme.seed }}>Seed Paper</p>
            <h1 className="text-[28px] sm:text-[34px] font-bold leading-tight max-w-[900px]" style={{ color: theme.textPrimary }}>
              {seed?.title ?? 'Untitled'}
            </h1>
            {seed?.year && <p className="mt-2 text-[13px] tabular-nums" style={{ color: theme.textSecondary }}>{seed.year}</p>}
          </div>
          {timeline?.from_cache && (
            <motion.span initial={{ scale: 0.9, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
              className="px-3 py-1.5 rounded-full text-[11px] font-medium"
              style={isDark
                ? { color: '#FACC15', background: '#FACC1514', border: '1px solid #FACC1540' }
                : { color: '#92400E', background: '#FEF3C7', border: '1px solid #F59E0B66' }}>
              ⚡ from cache
            </motion.span>
          )}
        </div>

        {/* Metrics */}
        <div className="mt-8 grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { label: 'Papers in chain', value: formatNumber(timeline?.total_papers ?? null) },
            { label: 'Year range', value: timeline?.year_range?.start && timeline?.year_range?.end ? `${timeline.year_range.start} → ${timeline.year_range.end}` : 'N/A', sub: typeof span === 'number' ? `${span} yrs` : undefined },
            { label: 'Tree nodes', value: formatNumber(tree ? countTreeNodes(tree) : null) },
            { label: 'Total elapsed', value: `${elapsed.total_sec.toFixed(1)}s`, sub: `tree ${elapsed.tree_sec.toFixed(1)}s · evo ${elapsed.evolution_sec.toFixed(1)}s` },
          ].map((m) => (
            <div key={m.label} className="rounded-xl px-4 py-3 transition-colors"
              style={{ background: isDark ? 'rgba(18,20,26,0.7)' : 'rgba(255,255,255,0.85)', border: `1px solid ${theme.border}`, backdropFilter: 'blur(8px)' }}>
              <div className="text-[10px] uppercase tracking-[0.12em] font-semibold" style={{ color: theme.textMuted }}>{m.label}</div>
              <div className="mt-1.5 text-[18px] font-bold tabular-nums leading-tight" style={{ color: theme.textPrimary }}>{m.value}</div>
              {m.sub && <div className="mt-0.5 text-[10px] tabular-nums" style={{ color: theme.textMuted }}>{m.sub}</div>}
            </div>
          ))}
        </div>
      </motion.div>

      {/* Tab bar */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.1 }}
        className="sticky top-[68px] z-30 mb-8">
        <div className="flex gap-1 p-1 rounded-xl w-fit"
          style={{ background: isDark ? 'rgba(18,20,26,0.70)' : 'rgba(255,255,255,0.80)', border: `1px solid ${theme.border}`, backdropFilter: 'blur(14px)' }}>
          {tabs.map((t) => (
            <button key={t.id} disabled={t.disabled} onClick={() => setTab(t.id)}
              className="relative px-4 py-2 text-[13px] font-medium transition-colors disabled:opacity-30 disabled:cursor-not-allowed">
              {tab === t.id && (
                <motion.div layoutId="tab-pill" transition={{ type: 'spring', stiffness: 320, damping: 28 }}
                  className="absolute inset-0 rounded-lg"
                  style={{ background: isDark ? '#1A1D25' : '#FFFFFF', boxShadow: '0 1px 8px rgba(0,0,0,0.10)' }}
                />
              )}
              <span className="relative z-10 flex items-center gap-2"
                style={{ color: tab === t.id ? theme.textPrimary : theme.textSecondary }}>
                <span className="text-[11px]" style={{ color: theme.accent }}>{t.icon}</span>
                {t.label}
              </span>
            </button>
          ))}
        </div>
      </motion.div>

      {/* Tab content */}
      <AnimatePresence mode="wait">
        <motion.div key={tab} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}>
          {tab === 'timeline' && timeline && <TimelineView timeline={timeline} theme={theme} />}
          {tab === 'tree' && tree && <TreeView tree={tree} theme={theme} />}
          {tab === 'raw' && <RawJson result={result} theme={theme} />}
        </motion.div>
      </AnimatePresence>
    </section>
  );
}

function RawJson({ result, theme }: { result: AnalyzeResponse; theme: Theme }) {
  const json = JSON.stringify(result, null, 2);
  const fname = `researchlineage_${(result.paper_id || 'output').replace(/[:/]/g, '_')}.json`;
  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <p className="text-[12px]" style={{ color: theme.textSecondary }}>Full response · {(json.length / 1024).toFixed(1)} KB</p>
        <a href={`data:application/json;charset=utf-8,${encodeURIComponent(json)}`} download={fname}
          className="px-3 py-1.5 rounded-lg text-[12px] transition-colors"
          style={{ background: theme.cardBgAlt, border: `1px solid ${theme.border}`, color: theme.textPrimary }}>
          ⬇ Download JSON
        </a>
      </div>
      <pre className="rounded-xl px-5 py-5 text-[11px] leading-relaxed overflow-auto max-h-[70vh] font-mono"
        style={{ background: theme.cardBgAlt, border: `1px solid ${theme.border}`, color: theme.textSecondary }}>
        {json}
      </pre>
    </div>
  );
}

function countTreeNodes(tree: { ancestors: unknown[]; descendants: unknown[] }): number {
  const walk = (nodes: unknown[], childKey: 'ancestors' | 'children'): number => {
    let total = nodes.length;
    for (const n of nodes) {
      const children = (n as Record<string, unknown>)[childKey] as unknown[] | undefined;
      if (Array.isArray(children)) total += walk(children, childKey);
    }
    return total;
  };
  return 1 + walk(tree.ancestors, 'ancestors') + walk(tree.descendants, 'children');
}
