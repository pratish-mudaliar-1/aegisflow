/**
 * AegisFlow :: components/StateGraphVisualizer.tsx
 * ──────────────────────────────────────────────────
 * High-performance native SVG LangGraph state network viewer.
 * Renders the 4 execution nodes with animated directional flow paths,
 * pulsing gradient stroke markers, and active-node glow highlighting.
 */

"use client";

import React, { useId } from "react";
import type { GraphNodeName } from "@/lib/types";

interface NodeDef {
  id: GraphNodeName;
  label: string;
  sublabel: string;
  x: number;
  y: number;
  accentClass: string;
  accentColor: string;
  glowColor: string;
  icon: React.ReactNode;
}

interface EdgeDef {
  from: GraphNodeName;
  to: GraphNodeName;
  label?: string;
  isConditional?: boolean;
}

interface StateGraphVisualizerProps {
  activeNode: GraphNodeName | null;
  className?: string;
}

// ─── SVG layout constants ─────────────────────────────────────────────────────
const W = 520;
const H = 340;
const NODE_W = 110;
const NODE_H = 62;

const NODES: NodeDef[] = [
  {
    id: "parse_input",
    label: "parse_input",
    sublabel: "NL → Task Steps",
    x: 20,
    y: 139,
    accentClass: "text-emerald-400",
    accentColor: "#34d399",
    glowColor: "rgba(52,211,153,0.35)",
    icon: (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <polyline points="16 18 22 12 16 6" /><polyline points="8 6 2 12 8 18" />
      </svg>
    ),
  },
  {
    id: "route_task",
    label: "route_task",
    sublabel: "LOCAL / CLOUD",
    x: 205,
    y: 60,
    accentClass: "text-indigo-400",
    accentColor: "#818cf8",
    glowColor: "rgba(129,140,248,0.35)",
    icon: (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <circle cx="12" cy="5" r="3" /><circle cx="5" cy="19" r="3" /><circle cx="19" cy="19" r="3" />
        <line x1="12" y1="8" x2="5.5" y2="16" /><line x1="12" y1="8" x2="18.5" y2="16" />
      </svg>
    ),
  },
  {
    id: "human_validation",
    label: "human_validation",
    sublabel: "HITL Intercept",
    x: 205,
    y: 218,
    accentClass: "text-amber-400",
    accentColor: "#fbbf24",
    glowColor: "rgba(251,191,36,0.35)",
    icon: (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      </svg>
    ),
  },
  {
    id: "execute_tool",
    label: "execute_tool",
    sublabel: "MCP Tool Call",
    x: 390,
    y: 139,
    accentClass: "text-emerald-400",
    accentColor: "#34d399",
    glowColor: "rgba(52,211,153,0.35)",
    icon: (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <polygon points="5 3 19 12 5 21 5 3" />
      </svg>
    ),
  },
];

const EDGES: EdgeDef[] = [
  { from: "parse_input", to: "route_task" },
  { from: "parse_input", to: "human_validation", isConditional: true },
  { from: "route_task", to: "execute_tool" },
  { from: "human_validation", to: "execute_tool" },
  { from: "human_validation", to: "parse_input", isConditional: true, label: "EDIT" },
];

function getNodeCenter(id: GraphNodeName): { cx: number; cy: number } {
  const n = NODES.find((n) => n.id === id)!;
  return { cx: n.x + NODE_W / 2, cy: n.y + NODE_H / 2 };
}

function buildPath(from: GraphNodeName, to: GraphNodeName): string {
  const { cx: x1, cy: y1 } = getNodeCenter(from);
  const { cx: x2, cy: y2 } = getNodeCenter(to);
  const dx = (x2 - x1) * 0.45;
  return `M${x1},${y1} C${x1 + dx},${y1} ${x2 - dx},${y2} ${x2},${y2}`;
}

export function StateGraphVisualizer({ activeNode, className = "" }: StateGraphVisualizerProps) {
  const uid = useId().replace(/:/g, "");

  return (
    <div className={`relative select-none ${className}`}>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        width="100%"
        height="100%"
        xmlns="http://www.w3.org/2000/svg"
        className="overflow-visible"
      >
        <defs>
          {/* Flow gradient for each edge */}
          {EDGES.map((e, i) => {
            const fromNode = NODES.find((n) => n.id === e.from)!;
            const toNode = NODES.find((n) => n.id === e.to)!;
            return (
              <linearGradient
                key={i}
                id={`${uid}-grad-${i}`}
                x1="0%"
                y1="0%"
                x2="100%"
                y2="0%"
                gradientUnits="userSpaceOnUse"
              >
                <stop offset="0%" stopColor={fromNode.accentColor} stopOpacity="0.8" />
                <stop offset="100%" stopColor={toNode.accentColor} stopOpacity="0.8" />
              </linearGradient>
            );
          })}

          {/* Arrow marker per accent color */}
          {["#34d399", "#818cf8", "#fbbf24"].map((color) => (
            <marker
              key={color}
              id={`${uid}-arrow-${color.replace("#", "")}`}
              markerWidth="8"
              markerHeight="8"
              refX="6"
              refY="3"
              orient="auto"
            >
              <path d="M0,0 L0,6 L8,3 z" fill={color} opacity="0.85" />
            </marker>
          ))}

          {/* Active node glow filter */}
          <filter id={`${uid}-glow`} x="-40%" y="-40%" width="180%" height="180%">
            <feGaussianBlur stdDeviation="4" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>

          {/* Animated pulse dash */}
          <style>{`
            @keyframes dashFlow {
              from { stroke-dashoffset: 200; }
              to   { stroke-dashoffset: 0; }
            }
            @keyframes pulseRing {
              0%, 100% { opacity: 0.5; transform: scale(1); }
              50%       { opacity: 1;   transform: scale(1.06); }
            }
            .dash-flow {
              stroke-dasharray: 8 6;
              animation: dashFlow 1.4s linear infinite;
            }
            .active-flow {
              stroke-dasharray: 10 5;
              animation: dashFlow 0.7s linear infinite;
            }
            .pulse-ring {
              animation: pulseRing 1.6s ease-in-out infinite;
              transform-origin: center;
            }
          `}</style>
        </defs>

        {/* ── Edges ─────────────────────────────────────────────────── */}
        {EDGES.map((edge, i) => {
          const fromNode = NODES.find((n) => n.id === edge.from)!;
          const toNode = NODES.find((n) => n.id === edge.to)!;
          const arrowId = `${uid}-arrow-${fromNode.accentColor.replace("#", "")}`;
          const isActive =
            activeNode === edge.from || activeNode === edge.to;

          return (
            <g key={i}>
              {/* Shadow trace */}
              <path
                d={buildPath(edge.from, edge.to)}
                fill="none"
                stroke="#374151"
                strokeWidth="2"
              />
              {/* Animated flow line */}
              <path
                d={buildPath(edge.from, edge.to)}
                fill="none"
                stroke={`url(#${uid}-grad-${i})`}
                strokeWidth={isActive ? 2.5 : 1.5}
                strokeLinecap="round"
                markerEnd={`url(#${arrowId})`}
                opacity={isActive ? 1 : 0.45}
                className={isActive ? "active-flow" : "dash-flow"}
              />
              {/* Edge label */}
              {edge.label && (() => {
                const { cx: x1, cy: y1 } = getNodeCenter(edge.from);
                const { cx: x2, cy: y2 } = getNodeCenter(edge.to);
                return (
                  <text
                    x={(x1 + x2) / 2}
                    y={(y1 + y2) / 2 - 8}
                    textAnchor="middle"
                    fill="#6b7280"
                    fontSize="9"
                    fontFamily="monospace"
                  >
                    {edge.label}
                  </text>
                );
              })()}
            </g>
          );
        })}

        {/* ── Nodes ─────────────────────────────────────────────────── */}
        {NODES.map((node) => {
          const isActive = activeNode === node.id;
          return (
            <g key={node.id} transform={`translate(${node.x}, ${node.y})`}>
              {/* Active glow pulse ring */}
              {isActive && (
                <rect
                  x="-6"
                  y="-6"
                  width={NODE_W + 12}
                  height={NODE_H + 12}
                  rx="12"
                  ry="12"
                  fill={node.glowColor}
                  className="pulse-ring"
                  style={{ filter: `drop-shadow(0 0 10px ${node.accentColor})` }}
                />
              )}

              {/* Node body */}
              <rect
                width={NODE_W}
                height={NODE_H}
                rx="8"
                ry="8"
                fill={isActive ? "#111827" : "#0f172a"}
                stroke={isActive ? node.accentColor : "#1f2937"}
                strokeWidth={isActive ? 1.5 : 1}
                filter={isActive ? `url(#${uid}-glow)` : undefined}
              />

              {/* Top accent bar */}
              <rect
                width={NODE_W}
                height="3"
                rx="8"
                ry="8"
                fill={node.accentColor}
                opacity={isActive ? 1 : 0.4}
              />

              {/* Icon + label */}
              <g transform="translate(10, 16)" fill={node.accentColor}>
                {node.icon}
              </g>
              <text
                x="28"
                y="27"
                fontSize="10"
                fontWeight="600"
                fontFamily="monospace"
                fill={isActive ? node.accentColor : "#9ca3af"}
              >
                {node.label}
              </text>
              <text
                x="10"
                y="48"
                fontSize="9"
                fontFamily="monospace"
                fill={isActive ? "#d1d5db" : "#4b5563"}
              >
                {node.sublabel}
              </text>

              {/* Active status dot */}
              {isActive && (
                <circle cx={NODE_W - 10} cy="12" r="4" fill={node.accentColor}>
                  <animate attributeName="opacity" values="1;0.3;1" dur="1s" repeatCount="indefinite" />
                </circle>
              )}
            </g>
          );
        })}

        {/* ── Legend ───────────────────────────────────────────────── */}
        <g transform={`translate(10, ${H - 22})`}>
          <circle cx="6" cy="6" r="4" fill="#34d399" opacity="0.8" />
          <text x="14" y="10" fontSize="8" fill="#6b7280" fontFamily="monospace">Compute</text>
          <circle cx="80" cy="6" r="4" fill="#818cf8" opacity="0.8" />
          <text x="88" y="10" fontSize="8" fill="#6b7280" fontFamily="monospace">Router</text>
          <circle cx="145" cy="6" r="4" fill="#fbbf24" opacity="0.8" />
          <text x="153" y="10" fontSize="8" fill="#6b7280" fontFamily="monospace">HITL Gate</text>
        </g>
      </svg>
    </div>
  );
}
