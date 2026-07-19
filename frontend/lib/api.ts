/**
 * AegisFlow :: lib/api.ts
 * ───────────────────────
 * Typed fetch helpers for all 4 FastAPI endpoints.
 * Base URL driven by NEXT_PUBLIC_API_URL env var.
 */

import type {
  HumanValidationDecision,
  RunWorkflowRequest,
  WorkflowStatusResponse,
} from "./types";

const BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ─── Health ───────────────────────────────────────────────────────────────────

export async function checkHealth(): Promise<{ status: string }> {
  const res = await fetch(`${BASE_URL}/api/v1/health`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Health check failed: ${res.status}`);
  return res.json();
}

// ─── Run Workflow (returns raw Response for SSE) ─────────────────────────────

export async function startWorkflow(
  payload: RunWorkflowRequest,
): Promise<Response> {
  const res = await fetch(`${BASE_URL}/api/v1/workflow/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Workflow start failed (${res.status}): ${body}`);
  }
  return res;
}

// ─── Resume HITL Checkpoint ───────────────────────────────────────────────────

export async function resumeWorkflow(
  decision: HumanValidationDecision,
): Promise<Response> {
  const res = await fetch(`${BASE_URL}/api/v1/workflow/resume`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(decision),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Resume failed (${res.status}): ${body}`);
  }
  return res;
}

// ─── Status Poll ──────────────────────────────────────────────────────────────

export async function getWorkflowStatus(
  sessionId: string,
): Promise<WorkflowStatusResponse> {
  const res = await fetch(
    `${BASE_URL}/api/v1/workflow/status/${sessionId}`,
    { cache: "no-store" },
  );
  if (!res.ok) throw new Error(`Status query failed: ${res.status}`);
  return res.json();
}
