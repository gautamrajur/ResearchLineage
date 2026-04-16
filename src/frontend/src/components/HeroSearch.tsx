import { useCallback, useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { searchPapers, ApiError } from '../lib/api';
import type { SearchResultPaper } from '../lib/types';
import type { Theme } from '../lib/theme';
import { cn, formatNumber, truncate } from '../lib/utils';

interface HeroSearchProps {
  onSubmitPaperId: (id: string) => void;
  onPickResult: (paper: SearchResultPaper) => void;
  error?: string | null;
  theme: Theme;
}

const EXAMPLES = [
  { id: '1706.03762', title: 'Attention Is All You Need', year: 2017 },
  { id: '1512.03385', title: 'Deep Residual Learning', year: 2015 },
  { id: '1406.2661', title: 'Generative Adversarial Nets', year: 2014 },
  { id: '1810.04805', title: 'BERT', year: 2018 },
];

function isDirectId(q: string): boolean {
  return /^(arxiv:|arxiv\.org|[0-9]{4}\.[0-9]{4,5})/i.test(q) || /^[A-Fa-f0-9]{30,}$/.test(q);
}

export function HeroSearch({ onSubmitPaperId, onPickResult, error, theme }: HeroSearchProps) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResultPaper[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [focused, setFocused] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const q = query.trim();
    if (q.length < 3) { setResults([]); setLoading(false); setSearchError(null); return; }
    if (/^(arxiv:|arxiv\.org|[0-9]{4}\.[0-9]{4,5})/i.test(q)) { setResults([]); setLoading(false); return; }

    setLoading(true);
    setSearchError(null);
    const ctrl = new AbortController();
    abortRef.current?.abort();
    abortRef.current = ctrl;

    const t = setTimeout(async () => {
      try {
        const resp = await searchPapers(q, ctrl.signal);
        if (!ctrl.signal.aborted) { setResults(resp.results ?? []); setLoading(false); }
      } catch (e) {
        if (ctrl.signal.aborted) return;
        setLoading(false);
        setSearchError(e instanceof ApiError ? e.detail : e instanceof Error ? e.message : 'Search failed');
      }
    }, 350);
    return () => { clearTimeout(t); ctrl.abort(); };
  }, [query]);

  const canSubmit =
    query.trim().length > 0 &&
    (isDirectId(query.trim()) || (!loading && results.length > 0));

  const submit = useCallback(() => {
    const q = query.trim();
    if (!q) return;
    if (isDirectId(q)) {
      onSubmitPaperId(q); return;
    }
    if (!loading && results[0]) onPickResult(results[0]);
  }, [query, results, loading, onSubmitPaperId, onPickResult]);

  const isDark = theme.id === 'dark';
  const boxShadowFocused = isDark
    ? '0 0 0 1px rgba(45,212,191,0.4), 0 20px 80px -20px rgba(45,212,191,0.3)'
    : `0 0 0 2px ${theme.accent}66, 0 20px 60px -16px ${theme.accent}22`;
  const boxShadowIdle = isDark
    ? '0 0 0 1px rgba(255,255,255,0.08), 0 12px 40px -12px rgba(0,0,0,0.6)'
    : `0 0 0 1px ${theme.border}, 0 8px 32px -8px rgba(0,0,0,0.10)`;

  return (
    <section className="min-h-screen flex flex-col items-center justify-center px-6 pt-24 pb-16">
      {/* Eyebrow */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.05 }}
        className="inline-flex items-center gap-2 px-3 py-1 rounded-full mb-6"
        style={{ border: `1px solid ${theme.border}`, background: isDark ? 'rgba(18,20,26,0.60)' : 'rgba(255,255,255,0.65)' }}
      >
        <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: theme.accent }} />
        <span className="text-[11px] uppercase tracking-[0.14em] font-medium" style={{ color: theme.textSecondary }}>
          Powered by Gemini · Semantic Scholar
        </span>
      </motion.div>

      {/* Title */}
      <motion.h1
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.7, delay: 0.1, ease: [0.22, 1, 0.36, 1] }}
        className="text-center text-[42px] sm:text-[62px] font-bold leading-[1.02] tracking-tight max-w-[900px]"
        style={{ color: theme.textPrimary }}
      >
        Trace the intellectual{' '}
        <span
          className="bg-clip-text text-transparent"
          style={{
            backgroundImage: `linear-gradient(135deg, ${theme.seed}, ${theme.accent})`,
          }}
        >
          ancestry
        </span>{' '}
        of any paper.
      </motion.h1>

      <motion.p
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.7, delay: 0.2 }}
        className="mt-5 text-center text-[15px] max-w-[600px] leading-relaxed"
        style={{ color: theme.textSecondary }}
      >
        From one seed paper, we reconstruct its lineage: the ideas that led to it,
        and the research it set in motion.
      </motion.p>

      {/* Search box */}
      <motion.div
        initial={{ opacity: 0, y: 16, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.6, delay: 0.3, ease: [0.22, 1, 0.36, 1] }}
        className="mt-10 w-full max-w-[720px] relative"
      >
        <div
          className="relative rounded-2xl transition-all duration-300"
          style={{ boxShadow: focused ? boxShadowFocused : boxShadowIdle }}
        >
          <div
            className="flex items-center gap-3 rounded-2xl px-5 py-4"
            style={{
              background: isDark ? 'rgba(18,20,26,0.85)' : 'rgba(255,255,255,0.92)',
              backdropFilter: 'blur(18px)',
            }}
          >
            <svg className="w-5 h-5 shrink-0" style={{ color: focused ? theme.accent : theme.textMuted }} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>
            </svg>
            <input
              autoFocus
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onFocus={() => setFocused(true)}
              onBlur={() => setTimeout(() => setFocused(false), 150)}
              onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); submit(); } }}
              placeholder="Paper title or arXiv ID, e.g. Attention Is All You Need or 1706.03762"
              className="flex-1 bg-transparent outline-none text-[15px]"
              style={{ color: theme.textPrimary }}
            />
            {loading && (
              <svg className="w-4 h-4 animate-spin shrink-0" style={{ color: theme.accent }} viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2.5" strokeOpacity="0.2"/>
                <path d="M22 12a10 10 0 0 1-10 10" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"/>
              </svg>
            )}
            <button
              onClick={submit}
              disabled={!canSubmit}
              className="px-4 py-1.5 rounded-lg text-[13px] font-semibold transition-all shrink-0"
              style={canSubmit ? {
                background: `linear-gradient(135deg, ${theme.seed}, ${theme.accent})`,
                color: '#fff',
                boxShadow: `0 4px 20px ${theme.accent}44`,
              } : {
                background: isDark ? '#1A1D25' : '#E5E7EB',
                color: theme.textMuted,
                cursor: 'not-allowed',
              }}
            >
              Trace →
            </button>
          </div>

          {/* Dropdown */}
          <AnimatePresence>
            {focused && (results.length > 0 || searchError) && (
              <motion.div
                initial={{ opacity: 0, y: -6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.18 }}
                className="absolute left-0 right-0 top-[calc(100%+6px)] z-20 rounded-2xl overflow-hidden"
                style={{
                  background: isDark ? 'rgba(18,20,26,0.97)' : 'rgba(255,255,255,0.97)',
                  border: `1px solid ${theme.border}`,
                  boxShadow: '0 20px 60px rgba(0,0,0,0.14)',
                  backdropFilter: 'blur(18px)',
                }}
              >
                {searchError && <div className="px-5 py-4 text-[13px] text-red-500">⚠ {searchError}</div>}
                {results.slice(0, 8).map((paper, i) => (
                  <motion.button
                    key={paper.paperId}
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.22, delay: i * 0.03 }}
                    onMouseDown={(e) => { e.preventDefault(); onPickResult(paper); }}
                    className="w-full text-left px-5 py-3 group transition-colors"
                    style={{ borderBottom: `1px solid ${theme.border}` }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = isDark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.03)')}
                    onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <p className="text-[14px] font-medium leading-snug line-clamp-2" style={{ color: theme.textPrimary }}>
                          {paper.title}
                        </p>
                        <div className="mt-1 flex items-center gap-3 text-[11px]" style={{ color: theme.textMuted }}>
                          {paper.year && <span className="font-semibold tabular-nums" style={{ color: theme.accent }}>{paper.year}</span>}
                          {paper.authors?.[0] && (
                            <span className="truncate max-w-[200px]">
                              {paper.authors.slice(0, 2).map(a => a.name).join(', ')}{paper.authors.length > 2 ? ' et al.' : ''}
                            </span>
                          )}
                          {typeof paper.citationCount === 'number' && (
                            <span className="tabular-nums">{formatNumber(paper.citationCount)} cites</span>
                          )}
                        </div>
                        {paper.abstract && (
                          <p className="mt-1 text-[11px] line-clamp-1" style={{ color: theme.textMuted }}>
                            {truncate(paper.abstract, 130)}
                          </p>
                        )}
                      </div>
                      <span className="text-lg transition-colors" style={{ color: theme.textMuted }}>→</span>
                    </div>
                  </motion.button>
                ))}
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {error && (
          <motion.p initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }}
            className="mt-4 text-center text-[13px] text-red-500">⚠ {error}</motion.p>
        )}
      </motion.div>

      {/* Examples */}
      <motion.div
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.6, delay: 0.55 }}
        className="mt-10 flex flex-wrap gap-2.5 justify-center max-w-[720px]"
      >
        <span className="text-[11px] uppercase tracking-[0.12em] self-center mr-2" style={{ color: theme.textMuted }}>Try</span>
        {EXAMPLES.map((ex, i) => (
          <motion.button
            key={ex.id}
            initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.6 + i * 0.07 }}
            whileHover={{ y: -2, scale: 1.02 }}
            onClick={() => onSubmitPaperId(ex.id)}
            className={cn('px-3 py-1.5 rounded-full text-[12px] transition-all')}
            style={{
              background: isDark ? 'rgba(18,20,26,0.70)' : 'rgba(255,255,255,0.75)',
              border: `1px solid ${theme.border}`,
              color: theme.textSecondary,
            }}
          >
            <span className="font-semibold tabular-nums mr-1.5" style={{ color: theme.accent }}>{ex.year}</span>
            {ex.title}
          </motion.button>
        ))}
      </motion.div>
    </section>
  );
}
