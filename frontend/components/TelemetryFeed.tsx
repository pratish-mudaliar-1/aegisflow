/**
 * AegisFlow :: components/TelemetryFeed.tsx
 * ─────────────────────────────────────────
 * High-velocity SSE terminal log pane styled as an IDE developer console.
 * Renders streamed SSE events with syntax-highlighted diagnostic rows,
 * auto-scroll anchoring, searchable filter bar, and timestamp columns.
 */

"use client";

import {
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  Circle,
  Filter,
  ScrollText,
  Terminal,
  XCircle,
  Zap,
} from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { SSEEvent, SSEEventType } from "@/lib/types";

interface TelemetryFeedProps {
  events: SSEEvent[];
  className?: string;
}

// ─── Event type styling config ────────────────────────────────────────────────

interface EventStyle {
  icon: React.ReactNode;
  labelColor: string;
  rowBg: string;
  borderColor: string;
  badge: string;
}

const EVENT_STYLES: Record<SSEEventType | "DEFAULT", EventStyle> = {
  THREAD_INITIALIZED: {
    icon: <Circle size={10} className="text-indigo-400" fill="currentColor" />,
    labelColor: "text-indigo-300",
    rowBg: "bg-indigo-950/20",
    borderColor: "border-indigo-800/40",
    badge: "bg-indigo-900/60 text-indigo-300",
  },
  NODE_TRANSITION: {
    icon: <ChevronRight size={12} className="text-emerald-400" />,
    labelColor: "text-emerald-300",
    rowBg: "bg-emerald-950/10",
    borderColor: "border-emerald-800/20",
    badge: "bg-emerald-900/50 text-emerald-300",
  },
  HUMAN_INTERRUPT_REQUIRED: {
    icon: <AlertTriangle size={11} className="text-amber-400" />,
    labelColor: "text-amber-300",
    rowBg: "bg-amber-950/25",
    borderColor: "border-amber-700/50",
    badge: "bg-amber-900/60 text-amber-300",
  },
  CRITICAL_FAILURE: {
    icon: <XCircle size={11} className="text-rose-400" />,
    labelColor: "text-rose-300",
    rowBg: "bg-rose-950/25",
    borderColor: "border-rose-800/50",
    badge: "bg-rose-900/60 text-rose-300",
  },
  WORKFLOW_COMPLETE: {
    icon: <CheckCircle2 size={11} className="text-emerald-400" />,
    labelColor: "text-emerald-300",
    rowBg: "bg-emerald-950/20",
    borderColor: "border-emerald-700/40",
    badge: "bg-emerald-900/60 text-emerald-300",
  },
  DEFAULT: {
    icon: <Zap size={10} className="text-zinc-500" />,
    labelColor: "text-zinc-400",
    rowBg: "bg-transparent",
    borderColor: "border-zinc-800/30",
    badge: "bg-zinc-800/60 text-zinc-400",
  },
};

function getStyle(evt: SSEEventType | string): EventStyle {
  return EVENT_STYLES[evt as SSEEventType] ?? EVENT_STYLES.DEFAULT;
}

// ─── Render a single payload value with syntax coloring ──────────────────────

function renderValue(val: unknown, depth = 0): React.ReactNode {
  if (val === null) return <span className="text-rose-400">null</span>;
  if (typeof val === "boolean")
    return <span className="text-amber-400">{String(val)}</span>;
  if (typeof val === "number")
    return <span className="text-sky-400">{val}</span>;
  if (typeof val === "string")
    return <span className="text-green-400">&quot;{val}&quot;</span>;
  if (Array.isArray(val)) {
    if (val.length === 0) return <span className="text-zinc-500">[]</span>;
    return (
      <span>
        [<span className="text-zinc-500">{val.length} items</span>]
      </span>
    );
  }
  if (typeof val === "object" && depth < 2) {
    const entries = Object.entries(val as Record<string, unknown>).slice(0, 5);
    return (
      <span className="text-zinc-300">
        {"{ "}
        {entries.map(([k, v], i) => (
          <span key={k}>
            <span className="text-violet-400">{k}</span>
            <span className="text-zinc-500">: </span>
            {renderValue(v, depth + 1)}
            {i < entries.length - 1 && <span className="text-zinc-600">, </span>}
          </span>
        ))}
        {Object.keys(val as object).length > 5 && (
          <span className="text-zinc-600"> …+{Object.keys(val as object).length - 5}</span>
        )}
        {" }"}
      </span>
    );
  }
  return <span className="text-zinc-500">[object]</span>;
}

// ─── Single event row ─────────────────────────────────────────────────────────

function EventRow({ event, index }: { event: SSEEvent; index: number }) {
  const [expanded, setExpanded] = useState(false);
  const style = getStyle(event.event);

  const ts = useMemo(() => {
    try {
      return new Date(event.timestamp).toISOString().slice(11, 23);
    } catch {
      return "--:--.---";
    }
  }, [event.timestamp]);

  const payloadEntries = Object.entries(event.data).filter(
    ([k]) => k !== "state",
  );

  return (
    <motion.div
      initial={{ opacity: 0, x: -6, height: 0 }}
      animate={{ opacity: 1, x: 0, height: "auto" }}
      transition={{ duration: 0.18, ease: "easeOut" }}
      className={`border-b ${style.borderColor} ${style.rowBg} group`}
    >
      {/* ── Primary row ── */}
      <div
        className="flex items-start gap-2 px-3 py-[5px] cursor-pointer hover:bg-white/[0.02] transition-colors"
        onClick={() => setExpanded((v) => !v)}
        role="button"
        aria-expanded={expanded}
      >
        {/* Row number */}
        <span className="text-zinc-700 font-mono text-[9px] pt-[1px] w-6 text-right shrink-0 select-none">
          {index + 1}
        </span>

        {/* Timestamp */}
        <span className="text-zinc-600 font-mono text-[9px] pt-[1px] w-20 shrink-0">
          {ts}
        </span>

        {/* Icon */}
        <span className="pt-[1px] shrink-0">{style.icon}</span>

        {/* Event type badge */}
        <span
          className={`font-mono text-[9px] px-1.5 py-0 rounded border border-current/20 shrink-0 ${style.badge}`}
        >
          {event.event}
        </span>

        {/* Inline data preview */}
        <span className={`font-mono text-[10px] ${style.labelColor} truncate flex-1`}>
          {event.data.node_name && (
            <span className="text-zinc-500 mr-1">node={event.data.node_name as string}</span>
          )}
          {event.data.message && (event.data.message as string)}
          {event.data.error && (
            <span className="text-rose-400">{event.data.error as string}</span>
          )}
          {event.data.proposed_tool && (
            <span>
              <span className="text-zinc-500">tool=</span>
              <span className="text-amber-400">{event.data.proposed_tool as string}</span>
            </span>
          )}
          {event.data.inference_route && (
            <span>
              <span className="text-zinc-500"> route=</span>
              <span className="text-indigo-400">{event.data.inference_route as string}</span>
            </span>
          )}
        </span>

        {/* Expand chevron */}
        {payloadEntries.length > 0 && (
          <ChevronRight
            size={10}
            className={`shrink-0 text-zinc-600 transition-transform ${expanded ? "rotate-90" : ""}`}
          />
        )}
      </div>

      {/* ── Expanded payload ── */}
      <AnimatePresence>
        {expanded && payloadEntries.length > 0 && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="overflow-hidden"
          >
            <div className="pl-[88px] pr-4 pb-2 font-mono text-[9px] space-y-0.5 bg-black/20">
              {payloadEntries.map(([key, val]) => (
                <div key={key} className="flex gap-2">
                  <span className="text-violet-400 shrink-0">{key}</span>
                  <span className="text-zinc-500">→</span>
                  <span>{renderValue(val)}</span>
                </div>
              ))}
              {/* Token budget inline if present */}
              {event.data.token_budget && (() => {
                const tb = event.data.token_budget as unknown as Record<string, unknown>;
                const total = ((tb.total_input_tokens as number) ?? 0) + ((tb.total_output_tokens as number) ?? 0);
                const ceiling = (tb.session_token_ceiling as number) ?? 50000;
                const pct = Math.round((total / ceiling) * 100);
                return (
                  <div className="mt-1 flex items-center gap-2">
                    <span className="text-zinc-600">budget</span>
                    <div className="flex-1 h-1 bg-zinc-800 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all ${pct > 80 ? "bg-rose-500" : pct > 50 ? "bg-amber-500" : "bg-emerald-500"}`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                    <span className="text-zinc-500">{pct}%</span>
                  </div>
                );
              })()}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

const FILTER_OPTIONS: Array<{ label: string; value: SSEEventType | "ALL" }> = [
  { label: "ALL", value: "ALL" },
  { label: "NODES", value: "NODE_TRANSITION" },
  { label: "HITL", value: "HUMAN_INTERRUPT_REQUIRED" },
  { label: "ERRORS", value: "CRITICAL_FAILURE" },
];

export function TelemetryFeed({ events, className = "" }: TelemetryFeedProps) {
  const [filter, setFilter] = useState<SSEEventType | "ALL">("ALL");
  const [search, setSearch] = useState("");
  const [autoScroll, setAutoScroll] = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const handleScroll = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 48;
    setAutoScroll(nearBottom);
  }, []);

  useEffect(() => {
    if (autoScroll) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [events, autoScroll]);

  const filtered = useMemo(() => {
    let list = events;
    if (filter !== "ALL") list = list.filter((e) => e.event === filter);
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter(
        (e) =>
          e.event.toLowerCase().includes(q) ||
          JSON.stringify(e.data).toLowerCase().includes(q),
      );
    }
    return list;
  }, [events, filter, search]);

  return (
    <div className={`flex flex-col ${className} bg-zinc-950 rounded-lg border border-zinc-800/60 overflow-hidden`}>
      {/* ── Header ── */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-zinc-800/60 bg-zinc-900/50 shrink-0">
        <Terminal size={12} className="text-zinc-500" />
        <span className="text-zinc-400 text-[10px] font-mono font-semibold uppercase tracking-widest">
          Telemetry Feed
        </span>
        <div className="flex-1" />

        {/* Event count */}
        <span className="text-zinc-600 font-mono text-[9px]">
          {filtered.length}/{events.length} events
        </span>

        {/* Live indicator */}
        <div className="flex items-center gap-1">
          <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
          <span className="text-emerald-600 font-mono text-[9px]">LIVE</span>
        </div>
      </div>

      {/* ── Filter bar ── */}
      <div className="flex items-center gap-1.5 px-3 py-1.5 border-b border-zinc-800/40 bg-zinc-900/30 shrink-0">
        <Filter size={10} className="text-zinc-600 shrink-0" />
        {FILTER_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            onClick={() => setFilter(opt.value)}
            className={`px-2 py-0.5 rounded text-[9px] font-mono transition-all ${
              filter === opt.value
                ? "bg-zinc-700 text-zinc-200"
                : "text-zinc-600 hover:text-zinc-400 hover:bg-zinc-800/50"
            }`}
          >
            {opt.label}
          </button>
        ))}
        <div className="flex-1 mx-1">
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="search events…"
            className="w-full bg-transparent text-[9px] font-mono text-zinc-400 placeholder-zinc-700 outline-none border-b border-zinc-800/60 focus:border-zinc-600 pb-0.5 transition-colors"
          />
        </div>

        {/* Auto-scroll toggle */}
        <button
          onClick={() => setAutoScroll((v) => !v)}
          className={`flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-mono transition-all ${
            autoScroll ? "text-emerald-400 bg-emerald-950/30" : "text-zinc-600 hover:text-zinc-400"
          }`}
          title="Toggle auto-scroll"
        >
          <ScrollText size={9} />
        </button>
      </div>

      {/* ── Event list ── */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto scrollbar-thin scrollbar-track-zinc-950 scrollbar-thumb-zinc-800"
      >
        {filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-2 text-zinc-700">
            <Terminal size={20} />
            <span className="font-mono text-[10px]">Awaiting telemetry stream…</span>
          </div>
        ) : (
          <AnimatePresence initial={false}>
            {filtered.map((evt, i) => (
              <EventRow key={`${evt.timestamp}-${i}`} event={evt} index={i} />
            ))}
          </AnimatePresence>
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
