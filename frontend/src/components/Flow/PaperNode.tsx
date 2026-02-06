import { Handle, Position } from '@xyflow/react';
import { motion } from 'framer-motion';

interface PaperNodeProps {
  data: {
    title: string;
    year: number;
    citations: number;
  };
}

export function PaperNode({ data }: PaperNodeProps) {
  return (
    <motion.div
      whileHover={{ scale: 1.05 }}
      transition={{ type: 'spring', stiffness: 400, damping: 25 }}
      style={{
        background: 'var(--color-bg-card)',
        borderColor: 'var(--color-border-default)',
        boxShadow: 'var(--shadow-inner-light), 0 0 20px rgba(99,102,241,0.08)',
      }}
      className="border rounded-lg px-4 py-3 min-w-[200px] max-w-[260px] backdrop-blur-xl cursor-pointer hover:border-[var(--color-border-strong)] hover:shadow-[0_0_24px_rgba(99,102,241,0.2)] transition-shadow"
    >
      <Handle type="target" position={Position.Left} className="!bg-chart-5 !border-chart-5 !w-2 !h-2" />
      <h3 className="text-[var(--color-text-primary)] font-medium text-sm leading-tight line-clamp-2">
        {data.title}
      </h3>
      <div className="flex items-center gap-2 mt-2">
        <span className="text-[var(--color-chart-5)] text-xs font-mono tabular-nums font-semibold">
          {data.year}
        </span>
        <span className="text-[var(--color-text-muted)] text-xs">&middot;</span>
        <span className="text-[var(--color-text-secondary)] text-xs tabular-nums">
          {data.citations.toLocaleString()} cites
        </span>
      </div>
      <Handle type="source" position={Position.Right} className="!bg-chart-5 !border-chart-5 !w-2 !h-2" />
    </motion.div>
  );
}
