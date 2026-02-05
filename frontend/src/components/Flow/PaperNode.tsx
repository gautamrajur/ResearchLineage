import { Handle, Position } from '@xyflow/react';
import { motion } from 'framer-motion';

export interface PaperNodeData {
  title: string;
  year: number;
  citationCount: number;
  authors?: string[];
}

interface PaperNodeProps {
  data: PaperNodeData;
  selected?: boolean;
}

export function PaperNode({ data, selected }: PaperNodeProps) {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.8 }}
      animate={{ opacity: 1, scale: 1 }}
      whileHover={{ scale: 1.05 }}
      transition={{ duration: 0.2 }}
      className={`
        bg-white/[0.03] backdrop-blur-xl
        border rounded-xl
        px-4 py-3 min-w-[220px] max-w-[280px]
        transition-all duration-300
        cursor-pointer
        ${selected
          ? 'border-indigo-500/60 shadow-[0_0_40px_rgba(99,102,241,0.35)]'
          : 'border-white/10 shadow-[0_0_20px_rgba(99,102,241,0.1)] hover:shadow-[0_0_30px_rgba(99,102,241,0.25)] hover:border-indigo-500/40'
        }
      `}
    >
      <Handle
        type="target"
        position={Position.Left}
        className="!bg-indigo-500 !border-indigo-400 !w-2 !h-2"
      />

      <h3 className="text-white font-medium text-sm leading-tight line-clamp-2">
        {data.title}
      </h3>

      <div className="flex items-center gap-2 mt-2">
        <span className="text-indigo-400 text-xs font-mono font-semibold">
          {data.year}
        </span>
        <span className="text-gray-600 text-xs">•</span>
        <span className="text-gray-400 text-xs">
          {data.citationCount.toLocaleString()} citations
        </span>
      </div>

      <Handle
        type="source"
        position={Position.Right}
        className="!bg-indigo-500 !border-indigo-400 !w-2 !h-2"
      />
    </motion.div>
  );
}
