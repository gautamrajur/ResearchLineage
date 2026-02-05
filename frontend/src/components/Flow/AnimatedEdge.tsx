import { BaseEdge, getStraightPath, type EdgeProps } from '@xyflow/react';

export function AnimatedEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  style,
}: EdgeProps) {
  const [edgePath] = getStraightPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
  });

  return (
    <>
      {/* Glow layer */}
      <BaseEdge
        id={`${id}-glow`}
        path={edgePath}
        style={{
          stroke: 'rgba(99, 102, 241, 0.3)',
          strokeWidth: 6,
          filter: 'blur(4px)',
        }}
      />

      {/* Main edge */}
      <BaseEdge
        id={id}
        path={edgePath}
        style={{
          stroke: 'url(#edge-gradient)',
          strokeWidth: 2,
          ...style,
        }}
      />

      {/* Animated particle */}
      <circle r="3" fill="#818cf8">
        <animateMotion dur="2s" repeatCount="indefinite" path={edgePath} />
      </circle>

      {/* SVG Gradient Definition */}
      <defs>
        <linearGradient id="edge-gradient" gradientUnits="userSpaceOnUse" x1={sourceX} y1={sourceY} x2={targetX} y2={targetY}>
          <stop offset="0%" stopColor="#6366f1" />
          <stop offset="100%" stopColor="#8b5cf6" />
        </linearGradient>
      </defs>
    </>
  );
}
