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
        border rounded-lg
        px-4 py-3 min-w-[220px] max-w-[280px]
        transition-all duration-200
        ${selected
          ? 'border-[#C8B272]/60 shadow-[0_0_20px_rgba(200,178,114,0.15)]'
          : 'border-[#C8B272]/20 hover:border-[#C8B272]/40'
        }
      `}
      style={{ background: '#3A2E21', boxShadow: '0 1px 4px rgba(0,0,0,0.3)' }}
    >
      <Handle type="target" position={Position.Left}
        className="!bg-[#C8B272] !border-[#3A2E21] !border-2 !w-2.5 !h-2.5" />

      <p className="text-[#E8DFC8] font-medium text-[13px] leading-tight line-clamp-2">
        {data.title}
      </p>

      <div className="flex items-center gap-2 mt-2.5">
        <span className="text-[#C8B272] text-xs font-medium tabular-nums">
          {data.year}
        </span>
        <span className="text-[#697153] text-xs">&middot;</span>
        <span className="text-[#A0A584] text-xs tabular-nums">
          {data.citations.toLocaleString()} cites
        </span>
      </div>

      <Handle type="source" position={Position.Right}
        className="!bg-[#C8B272] !border-[#3A2E21] !border-2 !w-2.5 !h-2.5" />
    </motion.div>
  );
}
