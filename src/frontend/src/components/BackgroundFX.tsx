import { motion } from 'framer-motion';
import type { Theme } from '../lib/theme';

interface BackgroundFXProps {
  variant: 'hero' | 'subtle';
  theme: Theme;
}

export function BackgroundFX({ variant, theme }: BackgroundFXProps) {
  const hero = variant === 'hero';
  const isDark = theme.id === 'dark';

  // ── Blob palette per theme ──────────────────────────────────
  const blobs: { color: string; opacityHero: number; opacitySub: number; style: string }[] =
    theme.id === 'warm'
      ? [
          { color: 'rgba(212,69,58,XXX)', opacityHero: 1, opacitySub: 0.7, style: 'radial-gradient(circle at 30% 30%, rgba(212,69,58,0.18), rgba(230,130,50,0.09) 45%, transparent 70%)' },
          { color: 'rgba(13,122,111,XXX)', opacityHero: 1, opacitySub: 0.6, style: 'radial-gradient(circle at 70% 70%, rgba(13,122,111,0.16), rgba(13,148,136,0.08) 45%, transparent 70%)' },
          { color: 'rgba(200,165,70,XXX)', opacityHero: 1, opacitySub: 0, style: 'radial-gradient(circle, rgba(200,165,70,0.12), transparent 65%)' },
        ]
      : theme.id === 'pearl'
        ? [
            { color: '', opacityHero: 1, opacitySub: 0.6, style: 'radial-gradient(circle at 25% 25%, rgba(56,96,220,0.14), rgba(99,102,241,0.08) 45%, transparent 70%)' },
            { color: '', opacityHero: 1, opacitySub: 0.6, style: 'radial-gradient(circle at 75% 75%, rgba(3,105,161,0.14), rgba(56,189,248,0.08) 45%, transparent 70%)' },
            { color: '', opacityHero: 1, opacitySub: 0, style: 'radial-gradient(circle, rgba(109,40,217,0.10), transparent 65%)' },
          ]
        : theme.id === 'morning'
          ? [
              { color: '', opacityHero: 1, opacitySub: 0.6, style: 'radial-gradient(circle at 25% 25%, rgba(196,65,46,0.16), rgba(220,100,70,0.08) 45%, transparent 70%)' },
              { color: '', opacityHero: 1, opacitySub: 0.6, style: 'radial-gradient(circle at 75% 75%, rgba(15,118,110,0.14), rgba(20,135,126,0.07) 45%, transparent 70%)' },
              { color: '', opacityHero: 1, opacitySub: 0, style: 'radial-gradient(circle, rgba(251,191,36,0.10), transparent 65%)' },
            ]
          : // dark
            [
              { color: '', opacityHero: 0.55, opacitySub: 0.2, style: 'radial-gradient(circle at 30% 30%, rgba(249,112,102,0.55), rgba(251,146,60,0.25) 40%, transparent 70%)' },
              { color: '', opacityHero: 0.5, opacitySub: 0.18, style: 'radial-gradient(circle at 70% 70%, rgba(45,212,191,0.45), rgba(56,189,248,0.2) 40%, transparent 70%)' },
              { color: '', opacityHero: 0.25, opacitySub: 0, style: 'radial-gradient(circle, rgba(124,58,237,0.35), transparent 70%)' },
            ];

  const gridColor = isDark ? 'rgba(255,255,255,0.6)' : 'rgba(0,0,0,0.18)';
  const gridOpacity = isDark ? 0.035 : 0.04;
  const noiseBlend = isDark ? 'mix-blend-overlay' : 'mix-blend-multiply';

  return (
    <div className="fixed inset-0 -z-10 overflow-hidden pointer-events-none">
      {/* Base */}
      <div
        className="absolute inset-0 transition-colors duration-700"
        style={{ background: theme.bodyBg }}
      />

      {/* Blob 1 — top-left */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: hero ? blobs[0].opacityHero : blobs[0].opacitySub }}
        transition={{ duration: 1.6 }}
        className="absolute -top-40 -left-40 w-[700px] h-[700px] rounded-full blur-[130px]"
        style={{ background: blobs[0].style, animation: 'aurora 18s ease-in-out infinite' }}
      />

      {/* Blob 2 — bottom-right */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: hero ? blobs[1].opacityHero : blobs[1].opacitySub }}
        transition={{ duration: 1.6, delay: 0.15 }}
        className="absolute -bottom-60 -right-40 w-[760px] h-[760px] rounded-full blur-[140px]"
        style={{ background: blobs[1].style, animation: 'aurora 22s ease-in-out infinite reverse' }}
      />

      {/* Blob 3 — center, hero only */}
      {hero && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: blobs[2].opacityHero }}
          transition={{ duration: 1.8, delay: 0.3 }}
          className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-[580px] h-[580px] rounded-full blur-[130px]"
          style={{ background: blobs[2].style, animation: 'drift-slow 14s ease-in-out infinite' }}
        />
      )}

      {/* Dot grid */}
      <div
        className="absolute inset-0"
        style={{
          opacity: gridOpacity,
          backgroundImage: `radial-gradient(circle, ${gridColor} 1px, transparent 1px)`,
          backgroundSize: '40px 40px',
          maskImage: 'radial-gradient(ellipse at center, black 35%, transparent 78%)',
          WebkitMaskImage: 'radial-gradient(ellipse at center, black 35%, transparent 78%)',
        }}
      />

      {/* Noise grain */}
      <div
        className={`absolute inset-0 ${noiseBlend}`}
        style={{
          opacity: isDark ? 0.04 : 0.025,
          backgroundImage: "url(\"data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E\")",
        }}
      />
    </div>
  );
}
