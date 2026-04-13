import { useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { THEMES, type ThemeId } from '../lib/theme';

interface ThemePickerProps {
  current: ThemeId;
  onChange: (id: ThemeId) => void;
}

export function ThemePicker({ current, onChange }: ThemePickerProps) {
  const [open, setOpen] = useState(false);

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col items-end gap-2">
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: 8, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.95 }}
            transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
            className="rounded-2xl border border-black/[0.07] bg-white/95 shadow-[0_16px_48px_rgba(0,0,0,0.18)] backdrop-blur-xl p-3 min-w-[160px]"
          >
            <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[#9BA3AF] px-2 mb-2">
              Background
            </p>
            {(Object.values(THEMES)).map((t) => (
              <button
                key={t.id}
                onClick={() => { onChange(t.id); setOpen(false); }}
                className="w-full flex items-center gap-3 px-2 py-2 rounded-xl hover:bg-black/[0.04] transition-colors text-left"
              >
                <span
                  className="w-5 h-5 rounded-full border border-black/10 shrink-0"
                  style={{ background: t.swatch }}
                />
                <span
                  className="text-[13px] font-medium"
                  style={{ color: current === t.id ? '#0D7A6F' : '#374151' }}
                >
                  {t.label}
                </span>
                {current === t.id && (
                  <motion.span
                    layoutId="theme-check"
                    className="ml-auto text-[#0D7A6F] text-[13px]"
                  >
                    ✓
                  </motion.span>
                )}
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>

      <motion.button
        whileHover={{ scale: 1.08 }}
        whileTap={{ scale: 0.94 }}
        onClick={() => setOpen((v) => !v)}
        className="w-10 h-10 rounded-full border border-black/[0.08] bg-white/90 shadow-[0_4px_20px_rgba(0,0,0,0.15)] backdrop-blur flex items-center justify-center"
        title="Change background"
      >
        <span className="text-[16px]">◐</span>
      </motion.button>
    </div>
  );
}
