import { clsx, type ClassValue } from 'clsx';

export function cn(...inputs: ClassValue[]): string {
  return clsx(inputs);
}

export function formatNumber(n: number | null | undefined): string {
  if (n == null) return 'N/A';
  return n.toLocaleString();
}

export function truncate(text: string | null | undefined, max = 120): string {
  if (!text) return '';
  return text.length > max ? text.slice(0, max - 1) + '…' : text;
}

/**
 * Normalize a user-entered paper ID into something the backend accepts.
 * - Strips arxiv URLs → extracts the bare ID
 * - Leaves Semantic Scholar paperIds alone
 */
export function normalizePaperId(input: string): string {
  const s = input.trim();
  const m = s.match(/arxiv\.org\/(?:abs|pdf)\/([^\s?#]+?)(?:v\d+)?(?:\.pdf)?(?:[?#].*)?$/i);
  if (m) return m[1];
  return s;
}
