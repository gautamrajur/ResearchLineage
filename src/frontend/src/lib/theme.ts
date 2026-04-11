export type ThemeId = 'dark' | 'warm' | 'pearl' | 'morning';

export interface Theme {
  id: ThemeId;
  label: string;
  swatch: string; // preview color
  bodyBg: string;
  cardBg: string;
  cardBgAlt: string;
  border: string;
  borderHover: string;
  textPrimary: string;
  textSecondary: string;
  textMuted: string;
  accent: string;
  accentMuted: string;
  seed: string;
  glassBg: string;
  glassBorder: string;
  scrollThumb: string;
}

export const THEMES: Record<ThemeId, Theme> = {
  dark: {
    id: 'dark',
    label: 'Dark',
    swatch: '#0B0D11',
    bodyBg: '#0B0D11',
    cardBg: '#12141A',
    cardBgAlt: '#1A1D25',
    border: 'rgba(255,255,255,0.06)',
    borderHover: 'rgba(255,255,255,0.12)',
    textPrimary: '#EAEDF2',
    textSecondary: '#8B95A5',
    textMuted: '#5A6375',
    accent: '#2DD4BF',
    accentMuted: '#14B8A6',
    seed: '#F97066',
    glassBg: 'rgba(18,20,26,0.70)',
    glassBorder: 'rgba(255,255,255,0.06)',
    scrollThumb: 'rgba(255,255,255,0.08)',
  },

  // ── Warm Scholar — ivory, navy text, logo-exact vibe ──
  warm: {
    id: 'warm',
    label: 'Warm',
    swatch: '#F2EDE6',
    bodyBg: '#F5F1EB',
    cardBg: '#FFFFFF',
    cardBgAlt: '#F9F6F1',
    border: 'rgba(27,35,88,0.08)',
    borderHover: 'rgba(27,35,88,0.16)',
    textPrimary: '#1B2358',
    textSecondary: '#4A5568',
    textMuted: '#9BA3AF',
    accent: '#0D7A6F',
    accentMuted: '#0F8F83',
    seed: '#D4453A',
    glassBg: 'rgba(245,241,235,0.82)',
    glassBorder: 'rgba(27,35,88,0.08)',
    scrollThumb: 'rgba(27,35,88,0.12)',
  },

  // ── Pearl — clean, cool blue-white ──
  pearl: {
    id: 'pearl',
    label: 'Pearl',
    swatch: '#EEF2F9',
    bodyBg: '#F2F6FC',
    cardBg: '#FFFFFF',
    cardBgAlt: '#EEF3FA',
    border: 'rgba(30,42,100,0.08)',
    borderHover: 'rgba(30,42,100,0.16)',
    textPrimary: '#1E2A64',
    textSecondary: '#475569',
    textMuted: '#94A3B8',
    accent: '#0369A1',
    accentMuted: '#0284C7',
    seed: '#DC4E41',
    glassBg: 'rgba(242,246,252,0.82)',
    glassBorder: 'rgba(30,42,100,0.08)',
    scrollThumb: 'rgba(30,42,100,0.12)',
  },

  // ── Morning — near-white with soft rose + sage ──
  morning: {
    id: 'morning',
    label: 'Morning',
    swatch: '#F8F4F2',
    bodyBg: '#FAF7F5',
    cardBg: '#FFFFFF',
    cardBgAlt: '#F5F0EE',
    border: 'rgba(80,30,30,0.07)',
    borderHover: 'rgba(80,30,30,0.14)',
    textPrimary: '#2D1F1A',
    textSecondary: '#6B534C',
    textMuted: '#A8928C',
    accent: '#0F766E',
    accentMuted: '#14877E',
    seed: '#C4412E',
    glassBg: 'rgba(250,247,245,0.82)',
    glassBorder: 'rgba(80,30,30,0.07)',
    scrollThumb: 'rgba(80,30,30,0.10)',
  },
};
