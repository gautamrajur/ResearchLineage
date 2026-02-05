export interface Paper {
  paperId: string;
  title: string;
  authors: string[];
  year: number;
  citationCount: number;
  abstract?: string;
  venue?: string;
  url?: string;
}

export type ViewMode = 'pre' | 'post';

export interface GraphNode {
  data: {
    id: string;
    label: string;
    year: number;
    citationCount: number;
    isSeed?: boolean;
  };
  position?: { x: number; y: number };
}

export interface GraphEdge {
  data: {
    id: string;
    source: string;
    target: string;
  };
}

export type GraphElement = GraphNode | GraphEdge;
