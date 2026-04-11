import { Handle, Position, type NodeProps } from '@xyflow/react';
import { motion } from 'framer-motion';
import type { TreePaperMeta } from '../../lib/types';
import { cn, formatNumber, truncate } from '../../lib/utils';

interface PaperNodeData {
  paper: TreePaperMeta;
  kind: 'ancestor' | 'descendant';
  depth: number;
  dim?: boolean;
}

export function PaperNode({ data, selected }: NodeProps) {
  const { paper, kind, dim } = data as unknown as PaperNodeData;
  const accentColor = kind === 'ancestor' ? '#38BDF8' : '#4ADE80';

  return (
    <motion.div
      whileHover={{ scale: 1.03, y: -2 }}
      transition={{ type: 'spring', stiffness: 380, damping: 26 }}
      className={cn(
        'bg-[#12141A] border rounded-xl px-4 py-3 min-w-[220px] max-w-[260px] transition-all',
        selected
          ? 'border-[#2DD4BF]/60 shadow-[0_0_24px_rgba(45,212,191,0.25)]'
          : 'border-white/[0.07] hover:border-white/[0.15]',
        dim && 'opacity-20 saturate-50',
      )}
      style={{ boxShadow: 'inset 0 1px 0 0 rgba(255,255,255,0.03)' }}
    >
      <Handle
        type="target"
        position={Position.Left}
        className="!w-2 !h-2 !border-2 !border-[#12141A]"
        style={{ background: accentColor }}
      />

      <p className="text-[12.5px] font-medium text-[#EAEDF2] leading-tight line-clamp-2">
        {truncate(paper.title, 80)}
      </p>

      <div className="mt-2 flex items-center gap-2">
        <span className="text-[11px] font-medium tabular-nums" style={{ color: accentColor }}>
          {paper.year ?? '?'}
        </span>
        <span className="text-[#5A6375]">·</span>
        <span className="text-[10px] text-[#8B95A5] tabular-nums">
          {formatNumber(paper.citationCount ?? null)} cites
        </span>
      </div>

      <Handle
        type="source"
        position={Position.Right}
        className="!w-2 !h-2 !border-2 !border-[#12141A]"
        style={{ background: accentColor }}
      />
    </motion.div>
  );
}
