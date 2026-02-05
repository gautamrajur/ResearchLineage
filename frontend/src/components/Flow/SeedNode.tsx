import { Handle, Position } from '@xyflow/react';
import { motion } from 'framer-motion';

export interface SeedNodeData {
  title: string;
  year: number;
  citationCount: number;
  authors?: string[];
}

interface SeedNodeProps {
  data: SeedNodeData;
}

export function SeedNode({ data }: SeedNodeProps) {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.5 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.4, type: 'spring' }}
      className="relative"
    >
      {/* Animated glow ring */}
      <motion.div
        animate={{
          opacity: [0.3, 0.6, 0.3],
          scale: [1, 1.05, 1],
        }}
        transition={{
          duration: 3,
          repeat: Infinity,
          ease: 'easeInOut',
        }}
        className="absolute inset-0 rounded-2xl bg-red-500/20 blur-2xl -z-10"
      />

      <div
        className="
          bg-gradient-to-br from-red-900/50 to-orange-900/40
          border-2 border-red-500/60 rounded-2xl
          px-6 py-4 min-w-[280px]
          shadow-[0_0_80px_rgba(239,68,68,0.35)]
          backdrop-blur-xl
        "
      >
        <Handle
          type="target"
          position={Position.Left}
          className="!bg-red-500 !border-red-400 !w-3 !h-3"
        />

        <div className="text-red-400 text-xs font-semibold uppercase tracking-wider mb-1">
          Origin Paper
        </div>

        <h3 className="text-white font-bold text-base leading-tight">
          {data.title}
        </h3>

        <div className="flex items-center gap-3 mt-3">
          <span className="text-red-300 text-sm font-mono font-bold">
            {data.year}
          </span>
          <span className="text-red-200/60 text-sm">
            {data.citationCount.toLocaleString()} citations
          </span>
        </div>

        <Handle
          type="source"
          position={Position.Right}
          className="!bg-red-500 !border-red-400 !w-3 !h-3"
        />
      </div>
    </motion.div>
  );
}
