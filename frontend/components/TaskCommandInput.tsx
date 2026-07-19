/**
 * AegisFlow :: components/TaskCommandInput.tsx
 * ─────────────────────────────────────────────
 * Natural language command ingestion engine with advanced controls.
 * Handles budget override, tool override, and step-progress visualization.
 */

"use client";

import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  ChevronRight,
  Cpu,
  Loader2,
  RefreshCcw,
  SendHorizontal,
  Terminal,
  Wand2,
  XCircle,
} from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import React, { useCallback, useEffect, useRef, useState } from "react";
import type { TaskStep, TokenBudgetTracker } from "@/lib/types";

interface TaskCommandInputProps {
  onSubmit: (input: string, tokenBudget?: number, toolOverride?: string) => void;
  isRunning: boolean;
  onReset: () => void;
  taskSteps: TaskStep[];
  activeStepIndex: number;
  tokenBudget: TokenBudgetTracker | null;
  sessionId: string | null;
  error: string | null;
}

const PLACEHOLDER_EXAMPLES = [
  "Summarize Q3 financials and send report to CFO via enterprise email…",
  "Schedule a compliance review meeting with legal team for next Thursday…",
  "Execute database migration for user schema v2.4 with backup checkpoint…",
  "Authorize $50,000 budget allocation for cloud infrastructure Q4…",
  "Write API integration spec to filesystem for the payments microservice…",
];

const STEP_STATUS_CONFIG = {
  pending: {
    icon: <div className="w-3 h-3 rounded-full border border-zinc-700" />,
    color: "text-zinc-600",
    bg: "bg-transparent",
  },
  running: {
    icon: (
      <motion.div
        animate={{ rotate: 360 }}
        transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
      >
        <Loader2 size={12} className="text-emerald-400" />
      </motion.div>
    ),
    color: "text-emerald-300",
    bg: "bg-emerald-950/20",
  },
  completed: {
    icon: <CheckCircle2 size={12} className="text-emerald-500" />,
    color: "text-zinc-500",
    bg: "bg-transparent",
  },
  failed: {
    icon: <XCircle size={12} className="text-rose-500" />,
    color: "text-rose-400",
    bg: "bg-rose-950/10",
  },
};

export function TaskCommandInput({
  onSubmit,
  isRunning,
  onReset,
  taskSteps,
  activeStepIndex,
  tokenBudget,
  sessionId,
  error,
}: TaskCommandInputProps) {
  const [input, setInput] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [tokenBudgetOverride, setTokenBudgetOverride] = useState<string>("");
  const [toolOverride, setToolOverride] = useState("");
  const [placeholderIdx, setPlaceholderIdx] = useState(0);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Cycle placeholder examples
  useEffect(() => {
    const interval = setInterval(() => {
      setPlaceholderIdx((i) => (i + 1) % PLACEHOLDER_EXAMPLES.length);
    }, 4000);
    return () => clearInterval(interval);
  }, []);

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [input]);

  const handleSubmit = useCallback(() => {
    const trimmed = input.trim();
    if (!trimmed || isRunning) return;
    const budget = tokenBudgetOverride
      ? Math.min(200000, Math.max(1000, parseInt(tokenBudgetOverride, 10)))
      : undefined;
    onSubmit(trimmed, budget, toolOverride.trim() || undefined);
    setInput("");
  }, [input, isRunning, tokenBudgetOverride, toolOverride, onSubmit]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit],
  );

  return (
    <div className="flex flex-col gap-4">
      {/* ── Session identity strip ── */}
      {sessionId && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          className="flex items-center gap-2 px-3 py-2 rounded-lg bg-zinc-900 border border-zinc-800/50"
        >
          <Terminal size={10} className="text-zinc-600" />
          <span className="text-zinc-600 font-mono text-[9px]">session</span>
          <span className="text-indigo-400 font-mono text-[9px] truncate">{sessionId}</span>
          <div className="ml-auto flex items-center gap-2">
            {isRunning && (
              <div className="flex items-center gap-1">
                <motion.div
                  className="w-1.5 h-1.5 rounded-full bg-emerald-500"
                  animate={{ opacity: [1, 0.2, 1] }}
                  transition={{ duration: 1, repeat: Infinity }}
                />
                <span className="text-emerald-500 font-mono text-[9px]">running</span>
              </div>
            )}
            <button
              onClick={onReset}
              className="text-zinc-700 hover:text-zinc-400 transition-colors"
              title="Reset session"
            >
              <RefreshCcw size={11} />
            </button>
          </div>
        </motion.div>
      )}

      {/* ── Command input card ── */}
      <div
        className={`relative rounded-xl border transition-all duration-200 overflow-hidden ${
          isRunning
            ? "border-emerald-700/40 shadow-[0_0_20px_rgba(52,211,153,0.06)]"
            : "border-zinc-700/40 hover:border-zinc-600/60 focus-within:border-zinc-600/80 focus-within:shadow-[0_0_20px_rgba(255,255,255,0.03)]"
        } bg-zinc-900`}
      >
        {/* Running progress bar */}
        {isRunning && (
          <motion.div
            className="absolute top-0 left-0 right-0 h-0.5 bg-gradient-to-r from-emerald-500 via-indigo-500 to-emerald-500"
            animate={{ backgroundPosition: ["0% 50%", "100% 50%", "0% 50%"] }}
            transition={{ duration: 2, repeat: Infinity }}
            style={{ backgroundSize: "200% 200%" }}
          />
        )}

        {/* Header row */}
        <div className="flex items-center gap-2 px-4 pt-3 pb-1">
          <Cpu size={12} className="text-zinc-600" />
          <span className="text-zinc-600 font-mono text-[10px] uppercase tracking-widest">
            Command Input
          </span>
          <div className="flex-1" />
          <span className="text-zinc-700 font-mono text-[9px]">⌘↵ to run</span>
        </div>

        {/* Textarea */}
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={PLACEHOLDER_EXAMPLES[placeholderIdx]}
          disabled={isRunning}
          rows={3}
          className="w-full bg-transparent text-zinc-200 font-sans text-sm px-4 py-2 outline-none resize-none placeholder-zinc-700 disabled:opacity-50 transition-all leading-relaxed"
        />

        {/* Footer row */}
        <div className="flex items-center gap-2 px-4 pb-3 pt-1">
          {/* Char count */}
          <span className="text-zinc-700 font-mono text-[9px]">
            {input.length} chars
          </span>

          {/* Advanced toggle */}
          <button
            onClick={() => setShowAdvanced((v) => !v)}
            className={`flex items-center gap-1 font-mono text-[9px] transition-colors ${
              showAdvanced ? "text-indigo-400" : "text-zinc-700 hover:text-zinc-500"
            }`}
          >
            <Wand2 size={9} />
            Advanced
          </button>

          <div className="flex-1" />

          {/* Submit button */}
          <motion.button
            onClick={handleSubmit}
            disabled={!input.trim() || isRunning}
            whileHover={{ scale: 1.03 }}
            whileTap={{ scale: 0.97 }}
            className={`flex items-center gap-2 px-4 py-1.5 rounded-lg font-mono text-xs font-semibold transition-all ${
              !input.trim() || isRunning
                ? "bg-zinc-800 text-zinc-600 cursor-not-allowed"
                : "bg-emerald-600/20 hover:bg-emerald-600/30 border border-emerald-600/50 text-emerald-300 shadow-[0_0_12px_rgba(52,211,153,0.15)]"
            }`}
          >
            {isRunning ? (
              <>
                <Loader2 size={12} className="animate-spin" />
                Running…
              </>
            ) : (
              <>
                <SendHorizontal size={12} />
                Run Workflow
              </>
            )}
          </motion.button>
        </div>

        {/* Advanced controls */}
        <AnimatePresence>
          {showAdvanced && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.18 }}
              className="overflow-hidden border-t border-zinc-800/50"
            >
              <div className="px-4 py-3 grid grid-cols-2 gap-3 bg-zinc-900/50">
                <div>
                  <label className="block text-zinc-600 font-mono text-[9px] uppercase tracking-widest mb-1">
                    Token Budget Override
                  </label>
                  <input
                    type="number"
                    value={tokenBudgetOverride}
                    onChange={(e) => setTokenBudgetOverride(e.target.value)}
                    placeholder="50000"
                    min={1000}
                    max={200000}
                    className="w-full bg-zinc-800 border border-zinc-700/50 rounded-md text-zinc-300 font-mono text-[11px] px-2.5 py-1.5 outline-none focus:border-indigo-600/50 transition-colors placeholder-zinc-700"
                  />
                  <p className="text-zinc-700 font-mono text-[9px] mt-0.5">1k – 200k tokens</p>
                </div>
                <div>
                  <label className="block text-zinc-600 font-mono text-[9px] uppercase tracking-widest mb-1">
                    Tool Override (debug)
                  </label>
                  <input
                    type="text"
                    value={toolOverride}
                    onChange={(e) => setToolOverride(e.target.value)}
                    placeholder="e.g. send_enterprise_email"
                    className="w-full bg-zinc-800 border border-zinc-700/50 rounded-md text-zinc-300 font-mono text-[11px] px-2.5 py-1.5 outline-none focus:border-indigo-600/50 transition-colors placeholder-zinc-700"
                  />
                  <p className="text-zinc-700 font-mono text-[9px] mt-0.5">MutatingToolRegistry key</p>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* ── Error display ── */}
      <AnimatePresence>
        {error && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            className="flex items-start gap-2.5 px-4 py-3 rounded-lg bg-rose-950/20 border border-rose-800/40"
          >
            <AlertCircle size={14} className="text-rose-400 mt-0.5 shrink-0" />
            <div>
              <p className="text-rose-300 font-semibold text-xs">Execution Error</p>
              <p className="text-rose-500 font-mono text-[10px] mt-0.5 leading-relaxed">{error}</p>
            </div>
            <button onClick={onReset} className="ml-auto text-rose-800 hover:text-rose-600 transition-colors">
              <XCircle size={14} />
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Task step progress ── */}
      <AnimatePresence>
        {taskSteps.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 6 }}
            className="rounded-xl border border-zinc-800/50 bg-zinc-900/40 overflow-hidden"
          >
            <div className="flex items-center gap-2 px-4 py-2.5 border-b border-zinc-800/40">
              <ArrowRight size={11} className="text-zinc-600" />
              <span className="text-zinc-500 font-mono text-[10px] uppercase tracking-widest">
                Execution Plan
              </span>
              <span className="ml-auto text-zinc-600 font-mono text-[9px]">
                {taskSteps.filter((s) => s.status === "completed").length}/{taskSteps.length} steps
              </span>
            </div>

            {/* Overall progress */}
            <div className="px-4 py-2 border-b border-zinc-800/30">
              <div className="flex items-center gap-2">
                <div className="flex-1 h-1 bg-zinc-800 rounded-full overflow-hidden">
                  <motion.div
                    className="h-full rounded-full bg-gradient-to-r from-emerald-500 to-indigo-500"
                    animate={{
                      width: `${(taskSteps.filter((s) => s.status === "completed").length / taskSteps.length) * 100}%`,
                    }}
                    transition={{ duration: 0.4 }}
                  />
                </div>
                <span className="text-zinc-600 font-mono text-[9px]">
                  {Math.round(
                    (taskSteps.filter((s) => s.status === "completed").length / taskSteps.length) * 100,
                  )}
                  %
                </span>
              </div>
            </div>

            {/* Step list */}
            <div className="divide-y divide-zinc-800/30">
              {taskSteps.map((step, idx) => {
                const cfg = STEP_STATUS_CONFIG[step.status];
                const isActive = idx === activeStepIndex && step.status === "running";
                return (
                  <motion.div
                    key={step.step_id}
                    className={`flex items-start gap-3 px-4 py-2.5 ${cfg.bg} transition-colors`}
                    animate={isActive ? { backgroundColor: ["rgba(6,78,59,0.1)", "rgba(6,78,59,0.2)", "rgba(6,78,59,0.1)"] } : {}}
                    transition={{ duration: 1.5, repeat: Infinity }}
                  >
                    <div className="mt-0.5 shrink-0">{cfg.icon}</div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-zinc-700 font-mono text-[9px]">
                          {String(idx + 1).padStart(2, "0")}
                        </span>
                        <span className={`font-mono text-[10px] truncate ${cfg.color}`}>
                          {step.description}
                        </span>
                      </div>
                      {step.tool_name && (
                        <div className="flex items-center gap-1 mt-0.5">
                          <ChevronRight size={8} className="text-zinc-700" />
                          <span className="text-zinc-700 font-mono text-[9px]">{step.tool_name}</span>
                        </div>
                      )}
                    </div>
                  </motion.div>
                );
              })}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
