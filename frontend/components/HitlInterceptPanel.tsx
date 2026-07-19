/**
 * AegisFlow :: components/HitlInterceptPanel.tsx
 * ────────────────────────────────────────────────
 * High-risk transaction validation control tray.
 * Renders when the workflow pauses at a human_validation checkpoint.
 * Provides Approve / Modify / Terminate action controls with full
 * JSON argument editing and validation.
 */

"use client";

import {
  AlertOctagon,
  CheckCircle2,
  Edit3,
  Fingerprint,
  Loader2,
  Shield,
  ShieldAlert,
  Siren,
  XCircle,
} from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import React, { useCallback, useEffect, useState } from "react";

interface HitlInterceptPanelProps {
  isVisible: boolean;
  proposedTool: string;
  toolArguments: Record<string, unknown>;
  onApprove: () => Promise<void>;
  onModify: (editedArgs: Record<string, unknown>, feedback: string) => Promise<void>;
  onTerminate: () => void;
}

type PanelMode = "review" | "edit" | "confirm_terminate";
type ActionState = "idle" | "loading" | "success" | "error";

export function HitlInterceptPanel({
  isVisible,
  proposedTool,
  toolArguments,
  onApprove,
  onModify,
  onTerminate,
}: HitlInterceptPanelProps) {
  const [mode, setMode] = useState<PanelMode>("review");
  const [editedJson, setEditedJson] = useState("");
  const [jsonError, setJsonError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState("");
  const [actionState, setActionState] = useState<ActionState>("idle");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Reset when panel becomes visible
  useEffect(() => {
    if (isVisible) {
      setMode("review");
      setEditedJson(JSON.stringify(toolArguments, null, 2));
      setJsonError(null);
      setFeedback("");
      setActionState("idle");
      setErrorMsg(null);
    }
  }, [isVisible, toolArguments]);

  const validateJson = useCallback((str: string): Record<string, unknown> | null => {
    try {
      const parsed = JSON.parse(str);
      if (typeof parsed !== "object" || Array.isArray(parsed) || parsed === null) {
        setJsonError("Root value must be a JSON object {}");
        return null;
      }
      setJsonError(null);
      return parsed as Record<string, unknown>;
    } catch (e) {
      setJsonError(`JSON parse error: ${(e as Error).message}`);
      return null;
    }
  }, []);

  const handleApprove = async () => {
    setActionState("loading");
    try {
      await onApprove();
      setActionState("success");
    } catch (e) {
      setActionState("error");
      setErrorMsg(e instanceof Error ? e.message : "Approval failed");
    }
  };

  const handleModifySubmit = async () => {
    const parsed = validateJson(editedJson);
    if (!parsed) return;
    setActionState("loading");
    try {
      await onModify(parsed, feedback);
      setActionState("success");
    } catch (e) {
      setActionState("error");
      setErrorMsg(e instanceof Error ? e.message : "Modification failed");
    }
  };

  const handleTerminateConfirm = () => {
    onTerminate();
  };

  if (!isVisible) return null;

  return (
    <AnimatePresence>
      <motion.div
        key="hitl-panel"
        initial={{ opacity: 0, scale: 0.97, y: 8 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.97, y: 8 }}
        transition={{ duration: 0.2, ease: "easeOut" }}
        className="relative rounded-xl overflow-hidden"
        style={{
          background: "linear-gradient(135deg, rgba(120,53,15,0.12) 0%, rgba(17,24,39,0.97) 50%, rgba(17,24,39,0.97) 100%)",
          boxShadow: "0 0 0 1px rgba(251,191,36,0.25), 0 0 40px rgba(251,191,36,0.08), 0 20px 60px rgba(0,0,0,0.6)",
        }}
      >
        {/* ── Animated amber border glow ── */}
        <div
          className="absolute inset-0 rounded-xl pointer-events-none"
          style={{
            background: "transparent",
            boxShadow: "inset 0 0 0 1px rgba(251,191,36,0.3)",
          }}
        />
        <motion.div
          className="absolute inset-0 rounded-xl pointer-events-none"
          animate={{ opacity: [0.3, 0.7, 0.3] }}
          transition={{ duration: 2.5, repeat: Infinity, ease: "easeInOut" }}
          style={{ boxShadow: "inset 0 0 30px rgba(251,191,36,0.06)" }}
        />

        {/* ── Intercept header ── */}
        <div className="relative px-5 py-4 border-b border-amber-800/30 bg-amber-950/10">
          <div className="flex items-center gap-3">
            <motion.div
              animate={{ rotate: [0, -4, 4, 0] }}
              transition={{ duration: 0.5, repeat: Infinity, repeatDelay: 2 }}
            >
              <ShieldAlert size={18} className="text-amber-400" />
            </motion.div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-amber-300 font-semibold text-sm tracking-tight">
                  HUMAN VALIDATION REQUIRED
                </span>
                <motion.div
                  animate={{ opacity: [1, 0.3, 1] }}
                  transition={{ duration: 1.2, repeat: Infinity }}
                  className="w-1.5 h-1.5 rounded-full bg-amber-500"
                />
              </div>
              <p className="text-zinc-500 text-[10px] font-mono mt-0.5">
                Execution paused — operator authorization required before proceeding
              </p>
            </div>
            <div className="ml-auto">
              <div className="flex items-center gap-1 px-2 py-1 rounded bg-amber-900/20 border border-amber-800/30">
                <Fingerprint size={10} className="text-amber-600" />
                <span className="text-amber-700 font-mono text-[9px]">HITL GATE ACTIVE</span>
              </div>
            </div>
          </div>
        </div>

        {/* ── Proposed tool identity ── */}
        <div className="px-5 py-3 border-b border-zinc-800/50 bg-black/10">
          <div className="flex items-center gap-2 mb-1.5">
            <Shield size={11} className="text-zinc-500" />
            <span className="text-zinc-500 font-mono text-[10px] uppercase tracking-widest">
              Proposed Tool
            </span>
          </div>
          <div className="flex items-center gap-2.5 p-2.5 rounded-lg bg-zinc-900 border border-zinc-700/40">
            <Siren size={14} className="text-amber-400 shrink-0" />
            <span className="font-mono text-amber-300 text-sm font-bold tracking-tight">
              {proposedTool}
            </span>
            <div className="ml-auto px-2 py-0.5 rounded text-[9px] font-mono bg-rose-900/30 text-rose-400 border border-rose-800/30">
              MUTATING
            </div>
          </div>
        </div>

        {/* ── Tab navigation ── */}
        <div className="flex items-center gap-0 border-b border-zinc-800/50 bg-zinc-900/30">
          {([
            { id: "review", label: "Review Arguments" },
            { id: "edit", label: "Modify Inputs" },
            { id: "confirm_terminate", label: "Terminate" },
          ] as const).map((tab) => (
            <button
              key={tab.id}
              onClick={() => {
                setMode(tab.id);
                setActionState("idle");
                setErrorMsg(null);
              }}
              className={`px-4 py-2.5 text-[10px] font-mono font-medium transition-all border-b-2 ${
                mode === tab.id
                  ? tab.id === "confirm_terminate"
                    ? "border-rose-500 text-rose-400 bg-rose-950/10"
                    : "border-amber-500 text-amber-300 bg-amber-950/10"
                  : "border-transparent text-zinc-600 hover:text-zinc-400 hover:bg-zinc-800/30"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* ── Content area ── */}
        <div className="p-5">
          <AnimatePresence mode="wait">
            {/* Review mode */}
            {mode === "review" && (
              <motion.div
                key="review"
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                transition={{ duration: 0.15 }}
              >
                <div className="mb-3 flex items-center gap-2">
                  <AlertOctagon size={11} className="text-zinc-500" />
                  <span className="text-zinc-500 font-mono text-[10px] uppercase tracking-widest">
                    Tool Arguments (read-only)
                  </span>
                </div>
                <div className="relative rounded-lg bg-zinc-950 border border-zinc-800/60 overflow-hidden">
                  {/* Syntax highlight header */}
                  <div className="flex items-center gap-1.5 px-3 py-1.5 bg-zinc-900 border-b border-zinc-800/50">
                    <div className="w-2 h-2 rounded-full bg-rose-500/60" />
                    <div className="w-2 h-2 rounded-full bg-amber-500/60" />
                    <div className="w-2 h-2 rounded-full bg-emerald-500/60" />
                    <span className="ml-2 text-zinc-600 font-mono text-[9px]">tool_arguments.json</span>
                  </div>
                  <pre className="px-4 py-3 font-mono text-[11px] text-emerald-300 overflow-auto max-h-[180px] scrollbar-thin scrollbar-track-zinc-950 scrollbar-thumb-zinc-800">
                    {JSON.stringify(toolArguments, null, 2)}
                  </pre>
                </div>

                {/* Approve action */}
                <div className="mt-4">
                  <ActionButton
                    onClick={handleApprove}
                    state={actionState}
                    variant="approve"
                    label="Approve Call"
                    icon={<CheckCircle2 size={14} />}
                  />
                  {errorMsg && (
                    <p className="mt-2 text-rose-400 font-mono text-[10px]">{errorMsg}</p>
                  )}
                </div>
              </motion.div>
            )}

            {/* Edit mode */}
            {mode === "edit" && (
              <motion.div
                key="edit"
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                transition={{ duration: 0.15 }}
              >
                <div className="mb-2 flex items-center gap-2">
                  <Edit3 size={11} className="text-indigo-400" />
                  <span className="text-zinc-500 font-mono text-[10px] uppercase tracking-widest">
                    Edit Arguments JSON
                  </span>
                </div>

                {/* Editable JSON textarea */}
                <div className={`relative rounded-lg border overflow-hidden transition-colors ${jsonError ? "border-rose-700/50" : "border-indigo-700/40 focus-within:border-indigo-500/70"}`}>
                  <div className="flex items-center gap-1.5 px-3 py-1.5 bg-zinc-900 border-b border-zinc-800/50">
                    <div className="w-2 h-2 rounded-full bg-rose-500/60" />
                    <div className="w-2 h-2 rounded-full bg-amber-500/60" />
                    <div className="w-2 h-2 rounded-full bg-emerald-500/60" />
                    <span className="ml-2 text-zinc-600 font-mono text-[9px]">tool_arguments.json — editable</span>
                    {!jsonError && editedJson && (
                      <span className="ml-auto text-emerald-600 font-mono text-[9px]">✓ valid JSON</span>
                    )}
                    {jsonError && (
                      <span className="ml-auto text-rose-500 font-mono text-[9px]">✗ invalid</span>
                    )}
                  </div>
                  <textarea
                    value={editedJson}
                    onChange={(e) => {
                      setEditedJson(e.target.value);
                      validateJson(e.target.value);
                    }}
                    className="w-full bg-zinc-950 text-indigo-300 font-mono text-[11px] px-4 py-3 outline-none resize-none h-[160px] scrollbar-thin scrollbar-track-zinc-950 scrollbar-thumb-zinc-800"
                    spellCheck={false}
                    autoComplete="off"
                  />
                </div>
                {jsonError && (
                  <p className="mt-1 text-rose-400 font-mono text-[10px] flex items-center gap-1">
                    <XCircle size={9} /> {jsonError}
                  </p>
                )}

                {/* Feedback / audit note */}
                <div className="mt-3">
                  <label className="text-zinc-600 font-mono text-[10px] uppercase tracking-widest block mb-1">
                    Audit Note (optional)
                  </label>
                  <textarea
                    value={feedback}
                    onChange={(e) => setFeedback(e.target.value)}
                    placeholder="Reason for modification…"
                    className="w-full bg-zinc-900 border border-zinc-800/50 focus:border-indigo-700/50 rounded-lg text-zinc-300 font-mono text-[11px] px-3 py-2 outline-none resize-none h-16 placeholder-zinc-700 transition-colors"
                  />
                </div>

                <div className="mt-4">
                  <ActionButton
                    onClick={handleModifySubmit}
                    state={actionState}
                    variant="modify"
                    label="Submit Modified Inputs"
                    icon={<Edit3 size={14} />}
                    disabled={!!jsonError}
                  />
                  {errorMsg && (
                    <p className="mt-2 text-rose-400 font-mono text-[10px]">{errorMsg}</p>
                  )}
                </div>
              </motion.div>
            )}

            {/* Terminate confirm mode */}
            {mode === "confirm_terminate" && (
              <motion.div
                key="terminate"
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                transition={{ duration: 0.15 }}
              >
                <div className="rounded-lg bg-rose-950/20 border border-rose-800/40 p-4 mb-4">
                  <div className="flex items-start gap-3">
                    <XCircle size={16} className="text-rose-400 mt-0.5 shrink-0" />
                    <div>
                      <p className="text-rose-300 font-semibold text-sm mb-1">
                        Terminate Execution Thread?
                      </p>
                      <p className="text-rose-700/80 font-mono text-[10px] leading-relaxed">
                        This will send a REJECT decision to the workflow engine, halt the
                        current session, and write a FATAL_ERROR entry to the audit trail.
                        This action cannot be undone.
                      </p>
                    </div>
                  </div>
                </div>
                <p className="text-zinc-600 font-mono text-[10px] mb-4">
                  Tool <span className="text-rose-400">{proposedTool}</span> will not be
                  executed. All pending steps in this session will be cancelled.
                </p>
                <ActionButton
                  onClick={handleTerminateConfirm}
                  state="idle"
                  variant="terminate"
                  label="Confirm — Terminate Thread"
                  icon={<XCircle size={14} />}
                />
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}

// ─── Action Button sub-component ─────────────────────────────────────────────

interface ActionButtonProps {
  onClick: () => void;
  state: ActionState;
  variant: "approve" | "modify" | "terminate";
  label: string;
  icon: React.ReactNode;
  disabled?: boolean;
}

const BUTTON_STYLES = {
  approve: {
    base: "bg-emerald-600/20 hover:bg-emerald-600/30 border-emerald-600/50 hover:border-emerald-500/80 text-emerald-300 hover:text-emerald-200",
    glow: "shadow-[0_0_16px_rgba(52,211,153,0.15)] hover:shadow-[0_0_24px_rgba(52,211,153,0.25)]",
  },
  modify: {
    base: "bg-indigo-600/20 hover:bg-indigo-600/30 border-indigo-600/50 hover:border-indigo-500/80 text-indigo-300 hover:text-indigo-200",
    glow: "shadow-[0_0_16px_rgba(129,140,248,0.15)] hover:shadow-[0_0_24px_rgba(129,140,248,0.25)]",
  },
  terminate: {
    base: "bg-rose-600/20 hover:bg-rose-600/30 border-rose-600/50 hover:border-rose-500/80 text-rose-300 hover:text-rose-200",
    glow: "shadow-[0_0_16px_rgba(244,63,94,0.15)] hover:shadow-[0_0_24px_rgba(244,63,94,0.25)]",
  },
};

function ActionButton({ onClick, state, variant, label, icon, disabled }: ActionButtonProps) {
  const s = BUTTON_STYLES[variant];
  const isLoading = state === "loading";
  const isSuccess = state === "success";

  return (
    <motion.button
      whileHover={{ scale: disabled || isLoading ? 1 : 1.01 }}
      whileTap={{ scale: disabled || isLoading ? 1 : 0.98 }}
      onClick={onClick}
      disabled={disabled || isLoading || isSuccess}
      className={`w-full flex items-center justify-center gap-2.5 px-4 py-3 rounded-lg border font-mono font-semibold text-sm
        transition-all duration-200 ${s.base} ${s.glow}
        disabled:opacity-50 disabled:cursor-not-allowed disabled:scale-100`}
    >
      {isLoading ? (
        <Loader2 size={14} className="animate-spin" />
      ) : isSuccess ? (
        <CheckCircle2 size={14} />
      ) : (
        icon
      )}
      {isLoading ? "Processing…" : isSuccess ? "Done" : label}
    </motion.button>
  );
}
