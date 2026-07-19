/**
 * AegisFlow :: components/SidebarNav.tsx
 * ─────────────────────────────────────
 * Left application mode switcher with icon navigation tabs.
 */

"use client";

import {
  BrainCog,
  CalendarClock,
  ChevronRight,
  KeyRound,
  LayoutDashboard,
  ListTodo,
  Settings,
  Zap,
} from "lucide-react";
import { motion } from "framer-motion";
import type { AppMode } from "@/lib/types";

interface NavItem {
  id: AppMode;
  label: string;
  sublabel: string;
  icon: React.ReactNode;
  accentColor: string;
  glowColor: string;
}

const NAV_ITEMS: NavItem[] = [
  {
    id: "tasks",
    label: "Tasks",
    sublabel: "Active workflows",
    icon: <ListTodo size={16} />,
    accentColor: "text-emerald-400",
    glowColor: "rgba(52,211,153,0.15)",
  },
  {
    id: "scheduler",
    label: "Scheduler",
    sublabel: "Cron & recurring",
    icon: <CalendarClock size={16} />,
    accentColor: "text-indigo-400",
    glowColor: "rgba(129,140,248,0.15)",
  },
  {
    id: "cryptonotes",
    label: "Crypto Notes",
    sublabel: "Encrypted vault",
    icon: <KeyRound size={16} />,
    accentColor: "text-amber-400",
    glowColor: "rgba(251,191,36,0.15)",
  },
];

interface SidebarNavProps {
  activeMode: AppMode;
  onModeChange: (mode: AppMode) => void;
}

export function SidebarNav({ activeMode, onModeChange }: SidebarNavProps) {
  return (
    <aside className="flex flex-col h-full bg-zinc-950 border-r border-zinc-800/60">
      {/* ── Logo / Brand ── */}
      <div className="px-4 py-5 border-b border-zinc-800/60">
        <div className="flex items-center gap-2.5">
          <div className="relative w-7 h-7 rounded-lg bg-gradient-to-br from-emerald-500 to-indigo-600 flex items-center justify-center shadow-lg shadow-emerald-900/30">
            <BrainCog size={14} className="text-white" />
            <motion.div
              className="absolute inset-0 rounded-lg"
              animate={{ boxShadow: ["0 0 0px rgba(52,211,153,0)", "0 0 12px rgba(52,211,153,0.5)", "0 0 0px rgba(52,211,153,0)"] }}
              transition={{ duration: 2.5, repeat: Infinity }}
            />
          </div>
          <div>
            <div className="flex items-baseline gap-1">
              <span className="text-white font-bold text-sm tracking-tight">AegisFlow</span>
              <span className="text-zinc-600 text-[9px] font-mono">v1.0</span>
            </div>
            <p className="text-zinc-600 text-[9px] font-mono leading-none">LangGraph Orchestrator</p>
          </div>
        </div>
      </div>

      {/* ── Status pulse ── */}
      <div className="px-4 py-2.5 border-b border-zinc-800/40">
        <div className="flex items-center gap-2 px-2.5 py-1.5 rounded-md bg-zinc-900 border border-zinc-800/40">
          <motion.div
            className="w-1.5 h-1.5 rounded-full bg-emerald-500"
            animate={{ opacity: [1, 0.3, 1] }}
            transition={{ duration: 1.8, repeat: Infinity }}
          />
          <span className="text-zinc-500 font-mono text-[9px]">Engine online</span>
          <div className="ml-auto">
            <Zap size={9} className="text-zinc-700" />
          </div>
        </div>
      </div>

      {/* ── Navigation ── */}
      <nav className="flex-1 px-2 py-3 space-y-1 overflow-y-auto">
        <p className="px-2 mb-2 text-zinc-700 font-mono text-[9px] uppercase tracking-widest">
          Workspace
        </p>
        {NAV_ITEMS.map((item) => {
          const isActive = activeMode === item.id;
          return (
            <motion.button
              key={item.id}
              onClick={() => onModeChange(item.id)}
              whileHover={{ x: 2 }}
              whileTap={{ scale: 0.97 }}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left transition-all duration-150 group ${
                isActive
                  ? "bg-zinc-800/70 border border-zinc-700/50"
                  : "hover:bg-zinc-900 border border-transparent"
              }`}
              style={isActive ? { boxShadow: `0 0 16px ${item.glowColor}` } : {}}
            >
              {/* Icon */}
              <span
                className={`shrink-0 transition-colors ${
                  isActive ? item.accentColor : "text-zinc-600 group-hover:text-zinc-400"
                }`}
              >
                {item.icon}
              </span>

              {/* Label */}
              <div className="flex-1 min-w-0">
                <p
                  className={`text-xs font-semibold truncate transition-colors ${
                    isActive ? "text-zinc-100" : "text-zinc-500 group-hover:text-zinc-300"
                  }`}
                >
                  {item.label}
                </p>
                <p className="text-zinc-700 text-[9px] font-mono truncate group-hover:text-zinc-600">
                  {item.sublabel}
                </p>
              </div>

              {/* Active chevron */}
              {isActive && (
                <ChevronRight size={12} className={item.accentColor} />
              )}
            </motion.button>
          );
        })}

        <div className="mt-4 pt-3 border-t border-zinc-800/40">
          <p className="px-2 mb-2 text-zinc-700 font-mono text-[9px] uppercase tracking-widest">
            System
          </p>
          <button className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left hover:bg-zinc-900 group transition-colors">
            <LayoutDashboard size={16} className="text-zinc-600 group-hover:text-zinc-400 shrink-0" />
            <span className="text-zinc-600 group-hover:text-zinc-400 text-xs font-medium">Overview</span>
          </button>
          <button className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left hover:bg-zinc-900 group transition-colors">
            <Settings size={16} className="text-zinc-600 group-hover:text-zinc-400 shrink-0" />
            <span className="text-zinc-600 group-hover:text-zinc-400 text-xs font-medium">Settings</span>
          </button>
        </div>
      </nav>

      {/* ── Footer ── */}
      <div className="px-4 py-3 border-t border-zinc-800/40">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-full bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center">
            <span className="text-white font-bold text-[9px]">OP</span>
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-zinc-300 text-[10px] font-semibold truncate">Operator</p>
            <p className="text-zinc-700 text-[9px] font-mono truncate">admin@aegisflow</p>
          </div>
        </div>
      </div>
    </aside>
  );
}
