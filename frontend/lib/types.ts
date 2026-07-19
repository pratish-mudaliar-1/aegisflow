/**
 * AegisFlow :: lib/types.ts
 * ─────────────────────────
 * TypeScript mirrors of schemas.py Pydantic models.
 * Keep in sync with the Python enums and field names.
 */

// ─── Enums ──────────────────────────────────────────────────────────────────

export type ValidationStatus =
  | "PENDING"
  | "APPROVE"
  | "EDIT"
  | "REJECT"
  | "FAILED"
  | "COMPLETED";

export type InferencePlane = "LOCAL_PLANE" | "CLOUD_PLANE";

export type MutatingTool =
  | "send_enterprise_email"
  | "execute_db_mutation"
  | "authorize_budget"
  | "write_filesystem"
  | "schedule_calendar_invite"
  | "revoke_access_token"
  | "publish_external_webhook";

// ─── Graph Node Names ────────────────────────────────────────────────────────

export type GraphNodeName =
  | "parse_input"
  | "route_task"
  | "human_validation"
  | "execute_tool"
  | "__start__"
  | "__end__";

// ─── Token Budget ────────────────────────────────────────────────────────────

export interface TokenBudgetTracker {
  session_token_ceiling: number;
  total_input_tokens: number;
  total_output_tokens: number;
  recovery_attempt_count: number;
  max_recovery_attempts: number;
  confidence_score: number;
  confidence_threshold: number;
}

// ─── Audit Event ─────────────────────────────────────────────────────────────

export interface AuditEvent {
  event_type: string;
  node_name: string;
  timestamp_utc: string;
  payload: Record<string, unknown>;
  fingerprint: string;
}

// ─── Agent Task State ────────────────────────────────────────────────────────

export interface TaskStep {
  step_id: number;
  description: string;
  status: "pending" | "running" | "completed" | "failed";
  tool_name?: string;
}

export interface AgentTaskState {
  session_id: string;
  original_input: string;
  task_steps: TaskStep[];
  active_step_index: number;
  proposed_tool: string | null;
  tool_arguments: Record<string, unknown>;
  validation_status: ValidationStatus;
  user_feedback: string;
  execution_errors: string[];
  token_budget: TokenBudgetTracker;
  inference_route: InferencePlane | null;
  audit_trail: AuditEvent[];
}

// ─── API Request / Response ───────────────────────────────────────────────────

export interface RunWorkflowRequest {
  user_input: string;
  proposed_tool_override?: string;
  token_budget_override?: number;
}

export interface HumanValidationDecision {
  session_id: string;
  decision: "APPROVE" | "EDIT" | "REJECT";
  feedback_message?: string;
  edited_arguments?: Record<string, unknown>;
}

export interface WorkflowStatusResponse {
  session_id: string;
  validation_status: ValidationStatus;
  active_step_index: number;
  total_steps: number;
  inference_route: InferencePlane | null;
  error_count: number;
  audit_event_count: number;
  token_usage: Record<string, unknown>;
}

// ─── SSE Event Types ──────────────────────────────────────────────────────────

export type SSEEventType =
  | "THREAD_INITIALIZED"
  | "NODE_TRANSITION"
  | "HUMAN_INTERRUPT_REQUIRED"
  | "CRITICAL_FAILURE"
  | "WORKFLOW_COMPLETE";

export interface SSEEvent {
  event: SSEEventType;
  data: {
    session_id?: string;
    node_name?: GraphNodeName;
    state?: Partial<AgentTaskState>;
    proposed_tool?: string;
    tool_arguments?: Record<string, unknown>;
    error?: string;
    timestamp?: string;
    message?: string;
    token_budget?: TokenBudgetTracker;
    inference_route?: InferencePlane;
    [key: string]: unknown;
  };
  timestamp: string;
  id?: string;
}

// ─── UI State ─────────────────────────────────────────────────────────────────

export type AppMode = "tasks" | "scheduler" | "cryptonotes";

export interface WorkflowSession {
  sessionId: string | null;
  isRunning: boolean;
  activeNode: GraphNodeName | null;
  state: Partial<AgentTaskState> | null;
  events: SSEEvent[];
  hitlPending: boolean;
  hitlData: {
    proposed_tool: string;
    tool_arguments: Record<string, unknown>;
  } | null;
  error: string | null;
}
