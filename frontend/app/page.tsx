/**
 * AegisFlow :: app/page.tsx
 * ─────────────────────────
 * Main 3-column operational cockpit workspace.
 *
 * Layout: Left Sidebar (240px) | Center Workspace (1fr) | Right Observability (380px)
 *
 * Center: Natural language command input + HITL intercept panel
 * Right:  StateGraphVisualizer (top 55%) + TelemetryFeed (bottom 45%)
 */

"use client";

import {
  BookLock,
  BrainCog,
  Clock,
  FileCode2,
  Globe2,
  Shield,
} from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";

import { HitlInterceptPanel } from "@/components/HitlInterceptPanel";
import { MetricsBadge } from "@/components/MetricsBadge";
import { SidebarNav } from "@/components/SidebarNav";
import { StateGraphVisualizer } from "@/components/StateGraphVisualizer";
import { StatusIndicator } from "@/components/StatusIndicator";
import { TaskCommandInput } from "@/components/TaskCommandInput";
import { TelemetryFeed } from "@/components/TelemetryFeed";
import { useWorkflowSession } from "@/hooks/useWorkflowSession";
import type { AppMode } from "@/lib/types";

// ─── Scheduler placeholder panel ─────────────────────────────────────────────

function SchedulerPanel() {
  const tasks = [
    { id: 1, name: "Daily Audit Digest", cron: "0 9 * * 1-5", status: "active", next: "Mon 09:00" },
    { id: 2, name: "DB Health Check", cron: "*/15 * * * *", status: "active", next: "in 12 min" },
    { id: 3, name: "Weekly Report Gen", cron: "0 18 * * 5", status: "paused", next: "Fri 18:00" },
    { id: 4, name: "Token Budget Reset", cron: "0 0 1 * *", status: "active", next: "Aug 1 00:00" },
  ];

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <Clock size={14} className="text-indigo-400" />
        <h2 className="text-zinc-200 font-semibold text-sm">Scheduled Tasks</h2>
        <div className="ml-auto px-2 py-0.5 rounded bg-indigo-900/30 border border-indigo-800/30 text-indigo-400 font-mono text-[9px]">
          {tasks.filter((t) => t.status === "active").length} ACTIVE
        </div>
      </div>

      <div className="space-y-2">
        {tasks.map((task) => (
          <div
            key={task.id}
            className="flex items-center gap-3 p-3 rounded-lg bg-zinc-900 border border-zinc-800/50 hover:border-zinc-700/50 transition-colors"
          >
            <div className={`w-2 h-2 rounded-full shrink-0 ${task.status === "active" ? "bg-emerald-500" : "bg-zinc-600"}`}>
              {task.status === "active" && (
                <div className="w-2 h-2 rounded-full bg-emerald-500 animate-ping opacity-75" />
              )}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-zinc-300 text-xs font-semibold truncate">{task.name}</p>
              <p className="text-zinc-600 font-mono text-[9px]">{task.cron}</p>
            </div>
            <div className="text-right">
              <p className="text-zinc-500 font-mono text-[9px]">next run</p>
              <p className="text-indigo-400 font-mono text-[10px]">{task.next}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── CryptoNotes placeholder panel ───────────────────────────────────────────

function CryptoNotesPanel() {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <BookLock size={14} className="text-amber-400" />
        <h2 className="text-zinc-200 font-semibold text-sm">Cryptographic Notes</h2>
        <div className="ml-auto px-2 py-0.5 rounded bg-amber-900/20 border border-amber-800/30 text-amber-500 font-mono text-[9px]">
          AES-256 VAULT
        </div>
      </div>

      <div className="p-4 rounded-xl bg-amber-950/10 border border-amber-800/25 text-center">
        <Shield size={28} className="text-amber-700 mx-auto mb-2" />
        <p className="text-amber-400/70 font-semibold text-sm mb-1">End-to-End Encrypted</p>
        <p className="text-zinc-600 font-mono text-[10px]">
          All notes are encrypted at rest using AES-256-GCM.
          <br />
          Key derivation via Argon2id · Zero-knowledge storage.
        </p>
      </div>

      <div className="space-y-2">
        {["API Key Inventory", "Operator Playbook", "Incident Runbooks", "Governance Policies"].map(
          (note, i) => (
            <div
              key={i}
              className="flex items-center gap-3 p-3 rounded-lg bg-zinc-900 border border-zinc-800/40 hover:border-amber-800/30 transition-colors cursor-pointer"
            >
              <FileCode2 size={13} className="text-amber-600 shrink-0" />
              <span className="text-zinc-400 text-xs font-medium">{note}</span>
              <div className="ml-auto text-zinc-700 font-mono text-[9px]">🔒 locked</div>
            </div>
          ),
        )}
      </div>
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function AegisFlowWorkspace() {
  const [appMode, setAppMode] = useState<AppMode>("tasks");

  const {
    sessionId,
    isRunning,
    activeNode,
    state,
    events,
    hitlPending,
    hitlData,
    error,
    run,
    approve,
    modify,
    terminate,
    reset,
  } = useWorkflowSession();

  const tokenBudget = state?.token_budget ?? null;
  const taskSteps = state?.task_steps ?? [];
  const activeStepIndex = state?.active_step_index ?? 0;
  const inferenceRoute = state?.inference_route ?? null;

  const handleRun = (input: string, budget?: number, toolOverride?: string) => {
    run(input, {
      token_budget_override: budget,
      proposed_tool_override: toolOverride,
    });
  };

  return (
    <div className="h-screen w-screen flex overflow-hidden bg-zinc-950 text-zinc-100">
      {/* ══════════════════ LEFT SIDEBAR ══════════════════ */}
      <div className="w-[220px] shrink-0 h-full border-r border-zinc-800/60">
        <SidebarNav activeMode={appMode} onModeChange={setAppMode} />
      </div>

      {/* ══════════════════ CENTER WORKSPACE ══════════════════ */}
      <main className="flex-1 flex flex-col h-full overflow-hidden min-w-0">
        {/* ── Top bar ── */}
        <header className="shrink-0 flex items-center gap-3 px-5 py-3 border-b border-zinc-800/60 bg-zinc-950/80 backdrop-blur-md">
          {/* Page title */}
          <div className="flex items-center gap-2">
            <BrainCog size={15} className="text-emerald-400" />
            <span className="text-zinc-200 font-semibold text-sm">
              {appMode === "tasks"
                ? "Workflow Command Center"
                : appMode === "scheduler"
                  ? "Task Scheduler"
                  : "Cryptographic Notes Suite"}
            </span>
          </div>

          {/* Divider */}
          <div className="w-px h-4 bg-zinc-800" />

          {/* Inference route badge */}
          <StatusIndicator route={inferenceRoute} />

          {/* Runtime info */}
          {sessionId && (
            <div className="flex items-center gap-1.5 px-2 py-1 rounded bg-zinc-900 border border-zinc-800/40">
              <Globe2 size={9} className="text-zinc-600" />
              <span className="text-zinc-600 font-mono text-[9px]">
                {sessionId.slice(0, 8)}…
              </span>
            </div>
          )}

          <div className="flex-1" />

          {/* Metrics row */}
          {tokenBudget && appMode === "tasks" && (
            <MetricsBadge budget={tokenBudget} />
          )}
        </header>

        {/* ── Scrollable content ── */}
        <div className="flex-1 overflow-y-auto px-5 py-5 space-y-5">
          <AnimatePresence mode="wait">
            {appMode === "tasks" ? (
              <motion.div
                key="tasks"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.2 }}
                className="space-y-5"
              >
                {/* Command Input Engine */}
                <TaskCommandInput
                  onSubmit={handleRun}
                  isRunning={isRunning}
                  onReset={reset}
                  taskSteps={taskSteps}
                  activeStepIndex={activeStepIndex}
                  tokenBudget={tokenBudget}
                  sessionId={sessionId}
                  error={error}
                />

                {/* HITL Intercept Panel */}
                <AnimatePresence>
                  {hitlPending && hitlData && (
                    <HitlInterceptPanel
                      isVisible={hitlPending}
                      proposedTool={hitlData.proposed_tool}
                      toolArguments={hitlData.tool_arguments}
                      onApprove={approve}
                      onModify={modify}
                      onTerminate={terminate}
                    />
                  )}
                </AnimatePresence>
              </motion.div>
            ) : appMode === "scheduler" ? (
              <motion.div
                key="scheduler"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.2 }}
              >
                <SchedulerPanel />
              </motion.div>
            ) : (
              <motion.div
                key="cryptonotes"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.2 }}
              >
                <CryptoNotesPanel />
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </main>

      {/* ══════════════════ RIGHT OBSERVABILITY PLANE ══════════════════ */}
      <aside className="w-[380px] shrink-0 flex flex-col h-full border-l border-zinc-800/60 bg-zinc-950">
        {/* ── Right panel header ── */}
        <div className="shrink-0 flex items-center gap-2 px-4 py-3 border-b border-zinc-800/60">
          <Shield size={12} className="text-zinc-500" />
          <span className="text-zinc-500 font-mono text-[10px] uppercase tracking-widest">
            Observability Plane
          </span>
        </div>

        {/* ── State Graph Visualizer (top 55%) ── */}
        <div className="shrink-0 border-b border-zinc-800/50">
          <div className="flex items-center gap-2 px-4 py-2 border-b border-zinc-800/30 bg-zinc-900/30">
            <div className="w-1.5 h-1.5 rounded-full bg-indigo-500" />
            <span className="text-zinc-600 font-mono text-[9px] uppercase tracking-widest">
              State Graph
            </span>
            {activeNode && (
              <span className="ml-auto text-emerald-500 font-mono text-[9px]">
                active: {activeNode}
              </span>
            )}
          </div>
          <div className="px-3 py-3" style={{ height: "220px" }}>
            <StateGraphVisualizer
              activeNode={activeNode}
              className="w-full h-full"
            />
          </div>
        </div>

        {/* ── Telemetry Feed (bottom 45%) ── */}
        <div className="flex-1 flex flex-col overflow-hidden">
          <TelemetryFeed events={events} className="flex-1 rounded-none border-0" />
        </div>
      </aside>
    </div>
  );
}
