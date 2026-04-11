import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Background,
  Controls,
  ReactFlow,
  useEdgesState,
  useNodesState,
  type Edge,
  type Node,
  type NodeTypes,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import dagre from 'dagre';
import { motion } from 'framer-motion';
import type { AncestorNode, DescendantNode, Tree, TreePaperMeta } from '../lib/types';
import { PaperNode } from './nodes/PaperNode';
import { SeedNode } from './nodes/SeedNode';
import type { Theme } from '../lib/theme';

const NODE_WIDTH = 240;
const NODE_HEIGHT = 92;
const SEED_WIDTH = 300;
const SEED_HEIGHT = 108;

type NodeKind = 'ancestor' | 'target' | 'descendant';

interface FlatNode {
  id: string;
  parentId: string | null;
  paper: TreePaperMeta;
  kind: NodeKind;
  depth: number;
}

function flatten(tree: Tree): FlatNode[] {
  const out: FlatNode[] = [];
  const targetId = tree.target.paperId;

  out.push({ id: targetId, parentId: null, paper: tree.target, kind: 'target', depth: 0 });

  const walkAnc = (nodes: AncestorNode[], parentId: string, depth: number) => {
    nodes.forEach((n, i) => {
      const pid = n.paper.paperId;
      // Unique ID per branch to avoid dagre collisions
      const id = `${pid}__anc_${depth}_${i}_${parentId.slice(0, 8)}`;
      out.push({ id, parentId, paper: n.paper, kind: 'ancestor', depth });
      if (n.ancestors?.length) walkAnc(n.ancestors, id, depth + 1);
    });
  };
  const walkDesc = (nodes: DescendantNode[], parentId: string, depth: number) => {
    nodes.forEach((n, i) => {
      const pid = n.paper.paperId;
      const id = `${pid}__desc_${depth}_${i}_${parentId.slice(0, 8)}`;
      out.push({ id, parentId, paper: n.paper, kind: 'descendant', depth });
      if (n.children?.length) walkDesc(n.children, id, depth + 1);
    });
  };

  if (tree.ancestors?.length) walkAnc(tree.ancestors, targetId, 1);
  if (tree.descendants?.length) walkDesc(tree.descendants, targetId, 1);

  return out;
}

function buildGraph(tree: Tree): { nodes: Node[]; edges: Edge[] } {
  const flat = flatten(tree);
  const g = new dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}));
  g.setGraph({
    rankdir: 'LR',
    ranker: 'network-simplex',
    nodesep: 40,
    ranksep: 140,
    edgesep: 20,
    marginx: 60,
    marginy: 60,
  });

  for (const n of flat) {
    const w = n.kind === 'target' ? SEED_WIDTH : NODE_WIDTH;
    const h = n.kind === 'target' ? SEED_HEIGHT : NODE_HEIGHT;
    g.setNode(n.id, { width: w, height: h });
  }

  // Edges: ancestor → target (points forward in time); target → descendant
  for (const n of flat) {
    if (!n.parentId) continue;
    if (n.kind === 'ancestor') {
      // Ancestor flows INTO its parent (which is closer to target)
      g.setEdge(n.id, n.parentId);
    } else {
      // Descendant flows FROM its parent (closer to target)
      g.setEdge(n.parentId, n.id);
    }
  }

  dagre.layout(g);

  const nodes: Node[] = flat.map((n) => {
    const pos = g.node(n.id);
    const w = n.kind === 'target' ? SEED_WIDTH : NODE_WIDTH;
    const h = n.kind === 'target' ? SEED_HEIGHT : NODE_HEIGHT;
    return {
      id: n.id,
      type: n.kind === 'target' ? 'seed' : 'paper',
      position: { x: pos.x - w / 2, y: pos.y - h / 2 },
      data: { paper: n.paper, kind: n.kind, depth: n.depth },
    };
  });

  const edges: Edge[] = flat
    .filter((n) => n.parentId)
    .map((n) => {
      const source = n.kind === 'ancestor' ? n.id : n.parentId!;
      const target = n.kind === 'ancestor' ? n.parentId! : n.id;
      const color = n.kind === 'ancestor' ? '#38BDF8' : '#4ADE80';
      return {
        id: `e-${n.id}`,
        source,
        target,
        type: 'smoothstep',
        animated: n.depth === 1,
        style: {
          stroke: color,
          strokeWidth: n.depth === 1 ? 1.8 : 1.1,
          opacity: n.depth === 1 ? 0.75 : 0.45,
        },
      };
    });

  return { nodes, edges };
}

const nodeTypes: NodeTypes = { paper: PaperNode, seed: SeedNode } as NodeTypes;

// ─────────────────────────────────────────────────────────────────────────
// TreeView
// ─────────────────────────────────────────────────────────────────────────

export function TreeView({ tree }: { tree: Tree; theme?: Theme }) {
  // Tree view is always dark for readability regardless of active theme
  const { nodes: initNodes, edges: initEdges } = useMemo(() => buildGraph(tree), [tree]);
  const [nodes, setNodes, onNodesChange] = useNodesState(initNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initEdges);
  const [showAncestors, setShowAncestors] = useState(true);
  const [showDescendants, setShowDescendants] = useState(true);

  useEffect(() => {
    setNodes(initNodes);
    setEdges(initEdges);
  }, [initNodes, initEdges, setNodes, setEdges]);

  // Apply filters
  useEffect(() => {
    setNodes((curr) =>
      curr.map((n) => {
        const kind = (n.data as { kind: NodeKind }).kind;
        const hidden =
          (kind === 'ancestor' && !showAncestors) ||
          (kind === 'descendant' && !showDescendants);
        return { ...n, hidden };
      }),
    );
    setEdges((curr) =>
      curr.map((e) => {
        const src = initNodes.find((n) => n.id === e.source);
        const tgt = initNodes.find((n) => n.id === e.target);
        const k = ((src?.data as { kind?: NodeKind })?.kind === 'ancestor' ||
          (tgt?.data as { kind?: NodeKind })?.kind === 'ancestor')
          ? 'ancestor'
          : 'descendant';
        const hidden =
          (k === 'ancestor' && !showAncestors) ||
          (k === 'descendant' && !showDescendants);
        return { ...e, hidden };
      }),
    );
  }, [showAncestors, showDescendants, setNodes, setEdges, initNodes]);

  // Click-to-highlight lineage path to target
  const onNodeClick = useCallback(
    (_: unknown, clicked: Node) => {
      const targetId = tree.target.paperId;
      if (clicked.id === targetId) {
        // reset
        setNodes((curr) => curr.map((n) => ({ ...n, data: { ...n.data, dim: false } })));
        setEdges((curr) => curr.map((e) => ({ ...e, style: { ...e.style, opacity: 0.55 } })));
        return;
      }

      // Walk edges to find path from clicked to target
      const keep = new Set<string>([clicked.id, targetId]);
      const keepEdges = new Set<string>();

      // BFS upward (for ancestors) or downward (for descendants)
      const visit = (id: string) => {
        for (const e of initEdges) {
          if (keepEdges.has(e.id)) continue;
          // Treat as undirected walk toward target
          let next: string | null = null;
          if (e.source === id) next = e.target;
          else if (e.target === id) next = e.source;
          if (!next) continue;
          keepEdges.add(e.id);
          keep.add(next);
          if (next !== targetId) visit(next);
        }
      };
      visit(clicked.id);

      setNodes((curr) =>
        curr.map((n) => ({
          ...n,
          data: { ...n.data, dim: !keep.has(n.id) },
        })),
      );
      setEdges((curr) =>
        curr.map((e) => ({
          ...e,
          style: {
            ...e.style,
            opacity: keepEdges.has(e.id) ? 0.95 : 0.1,
            strokeWidth: keepEdges.has(e.id) ? 2.4 : 1,
          },
        })),
      );
    },
    [initEdges, tree.target.paperId, setNodes, setEdges],
  );

  const onPaneClick = useCallback(() => {
    setNodes((curr) => curr.map((n) => ({ ...n, data: { ...n.data, dim: false } })));
    setEdges((curr) =>
      curr.map((e) => ({
        ...e,
        style: { ...e.style, opacity: e.animated ? 0.75 : 0.45, strokeWidth: 1.5 },
      })),
    );
  }, [setNodes, setEdges]);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.5 }}
      className="relative w-full rounded-2xl overflow-hidden"
      style={{ border: '1px solid rgba(255,255,255,0.06)', background: '#0B0D11', height: '78vh', minHeight: 620 }}
    >
      {/* Legend & filters */}
      <div className="absolute top-4 left-4 z-10 flex flex-col gap-2">
        <div className="rounded-xl px-4 py-2.5 flex items-center gap-4"
          style={{ background: 'rgba(18,20,26,0.80)', border: '1px solid rgba(255,255,255,0.07)', backdropFilter: 'blur(12px)' }}>
          <LegendPill color="#38BDF8" label="Ancestors" active={showAncestors} onClick={() => setShowAncestors((v) => !v)} />
          <LegendPill color="#F97066" label="Target" active solid onClick={() => undefined} />
          <LegendPill color="#4ADE80" label="Descendants" active={showDescendants} onClick={() => setShowDescendants((v) => !v)} />
        </div>
        <div className="rounded-xl px-4 py-2 text-[10px] tracking-wide"
          style={{ background: 'rgba(18,20,26,0.80)', border: '1px solid rgba(255,255,255,0.07)', backdropFilter: 'blur(12px)', color: '#5A6375' }}>
          ◉ Click any node to highlight its lineage to the target · ⌘ scroll to zoom · drag to pan
        </div>
      </div>

      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={onNodeClick}
        onPaneClick={onPaneClick}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.25 }}
        minZoom={0.15}
        maxZoom={2.2}
        proOptions={{ hideAttribution: true }}
        defaultEdgeOptions={{ type: 'smoothstep' }}
      >
        <Background color="#1A1D25" gap={28} size={1.2} />
        <Controls showInteractive={false} position="bottom-right" />
      </ReactFlow>
    </motion.div>
  );
}

function LegendPill({
  color,
  label,
  active,
  solid,
  onClick,
}: {
  color: string;
  label: string;
  active: boolean;
  solid?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="inline-flex items-center gap-2 text-[11px] transition-colors"
      style={{ color: active ? '#EAEDF2' : '#5A6375' }}
    >
      <span
        className="w-2.5 h-2.5 rounded-full"
        style={{
          background: active ? color : 'transparent',
          border: `1.5px solid ${color}${active ? '' : '55'}`,
          boxShadow: active && solid ? `0 0 10px ${color}` : 'none',
        }}
      />
      {label}
    </button>
  );
}
