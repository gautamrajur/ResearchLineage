import { motion, AnimatePresence } from 'framer-motion';
import type { Paper } from '../../types/paper';

interface PaperDetailsProps {
  paper: Paper | null;
}

export function PaperDetails({ paper }: PaperDetailsProps) {
  return (
    <div className="h-full bg-white/[0.02] backdrop-blur-xl border-l border-white/10">
      <div className="border-b border-white/10 px-5 py-4">
        <h2 className="text-white font-semibold text-sm uppercase tracking-wider">
          Paper Details
        </h2>
      </div>

      <AnimatePresence mode="wait">
        {paper ? (
          <motion.div
            key={paper.paperId}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.2 }}
            className="p-5 space-y-5"
          >
            <div>
              <h3 className="text-white font-semibold text-lg leading-tight">
                {paper.title}
              </h3>
            </div>

            <div className="flex flex-wrap gap-3">
              <div className="bg-indigo-500/20 border border-indigo-500/30 rounded-lg px-3 py-1.5">
                <span className="text-indigo-300 text-sm font-mono font-semibold">
                  {paper.year}
                </span>
              </div>
              <div className="bg-purple-500/20 border border-purple-500/30 rounded-lg px-3 py-1.5">
                <span className="text-purple-300 text-sm">
                  {paper.citationCount.toLocaleString()} citations
                </span>
              </div>
            </div>

            {paper.authors && paper.authors.length > 0 && (
              <div>
                <label className="text-gray-500 text-xs uppercase tracking-wider font-medium">
                  Authors
                </label>
                <p className="text-gray-300 text-sm mt-1 leading-relaxed">
                  {paper.authors.join(', ')}
                </p>
              </div>
            )}

            {paper.venue && (
              <div>
                <label className="text-gray-500 text-xs uppercase tracking-wider font-medium">
                  Venue
                </label>
                <p className="text-gray-300 text-sm mt-1">{paper.venue}</p>
              </div>
            )}

            {paper.abstract && (
              <div>
                <label className="text-gray-500 text-xs uppercase tracking-wider font-medium">
                  Abstract
                </label>
                <p className="text-gray-400 text-sm mt-2 leading-relaxed">
                  {paper.abstract}
                </p>
              </div>
            )}

            {paper.url && (
              <a
                href={paper.url}
                target="_blank"
                rel="noopener noreferrer"
                className="
                  inline-flex items-center gap-2
                  bg-indigo-600/20 hover:bg-indigo-600/30
                  border border-indigo-500/40 hover:border-indigo-500/60
                  text-indigo-300 hover:text-indigo-200
                  rounded-lg px-4 py-2 text-sm font-medium
                  transition-all duration-200
                "
              >
                View Paper
                <svg
                  className="w-4 h-4"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
                  />
                </svg>
              </a>
            )}
          </motion.div>
        ) : (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="p-5 text-gray-500 text-sm"
          >
            <p>Click a node to see paper details</p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
