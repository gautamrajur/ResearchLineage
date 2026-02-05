import { useState, useEffect, useMemo, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { FlowCanvas } from './components/Flow/FlowCanvas';
import { PaperDetails } from './components/Sidebar/PaperDetails';
import { ViewToggle } from './components/Controls/ViewToggle';
import { FilterPanel } from './components/Controls/FilterPanel';
import { getSeedPaper, getReferences, getCitations, getPaper } from './api/client';
import type { Paper, ViewMode } from './types/paper';

function App() {
  const [seedPaper, setSeedPaper] = useState<Paper | null>(null);
  const [references, setReferences] = useState<Paper[]>([]);
  const [citations, setCitations] = useState<Paper[]>([]);
  const [viewMode, setViewMode] = useState<ViewMode>('post');
  const [selectedPaper, setSelectedPaper] = useState<Paper | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [yearRange, setYearRange] = useState<[number, number]>([1997, 2024]);
  const [minCitations, setMinCitations] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadData() {
      try {
        setLoading(true);
        const seed = await getSeedPaper();
        setSeedPaper(seed);
        setSelectedPaper(seed);
        setSelectedNodeId(seed.paperId);

        const [refs, cites] = await Promise.all([
          getReferences(seed.paperId),
          getCitations(seed.paperId),
        ]);
        setReferences(refs);
        setCitations(cites);
      } catch (err) {
        setError('Failed to load data. Make sure the backend is running.');
        console.error(err);
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, []);

  const handleNodeClick = useCallback(async (nodeId: string) => {
    setSelectedNodeId(nodeId);
    try {
      const paper = await getPaper(nodeId);
      setSelectedPaper(paper);
    } catch (err) {
      console.error('Failed to fetch paper details:', err);
    }
  }, []);

  const filteredPapers = useMemo(() => {
    const papers = viewMode === 'pre' ? references : citations;
    return papers.filter(
      (p) =>
        p.year >= yearRange[0] &&
        p.year <= yearRange[1] &&
        p.citationCount >= minCitations
    );
  }, [viewMode, references, citations, yearRange, minCitations]);

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0a0a0f] flex items-center justify-center">
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="text-center"
        >
          <div className="w-12 h-12 border-2 border-indigo-500/30 border-t-indigo-500 rounded-full animate-spin mx-auto mb-4" />
          <p className="text-gray-400">Loading research data...</p>
        </motion.div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-[#0a0a0f] flex items-center justify-center">
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          className="text-center bg-red-500/10 border border-red-500/30 rounded-xl p-8 max-w-md"
        >
          <div className="w-12 h-12 rounded-full bg-red-500/20 flex items-center justify-center mx-auto mb-4">
            <svg className="w-6 h-6 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <p className="text-red-300 mb-2 font-medium">Connection Error</p>
          <p className="text-red-400/70 text-sm">{error}</p>
        </motion.div>
      </div>
    );
  }

  if (!seedPaper) return null;

  return (
    <div className="h-screen flex flex-col bg-[#0a0a0f] overflow-hidden">
      {/* Header */}
      <header className="relative z-20 bg-[#0a0a0f]/80 backdrop-blur-xl border-b border-white/5">
        <div className="px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <motion.div
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              className="flex items-center gap-3"
            >
              <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center">
                <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
                </svg>
              </div>
              <h1 className="text-white text-lg font-bold tracking-tight">
                Research Lineage
              </h1>
            </motion.div>

            {/* Stats */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.2 }}
              className="hidden sm:flex items-center gap-2 ml-4 pl-4 border-l border-white/10"
            >
              <span className="text-gray-500 text-sm">
                Showing{' '}
                <span className="text-indigo-400 font-medium">
                  {filteredPapers.length}
                </span>{' '}
                {viewMode === 'pre' ? 'references' : 'citations'}
              </span>
            </motion.div>
          </div>

          <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
          >
            <ViewToggle view={viewMode} onChange={setViewMode} />
          </motion.div>
        </div>
      </header>

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Graph Canvas */}
        <main className="flex-1 relative">
          <AnimatePresence mode="wait">
            <motion.div
              key={viewMode}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.3 }}
              className="absolute inset-0"
            >
              <FlowCanvas
                seedPaper={seedPaper}
                papers={filteredPapers}
                viewMode={viewMode}
                onNodeClick={handleNodeClick}
                selectedNodeId={selectedNodeId}
              />
            </motion.div>
          </AnimatePresence>

          {/* View Mode Label */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
            className="absolute bottom-20 left-6 pointer-events-none"
          >
            <div className="text-gray-600 text-xs uppercase tracking-widest mb-1">
              {viewMode === 'pre' ? 'Pre-Order View' : 'Post-Order View'}
            </div>
            <div className="text-gray-500 text-xs">
              {viewMode === 'pre'
                ? 'Papers that the seed paper cited'
                : 'Papers that cite the seed paper'}
            </div>
          </motion.div>
        </main>

        {/* Sidebar */}
        <motion.aside
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.2 }}
          className="w-80 flex-shrink-0 overflow-y-auto"
        >
          <PaperDetails paper={selectedPaper} />
        </motion.aside>
      </div>

      {/* Footer / Filters */}
      <motion.footer
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3 }}
        className="relative z-20 bg-[#0a0a0f]/80 backdrop-blur-xl border-t border-white/5 px-6 py-4"
      >
        <FilterPanel
          yearRange={yearRange}
          minCitations={minCitations}
          onYearRangeChange={setYearRange}
          onMinCitationsChange={setMinCitations}
        />
      </motion.footer>
    </div>
  );
}

export default App;
