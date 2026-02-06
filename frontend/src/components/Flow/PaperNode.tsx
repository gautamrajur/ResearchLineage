import { Handle, Position } from '@xyflow/react';
import { motion } from 'framer-motion';

interface PaperNodeProps {
  data: {
    title: string;
    year: number;
    citations: number;
  };
  selected?: boolean;
}

export function PaperNode({ data, selected }: PaperNodeProps) {
  return (
    <motion.div
      whileHover={{ scale: 1.02, y: -2 }}
      transition={{ type: 'spring', stiffness: 400, damping: 25 }}
      className={`
        bg-[#12141A]
        border rounded-lg
        px-4 py-3 min-w-[220px] max-w-[280px]
        transition-all duration-200
        ${selected
          ? 'border-[#2DD4BF]/50 shadow-[0_0_20px_rgba(45,212,191,0.15)]'
          : 'border-white/[0.06] hover:border-white/[0.12]'
        }
      `}
      style={{ boxShadow: 'inset 0 1px 0 0 rgba(255,255,255,0.03)' }}
    >
      <Handle type="target" position={Position.Left}
        className="!bg-[#4ADE80] !border-[#12141A] !border-2 !w-2.5 !h-2.5" />

      <p className="text-[#EAEDF2] font-medium text-[13px] leading-tight line-clamp-2">
        {data.title}
      </p>

      <div className="flex items-center gap-2 mt-2.5">
        <span className="text-[#2DD4BF] text-xs font-medium tabular-nums">
          {data.year}
        </span>
        <span className="text-[#5A6375] text-xs">&middot;</span>
        <span className="text-[#8B95A5] text-xs tabular-nums">
          {data.citations.toLocaleString()} cites
        </span>
      </div>

      <Handle type="source" position={Position.Right}
        className="!bg-[#4ADE80] !border-[#12141A] !border-2 !w-2.5 !h-2.5" />
    </motion.div>
  );
}
