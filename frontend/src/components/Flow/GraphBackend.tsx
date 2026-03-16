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
import { useState, useEffect, useMemo, useCallback, useRef } from 'react';

const nodeTypes: NodeTypes = { paper: PaperNode, seed: SeedNode } as NodeTypes;

const NODE_WIDTH = 220;
const NODE_HEIGHT = 70;
const SEED_WIDTH = 280;
const SEED_HEIGHT = 90;

// Backend API URL
const API_BASE_URL = import.meta.env.VITE_API_URL ?? '';

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
    ranker: 'network-simplex',
    nodesep,
    ranksep,
    edgesep: 20,
    marginx: 60,
    marginy: 60,
  });

  // Sort papers so children of the same parent are adjacent.
  // This gives dagre's barycenter heuristic a better initial ordering,
  // which dramatically reduces edge crossings.
  const sorted = [...papers].sort((a, b) => {
    if (a.depth !== b.depth) return a.depth - b.depth;
    if (a.parentId !== b.parentId) return a.parentId.localeCompare(b.parentId);
    return a.year - b.year;
  });

  // Add seed node
  g.setNode(seed.paperId, { width: SEED_WIDTH, height: SEED_HEIGHT });

  // Add paper nodes — depth-sorted so dagre processes parent groups together
  sorted.forEach((paper) => {
    g.setNode(paper.paperId, { width: NODE_WIDTH, height: NODE_HEIGHT });
  });

  // Add edges — also in sorted order for consistent barycenter computation
  sorted.forEach((paper) => {
    const parentId = paper.parentId;
    if (view === 'pre') {
      g.setEdge(paper.paperId, parentId);
    } else {
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

type TreeStatus = 'idle' | 'building' | 'ready' | 'error';

export function GraphCanvas({ view }: { view: 'pre' | 'post' }) {
  const [seedPaper, setSeedPaper] = useState<SeedPaper | null>(null);
  const [papers, setPapers] = useState<MockPaper[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [treeStatus, setTreeStatus] = useState<TreeStatus>('idle');
  const [dataSource, setDataSource] = useState<'mock' | 'live'>('mock');
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Fetch papers (references or citations) for the current seed
  const fetchPapers = useCallback(async (seedId: string) => {
    const endpoint = view === 'pre' ? 'references' : 'citations';
    const papersUrl = `${API_BASE_URL}/api/paper/${seedId}/${endpoint}`;
    const papersResponse = await fetch(papersUrl);
    if (!papersResponse.ok) {
      throw new Error(`Failed to fetch ${endpoint}`);
    }
    return papersResponse.json();
  }, [view]);

  // Trigger tree build and start polling
  const triggerTreeBuild = useCallback(async (seedId: string) => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/tree/${seedId}`, { method: 'POST' });
      if (!res.ok) return;
      const data = await res.json();

      if (data.status === 'ready') {
        // Tree was already cached — re-fetch live data now
        setTreeStatus('ready');
        setDataSource('live');
        const papersData = await fetchPapers(seedId);
        setPapers(papersData);
        return;
      }

      setTreeStatus('building');

      // Poll status every 5 seconds
      pollRef.current = setInterval(async () => {
        try {
          const statusRes = await fetch(`${API_BASE_URL}/api/tree/${seedId}/status`);
          if (!statusRes.ok) return;
          const statusData = await statusRes.json();

          if (statusData.status === 'ready') {
            if (pollRef.current) clearInterval(pollRef.current);
            pollRef.current = null;
            setTreeStatus('ready');
            setDataSource('live');
            // Re-fetch with live data
            const papersData = await fetchPapers(seedId);
            setPapers(papersData);
          } else if (statusData.status === 'error') {
            if (pollRef.current) clearInterval(pollRef.current);
            pollRef.current = null;
            setTreeStatus('error');
          }
        } catch {
          // Ignore polling errors — keep retrying
        }
      }, 5000);
    } catch {
      // Tree build trigger failed — mock data still works
      setTreeStatus('error');
    }
  }, [fetchPapers]);

  // Initial data fetch
  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        setError(null);

        // 1. Get seed paper
        const seedResponse = await fetch(`${API_BASE_URL}/api/seed`);
        if (!seedResponse.ok) {
          throw new Error('Failed to fetch seed paper');
        }
        const seed = await seedResponse.json();
        setSeedPaper(seed);

        // 2. Get references or citations (initially mock data)
        const papersData = await fetchPapers(seed.paperId);
        setPapers(papersData);

        // 3. Trigger tree build in background
        triggerTreeBuild(seed.paperId);

      } catch (err) {
        console.error('Error fetching data:', err);
        setError(err instanceof Error ? err.message : 'Failed to load data');
      } finally {
        setLoading(false);
      }
    };

    fetchData();

    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [view, fetchPapers, triggerTreeBuild]);

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
    <div className="w-full h-screen relative" style={{ background: '#0B0D11' }}>
      {/* Data source status indicator — always visible, centered at top */}
      <div className="absolute top-4 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 bg-[#E8EBF0] rounded-full px-5 py-2 shadow-lg">
        {dataSource === 'mock' && treeStatus !== 'building' && (
          <>
            <div className="w-2.5 h-2.5 bg-[#8B95A5] rounded-full" />
            <span className="text-[#12141A] text-sm font-medium">Mock data</span>
          </>
        )}
        {treeStatus === 'building' && (
          <>
            <div className="w-2.5 h-2.5 bg-[#F59E0B] rounded-full animate-pulse" />
            <span className="text-[#12141A] text-sm font-medium">Building live tree&hellip;</span>
          </>
        )}
        {treeStatus === 'ready' && dataSource === 'live' && (
          <>
            <div className="w-2.5 h-2.5 bg-[#22C55E] rounded-full" />
            <span className="text-[#12141A] text-sm font-medium">Live data &mdash; Semantic Scholar</span>
          </>
        )}
        {treeStatus === 'error' && dataSource === 'mock' && (
          <>
            <div className="w-2.5 h-2.5 bg-[#F97066] rounded-full" />
            <span className="text-[#12141A] text-sm font-medium">Mock data (live fetch failed)</span>
          </>
        )}
      </div>
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
