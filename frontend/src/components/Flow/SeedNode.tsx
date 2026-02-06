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
        bg-gradient-to-br from-[#F97066]/10 to-[#FB923C]/5
        border border-[#F97066]/30
        rounded-xl px-5 py-4 min-w-[260px]
        shadow-[0_0_40px_rgba(249,112,102,0.12)]
        relative
      "
    >
      {/* Soft glow behind */}
      <div className="absolute inset-0 -z-10 rounded-xl bg-[#F97066]/10 blur-2xl" />

      <Handle type="target" position={Position.Left}
        className="!bg-[#F97066] !border-[#12141A] !border-2 !w-3 !h-3" />

      <span className="text-[#F97066]/80 text-[10px] font-semibold uppercase tracking-[0.1em]">
        Origin Paper
      </span>

      <h3 className="text-[#EAEDF2] font-semibold text-[15px] leading-snug mt-1">
        {data.title}
      </h3>

      <div className="flex items-center gap-3 mt-2.5">
        <span className="text-[#F97066] text-sm font-medium tabular-nums">{data.year}</span>
        <span className="text-[#8B95A5] text-sm tabular-nums">
          {data.citations.toLocaleString()} citations
        </span>
      </div>

      <Handle type="source" position={Position.Right}
        className="!bg-[#F97066] !border-[#12141A] !border-2 !w-3 !h-3" />
    </motion.div>
  );
}
