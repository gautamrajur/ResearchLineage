import { Handle, Position, type NodeProps } from '@xyflow/react';
import { useState } from 'react';
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
  const [hovered, setHovered] = useState(false);

  const arxivId = paper.externalIds?.ArXiv;
  const s2Url = `https://www.semanticscholar.org/paper/${paper.paperId}`;
  const arxivUrl = arxivId ? `https://arxiv.org/abs/${arxivId}` : null;

  return (
    <motion.div
      whileHover={{ scale: 1.03, y: -2 }}
      transition={{ type: 'spring', stiffness: 380, damping: 26 }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      className={cn(
        'relative bg-[#12141A] border rounded-xl px-4 py-3 min-w-[220px] max-w-[260px] transition-all',
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

      {/* Paper links - visible on hover */}
      {hovered && (
        <div className="absolute -top-8 left-0 flex items-center gap-1.5 px-2 py-1 rounded-lg"
          style={{ background: 'rgba(18,20,26,0.95)', border: '1px solid rgba(255,255,255,0.10)' }}>
          <a
            href={s2Url}
            target="_blank"
            rel="noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="text-[10px] text-[#8B95A5] hover:text-[#EAEDF2] transition-colors flex items-center gap-1"
          >
            S2 ↗
          </a>
          {arxivUrl && (
            <>
              <span className="text-[#5A6375]">·</span>
              <a
                href={arxivUrl}
                target="_blank"
                rel="noreferrer"
                onClick={(e) => e.stopPropagation()}
                className="text-[10px] text-[#8B95A5] hover:text-[#EAEDF2] transition-colors flex items-center gap-1"
              >
                arXiv ↗
              </a>
            </>
          )}
        </div>
      )}

      <Handle
        type="source"
        position={Position.Right}
        className="!w-2 !h-2 !border-2 !border-[#12141A]"
        style={{ background: accentColor }}
      />
    </motion.div>
  );
}
