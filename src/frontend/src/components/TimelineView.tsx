import React, { useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import type {
  BreakthroughLevel,
  Timeline,
  TimelineEntry,
} from '../lib/types';
import { formatNumber } from '../lib/utils';
import type { Theme } from '../lib/theme';
import { ChatPanel } from './ChatPanel';
import { submitFeedback } from '../lib/api';

interface TimelineViewProps {
  timeline: Timeline;
  theme: Theme;
}

export function TimelineView({ timeline, theme }: TimelineViewProps) {
  const isDark = theme.id === 'dark';
  const chain = timeline.chain;
  const seedTitle = timeline.seed_paper?.title ?? '';
  const seedPaperId = timeline.seed_paper?.paper_id ?? '';
  const [chatOpen, setChatOpen] = useState(false);
  const [legendOpen, setLegendOpen] = useState(false);
  const legendRef = useRef<HTMLDivElement>(null);

  return (
    <div className="flex gap-6 items-start">
      {/* Timeline — flex-1 fills all remaining space */}
      <div className="relative flex-1 min-w-0">
        {/* Legend info button */}
        <div className="relative inline-block mb-6 ml-16" ref={legendRef}>
          <button
            onClick={() => setLegendOpen((v) => !v)}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] transition-colors"
            style={{
              color: legendOpen ? theme.accent : theme.textMuted,
              border: `1px solid ${legendOpen ? theme.accent + '55' : theme.border}`,
              background: legendOpen
                ? (isDark ? `${theme.accent}12` : `${theme.accent}0E`)
                : 'transparent',
            }}
          >
            <span style={{ fontWeight: 600 }}>ⓘ</span> Badge guide
          </button>

          <AnimatePresence>
            {legendOpen && (
              <motion.div
                initial={{ opacity: 0, y: -6, scale: 0.97 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: -6, scale: 0.97 }}
                transition={{ duration: 0.18 }}
                className="absolute left-0 top-full mt-2 z-30 rounded-2xl p-4 w-[380px]"
                style={{
                  background: isDark ? '#0E1018' : '#FFFFFF',
                  border: `1px solid ${theme.border}`,
                  boxShadow: isDark
                    ? '0 12px 40px rgba(0,0,0,0.55)'
                    : '0 8px 32px rgba(0,0,0,0.12)',
                }}
              >
                {/* Breakthrough levels */}
                <p className="text-[10px] font-semibold uppercase tracking-[0.14em] mb-2.5"
                  style={{ color: theme.textMuted }}>Breakthrough level</p>
                <div className="space-y-2 mb-4">
                  {LEGEND_BREAKTHROUGH.map(({ level, desc }) => {
                    const s = BADGE_STYLES[level];
                    return (
                      <div key={level} className="flex items-start gap-2.5">
                        <span className="px-2 py-0.5 rounded-md text-[10px] font-semibold uppercase tracking-wider border shrink-0 mt-0.5"
                          style={{ color: s.color, background: s.bg, borderColor: s.border }}>
                          <span className="mr-1">{s.icon}</span>{level}
                        </span>
                        <span className="text-[11.5px] leading-snug" style={{ color: theme.textSecondary }}>{desc}</span>
                      </div>
                    );
                  })}
                </div>

                {/* Source types */}
                <p className="text-[10px] font-semibold uppercase tracking-[0.14em] mb-2.5"
                  style={{ color: theme.textMuted }}>Source type</p>
                <div className="space-y-2">
                  {LEGEND_SOURCE.map(({ label, pill, desc }) => (
                    <div key={label} className="flex items-start gap-2.5">
                      <span className="shrink-0 mt-0.5">{pill}</span>
                      <span className="text-[11.5px] leading-snug" style={{ color: theme.textSecondary }}>{desc}</span>
                    </div>
                  ))}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Animated vertical rail */}
        <div
          aria-hidden
          className="absolute left-[27px] top-2 bottom-2 w-px"
          style={{
            background: `linear-gradient(to bottom, transparent 0%, ${theme.accent}44 8%, ${theme.seed}55 50%, ${theme.accent}44 92%, transparent 100%)`,
          }}
        />

        <ol className="space-y-8">
          {chain.map((entry, i) => (
            <TimelineCard
              key={`${entry.paper.paper_id}-${i}`}
              entry={entry}
              index={i}
              total={chain.length}
              theme={theme}
              isDark={isDark}
              seedPaperId={seedPaperId}
            />
          ))}
        </ol>

        <motion.div
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.6 }}
          className="text-center mt-10 text-[11px] uppercase tracking-[0.14em]"
          style={{ color: theme.textMuted }}
        >
          ◇ Seed paper · {chain.length} total
        </motion.div>
      </div>

      {/* Chat panel — fixed to viewport right edge */}
      <ChatPanel
        paperId={seedPaperId}
        seedTitle={seedTitle}
        theme={theme}
        open={chatOpen}
        onOpenChange={setChatOpen}
      />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Timeline card
// ─────────────────────────────────────────────────────────────────────────

function TimelineCard({
  entry,
  index,
  total,
  theme,
  isDark,
  seedPaperId,
}: {
  entry: TimelineEntry;
  index: number;
  total: number;
  theme: Theme;
  isDark: boolean;
  seedPaperId: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const paper = entry.paper;
  const analysis = entry.analysis;
  const comparison = entry.comparison;
  const bt = (analysis.breakthrough_level ?? 'minor') as BreakthroughLevel;
  const isSeed = index === total - 1;

  return (
    <motion.li
      initial={{ opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.25 }}
      transition={{ duration: 0.5, delay: Math.min(index * 0.05, 0.35), ease: [0.22, 1, 0.36, 1] }}
      className="relative pl-16"
    >
      {/* Rail node */}
      <div className="absolute left-5 top-6 flex items-center justify-center">
        <motion.div
          className="w-5 h-5 rounded-full border-2 flex items-center justify-center"
          style={isSeed ? {
            background: `linear-gradient(135deg, ${theme.seed}, #FB923C)`,
            borderColor: theme.seed,
            boxShadow: `0 0 24px ${theme.seed}88`,
          } : {
            background: theme.bodyBg,
            borderColor: `${theme.accent}99`,
          }}
          whileHover={{ scale: 1.2 }}
          transition={{ type: 'spring', stiffness: 300, damping: 20 }}
        >
          {!isSeed && <div className="w-1.5 h-1.5 rounded-full" style={{ background: theme.accent }} />}
        </motion.div>
        {isSeed && (
          <motion.div
            className="absolute w-5 h-5 rounded-full"
            style={{ background: `${theme.seed}44` }}
            animate={{ scale: [1, 1.8, 1], opacity: [0.6, 0, 0.6] }}
            transition={{ duration: 2.4, repeat: Infinity }}
          />
        )}
      </div>

      {/* Card */}
      <motion.div
        whileHover={{ y: -2 }}
        transition={{ type: 'spring', stiffness: 300, damping: 26 }}
        className="relative rounded-2xl transition-all"
        style={{
          background: isSeed
            ? isDark ? `linear-gradient(135deg, ${theme.seed}18, rgba(18,20,26,0.70))` : `linear-gradient(135deg, ${theme.seed}22, rgba(255,255,255,0.95))`
            : isDark ? 'rgba(18,20,26,0.70)' : 'rgba(255,255,255,0.85)',
          border: isSeed ? `1px solid ${theme.seed}${isDark ? '44' : '66'}` : `1px solid ${theme.border}`,
          backdropFilter: 'blur(14px)',
          boxShadow: isSeed && !isDark ? `0 4px 24px ${theme.seed}22, 0 2px 8px rgba(0,0,0,0.06)` : isDark ? 'inset 0 1px 0 0 rgba(255,255,255,0.03)' : '0 2px 16px rgba(0,0,0,0.06)',
        }}
      >
        <div className="p-6">
          {/* Meta row */}
          <div className="flex flex-wrap items-center gap-2 mb-4">
            <YearChip year={paper.year} theme={theme} />
            <BreakthroughBadge level={bt} />
            <SourcePill source={entry.source_type} foundational={entry.is_foundational} />
            {isSeed && (
              <span className="px-2.5 py-0.5 rounded-md text-[10px] font-semibold tracking-wider uppercase"
                style={{ background: `${theme.seed}14`, color: theme.seed, border: `1px solid ${theme.seed}44` }}>
                ◎ Seed
              </span>
            )}
            <span className="ml-auto text-[11px] tabular-nums" style={{ color: theme.textMuted }}>
              {typeof paper.citation_count === 'number' ? `${formatNumber(paper.citation_count)} citations` : ''}
            </span>
          </div>

          {/* Title */}
          <h3 className="text-[18px] font-semibold leading-snug" style={{ color: theme.textPrimary }}>
            {paper.title || 'Untitled'}
          </h3>

          {/* Key innovation */}
          {analysis.key_innovation && (
            <div className="mt-4 flex gap-3">
              <div className="shrink-0 w-1 rounded-full" style={{ background: `linear-gradient(to bottom, ${theme.accent}, ${theme.accent}30)` }} />
              <p className="text-[13px] leading-relaxed" style={{ color: theme.textSecondary }}>
                <span className="font-medium" style={{ color: theme.accent }}>Key innovation · </span>
                {analysis.key_innovation}
              </p>
            </div>
          )}

          {/* Action row */}
          <div className="mt-5 flex items-center gap-3">
            <button
              onClick={() => setExpanded((e) => !e)}
              className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-[12px] transition-colors"
              style={{ color: theme.textSecondary, border: `1px solid ${theme.border}` }}
              onMouseEnter={(e) => (e.currentTarget.style.background = isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.04)')}
              onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
            >
              <motion.span animate={{ rotate: expanded ? 90 : 0 }} className="inline-block">▸</motion.span>
              {expanded ? 'Hide details' : 'Show details'}
            </button>
            {paper.arxiv_id && (
              <a href={`https://arxiv.org/abs/${paper.arxiv_id}`} target="_blank" rel="noreferrer"
                className="inline-flex items-center gap-1 text-[12px] transition-colors"
                style={{ color: theme.textMuted }}
                onMouseEnter={(e) => (e.currentTarget.style.color = theme.accent)}
                onMouseLeave={(e) => (e.currentTarget.style.color = theme.textMuted)}
              >
                arXiv:{paper.arxiv_id} ↗
              </a>
            )}
          </div>
        </div>

        {/* Expandable detail */}
        <AnimatePresence initial={false}>
          {expanded && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
              className="overflow-hidden"
            >
              <div className="px-6 pb-6 pt-1" style={{ borderTop: `1px solid ${theme.border}` }}>
                <div className="grid md:grid-cols-2 gap-x-6 gap-y-5 mt-5">
                  <DetailBlock label="Problem addressed" body={analysis.problem_addressed} theme={theme} />
                  <DetailBlock label="Core method" body={analysis.core_method} theme={theme} />
                  <DetailBlock label="ELI5" body={analysis.explanation_eli5} theme={theme} />
                  <DetailBlock label="Intuitive" body={analysis.explanation_intuitive} theme={theme} />
                </div>

                {analysis.explanation_technical && (
                  <div className="mt-5">
                    <DetailBlock label="Technical" body={analysis.explanation_technical} theme={theme} />
                  </div>
                )}

                {(analysis.limitations?.length ?? 0) > 0 && (
                  <div className="mt-5">
                    <p className="text-[10px] uppercase tracking-[0.14em] font-semibold mb-2" style={{ color: theme.textMuted }}>Limitations</p>
                    <ul className="space-y-1.5">
                      {analysis.limitations!.map((lim, i) => (
                        <li key={i} className="text-[12px] flex gap-2" style={{ color: theme.textSecondary }}>
                          <span style={{ color: theme.seed, opacity: 0.7 }}>−</span>{lim}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {entry.secondary_influences.length > 0 && (
                  <div className="mt-5">
                    <p className="text-[10px] uppercase tracking-[0.14em] font-semibold mb-2" style={{ color: theme.textMuted }}>Secondary influences</p>
                    <div className="flex flex-wrap gap-2">
                      {entry.secondary_influences.map((inf, i) => (
                        <div key={i} className="px-2.5 py-1.5 rounded-md text-[11px] max-w-[320px]"
                          style={{ background: isDark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.04)', border: `1px solid ${theme.border}`, color: theme.textSecondary }}>
                          <span className="font-medium" style={{ color: theme.textPrimary }}>
                            {inf.title || (inf.paper_id && inf.paper_id.slice(0, 12) + '...') || 'Unknown'}
                          </span>
                          {inf.year && <span className="tabular-nums ml-1">({inf.year})</span>}
                          {inf.contribution && <span className="block mt-0.5 line-clamp-2" style={{ color: theme.textMuted }}>{inf.contribution}</span>}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {paper.abstract && (
                  <div className="mt-5">
                    <p className="text-[10px] uppercase tracking-[0.14em] font-semibold mb-2" style={{ color: theme.textMuted }}>Abstract</p>
                    <p className="text-[12px] leading-relaxed line-clamp-6" style={{ color: theme.textSecondary }}>{paper.abstract}</p>
                  </div>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>

      {/* Comparison card → leads to next paper */}
      {comparison && index < total - 1 && (
        <ComparisonCard
          comparison={comparison}
          theme={theme}
          isDark={isDark}
          seedPaperId={seedPaperId}
          relatedPaperId={paper.paper_id}
        />
      )}
    </motion.li>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Sub-components
// ─────────────────────────────────────────────────────────────────────────

function DetailBlock({ label, body, theme }: { label: string; body?: string | null; theme: Theme }) {
  if (!body) return null;
  return (
    <div>
      <p className="text-[10px] uppercase tracking-[0.14em] font-semibold mb-1.5" style={{ color: theme.textMuted }}>{label}</p>
      <p className="text-[12.5px] leading-relaxed" style={{ color: theme.textSecondary }}>{body}</p>
    </div>
  );
}

function YearChip({ year, theme }: { year: number | null; theme: Theme }) {
  return (
    <span className="px-2 py-0.5 rounded-md text-[11px] font-semibold tabular-nums"
      style={{ background: `${theme.textMuted}14`, color: theme.textSecondary, border: `1px solid ${theme.border}` }}>
      {year ?? '?'}
    </span>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Legend data
// ─────────────────────────────────────────────────────────────────────────

const LEGEND_BREAKTHROUGH: { level: BreakthroughLevel; desc: string }[] = [
  { level: 'revolutionary', desc: 'Paradigm shift — redefines an entire field or introduces a fundamentally new approach.' },
  { level: 'major',         desc: 'Significant leap — substantially advances state-of-the-art in a meaningful direction.' },
  { level: 'moderate',      desc: 'Incremental advance — solid improvement on prior work within an established direction.' },
  { level: 'minor',         desc: 'Marginal refinement — small contribution, optimization, or ablation.' },
];

const LEGEND_SOURCE: { label: string; pill: React.ReactElement; desc: string }[] = [
  {
    label: 'Full text',
    pill: (
      <span className="px-2.5 py-0.5 rounded-full text-[10px] font-medium bg-[#22c55e]/10 text-[#4ade80] border border-[#22c55e]/30">
        ● Full text
      </span>
    ),
    desc: 'Full PDF was sent to Gemini — lowest hallucination risk.',
  },
  {
    label: 'Abstract only',
    pill: (
      <span className="px-2.5 py-0.5 rounded-full text-[10px] font-medium bg-[#d97706]/10 text-[#fbbf24] border border-[#d97706]/30">
        ◐ Abstract only
      </span>
    ),
    desc: 'Only the abstract was available — higher hallucination risk.',
  },
  {
    label: 'Foundation',
    pill: (
      <span className="px-2.5 py-0.5 rounded-full text-[10px] font-medium bg-[#7c3aed]/10 text-[#a78bfa] border border-[#7c3aed]/30">
        🏛 Foundation
      </span>
    ),
    desc: 'Identified as a foundational work in the lineage — the earliest anchor paper.',
  },
];

const BADGE_STYLES: Record<
  BreakthroughLevel,
  { color: string; bg: string; border: string; icon: string }
> = {
  revolutionary: {
    color: '#F87171',
    bg: 'rgba(248,113,113,0.08)',
    border: 'rgba(248,113,113,0.32)',
    icon: '▲',
  },
  major: {
    color: '#FB923C',
    bg: 'rgba(251,146,60,0.08)',
    border: 'rgba(251,146,60,0.32)',
    icon: '◆',
  },
  moderate: {
    color: '#FACC15',
    bg: 'rgba(250,204,21,0.08)',
    border: 'rgba(250,204,21,0.32)',
    icon: '●',
  },
  minor: {
    color: '#94A3B8',
    bg: 'rgba(148,163,184,0.08)',
    border: 'rgba(148,163,184,0.28)',
    icon: '○',
  },
};

function BreakthroughBadge({ level }: { level: BreakthroughLevel }) {
  const s = BADGE_STYLES[level];
  return (
    <span
      className="px-2 py-0.5 rounded-md text-[10px] font-semibold uppercase tracking-wider border"
      style={{ color: s.color, background: s.bg, borderColor: s.border }}
    >
      <span className="mr-1">{s.icon}</span>
      {level}
    </span>
  );
}

function SourcePill({
  source,
  foundational,
}: {
  source: string;
  foundational: boolean;
}) {
  if (foundational) {
    return (
      <span className="px-2.5 py-0.5 rounded-full text-[10px] font-medium bg-[#7c3aed]/10 text-[#a78bfa] border border-[#7c3aed]/30">
        🏛 Foundation
      </span>
    );
  }
  if (source === 'ABSTRACT_ONLY') {
    return (
      <span className="px-2.5 py-0.5 rounded-full text-[10px] font-medium bg-[#d97706]/10 text-[#fbbf24] border border-[#d97706]/30">
        ◐ Abstract only
      </span>
    );
  }
  return (
    <span className="px-2.5 py-0.5 rounded-full text-[10px] font-medium bg-[#22c55e]/10 text-[#4ade80] border border-[#22c55e]/30">
      ● Full text
    </span>
  );
}

function ComparisonCard({ comparison, theme, isDark, seedPaperId, relatedPaperId }: {
  comparison: NonNullable<TimelineEntry['comparison']>;
  theme: Theme;
  isDark: boolean;
  seedPaperId: string;
  relatedPaperId: string;
}) {
  const [thumb, setThumb] = useState<1 | -1 | null>(null);
  const [comment, setComment] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  async function handleThumb(rating: 1 | -1) {
    if (submitted) return;
    setThumb(rating);
    // thumbs up submits immediately; thumbs down waits for optional comment
    if (rating === 1) {
      setSubmitting(true);
      try {
        await submitFeedback({
          paper_id: seedPaperId,
          related_paper_id: relatedPaperId,
          view_type: 'timeline',
          feedback_target: 'predecessor_selection',
          rating: 1,
        });
        setSubmitted(true);
      } finally {
        setSubmitting(false);
      }
    }
  }

  async function handleSubmitComment() {
    if (submitted || submitting) return;
    setSubmitting(true);
    try {
      await submitFeedback({
        paper_id: seedPaperId,
        related_paper_id: relatedPaperId,
        view_type: 'timeline',
        feedback_target: 'predecessor_selection',
        rating: -1,
        comment: comment.trim() || null,
      });
      setSubmitted(true);
    } finally {
      setSubmitting(false);
    }
  }

  const borderColor = `${theme.accent}${isDark ? '30' : '50'}`;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }} whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.3 }} transition={{ duration: 0.5, delay: 0.15 }}
      className="relative mt-5 mb-1 ml-2"
    >
      <div className="flex items-start gap-3">
        <div className="shrink-0 mt-1 text-[18px] font-bold" style={{ color: theme.accent }}>↓</div>
        <div className="flex-1 rounded-xl overflow-hidden"
          style={{
            border: `1px solid ${borderColor}`,
            background: isDark ? `${theme.accent}08` : `${theme.accent}0F`,
            boxShadow: isDark ? 'none' : `0 2px 12px ${theme.accent}18`,
          }}>
          {/* Header */}
          <div className="px-5 py-3 flex items-center gap-2"
            style={{ background: isDark ? `${theme.accent}10` : `${theme.accent}18`, borderBottom: `1px solid ${theme.accent}${isDark ? '20' : '35'}` }}>
            <span className="text-[13px]" style={{ color: theme.accent }}>↟</span>
            <p className="text-[10px] font-bold uppercase tracking-[0.16em]" style={{ color: theme.accent }}>
              Improvement over predecessor
            </p>
          </div>

          {/* Content */}
          <div className="px-5 py-4 grid md:grid-cols-2 gap-x-6 gap-y-4">
            <CompField label="What was improved" body={comparison.what_was_improved} theme={theme} isDark={isDark} />
            <CompField label="How" body={comparison.how_it_was_improved} theme={theme} isDark={isDark} />
            <CompField label="Why it matters" body={comparison.why_it_matters} theme={theme} isDark={isDark} />
            <CompField label="Problem solved" body={comparison.problem_solved_from_predecessor} theme={theme} isDark={isDark} />
          </div>

          {/* Feedback footer */}
          <div className="px-5 py-3 flex flex-col gap-2"
            style={{ borderTop: `1px solid ${theme.accent}${isDark ? '18' : '28'}` }}>
            {submitted ? (
              <p className="text-[11px]" style={{ color: theme.textMuted }}>
                Thanks for the feedback!
              </p>
            ) : (
              <>
                <div className="flex items-center gap-3">
                  <span className="text-[10px] uppercase tracking-[0.12em]" style={{ color: theme.textMuted }}>
                    Correct predecessor?
                  </span>
                  <div className="flex items-center gap-1.5">
                    <button
                      onClick={() => handleThumb(1)}
                      disabled={submitting}
                      className="w-7 h-7 rounded-lg flex items-center justify-center text-[14px] transition-all"
                      style={{
                        background: thumb === 1
                          ? (isDark ? 'rgba(74,222,128,0.15)' : 'rgba(74,222,128,0.12)')
                          : (isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.04)'),
                        border: `1px solid ${thumb === 1 ? '#4ADE8066' : theme.border}`,
                        color: thumb === 1 ? '#4ADE80' : theme.textMuted,
                      }}
                    >
                      👍
                    </button>
                    <button
                      onClick={() => handleThumb(-1)}
                      disabled={submitting}
                      className="w-7 h-7 rounded-lg flex items-center justify-center text-[14px] transition-all"
                      style={{
                        background: thumb === -1
                          ? (isDark ? 'rgba(248,113,113,0.15)' : 'rgba(248,113,113,0.10)')
                          : (isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.04)'),
                        border: `1px solid ${thumb === -1 ? '#F8717166' : theme.border}`,
                        color: thumb === -1 ? '#F87171' : theme.textMuted,
                      }}
                    >
                      👎
                    </button>
                  </div>
                </div>

                {/* Comment field — only on thumbs down */}
                <AnimatePresence>
                  {thumb === -1 && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: 'auto' }}
                      exit={{ opacity: 0, height: 0 }}
                      transition={{ duration: 0.22 }}
                      className="overflow-hidden"
                    >
                      <div className="flex gap-2 pt-1">
                        <input
                          type="text"
                          value={comment}
                          onChange={(e) => setComment(e.target.value)}
                          onKeyDown={(e) => { if (e.key === 'Enter') handleSubmitComment(); }}
                          placeholder="What's wrong with this predecessor? (optional)"
                          className="flex-1 bg-transparent outline-none text-[11.5px] px-2.5 py-1.5 rounded-lg"
                          style={{
                            color: theme.textPrimary,
                            border: `1px solid ${theme.border}`,
                            background: isDark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.04)',
                          }}
                        />
                        <button
                          onClick={handleSubmitComment}
                          disabled={submitting}
                          className="px-3 py-1.5 rounded-lg text-[11px] font-medium transition-colors"
                          style={{
                            background: isDark ? 'rgba(248,113,113,0.15)' : 'rgba(248,113,113,0.10)',
                            color: '#F87171',
                            border: '1px solid rgba(248,113,113,0.30)',
                          }}
                        >
                          {submitting ? '…' : 'Send'}
                        </button>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </>
            )}
          </div>
        </div>
      </div>
    </motion.div>
  );
}

function CompField({ label, body, theme, isDark }: { label: string; body?: string | null; theme: Theme; isDark: boolean }) {
  if (!body) return null;
  return (
    <div>
      <div className="text-[9px] uppercase tracking-[0.14em] font-semibold mb-1" style={{ color: isDark ? theme.textMuted : theme.accent }}>{label}</div>
      <div className="text-[12.5px] leading-relaxed" style={{ color: theme.textPrimary }}>{body}</div>
    </div>
  );
}
