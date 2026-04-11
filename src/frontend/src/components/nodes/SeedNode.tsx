import { Handle, Position, type NodeProps } from '@xyflow/react';
import { motion } from 'framer-motion';
import type { TreePaperMeta } from '../../lib/types';
import { cn, formatNumber, truncate } from '../../lib/utils';

interface SeedNodeData {
  paper: TreePaperMeta;
  dim?: boolean;
}

export function SeedNode({ data }: NodeProps) {
  const { paper, dim } = data as unknown as SeedNodeData;

  return (
    <motion.div
      initial={{ scale: 0.94, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
      className={cn(
        'relative rounded-2xl px-5 py-4 min-w-[280px] max-w-[300px]',
        'bg-gradient-to-br from-[#F97066]/12 via-[#FB923C]/8 to-[#12141A]/70',
        'border border-[#F97066]/35 backdrop-blur',
        dim && 'opacity-40',
      )}
      style={{ boxShadow: '0 0 50px rgba(249,112,102,0.18), inset 0 1px 0 0 rgba(255,255,255,0.05)' }}
    >
      {/* Pulsing glow ring */}
      <motion.div
        aria-hidden
        className="absolute inset-0 -z-10 rounded-2xl"
        animate={{ opacity: [0.35, 0.6, 0.35] }}
        transition={{ duration: 3.4, repeat: Infinity, ease: 'easeInOut' }}
        style={{
          background: 'radial-gradient(ellipse at center, rgba(249,112,102,0.35), transparent 65%)',
          filter: 'blur(22px)',
        }}
      />

      <Handle
        type="target"
        position={Position.Left}
        className="!w-2.5 !h-2.5 !bg-[#F97066] !border-2 !border-[#12141A]"
      />

      <div className="text-[9px] font-semibold uppercase tracking-[0.16em] text-[#F97066]/80 mb-1.5">
        ◎ Target paper
      </div>

      <h3 className="text-[14px] font-semibold text-[#EAEDF2] leading-snug line-clamp-3">
        {truncate(paper.title, 120)}
      </h3>

      <div className="mt-2.5 flex items-center gap-3">
        <span className="text-[12px] text-[#F97066] font-semibold tabular-nums">
          {paper.year ?? '?'}
        </span>
        <span className="text-[11px] text-[#8B95A5] tabular-nums">
          {formatNumber(paper.citationCount ?? null)} citations
        </span>
      </div>

      <Handle
        type="source"
        position={Position.Right}
        className="!w-2.5 !h-2.5 !bg-[#F97066] !border-2 !border-[#12141A]"
      />
    </motion.div>
  );
}
