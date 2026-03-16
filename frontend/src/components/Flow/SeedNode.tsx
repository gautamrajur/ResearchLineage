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
      initial={{ scale: 0.9, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      className="
        bg-gradient-to-br from-[#C4622D]/10 to-[#D97706]/6
        border border-[#C4622D]/35
        rounded-xl px-5 py-4 min-w-[260px]
        shadow-[0_2px_12px_rgba(196,98,45,0.12)]
        relative
      "
    >
      <div className="absolute inset-0 -z-10 rounded-xl bg-[#C4622D]/6 blur-2xl" />

      <Handle type="target" position={Position.Left}
        className="!bg-[#C4622D] !border-[#FDFAF6] !border-2 !w-3 !h-3" />

      <span className="text-[#A05028]/80 text-[10px] font-semibold uppercase tracking-[0.1em]">
        Origin Paper
      </span>

      <h3 className="text-[#1C1510] font-semibold text-[15px] leading-snug mt-1">
        {data.title}
      </h3>

      <div className="flex items-center gap-3 mt-2.5">
        <span className="text-[#C4622D] text-sm font-medium tabular-nums">{data.year}</span>
        <span className="text-[#9B8B77] text-sm tabular-nums">
          {data.citations.toLocaleString()} citations
        </span>
      </div>

      <Handle type="source" position={Position.Right}
        className="!bg-[#C4622D] !border-[#FDFAF6] !border-2 !w-3 !h-3" />
    </motion.div>
  );
}
