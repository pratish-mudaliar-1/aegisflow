/**
 * AegisFlow :: components/StatusIndicator.tsx
 * ─────────────────────────────────────────────
 * Compact routing plane indicator — LOCAL (Qwen3) vs CLOUD (Claude/GPT-4o).
 */

"use client";

import { Cloud, Cpu } from "lucide-react";
import { motion } from "framer-motion";
import type { InferencePlane } from "@/lib/types";

interface StatusIndicatorProps {
  route: InferencePlane | null;
  className?: string;
}

export function StatusIndicator({ route, className = "" }: StatusIndicatorProps) {
  if (!route) {
    return (
      <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-zinc-900 border border-zinc-800/50 ${className}`}>
        <div className="w-1.5 h-1.5 rounded-full bg-zinc-700" />
        <span className="text-zinc-600 font-mono text-[9px]">NO ROUTE</span>
      </div>
    );
  }

  const isLocal = route === "LOCAL_PLANE";

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md border ${className} ${
        isLocal
          ? "bg-emerald-950/30 border-emerald-800/50"
          : "bg-indigo-950/30 border-indigo-800/50"
      }`}
    >
      {isLocal ? (
        <Cpu size={10} className="text-emerald-400" />
      ) : (
        <Cloud size={10} className="text-indigo-400" />
      )}
      <span
        className={`font-mono text-[9px] font-semibold ${
          isLocal ? "text-emerald-400" : "text-indigo-400"
        }`}
      >
        {isLocal ? "LOCAL · Qwen3" : "CLOUD · Claude"}
      </span>
      <motion.div
        className={`w-1.5 h-1.5 rounded-full ${isLocal ? "bg-emerald-500" : "bg-indigo-500"}`}
        animate={{ opacity: [1, 0.3, 1] }}
        transition={{ duration: 1.5, repeat: Infinity }}
      />
    </motion.div>
  );
}
