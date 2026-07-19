/**
 * AegisFlow :: hooks/useWorkflowSession.ts
 * ─────────────────────────────────────────
 * Central session orchestrator. Manages workflow lifecycle: launch → stream
 * SSE events → handle HITL intercept → resume. Exposes all UI state and
 * control actions as a single coherent hook.
 */

"use client";

import { useCallback, useReducer, useRef } from "react";
import { resumeWorkflow, startWorkflow } from "@/lib/api";
import type {
  AgentTaskState,
  GraphNodeName,
  HumanValidationDecision,
  RunWorkflowRequest,
  SSEEvent,
  WorkflowSession,
} from "@/lib/types";
import { useSSEStream } from "./useSSEStream";

// ─── State & Reducer ──────────────────────────────────────────────────────────

type Action =
  | { type: "START"; sessionId: string }
  | { type: "NODE_TRANSITION"; node: GraphNodeName; state: Partial<AgentTaskState> }
  | { type: "HITL_REQUIRED"; proposed_tool: string; tool_arguments: Record<string, unknown> }
  | { type: "APPEND_EVENT"; event: SSEEvent }
  | { type: "COMPLETE" }
  | { type: "FAILURE"; error: string }
  | { type: "RESET" };

const initial: WorkflowSession = {
  sessionId: null,
  isRunning: false,
  activeNode: null,
  state: null,
  events: [],
  hitlPending: false,
  hitlData: null,
  error: null,
};

function reducer(state: WorkflowSession, action: Action): WorkflowSession {
  switch (action.type) {
    case "START":
      return {
        ...initial,
        sessionId: action.sessionId,
        isRunning: true,
        events: [],
      };
    case "NODE_TRANSITION":
      return {
        ...state,
        activeNode: action.node,
        state: { ...state.state, ...action.state },
      };
    case "HITL_REQUIRED":
      return {
        ...state,
        isRunning: false,
        hitlPending: true,
        hitlData: {
          proposed_tool: action.proposed_tool,
          tool_arguments: action.tool_arguments,
        },
      };
    case "APPEND_EVENT":
      return {
        ...state,
        events: [...state.events, action.event],
      };
    case "COMPLETE":
      return {
        ...state,
        isRunning: false,
        activeNode: null,
      };
    case "FAILURE":
      return {
        ...state,
        isRunning: false,
        error: action.error,
      };
    case "RESET":
      return { ...initial };
    default:
      return state;
  }
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

export interface WorkflowSessionActions {
  run: (input: string, opts?: Partial<RunWorkflowRequest>) => Promise<void>;
  approve: () => Promise<void>;
  modify: (editedArgs: Record<string, unknown>, feedback?: string) => Promise<void>;
  terminate: () => void;
  reset: () => void;
}

export function useWorkflowSession(): WorkflowSession & WorkflowSessionActions {
  const [session, dispatch] = useReducer(reducer, initial);
  const { consume, abort } = useSSEStream();
  const sessionIdRef = useRef<string | null>(null);

  // ─── SSE processor ──────────────────────────────────────────────────────────
  const processSseResponse = useCallback(
    async (response: Response) => {
      await consume(response, (evt) => {
        dispatch({ type: "APPEND_EVENT", event: evt });

        switch (evt.event) {
          case "THREAD_INITIALIZED": {
            // session_id is at the top level of the data payload
            const sid =
              (evt.data.session_id as string) ??
              (evt.data.data as Record<string,unknown>)?.session_id as string;
            if (sid) {
              sessionIdRef.current = sid;
              dispatch({ type: "START", sessionId: sid });
            }
            break;
          }
          case "NODE_TRANSITION": {
            // Backend uses `node_completed` as the field name
            const node = (
              evt.data.node_completed ??
              evt.data.node_name ??
              "parse_input"
            ) as GraphNodeName;
            dispatch({
              type: "NODE_TRANSITION",
              node,
              state: (evt.data.state ?? {}) as Partial<AgentTaskState>,
            });
            break;
          }
          case "HUMAN_INTERRUPT_REQUIRED": {
            // Backend nests tool info inside `interrupt_details`
            const details = (evt.data.interrupt_details ?? {}) as Record<string, unknown>;
            const proposedTool =
              (details.proposed_tool as string) ??
              (evt.data.proposed_tool as string) ??
              "unknown_tool";
            const toolArgs =
              (details.tool_arguments as Record<string, unknown>) ??
              (evt.data.tool_arguments as Record<string, unknown>) ??
              {};
            dispatch({
              type: "HITL_REQUIRED",
              proposed_tool: proposedTool,
              tool_arguments: toolArgs,
            });
            break;
          }
          case "CRITICAL_FAILURE": {
            dispatch({
              type: "FAILURE",
              error: (evt.data.error ?? "Unknown critical failure") as string,
            });
            break;
          }
          case "WORKFLOW_COMPLETE": {
            dispatch({ type: "COMPLETE" });
            break;
          }
        }
      });
    },
    [consume],
  );

  // ─── Launch new workflow ─────────────────────────────────────────────────────
  const run = useCallback(
    async (input: string, opts: Partial<RunWorkflowRequest> = {}) => {
      abort();
      dispatch({ type: "RESET" });

      try {
        const response = await startWorkflow({ user_input: input, ...opts });
        // Extract session_id from first SSE event (THREAD_INITIALIZED)
        await processSseResponse(response);
      } catch (err) {
        dispatch({
          type: "FAILURE",
          error: err instanceof Error ? err.message : String(err),
        });
      }
    },
    [abort, processSseResponse],
  );

  // ─── Approve HITL ───────────────────────────────────────────────────────────
  const approve = useCallback(async () => {
    const sid = sessionIdRef.current;
    if (!sid) return;

    const decision: HumanValidationDecision = {
      session_id: sid,
      decision: "APPROVE",
    };

    dispatch({ type: "RESET" });
    try {
      const response = await resumeWorkflow(decision);
      dispatch({ type: "START", sessionId: sid });
      await processSseResponse(response);
    } catch (err) {
      dispatch({
        type: "FAILURE",
        error: err instanceof Error ? err.message : String(err),
      });
    }
  }, [processSseResponse]);

  // ─── Modify HITL ────────────────────────────────────────────────────────────
  const modify = useCallback(
    async (editedArgs: Record<string, unknown>, feedback = "") => {
      const sid = sessionIdRef.current;
      if (!sid) return;

      const decision: HumanValidationDecision = {
        session_id: sid,
        decision: "EDIT",
        feedback_message: feedback,
        edited_arguments: editedArgs,
      };

      dispatch({ type: "RESET" });
      try {
        const response = await resumeWorkflow(decision);
        dispatch({ type: "START", sessionId: sid });
        await processSseResponse(response);
      } catch (err) {
        dispatch({
          type: "FAILURE",
          error: err instanceof Error ? err.message : String(err),
        });
      }
    },
    [processSseResponse],
  );

  // ─── Terminate thread ────────────────────────────────────────────────────────
  const terminate = useCallback(async () => {
    const sid = sessionIdRef.current;
    abort();

    if (sid) {
      try {
        await resumeWorkflow({ session_id: sid, decision: "REJECT", feedback_message: "Thread terminated by operator." });
      } catch {
        // Best-effort — abort already cancelled the stream
      }
    }

    dispatch({ type: "FAILURE", error: "Thread terminated by operator." });
  }, [abort]);

  const reset = useCallback(() => {
    abort();
    dispatch({ type: "RESET" });
    sessionIdRef.current = null;
  }, [abort]);

  return {
    ...session,
    run,
    approve,
    modify,
    terminate,
    reset,
  };
}
