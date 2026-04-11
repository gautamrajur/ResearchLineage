import { motion } from 'framer-motion';
import { cn } from '../lib/utils';
import type { Theme } from '../lib/theme';

interface HeaderProps {
  onHome: () => void;
  compact?: boolean;
  theme: Theme;
}

export function Header({ onHome, compact, theme }: HeaderProps) {
  const isDark = theme.id === 'dark';

  return (
    <motion.header
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
      className={cn(
        'fixed top-0 left-0 right-0 z-40 transition-all duration-300',
        compact && 'backdrop-blur-xl',
      )}
      style={{
        paddingTop: compact ? '12px' : '20px',
        paddingBottom: compact ? '12px' : '20px',
        background: compact ? theme.glassBg : 'transparent',
        borderBottom: compact ? `1px solid ${theme.glassBorder}` : 'none',
      }}
    >
      <div className="max-w-[1400px] mx-auto px-6 flex items-center justify-between">
        {/* Wordmark — matches logo: Research bold + Lineage regular, navy */}
        <button
          onClick={onHome}
          className="group flex items-center gap-3 focus:outline-none"
        >
          {/* Logo mark — tree + book abstraction */}
          <motion.div
            whileHover={{ scale: 1.08 }}
            transition={{ type: 'spring', stiffness: 280, damping: 22 }}
            className="relative w-8 h-8 shrink-0"
          >
            <svg viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg" className="w-full h-full">
              {/* Book base */}
              <path d="M4 22 Q8 20 16 22 Q24 20 28 22 L28 26 Q24 24 16 26 Q8 24 4 26 Z"
                stroke={theme.seed} strokeWidth="1.5" fill="none" strokeLinecap="round"/>
              {/* Trunk */}
              <path d="M16 22 Q15 17 16 14 Q17 11 16 8" stroke={theme.accent} strokeWidth="1.8" strokeLinecap="round"/>
              {/* Left branch */}
              <path d="M16 16 Q12 14 10 11" stroke={theme.accent} strokeWidth="1.4" strokeLinecap="round"/>
              {/* Right branch */}
              <path d="M16 14 Q20 12 22 9" stroke={theme.accent} strokeWidth="1.4" strokeLinecap="round"/>
              {/* Left node */}
              <circle cx="9.5" cy="10.5" r="2" fill={isDark ? '#0B0D11' : theme.bodyBg} stroke={theme.accent} strokeWidth="1.4"/>
              {/* Right node */}
              <circle cx="22.5" cy="8.5" r="2" fill={isDark ? '#0B0D11' : theme.bodyBg} stroke={theme.seed} strokeWidth="1.4"/>
              {/* Top node */}
              <circle cx="16" cy="7" r="2.2" fill={theme.seed} />
            </svg>
          </motion.div>

          <div className="leading-none">
            <div className="text-[16px] tracking-tight">
              <span style={{ fontWeight: 700, color: theme.textPrimary }}>Research</span>
              <span style={{ fontWeight: 400, color: theme.textPrimary }}>Lineage</span>
            </div>
            <div
              className="text-[9.5px] uppercase tracking-[0.14em] mt-0.5"
              style={{ color: theme.textMuted }}
            >
              Trace the ancestry
            </div>
          </div>
        </button>

        {/* Live badge */}
        <div
          className="hidden sm:inline-flex items-center gap-1.5 text-[11px] px-2.5 py-1 rounded-md"
          style={{
            color: theme.textSecondary,
            background: isDark ? 'rgba(18,20,26,0.6)' : 'rgba(0,0,0,0.04)',
            border: `1px solid ${theme.border}`,
          }}
        >
          <span className="w-1.5 h-1.5 rounded-full bg-[#4ADE80] animate-pulse" />
          Live
        </div>
      </div>
    </motion.header>
  );
}
