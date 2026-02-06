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
import { useState, useEffect, useMemo } from 'react';

const nodeTypes: NodeTypes = { paper: PaperNode, seed: SeedNode } as NodeTypes;

const NODE_WIDTH = 220;
const NODE_HEIGHT = 70;
const SEED_WIDTH = 280;
const SEED_HEIGHT = 90;

// Backend API URL
const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';;

interface MockPaper {
  paperId: string;
  title: string;
  year: number;
  citationCount: number;
  depth: number;
  parentId: string;
}

interface SeedPaper {
  paperId: string;
  title: string;
  authors: string[];
  year: number;
  citationCount: number;
  venue: string;
  abstract: string;
}

const buildGraph = (
  seed: SeedPaper,
  papers: MockPaper[],
  view: 'pre' | 'post'
) => {
  const g = new dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}));
  
  // Calculate dynamic spacing based on depth distribution
  const maxDepth = Math.max(...papers.map(p => p.depth), 1);
  const papersPerDepth = new Map<number, number>();
  papers.forEach(p => {
    papersPerDepth.set(p.depth, (papersPerDepth.get(p.depth) || 0) + 1);
  });
  const maxPapersInAnyDepth = Math.max(...Array.from(papersPerDepth.values()), 1);
  
  console.log(`📊 Papers: ${papers.length}, Max depth: ${maxDepth}, Max papers at any depth: ${maxPapersInAnyDepth}`);
  
  // Dynamic spacing
  const nodesep = Math.min(50 + maxPapersInAnyDepth * 3, 120);
  const ranksep = 180;
  
  g.setGraph({
    rankdir: 'LR',
    ranker: 'longest-path',
    nodesep,
    ranksep,
    edgesep: 20,
    marginx: 60,
    marginy: 60,
  });

  // Add seed node
  g.setNode(seed.paperId, { 
    width: SEED_WIDTH, 
    height: SEED_HEIGHT,
    rank: 0  // Seed is always at rank 0
  });

  // Add all paper nodes with their depth-based rank
  papers.forEach((paper) => {
    // For 'pre' view (references): deeper papers are further LEFT (negative rank)
    // For 'post' view (citations): deeper papers are further RIGHT (positive rank)
    const rank = view === 'pre' ? -paper.depth : paper.depth;
    
    g.setNode(paper.paperId, { 
      width: NODE_WIDTH, 
      height: NODE_HEIGHT,
      rank: rank
    });
  });

  // Add edges based on actual citation relationships
  papers.forEach((paper) => {
    // Each paper connects to its parent (the paper it cites or is cited by)
    const parentId = paper.parentId;
    
    if (view === 'pre') {
      // References view: Papers cite their parents (edge goes LEFT to RIGHT)
      // Paper A → Paper B means "A cites B"
      g.setEdge(paper.paperId, parentId);
    } else {
      // Citations view: Parents cite papers (edge goes LEFT to RIGHT)
      // Paper B → Paper A means "B cites A" (where B is parent)
      g.setEdge(parentId, paper.paperId);
    }
  });

  dagre.layout(g);

  const nodes: Node[] = [];
  const edges: Edge[] = [];

  // Add seed node
  const seedPos = g.node(seed.paperId);
  nodes.push({
    id: seed.paperId,
    type: 'seed',
    position: { x: seedPos.x - SEED_WIDTH / 2, y: seedPos.y - SEED_HEIGHT / 2 },
    data: { 
      title: seed.title,
      year: seed.year,
      citations: seed.citationCount
    },
  });

  // Add paper nodes and edges
  papers.forEach((paper) => {
    const pos = g.node(paper.paperId);

    nodes.push({
      id: paper.paperId,
      type: 'paper',
      position: { x: pos.x - NODE_WIDTH / 2, y: pos.y - NODE_HEIGHT / 2 },
      data: { 
        title: paper.title,
        year: paper.year,
        citations: paper.citationCount
      },
    });

    // Create edge based on view
    const parentId = paper.parentId;
    let sourceId: string;
    let targetId: string;
    
    if (view === 'pre') {
      // References: paper → parent (paper cites parent)
      sourceId = paper.paperId;
      targetId = parentId;
    } else {
      // Citations: parent → paper (parent cites paper)
      sourceId = parentId;
      targetId = paper.paperId;
    }

    edges.push({
      id: `e-${paper.paperId}`,
      source: sourceId,
      target: targetId,
      type: 'smoothstep',
      animated: false,
      style: {
        stroke: paper.depth === 1 ? '#4ADE80' : paper.depth === 2 ? '#38BDF8' : '#A78BFA',
        strokeWidth: paper.depth === 1 ? 1.5 : 1,
        opacity: 0.6,
      },
    });
  });

  console.log(`✅ Built graph: ${nodes.length} nodes, ${edges.length} edges`);
  
  return { nodes, edges };
};

export function GraphCanvas({ view }: { view: 'pre' | 'post' }) {
  const [seedPaper, setSeedPaper] = useState<SeedPaper | null>(null);
  const [papers, setPapers] = useState<MockPaper[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Fetch data from backend API
  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        setError(null);

        console.log('🚀 Starting data fetch...');
        console.log('📍 API_BASE_URL:', API_BASE_URL);
        console.log('📍 View:', view);

        // 1. Get seed paper
        const seedUrl = `${API_BASE_URL}/api/seed`;
        console.log('📡 Fetching seed from:', seedUrl);
        
        const seedResponse = await fetch(seedUrl);
        console.log('📥 Seed response status:', seedResponse.status);
        
        if (!seedResponse.ok) {
          throw new Error('Failed to fetch seed paper');
        }
        
        const seed = await seedResponse.json();
        console.log('✅ Seed paper loaded:', seed);
        console.log('📍 Seed paperId:', seed.paperId);
        
        setSeedPaper(seed);

        // 2. Get references or citations based on view
        const endpoint = view === 'pre' ? 'references' : 'citations';
        const papersUrl = `${API_BASE_URL}/api/paper/${seed.paperId}/${endpoint}`;
        
        console.log('📡 Fetching papers from:', papersUrl);
        
        const papersResponse = await fetch(papersUrl);
        console.log('📥 Papers response status:', papersResponse.status);
        
        if (!papersResponse.ok) {
          throw new Error(`Failed to fetch ${endpoint}`);
        }
        
        const papersData = await papersResponse.json();
        console.log('✅ Papers loaded:', papersData);
        console.log('📊 Number of papers:', papersData.length);
        
        setPapers(papersData);

      } catch (err) {
        console.error('❌ Error fetching data:', err);
        setError(err instanceof Error ? err.message : 'Failed to load data');
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [view]);

  const { nodes: init, edges: initE } = useMemo(() => {
    if (!seedPaper || papers.length === 0) {
      return { nodes: [], edges: [] };
    }
    return buildGraph(seedPaper, papers, view);
  }, [seedPaper, papers, view]);

  const [nodes, setNodes, onNodesChange] = useNodesState(init);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initE);

  useEffect(() => {
    setNodes(init);
    setEdges(initE);
  }, [init, initE, setNodes, setEdges]);

  // Loading state
  if (loading) {
    return (
      <div className="w-full h-screen flex items-center justify-center" style={{ background: '#0B0D11' }}>
        <div className="text-center">
          <div className="text-[#EAEDF2] text-lg mb-2">Loading graph...</div>
          <div className="text-[#8B95A5] text-sm">Fetching data from API</div>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="w-full h-screen flex items-center justify-center" style={{ background: '#0B0D11' }}>
        <div className="text-center">
          <div className="text-red-400 text-lg mb-2">Error loading graph</div>
          <div className="text-[#8B95A5] text-sm">{error}</div>
          <div className="text-[#8B95A5] text-xs mt-4">
            Make sure backend is running on http://127.0.0.1:8000
          </div>
        </div>
      </div>
    );
  }

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
