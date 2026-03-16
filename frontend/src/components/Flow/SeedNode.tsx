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
        border rounded-xl px-5 py-4 min-w-[260px]
        relative
      "
      style={{
        background: 'linear-gradient(135deg, rgba(168,139,76,0.25) 0%, rgba(200,178,114,0.12) 100%)',
        border: '1px solid rgba(200,178,114,0.45)',
        boxShadow: '0 0 32px rgba(168,139,76,0.15)',
      }}
    >
      <div className="absolute inset-0 -z-10 rounded-xl blur-2xl"
        style={{ background: 'rgba(168,139,76,0.08)' }} />

      <Handle type="target" position={Position.Left}
        className="!bg-[#A88B4C] !border-[#3A2E21] !border-2 !w-3 !h-3" />

      <span className="text-[#C8B272]/80 text-[10px] font-semibold uppercase tracking-[0.1em]">
        Origin Paper
      </span>

      <h3 className="text-[#E8DFC8] font-semibold text-[15px] leading-snug mt-1">
        {data.title}
      </h3>

      <div className="flex items-center gap-3 mt-2.5">
        <span className="text-[#C8B272] text-sm font-medium tabular-nums">{data.year}</span>
        <span className="text-[#A0A584] text-sm tabular-nums">
          {data.citations.toLocaleString()} citations
        </span>
      </div>

      <Handle type="source" position={Position.Right}
        className="!bg-[#A88B4C] !border-[#3A2E21] !border-2 !w-3 !h-3" />
    </motion.div>
  );
}
