import type { Paper } from '../types/paper';

const API_BASE = '/api';

export async function getSeedPaper(): Promise<Paper> {
  const res = await fetch(`${API_BASE}/seed`);
  if (!res.ok) throw new Error('Failed to fetch seed paper');
  return res.json();
}

export async function getPaper(paperId: string): Promise<Paper> {
  const res = await fetch(`${API_BASE}/paper/${encodeURIComponent(paperId)}`);
  if (!res.ok) throw new Error('Failed to fetch paper');
  return res.json();
}

export async function getReferences(paperId: string, limit = 20): Promise<Paper[]> {
  const res = await fetch(`${API_BASE}/paper/${encodeURIComponent(paperId)}/references?limit=${limit}`);
  if (!res.ok) throw new Error('Failed to fetch references');
  return res.json();
}

export async function getCitations(paperId: string, limit = 20): Promise<Paper[]> {
  const res = await fetch(`${API_BASE}/paper/${encodeURIComponent(paperId)}/citations?limit=${limit}`);
  if (!res.ok) throw new Error('Failed to fetch citations');
  return res.json();
}

export async function searchPapers(query: string): Promise<Paper[]> {
  const res = await fetch(`${API_BASE}/search?q=${encodeURIComponent(query)}`);
  if (!res.ok) throw new Error('Failed to search papers');
  return res.json();
}
