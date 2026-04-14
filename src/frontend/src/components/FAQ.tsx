import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import type { Theme } from '../lib/theme';

interface FAQItem {
  question: string;
  answer: string | React.ReactNode;
}

interface FAQSection {
  id: string;
  label: string;
  icon: string;
  items: FAQItem[];
}

const SECTIONS: FAQSection[] = [
  {
    id: 'usage',
    label: 'Using the app',
    icon: '◎',
    items: [
      {
        question: 'How do I look up a paper?',
        answer:
          'Type a title and pick from the suggestions, or paste an ArXiv ID directly (e.g. 1706.03762). Both formats work.',
      },
      {
        question: 'What do the two views show?',
        answer: (
          <>
            <span className="block mb-1.5"><strong>Predecessor / Successor Tree</strong> shows the network around your paper: which papers it builds on and which later papers cite it as influential.</span>
            <span className="block"><strong>Evolution Timeline</strong> traces a chronological lineage chain from the oldest foundational work up to your paper, with Gemini analysis of what each step contributed.</span>
          </>
        ),
      },
      {
        question: 'What is the Lineage Assistant?',
        answer:
          'Once a paper is analyzed, the chat panel lets you ask questions about its lineage. It uses Gemini with the full lineage as context, so it only answers questions about the papers in the chain.',
      },
      {
        question: 'Why does analysis take 30 to 90 seconds?',
        answer:
          'The app fetches live citation data from Semantic Scholar, traces the lineage up to 4 levels deep, and runs Gemini analysis on each step. Results are cached so the same paper loads instantly on repeat visits.',
      },
      {
        question: 'What do the thumbs up and down buttons do?',
        answer:
          'They record anonymous feedback on predecessor relationships, helping us understand where the algorithm gets the lineage right or wrong.',
      },
    ],
  },
  {
    id: 'data',
    label: 'Data and coverage',
    icon: '◈',
    items: [
      {
        question: 'Which papers are covered?',
        answer:
          'Any paper in the Semantic Scholar index, which contains over 200 million papers across CS, Physics, Math, Biology, and more. Papers with a Semantic Scholar ID or ArXiv ID are supported.',
      },
      {
        question: 'What if my paper is not found?',
        answer: (
          <>
            <span className="block mb-1.5">A few common reasons:</span>
            <ul className="space-y-1">
              <li className="flex gap-2"><span className="opacity-40 shrink-0">·</span><span>Paper not yet indexed in Semantic Scholar, common for papers less than 3 months old.</span></li>
              <li className="flex gap-2"><span className="opacity-40 shrink-0">·</span><span>Title search returned no match. Try pasting the ArXiv ID directly.</span></li>
              <li className="flex gap-2"><span className="opacity-40 shrink-0">·</span><span>Paper is from a venue S2 does not index, such as some workshops or technical reports.</span></li>
            </ul>
          </>
        ),
      },
      {
        question: 'How current is the citation data?',
        answer:
          'Semantic Scholar updates continuously, but citation counts for papers less than 6 months old may be incomplete. Older foundational papers generally have the most accurate lineage data.',
      },
    ],
  },
  {
    id: 'limitations',
    label: 'Limitations',
    icon: '◇',
    items: [
      {
        question: 'Why does the lineage sometimes look wrong?',
        answer:
          'The lineage is built algorithmically using citation graphs and Gemini analysis. It prioritises papers that Semantic Scholar flags as methodologically influential, which does not always match expert domain knowledge. Niche sub-fields and interdisciplinary work can produce imperfect results.',
      },
      {
        question: 'Why are some papers missing from the tree?',
        answer:
          'The tree is pruned to a depth of 2 and a maximum of 5 children per node to keep analysis fast. Papers that are cited but not flagged as influential, plus generic background references like textbooks and surveys, are filtered out.',
      },
      {
        question: 'Does it work for non-CS papers?',
        answer:
          'Partially. The pipeline is tuned for CS, ML, and AI papers. Physics and Math papers on arXiv generally work well. Biology, Medicine, and Social Science are indexed but lineage quality is lower due to different citation conventions.',
      },
      {
        question: 'Can the chat answer questions outside the lineage?',
        answer:
          'No. The assistant is intentionally scoped to the lineage of the analyzed paper. Questions about unrelated topics or recent developments outside the chain will be politely redirected.',
      },
    ],
  },
];

function QuestionRow({
  item,
  isOpen,
  onToggle,
  theme,
  isLast,
}: {
  item: FAQItem;
  isOpen: boolean;
  onToggle: () => void;
  theme: Theme;
  isLast: boolean;
}) {
  return (
    <div style={{ borderBottom: isLast ? 'none' : `1px solid ${theme.border}` }}>
      <button
        onClick={onToggle}
        className="w-full flex items-start justify-between gap-3 py-3 text-left"
        aria-expanded={isOpen}
      >
        <span
          className="text-[13px] leading-snug font-medium"
          style={{ color: isOpen ? theme.accent : theme.textPrimary }}
        >
          {item.question}
        </span>
        <motion.svg
          animate={{ rotate: isOpen ? 180 : 0 }}
          transition={{ duration: 0.2 }}
          className="shrink-0 mt-0.5"
          width="12"
          height="12"
          viewBox="0 0 12 12"
          fill="none"
        >
          <path
            d="M2 4l4 4 4-4"
            stroke={isOpen ? theme.accent : theme.textMuted}
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </motion.svg>
      </button>

      <AnimatePresence initial={false}>
        {isOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
            className="overflow-hidden"
          >
            <p
              className="pb-3.5 text-[12.5px] leading-relaxed"
              style={{ color: theme.textSecondary }}
            >
              {item.answer}
            </p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export function FAQ({ theme }: { theme: Theme }) {
  const [openSection, setOpenSection] = useState<string | null>(null);
  const [openQuestion, setOpenQuestion] = useState<string | null>(null);

  const isDark = theme.id === 'dark';

  return (
    <section className="w-full max-w-xl mx-auto px-6 pb-20">
      <p
        className="text-center text-[10px] uppercase tracking-[0.18em] font-semibold mb-6"
        style={{ color: theme.textMuted }}
      >
        FAQ
      </p>

      <div className="space-y-2">
        {SECTIONS.map((section) => {
          const isOpen = openSection === section.id;
          return (
            <div
              key={section.id}
              className="rounded-xl overflow-hidden transition-all duration-200"
              style={{
                border: `1px solid ${isOpen ? theme.borderHover : theme.border}`,
                background: isOpen
                  ? isDark ? 'rgba(255,255,255,0.03)' : 'rgba(255,255,255,0.7)'
                  : 'transparent',
              }}
            >
              {/* Section header */}
              <button
                onClick={() => {
                  setOpenSection(isOpen ? null : section.id);
                  setOpenQuestion(null);
                }}
                className="w-full flex items-center justify-between gap-3 px-4 py-3.5 text-left"
              >
                <div className="flex items-center gap-2.5">
                  <span
                    className="text-[11px] leading-none"
                    style={{ color: isOpen ? theme.accent : theme.textMuted }}
                  >
                    {section.icon}
                  </span>
                  <span
                    className="text-[13px] font-semibold tracking-tight"
                    style={{ color: isOpen ? theme.textPrimary : theme.textSecondary }}
                  >
                    {section.label}
                  </span>
                </div>
                <div className="flex items-center gap-2.5">
                  <span
                    className="text-[11px] tabular-nums"
                    style={{ color: theme.textMuted }}
                  >
                    {section.items.length}
                  </span>
                  <motion.svg
                    animate={{ rotate: isOpen ? 180 : 0 }}
                    transition={{ duration: 0.2 }}
                    width="12"
                    height="12"
                    viewBox="0 0 12 12"
                    fill="none"
                  >
                    <path
                      d="M2 4l4 4 4-4"
                      stroke={isOpen ? theme.accent : theme.textMuted}
                      strokeWidth="1.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </motion.svg>
                </div>
              </button>

              {/* Questions */}
              <AnimatePresence initial={false}>
                {isOpen && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
                    className="overflow-hidden"
                  >
                    <div
                      className="px-4 pb-1"
                      style={{ borderTop: `1px solid ${theme.border}` }}
                    >
                      {section.items.map((item, j) => {
                        const key = `${section.id}-${j}`;
                        return (
                          <QuestionRow
                            key={key}
                            item={item}
                            isOpen={openQuestion === key}
                            onToggle={() => setOpenQuestion(openQuestion === key ? null : key)}
                            theme={theme}
                            isLast={j === section.items.length - 1}
                          />
                        );
                      })}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          );
        })}
      </div>
    </section>
  );
}
