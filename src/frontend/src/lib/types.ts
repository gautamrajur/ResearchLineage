// ─────────────────────────────────────────────────────────────────────────
// Backend response shapes - mirrors src/backend/api.py + data_export.py
// ─────────────────────────────────────────────────────────────────────────

export type BreakthroughLevel = 'revolutionary' | 'major' | 'moderate' | 'minor';
export type SourceType = 'FULL_TEXT' | 'ABSTRACT_ONLY' | string;

// ── /search results ──
export interface SearchResultPaper {
  paperId: string;
  externalIds?: { ArXiv?: string; DOI?: string } | null;
  arxiv_id?: string | null;
  title: string;
  abstract?: string | null;
  year?: number | null;
  citationCount?: number | null;
  influentialCitationCount?: number | null;
  authors?: { authorId?: string; name: string }[];
  venue?: string | null;
}

export interface SearchResponse {
  results: SearchResultPaper[];
  source: 'semantic_scholar' | 'database' | 'none';
}

// ── /analyze → timeline (evolution_view) ──
export interface TimelinePaper {
  paper_id: string;
  title: string;
  year: number | null;
  abstract?: string | null;
  citation_count?: number | null;
  arxiv_id?: string | null;
}

export interface TimelineAnalysis {
  problem_addressed?: string | null;
  core_method?: string | null;
  key_innovation?: string | null;
  limitations?: string[];
  breakthrough_level?: BreakthroughLevel | null;
  explanation_eli5?: string | null;
  explanation_intuitive?: string | null;
  explanation_technical?: string | null;
}

export interface TimelineComparison {
  what_was_improved?: string | null;
  how_it_was_improved?: string | null;
  why_it_matters?: string | null;
  problem_solved_from_predecessor?: string | null;
  remaining_limitations?: string[];
}

export interface SecondaryInfluence {
  paper_id?: string;
  title?: string;
  year?: number | string;
  contribution?: string;
}

export interface TimelineEntry {
  paper: TimelinePaper;
  source_type: SourceType;
  is_foundational: boolean;
  selection_reasoning?: string | null;
  analysis: TimelineAnalysis;
  comparison: TimelineComparison | null;
  secondary_influences: SecondaryInfluence[];
  position: number;
}

export interface Timeline {
  seed_paper: { paper_id: string; title: string; year: number | null };
  from_cache: boolean;
  elapsed_time: number | null;
  generated_at: string;
  total_papers: number;
  year_range: { start: number | null; end: number | null; span: number | null };
  chain: TimelineEntry[];
}

// ── /analyze → tree (pred_successor_view) ──
export interface TreePaperMeta {
  paperId: string;
  title: string;
  year?: number | null;
  citationCount?: number | null;
  influentialCitationCount?: number | null;
  externalIds?: { ArXiv?: string } | null;
}

export interface FeedbackPayload {
  paper_id: string;
  related_paper_id?: string | null;
  view_type?: string;
  feedback_target?: string;
  rating: 1 | -1;
  comment?: string | null;
}

export interface AncestorNode {
  paper: TreePaperMeta;
  ancestors: AncestorNode[];
}

export interface DescendantNode {
  paper: TreePaperMeta;
  children: DescendantNode[];
}

export interface Tree {
  target: TreePaperMeta;
  ancestors: AncestorNode[];
  descendants: DescendantNode[];
}

// ── Full /analyze response ──
export interface AnalyzeResponse {
  paper_id: string;
  tree: Tree | null;
  timeline: Timeline | null;
  elapsed: { tree_sec: number; evolution_sec: number; total_sec: number };
}

// ── AnalyzeRequest params ──
export interface AnalyzeParams {
  paper_id: string;
  max_children?: number;
  max_depth_tree?: number;
  window_years?: number;
  max_depth_evolution?: number;
}
