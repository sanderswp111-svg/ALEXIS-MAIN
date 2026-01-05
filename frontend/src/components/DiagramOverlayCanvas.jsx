import React, { useEffect, useState } from "react";

// Primitive definitions
// type OverlayCommand = {
//   id: string;
//   type: "HIGHLIGHT_BOX" | "PULSE_DOT" | "TRACE_PATH" | "ARROW_POINTER";
//   page: number;
//   bounds?: { x: number; y: number; width: number; height: number };
//   pathPoints?: { x: number; y: number }[];
//   anchor?: { x: number; y: number };
//   style?: { color?: string; intensity?: number; pulse?: boolean };
//   durationMs?: number;
// };

const colorMap = {
  cyan: "rgba(56, 189, 248, INTENSITY)",
  green: "rgba(34, 197, 94, INTENSITY)",
  purple: "rgba(168, 85, 247, INTENSITY)",
  yellow: "rgba(234, 179, 8, INTENSITY)",
};

export const DiagramOverlayCanvas = ({
  page,
  zoom,
  viewportOrigin,
  overlayCommands,
}) => {
  const [activeCommands, setActiveCommands] = useState([]);

  // Apply commands with duration
  useEffect(() => {
    if (!overlayCommands || overlayCommands.length === 0) return;

    const now = Date.now();
    const withExpiry = overlayCommands.map((cmd) => ({
      ...cmd,
      _expiresAt: now + (cmd.durationMs || 1500),
    }));

    setActiveCommands((prev) => [...prev, ...withExpiry]);
  }, [overlayCommands]);

  // Prune expired overlays
  useEffect(() => {
    if (activeCommands.length === 0) return;

    const timer = setInterval(() => {
      const now = Date.now();
      setActiveCommands((prev) => prev.filter((cmd) => cmd._expiresAt > now));
    }, 100);

    return () => clearInterval(timer);
  }, [activeCommands.length]);

  if (!page) return null;

  const renderCommand = (cmd) => {
    if (cmd.page !== page) return null;

    const intensity = cmd.style?.intensity ?? 0.5;
    const colorKey = cmd.style?.color || "cyan";
    const base = colorMap[colorKey] || colorMap.cyan;
    const rgba = base.replace("INTENSITY", intensity.toString());

    if (cmd.type === "HIGHLIGHT_BOX" && cmd.bounds) {
      const { x, y, width, height } = cmd.bounds;
      return (
        <div
          key={cmd.id}
          className="absolute rounded-md border border-cyan-400/70 shadow-[0_0_0_2px_rgba(8,47,73,0.6)]"
          style={{
            left: (x - viewportOrigin.x) * zoom,
            top: (y - viewportOrigin.y) * zoom,
            width: width * zoom,
            height: height * zoom,
            boxShadow: `0 0 0 2px ${rgba}`,
            pointerEvents: "none",
          }}
        />
      );
    }

    if (cmd.type === "PULSE_DOT" && cmd.anchor) {
      const { x, y } = cmd.anchor;
      return (
        <div
          key={cmd.id}
          className="absolute rounded-full animate-pulse"
          style={{
            left: (x - viewportOrigin.x) * zoom - 6,
            top: (y - viewportOrigin.y) * zoom - 6,
            width: 12,
            height: 12,
            backgroundColor: rgba,
            boxShadow: `0 0 0 4px ${rgba}`,
            pointerEvents: "none",
          }}
        />
      );
    }

    if (cmd.type === "TRACE_PATH" && cmd.pathPoints && cmd.pathPoints.length > 1) {
      const d = cmd.pathPoints
        .map((pt, idx) => {
          const px = (pt.x - viewportOrigin.x) * zoom;
          const py = (pt.y - viewportOrigin.y) * zoom;
          return `${idx === 0 ? "M" : "L"}${px},${py}`;
        })
        .join(" ");
      return (
        <svg
          key={cmd.id}
          className="absolute inset-0 pointer-events-none"
        >
          <path
            d={d}
            fill="none"
            stroke={rgba}
            strokeWidth={2}
            strokeLinecap="round"
          />
        </svg>
      );
    }

    if (cmd.type === "ARROW_POINTER" && cmd.anchor) {
      const { x, y } = cmd.anchor;
      const px = (x - viewportOrigin.x) * zoom;
      const py = (y - viewportOrigin.y) * zoom;
      const size = 16;
      return (
        <svg
          key={cmd.id}
          className="absolute pointer-events-none"
          style={{ left: px, top: py - size }}
          width={size}
          height={size}
          viewBox="0 0 24 24"
        >
          <polygon
            points="12,0 24,24 12,18 0,24"
            fill={rgba}
          />
        </svg>
      );
    }

    return null;
  };

  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden">
      {activeCommands.map(renderCommand)}
    </div>
  );
};
