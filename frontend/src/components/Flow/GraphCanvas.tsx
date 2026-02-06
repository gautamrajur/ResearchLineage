import {
  ReactFlow,
  Background,
  Controls,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  type NodeTypes,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import dagre from 'dagre';
import { PaperNode } from './PaperNode';
import { SeedNode } from './SeedNode';
import { useMemo, useEffect } from 'react';
import { mockData } from '../../data/mockPapers';

const nodeTypes: NodeTypes = { paper: PaperNode, seed: SeedNode } as NodeTypes;

const NODE_WIDTH = 220;
const NODE_HEIGHT = 70;
const SEED_WIDTH = 280;
const SEED_HEIGHT = 90;

interface MockPaper {
  id: string;
  title: string;
  year: number;
  citations: number;
  depth: number;
  parentId?: string;
}

const buildGraph = (
  seed: typeof mockData.seed,
  papers: MockPaper[],
  view: 'pre' | 'post'
) => {
  const g = new dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}));
  g.setGraph({
    rankdir: 'LR',
    ranker: 'network-simplex',
    nodesep: 50,
    ranksep: 120,
    edgesep: 15,
    marginx: 40,
    marginy: 40,
  });

  g.setNode(seed.id, { width: SEED_WIDTH, height: SEED_HEIGHT });

  papers.forEach((paper) => {
    g.setNode(paper.id, { width: NODE_WIDTH, height: NODE_HEIGHT });

    const depth = paper.depth || 1;
    if (view === 'pre') {
      const target = depth === 1 ? seed.id : paper.parentId!;
      g.setEdge(paper.id, target);
    } else {
      const source = depth === 1 ? seed.id : paper.parentId!;
      g.setEdge(source, paper.id);
    }
  });

  dagre.layout(g);

  const nodes: Node[] = [];
  const edges: Edge[] = [];

  const seedPos = g.node(seed.id);
  nodes.push({
    id: seed.id,
    type: 'seed',
    position: { x: seedPos.x - SEED_WIDTH / 2, y: seedPos.y - SEED_HEIGHT / 2 },
    data: { ...seed },
  });

  papers.forEach((paper) => {
    const pos = g.node(paper.id);
    const depth = paper.depth || 1;

    nodes.push({
      id: paper.id,
      type: 'paper',
      position: { x: pos.x - NODE_WIDTH / 2, y: pos.y - NODE_HEIGHT / 2 },
      data: { ...paper },
    });

    const src = view === 'pre' ? paper.id : (depth === 1 ? seed.id : paper.parentId!);
    const tgt = view === 'pre' ? (depth === 1 ? seed.id : paper.parentId!) : paper.id;

    edges.push({
      id: `e-${paper.id}`,
      source: src,
      target: tgt,
      type: 'smoothstep',
      animated: false,
      style: {
        stroke: depth === 1 ? '#4ADE80' : '#38BDF8',
        strokeWidth: depth === 1 ? 1.5 : 1,
        opacity: 0.6,
      },
    });
  });

  return { nodes, edges };
};

export function GraphCanvas({ view }: { view: 'pre' | 'post' }) {
  const { nodes: init, edges: initE } = useMemo(
    () =>
      buildGraph(
        mockData.seed,
        view === 'pre' ? mockData.references : mockData.citations,
        view
      ),
    [view]
  );

  const [nodes, setNodes, onNodesChange] = useNodesState(init);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initE);

  useEffect(() => {
    setNodes(init);
    setEdges(initE);
  }, [init, initE, setNodes, setEdges]);

  return (
    <div className="w-full h-screen" style={{ background: '#0B0D11' }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        defaultEdgeOptions={{
          type: 'smoothstep',
          style: { strokeWidth: 1.5, opacity: 0.6 },
        }}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        minZoom={0.2}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#1A1D25" gap={24} size={1} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
