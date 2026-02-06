import { Handle, Position } from '@xyflow/react';
import { motion } from 'framer-motion';

interface SeedNodeProps {
  data: {
    title: string;
    year: number;
    citations: number;
  };
}

export function SeedNode({ data }: SeedNodeProps) {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.8 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.4, type: 'spring' }}
      className="relative"
    >
      {/* Pulsing glow ring */}
      <motion.div
        animate={{ opacity: [0.25, 0.5, 0.25], scale: [1, 1.04, 1] }}
        transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut' }}
        className="absolute inset-0 rounded-xl bg-[var(--color-seed)] blur-2xl -z-10"
        style={{ opacity: 0.15 }}
      />

      <div
        className="rounded-xl px-6 py-4 min-w-[260px] backdrop-blur-xl border-2"
        style={{
          background: 'linear-gradient(135deg, rgba(153,27,27,0.35), rgba(154,52,18,0.25))',
          borderColor: 'rgba(239,68,68,0.5)',
          boxShadow: '0 0 60px var(--color-seed-glow), var(--shadow-inner-light)',
        }}
      >
        <Handle type="target" position={Position.Left} className="!bg-[var(--color-seed)] !w-3 !h-3" />
        <div
          className="text-xs font-semibold uppercase tracking-wider mb-1"
          style={{ color: 'var(--color-seed)', letterSpacing: '0.05em' }}
        >
          Origin Paper
        </div>
        <h3 className="text-[var(--color-text-primary)] font-bold text-base leading-tight">
          {data.title}
        </h3>
        <div className="flex items-center gap-3 mt-2">
          <span className="text-red-300 text-sm font-mono tabular-nums font-bold">
            {data.year}
          </span>
          <span className="text-red-200/50 text-sm tabular-nums">
            {data.citations.toLocaleString()} citations
          </span>
        </div>
        <Handle type="source" position={Position.Right} className="!bg-[var(--color-seed)] !w-3 !h-3" />
      </div>
    </motion.div>
  );
}
