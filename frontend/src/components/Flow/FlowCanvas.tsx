import { useMemo, useCallback, useEffect } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  type NodeTypes,
  type EdgeTypes,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { PaperNode } from './PaperNode';
import { SeedNode } from './SeedNode';
import { AnimatedEdge } from './AnimatedEdge';
import type { Paper, ViewMode } from '../../types/paper';

const nodeTypes: NodeTypes = {
  paper: PaperNode,
  seed: SeedNode,
} as NodeTypes;

const edgeTypes: EdgeTypes = {
  animated: AnimatedEdge,
} as EdgeTypes;

interface FlowCanvasProps {
  seedPaper: Paper;
  papers: Paper[];
  viewMode: ViewMode;
  onNodeClick: (paperId: string) => void;
  selectedNodeId: string | null;
}

export function FlowCanvas({
  seedPaper,
  papers,
  viewMode,
  onNodeClick,
  selectedNodeId,
}: FlowCanvasProps) {
  const { initialNodes, initialEdges } = useMemo(() => {
    const nodes: Node[] = [];
    const edges: Edge[] = [];

    // Calculate layout positions
    const seedX = 600;
    const seedY = 350;

    // Seed node in center
    nodes.push({
      id: seedPaper.paperId,
      type: 'seed',
      position: { x: seedX, y: seedY },
      data: {
        title: seedPaper.title,
        year: seedPaper.year,
        citationCount: seedPaper.citationCount,
        authors: seedPaper.authors,
      },
      selected: selectedNodeId === seedPaper.paperId,
    });

    // Sort papers by year
    const sortedPapers = [...papers].sort((a, b) => a.year - b.year);

    // Group papers by year for vertical stacking
    const yearGroups = new Map<number, Paper[]>();
    sortedPapers.forEach((paper) => {
      const group = yearGroups.get(paper.year) || [];
      group.push(paper);
      yearGroups.set(paper.year, group);
    });

    // Position papers
    if (viewMode === 'pre') {
      // Pre-order: references flow INTO seed from left
      const years = Array.from(yearGroups.keys()).sort((a, b) => a - b);
      const minYear = years.length > 0 ? Math.min(...years) : seedPaper.year;
      const maxYear = seedPaper.year;
      const yearSpan = maxYear - minYear || 1;

      sortedPapers.forEach((paper) => {
        const yearGroup = yearGroups.get(paper.year) || [];
        const indexInYear = yearGroup.indexOf(paper);
        const groupSize = yearGroup.length;

        // X position based on year (older = more left)
        const yearProgress = (paper.year - minYear) / yearSpan;
        const xPos = 80 + yearProgress * (seedX - 200);

        // Y position - spread vertically within year group
        const baseY = seedY - ((groupSize - 1) * 100) / 2;
        const yPos = baseY + indexInYear * 100;

        nodes.push({
          id: paper.paperId,
          type: 'paper',
          position: { x: xPos, y: yPos },
          data: {
            title: paper.title,
            year: paper.year,
            citationCount: paper.citationCount,
            authors: paper.authors,
          },
          selected: selectedNodeId === paper.paperId,
        });

        edges.push({
          id: `e-${paper.paperId}-${seedPaper.paperId}`,
          source: paper.paperId,
          target: seedPaper.paperId,
          type: 'animated',
          animated: true,
        });
      });
    } else {
      // Post-order: citations flow OUT from seed to right
      const years = Array.from(yearGroups.keys()).sort((a, b) => a - b);
      const minYear = seedPaper.year;
      const maxYear = years.length > 0 ? Math.max(...years) : seedPaper.year;
      const yearSpan = maxYear - minYear || 1;

      sortedPapers.forEach((paper) => {
        const yearGroup = yearGroups.get(paper.year) || [];
        const indexInYear = yearGroup.indexOf(paper);
        const groupSize = yearGroup.length;

        // X position based on year (newer = more right)
        const yearProgress = (paper.year - minYear) / yearSpan;
        const xPos = seedX + 200 + yearProgress * 500;

        // Y position - spread vertically within year group
        const baseY = seedY - ((groupSize - 1) * 100) / 2;
        const yPos = baseY + indexInYear * 100;

        nodes.push({
          id: paper.paperId,
          type: 'paper',
          position: { x: xPos, y: yPos },
          data: {
            title: paper.title,
            year: paper.year,
            citationCount: paper.citationCount,
            authors: paper.authors,
          },
          selected: selectedNodeId === paper.paperId,
        });

        edges.push({
          id: `e-${seedPaper.paperId}-${paper.paperId}`,
          source: seedPaper.paperId,
          target: paper.paperId,
          type: 'animated',
          animated: true,
        });
      });
    }

    return { initialNodes: nodes, initialEdges: edges };
  }, [seedPaper, papers, viewMode, selectedNodeId]);

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  // Update nodes when data changes
  useEffect(() => {
    setNodes(initialNodes);
    setEdges(initialEdges);
  }, [initialNodes, initialEdges, setNodes, setEdges]);

  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      onNodeClick(node.id);
    },
    [onNodeClick]
  );

  return (
    <div className="w-full h-full bg-[#0a0a0f]">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.3}
        maxZoom={1.5}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#1a1a2e" gap={24} size={1} />
        <Controls showInteractive={false} />

        {/* SVG definitions for gradients */}
        <svg style={{ position: 'absolute', width: 0, height: 0 }}>
          <defs>
            <linearGradient id="edge-gradient-default" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#6366f1" />
              <stop offset="100%" stopColor="#8b5cf6" />
            </linearGradient>
          </defs>
        </svg>
      </ReactFlow>
    </div>
  );
}
