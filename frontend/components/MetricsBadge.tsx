/**
 * AegisFlow :: components/MetricsBadge.tsx
 * ─────────────────────────────────────────
 * Token budget & confidence mini-widget row.
 */

"use client";

import { Activity, Brain, Coins, RefreshCw } from "lucide-react";
import { motion } from "framer-motion";
import type { TokenBudgetTracker } from "@/lib/types";

interface MetricsBadgeProps {
  budget: TokenBudgetTracker | null;
  className?: string;
}

interface MiniMetricProps {
  label: string;
  value: string | number;
  icon: React.ReactNode;
  color: string;
  warning?: boolean;
}

function MiniMetric({ label, value, icon, color, warning }: MiniMetricProps) {
  return (
    <div
      className={`flex items-center gap-2 px-3 py-2 rounded-lg border transition-colors ${
        warning
          ? "bg-amber-950/20 border-amber-800/40"
          : "bg-zinc-900 border-zinc-800/40"
      }`}
    >
      <span className={color}>{icon}</span>
      <div>
        <p className={`font-mono text-[9px] ${warning ? "text-amber-500" : "text-zinc-600"}`}>
          {label}
        </p>
        <p className={`font-mono text-xs font-bold ${warning ? "text-amber-300" : "text-zinc-300"}`}>
          {value}
        </p>
      </div>
    </div>
  );
}

export function MetricsBadge({ budget, className = "" }: MetricsBadgeProps) {
  if (!budget) {
    return (
      <div className={`flex items-center gap-2 ${className}`}>
        <div className="h-8 w-28 rounded-lg bg-zinc-900 border border-zinc-800/40 animate-pulse" />
        <div className="h-8 w-28 rounded-lg bg-zinc-900 border border-zinc-800/40 animate-pulse" />
        <div className="h-8 w-28 rounded-lg bg-zinc-900 border border-zinc-800/40 animate-pulse" />
      </div>
    );
  }

  const totalTokens = budget.total_input_tokens + budget.total_output_tokens;
  const budgetPct = Math.round((totalTokens / budget.session_token_ceiling) * 100);
  const budgetWarning = budgetPct > 75;
  const confidenceWarning = budget.confidence_score < budget.confidence_threshold;
  const retryWarning = budget.recovery_attempt_count >= budget.max_recovery_attempts - 1;

  return (
    <div className={`flex items-center gap-2 flex-wrap ${className}`}>
      {/* Token budget */}
      <div className={`flex items-center gap-2 px-3 py-2 rounded-lg border ${budgetWarning ? "bg-amber-950/20 border-amber-800/40" : "bg-zinc-900 border-zinc-800/40"}`}>
        <Coins size={12} className={budgetWarning ? "text-amber-400" : "text-zinc-500"} />
        <div>
          <p className={`font-mono text-[9px] ${budgetWarning ? "text-amber-600" : "text-zinc-600"}`}>
            Token Budget
          </p>
          <div className="flex items-center gap-1.5">
            <p className={`font-mono text-xs font-bold ${budgetWarning ? "text-amber-300" : "text-zinc-300"}`}>
              {totalTokens.toLocaleString()}
            </p>
            <span className="text-zinc-700 font-mono text-[9px]">/ {budget.session_token_ceiling.toLocaleString()}</span>
          </div>
        </div>
        {/* Mini progress */}
        <div className="w-12 h-1 rounded-full bg-zinc-800 overflow-hidden">
          <motion.div
            className={`h-full rounded-full ${budgetWarning ? "bg-amber-500" : "bg-emerald-500"}`}
            animate={{ width: `${budgetPct}%` }}
            transition={{ duration: 0.4 }}
          />
        </div>
      </div>

      {/* Confidence score */}
      <MiniMetric
        label="Confidence θ"
        value={budget.confidence_score.toFixed(3)}
        icon={<Brain size={12} />}
        color={confidenceWarning ? "text-amber-400" : "text-indigo-400"}
        warning={confidenceWarning}
      />

      {/* Recovery attempts */}
      <MiniMetric
        label="Recovery n"
        value={`${budget.recovery_attempt_count} / ${budget.max_recovery_attempts}`}
        icon={<RefreshCw size={12} />}
        color={retryWarning ? "text-amber-400" : "text-zinc-500"}
        warning={retryWarning}
      />

      {/* I/O token split */}
      <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-zinc-900 border border-zinc-800/40">
        <Activity size={12} className="text-zinc-500" />
        <div>
          <p className="font-mono text-[9px] text-zinc-600">I → O Tokens</p>
          <p className="font-mono text-xs text-zinc-300">
            <span className="text-sky-400">{budget.total_input_tokens.toLocaleString()}</span>
            <span className="text-zinc-600 mx-0.5">→</span>
            <span className="text-violet-400">{budget.total_output_tokens.toLocaleString()}</span>
          </p>
        </div>
      </div>
    </div>
  );
}
