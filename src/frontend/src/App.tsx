import { useCallback, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Header } from './components/Header';
import { BackgroundFX } from './components/BackgroundFX';
import { HeroSearch } from './components/HeroSearch';
import { FAQ } from './components/FAQ';
import { AnalyzeLoader } from './components/AnalyzeLoader';
import { ResultsPage } from './components/ResultsPage';
import { ThemePicker } from './components/ThemePicker';
import { analyzePaper, ApiError } from './lib/api';
import { normalizePaperId } from './lib/utils';
import { THEMES, type ThemeId } from './lib/theme';
import type {
  AnalyzeParams,
  AnalyzeResponse,
  SearchResultPaper,
} from './lib/types';

type View = 'home' | 'loading' | 'results';

interface LoadingContext {
  paperId: string;
  title?: string;
  year?: number | null;
}

export default function App() {
  const [view, setView] = useState<View>('home');
  const [result, setResult] = useState<AnalyzeResponse | null>(null);
  const [loadingCtx, setLoadingCtx] = useState<LoadingContext | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [themeId, setThemeId] = useState<ThemeId>('warm');
  const theme = THEMES[themeId];
  const analyzingRef = useRef(false);

  const runAnalyze = useCallback(
    async (rawPaperId: string, title?: string, year?: number | null) => {
      if (analyzingRef.current) return;
      analyzingRef.current = true;
      const paperId = normalizePaperId(rawPaperId);
      setError(null);
      setLoadingCtx({ paperId, title, year });
      setView('loading');

      const params: AnalyzeParams = {
        paper_id: paperId,
        max_children: 5,
        max_depth_tree: 2,
        window_years: 3,
        max_depth_evolution: 4,
      };

      try {
        const data = await analyzePaper(params);
        setResult(data);
        setView('results');
      } catch (e) {
        const msg =
          e instanceof ApiError
            ? e.status === 404
              ? `Paper not found: ${paperId}`
              : `API error ${e.status}: ${e.detail}`
            : e instanceof Error
              ? e.message
              : 'Unknown error';
        setError(msg);
        setView('home');
      } finally {
        analyzingRef.current = false;
      }
    },
    [],
  );

  const handlePickSearchResult = useCallback(
    (paper: SearchResultPaper) => {
      const pid =
        paper.externalIds?.ArXiv
          ? `ARXIV:${paper.externalIds.ArXiv}`
          : paper.arxiv_id
            ? `ARXIV:${paper.arxiv_id}`
            : paper.paperId;
      runAnalyze(pid, paper.title, paper.year ?? null);
    },
    [runAnalyze],
  );

  const handleBackHome = useCallback(() => {
    setView('home');
    setResult(null);
    setError(null);
  }, []);

  return (
    <div
      className="relative min-h-screen overflow-x-hidden transition-colors duration-700"
      style={{ background: theme.bodyBg, color: theme.textPrimary }}
    >
      <BackgroundFX variant={view === 'home' ? 'hero' : 'subtle'} theme={theme} />
      <Header onHome={handleBackHome} compact={view !== 'home'} theme={theme} />

      <AnimatePresence mode="wait">
        {view === 'home' && (
          <motion.main
            key="home"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
            transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
          >
            <HeroSearch
              onSubmitPaperId={(id) => runAnalyze(id)}
              onPickResult={handlePickSearchResult}
              error={error}
              theme={theme}
            />
            <FAQ theme={theme} />
          </motion.main>
        )}

        {view === 'loading' && (
          <motion.main
            key="loading"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.4 }}
          >
            <AnalyzeLoader
              paperId={loadingCtx?.paperId ?? ''}
              title={loadingCtx?.title}
              year={loadingCtx?.year ?? null}
              onCancel={handleBackHome}
              theme={theme}
            />
          </motion.main>
        )}

        {view === 'results' && result && (
          <motion.main
            key="results"
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -16 }}
            transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
          >
            <ResultsPage result={result} onBack={handleBackHome} theme={theme} />
          </motion.main>
        )}
      </AnimatePresence>

      <ThemePicker current={themeId} onChange={setThemeId} />
    </div>
  );
}
