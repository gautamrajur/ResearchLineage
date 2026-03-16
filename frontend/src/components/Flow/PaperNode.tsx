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
        bg-[#FDFAF6]
        border rounded-lg
        px-4 py-3 min-w-[220px] max-w-[280px]
        transition-all duration-200
        ${selected
          ? 'border-[#9B7A50]/60 shadow-[0_0_20px_rgba(155,122,80,0.15)]'
          : 'border-[#D8CCB8] hover:border-[#C4B89A]'
        }
      `}
      style={{ boxShadow: '0 1px 3px rgba(100,80,50,0.08)' }}
    >
      <Handle type="target" position={Position.Left}
        className="!bg-[#9B7A50] !border-[#FDFAF6] !border-2 !w-2.5 !h-2.5" />

      <p className="text-[#1C1510] font-medium text-[13px] leading-tight line-clamp-2">
        {data.title}
      </p>

      <div className="flex items-center gap-2 mt-2.5">
        <span className="text-[#8B5E3C] text-xs font-medium tabular-nums">
          {data.year}
        </span>
        <span className="text-[#C4B89A] text-xs">&middot;</span>
        <span className="text-[#9B8B77] text-xs tabular-nums">
          {data.citations.toLocaleString()} cites
        </span>
      </div>

      <Handle type="source" position={Position.Right}
        className="!bg-[#9B7A50] !border-[#FDFAF6] !border-2 !w-2.5 !h-2.5" />
    </motion.div>
  );
}
