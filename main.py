"""
AegisFlow :: main.py
====================
Backend Control Plane — FastAPI Production Server & SSE Streaming Gateway

This module is the entry point for the AegisFlow Backend Control Plane. It
exposes a production-ready FastAPI application that acts as the HTTP gateway
between the Client UX Plane (Next.js frontend) and the Orchestration &
Recovery Plane (LangGraph execution engine).

API Surface:
============
  POST /api/v1/workflow/run      — Launch a new workflow session with SSE streaming.
  POST /api/v1/workflow/resume   — Resume a paused HITL checkpoint with operator decision.
  GET  /api/v1/workflow/status/{session_id} — Query the current status of a running thread.
  GET  /api/v1/health            — Liveliness probe for load balancer health checks.
  GET  /docs                     — Auto-generated Swagger UI (FastAPI built-in).

SSE Event Types:
================
  THREAD_INITIALIZED      — Emitted once at workflow start with session metadata.
  NODE_TRANSITION         — Emitted for each LangGraph node that completes.
  HUMAN_INTERRUPT_REQUIRED — Emitted when the graph pauses at a HITL checkpoint.
  CRITICAL_FAILURE        — Emitted when an unrecoverable error terminates the workflow.
  WORKFLOW_COMPLETE       — Emitted when execute_tool reaches END successfully.

Architecture Plane: II — Backend Control Plane
Dependencies:
  - fastapi (>=0.111.0): Web framework with OpenAPI auto-documentation
  - uvicorn (>=0.30.0): ASGI server for production deployment
  - langgraph (>=0.2.0): StateGraph with interrupt() support
  - schemas.py: AgentTaskState, RunWorkflowRequest, HumanValidationDecision
  - graph.py: aegisflow_engine (compiled LangGraph instance)
"""

from __future__ import annotations

import os
# Load .env file so GROQ_API_KEY / GEMINI_API_KEY are available via os.getenv()
from pathlib import Path
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

import asyncio

import json
import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Path, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langgraph.errors import GraphInterrupt

from graph import aegisflow_engine
from schemas import (
    AgentTaskState,
    HumanValidationDecision,
    RunWorkflowRequest,
    TokenBudgetTracker,
    ValidationStatus,
    WorkflowStatusResponse,
)

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
# Configure the root logger to output structured log lines to stdout.
# In production, replace this with a JSON formatter (e.g., python-json-logger)
# feeding into a centralized log aggregation system (Datadog, Splunk, etc.).

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("aegisflow.main")
logger.setLevel(logging.DEBUG)

# ---------------------------------------------------------------------------
# Application lifespan context manager
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    FastAPI lifespan event handler managing application startup and shutdown.

    On startup:
    - Logs the AegisFlow banner with version and plane configuration.
    - Verifies that the aegisflow_engine compiled graph is loaded.
    - Initializes any shared application state (active_sessions registry).

    On shutdown:
    - Logs the graceful shutdown sequence.
    - Cancels any pending background session tasks (future: Kafka producer flush).
    """
    # ------------------------------------------------------------------
    # Startup
    # ------------------------------------------------------------------
    logger.info("=" * 72)
    logger.info("  AegisFlow Backend Control Plane — Starting Up")
    logger.info("  Version:     1.0.0")
    logger.info("  API Version: v1")
    logger.info("  Planes:      Client UX | Backend Control | Orchestration | Integration")
    logger.info("  Checkpointer: MemorySaver (in-memory, per-process)")
    logger.info("  HITL Support: LangGraph interrupt() with resume endpoint")
    logger.info("=" * 72)

    if aegisflow_engine is None:
        logger.critical(
            "FATAL: aegisflow_engine graph failed to compile. "
            "Check graph.py imports and LangGraph installation."
        )
        raise RuntimeError(
            "AegisFlow graph engine is None — application cannot start."
        )

    logger.info(
        "LangGraph execution engine loaded successfully. "
        "Ready to accept workflow sessions."
    )

    # Initialize the in-memory active sessions registry.
    # Maps session_id -> last known AgentTaskState snapshot for status queries.
    app.state.active_sessions: Dict[str, Dict[str, Any]] = {}

    logger.info("Active sessions registry initialized.")
    logger.info("AegisFlow Backend Control Plane is READY.")

    yield  # Application runs here

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------
    logger.info("AegisFlow Backend Control Plane — Graceful Shutdown Initiated.")
    active_count = len(app.state.active_sessions)
    logger.info(
        "Draining %d active session record(s) from memory registry.",
        active_count,
    )
    app.state.active_sessions.clear()
    logger.info("AegisFlow Backend Control Plane — Shutdown complete.")


# ---------------------------------------------------------------------------
# FastAPI Application Instance
# ---------------------------------------------------------------------------

app = FastAPI(
    title="AegisFlow Core API",
    description=(
        "Enterprise-grade multi-agent workflow orchestration backend. "
        "Provides a stateful, governance-controlled execution environment "
        "combining LangGraph state machines, PydanticAI type validation, "
        "and human-in-the-loop interrupt checkpoints.\n\n"
        "**Architecture Planes:**\n"
        "- II: Backend Control Plane (this server)\n"
        "- III: Orchestration & Recovery Plane (LangGraph engine)\n"
        "- IV: Integration Plane (MCP Gateway — future)\n\n"
        "**Governance:** All mutating tool calls require human validation before execution."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/api/v1/openapi.json",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS Middleware
# ---------------------------------------------------------------------------
# Configure CORS to allow the Next.js frontend to connect. In production,
# replace the wildcard origin with the specific frontend domain.

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",    # Next.js development server
        "http://localhost:3001",    # Alternative frontend port
        "https://aegisflow.app",    # Production domain (configure at deployment)
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# SSE Event Formatting Utilities
# ---------------------------------------------------------------------------

def format_sse_event(event_type: str, payload: Dict[str, Any]) -> str:
    """
    Format a dictionary payload as a Server-Sent Events (SSE) compliant string.

    SSE protocol requires:
    - Lines starting with "data:" for the event payload
    - An empty line (\n\n) to terminate each event frame

    The payload is serialized as a JSON string with the `event_type` embedded
    so the frontend can switch on it to render the correct UI component.

    Args:
        event_type: The string identifier for this event category.
        payload:    Dictionary of event-specific context data.

    Returns:
        SSE-formatted string ready to be yielded from the async generator.
    """
    event_body = {
        "event": event_type,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        **payload,
    }
    return f"data: {json.dumps(event_body, default=str)}\n\n"


def format_sse_thread_initialized(
    session_id: str,
    user_input_preview: str,
    token_budget_ceiling: int,
) -> str:
    """
    Emit the THREAD_INITIALIZED event — the first SSE frame streamed to the
    client after a workflow session is successfully created.

    Args:
        session_id:           The UUID4 session identifier for this thread.
        user_input_preview:   First 120 characters of the user's input.
        token_budget_ceiling: The configured token budget ceiling for this session.

    Returns:
        SSE-formatted THREAD_INITIALIZED event string.
    """
    return format_sse_event(
        event_type="THREAD_INITIALIZED",
        payload={
            "session_id": session_id,
            "user_input_preview": user_input_preview,
            "token_budget_ceiling": token_budget_ceiling,
            "graph_nodes": ["parse_input", "route_task", "human_validation", "execute_tool"],
            "governance_controls": {
                "hitl_enabled": True,
                "mutating_tool_registry_active": True,
                "audit_trail_enabled": True,
                "token_budget_enforced": True,
            },
            "message": (
                f"AegisFlow workflow session initialized. "
                f"Token budget: {token_budget_ceiling:,} tokens. "
                f"Human-in-the-loop governance is ACTIVE."
            ),
        },
    )


def format_sse_node_transition(
    node_name: str,
    node_output: Dict[str, Any],
    session_id: str,
) -> str:
    """
    Emit a NODE_TRANSITION event whenever a LangGraph node completes and the
    graph yields the node's output state updates.

    Args:
        node_name:   Name of the node that just completed execution.
        node_output: The state update dictionary returned by the node.
        session_id:  The thread's session identifier.

    Returns:
        SSE-formatted NODE_TRANSITION event string.
    """
    # Extract safe summary fields from the node output — avoid leaking
    # full tool_arguments payloads or large audit_trail arrays to the SSE feed.
    safe_summary = {
        "node_completed": node_name,
        "session_id": session_id,
        "validation_status": node_output.get("validation_status"),
        "inference_route": node_output.get("inference_route"),
        "proposed_tool": node_output.get("proposed_tool"),
        "active_step_index": node_output.get("active_step_index"),
        "audit_events_in_update": len(node_output.get("audit_trail", [])),
        "execution_errors_count": len(node_output.get("execution_errors", [])),
        "token_budget_status": {
            "total_consumed": (
                node_output.get("token_budget", {}).total_tokens_consumed
                if hasattr(node_output.get("token_budget"), "total_tokens_consumed")
                else None
            ),
        },
    }

    return format_sse_event(
        event_type="NODE_TRANSITION",
        payload=safe_summary,
    )


def format_sse_human_interrupt(
    session_id: str,
    interrupt_data: Any,
) -> str:
    """
    Emit the HUMAN_INTERRUPT_REQUIRED event when the graph's `human_validation`
    node triggers a LangGraph interrupt() pause checkpoint.

    This event carries the full interrupt payload (tool name, arguments,
    risk classification, available decisions) so the frontend can render
    a comprehensive approval panel without making additional API calls.

    Args:
        session_id:     The thread's session identifier.
        interrupt_data: The payload dict passed to interrupt() by human_validation.

    Returns:
        SSE-formatted HUMAN_INTERRUPT_REQUIRED event string.
    """
    # Safely extract the interrupt payload
    if isinstance(interrupt_data, dict):
        interrupt_payload = interrupt_data
    elif hasattr(interrupt_data, "value"):
        # LangGraph wraps interrupt values in an Interrupt object in some versions
        interrupt_payload = interrupt_data.value if isinstance(interrupt_data.value, dict) else {"raw": str(interrupt_data.value)}
    else:
        interrupt_payload = {"raw_interrupt_data": str(interrupt_data)[:500]}

    return format_sse_event(
        event_type="HUMAN_INTERRUPT_REQUIRED",
        payload={
            "session_id": session_id,
            "resume_endpoint": f"/api/v1/workflow/resume",
            "resume_instructions": (
                "POST to /api/v1/workflow/resume with a HumanValidationDecision "
                "payload containing session_id, decision (APPROVE/EDIT/REJECT), "
                "optional feedback_message, and edited_arguments if decision=EDIT."
            ),
            "interrupt_details": interrupt_payload,
            "message": (
                "Workflow execution PAUSED. High-risk tool operation requires "
                "operator authorization before proceeding. Review the tool "
                "details and submit your decision to resume execution."
            ),
        },
    )


def format_sse_critical_failure(
    session_id: str,
    error_type: str,
    error_message: str,
    node_context: Optional[str] = None,
) -> str:
    """
    Emit a CRITICAL_FAILURE event when an unrecoverable exception terminates
    the workflow. Closes the SSE stream with a structured error payload.

    Args:
        session_id:    The thread's session identifier.
        error_type:    Exception class name.
        error_message: Full exception message string.
        node_context:  Optional: the node name where the failure occurred.

    Returns:
        SSE-formatted CRITICAL_FAILURE event string.
    """
    return format_sse_event(
        event_type="CRITICAL_FAILURE",
        payload={
            "session_id": session_id,
            "error_type": error_type,
            "error_message": error_message[:1_000],  # Truncate to prevent oversized events
            "node_context": node_context,
            "recovery_action": (
                "The workflow session has terminated due to an unrecoverable error. "
                "Check server logs for the full stack trace. "
                "Start a new session to retry the operation."
            ),
            "support_reference": f"session_id={session_id} | error={error_type}",
        },
    )


def format_sse_workflow_complete(
    session_id: str,
    final_state_summary: Dict[str, Any],
) -> str:
    """
    Emit the WORKFLOW_COMPLETE event when the execution graph reaches END
    and all steps have been processed.

    Args:
        session_id:          The thread's session identifier.
        final_state_summary: Condensed summary of the final AgentTaskState.

    Returns:
        SSE-formatted WORKFLOW_COMPLETE event string.
    """
    return format_sse_event(
        event_type="WORKFLOW_COMPLETE",
        payload={
            "session_id": session_id,
            "final_validation_status": final_state_summary.get("validation_status"),
            "total_steps_processed": final_state_summary.get("active_step_index", 0),
            "total_audit_events": final_state_summary.get("audit_event_count", 0),
            "total_tokens_consumed": final_state_summary.get("total_tokens_consumed", 0),
            "execution_errors_count": final_state_summary.get("execution_errors_count", 0),
            "inference_route_used": final_state_summary.get("inference_route"),
            "message": (
                "AegisFlow workflow session completed successfully. "
                "All task steps have been processed and sealed in the audit trail."
            ),
        },
    )


# ---------------------------------------------------------------------------
# Endpoint 1: POST /api/v1/workflow/run
# ---------------------------------------------------------------------------

@app.post(
    "/api/v1/workflow/run",
    summary="Launch a new AegisFlow workflow session",
    description=(
        "Accepts a natural language user command, initializes a new LangGraph "
        "thread session, and streams execution progress back to the client "
        "using Server-Sent Events (SSE). The stream yields events for each "
        "graph node transition, human-in-the-loop interrupt checkpoints, and "
        "final workflow completion or critical failures."
    ),
    response_description="SSE stream of workflow execution events (text/event-stream)",
    status_code=status.HTTP_200_OK,
    tags=["Workflow Orchestration"],
)
async def run_workflow(
    payload: RunWorkflowRequest,
) -> StreamingResponse:
    """
    Primary workflow execution endpoint for the AegisFlow Backend Control Plane.

    Request Flow:
    1. Validates the incoming RunWorkflowRequest (FastAPI handles this automatically).
    2. Generates a unique session_id UUID4 for this workflow thread.
    3. Constructs the initial AgentTaskState with any overrides from the request.
    4. Builds the LangGraph thread config with the session_id as thread_id.
    5. Returns a StreamingResponse that yields SSE events as the graph executes.
    6. Stores the session ID in app.state.active_sessions for status queries.

    The SSE stream yields the following event sequence for a normal execution:
      THREAD_INITIALIZED → NODE_TRANSITION (parse_input) → NODE_TRANSITION (route_task)
      → [HUMAN_INTERRUPT_REQUIRED if mutating tool] → NODE_TRANSITION (execute_tool)
      → WORKFLOW_COMPLETE

    For a mutating tool, execution pauses at HUMAN_INTERRUPT_REQUIRED and resumes
    only after POST /api/v1/workflow/resume is called with the operator's decision.

    Args:
        payload: Validated RunWorkflowRequest with user_input and optional overrides.

    Returns:
        StreamingResponse with media_type="text/event-stream" containing SSE events.
    """
    # Generate the unique session identifier for this workflow thread
    session_id = str(uuid4())

    logger.info(
        "New workflow request received. session_id=%s | input_length=%d | "
        "tool_override=%s | budget_override=%s",
        session_id,
        len(payload.user_input),
        payload.proposed_tool_override,
        payload.token_budget_override,
    )

    # ------------------------------------------------------------------
    # Build the token budget with any client-supplied override
    # ------------------------------------------------------------------
    token_budget = TokenBudgetTracker()
    if payload.token_budget_override is not None:
        token_budget.session_token_ceiling = payload.token_budget_override
        logger.info(
            "Token budget override applied: %d tokens for session_id=%s",
            payload.token_budget_override,
            session_id,
        )

    # ------------------------------------------------------------------
    # Construct the initial AgentTaskState
    # ------------------------------------------------------------------
    # The state is fully validated by Pydantic at construction time.
    # Any schema violations will raise a ValidationError here — before
    # the SSE stream starts — so FastAPI can return a clean 422 response.
    initial_state = AgentTaskState(
        session_id=session_id,
        original_input=payload.user_input,
        task_steps=[],
        active_step_index=0,
        proposed_tool=payload.proposed_tool_override,  # None unless testing/debug
        tool_arguments={},
        validation_status=ValidationStatus.PENDING.value,
        user_feedback="",
        execution_errors=[],
        token_budget=token_budget,
        inference_route=None,
        audit_trail=[],
    )

    logger.info(
        "AgentTaskState constructed and validated for session_id=%s",
        session_id,
    )

    # ------------------------------------------------------------------
    # Build the LangGraph thread configuration
    # ------------------------------------------------------------------
    # The `thread_id` in the config dict is how LangGraph scopes the
    # MemorySaver checkpointer to this specific session. Every call to
    # astream() with the same thread_id continues from the saved checkpoint.
    thread_config: Dict[str, Any] = {
        "configurable": {
            "thread_id": session_id,
        },
        "recursion_limit": 25,  # Safety cap to prevent infinite graph cycles
    }

    # Register this session in the active sessions registry
    # for status queries and debugging purposes
    app.state.active_sessions[session_id] = {
        "session_id": session_id,
        "status": "RUNNING",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "user_input_preview": payload.user_input[:120],
    }

    # ------------------------------------------------------------------
    # Define the SSE event generator
    # ------------------------------------------------------------------
    async def event_generator() -> AsyncGenerator[str, None]:
        """
        Async generator that drives the LangGraph execution engine and yields
        Server-Sent Events to the frontend connection.

        This generator:
        1. Emits THREAD_INITIALIZED to confirm session creation.
        2. Iterates over aegisflow_engine.astream() events.
        3. For each yielded node update, emits a NODE_TRANSITION event.
        4. Catches GraphInterrupt to emit HUMAN_INTERRUPT_REQUIRED.
        5. Catches any other exception to emit CRITICAL_FAILURE.
        6. Emits WORKFLOW_COMPLETE on clean graph termination.
        """
        logger.info(
            "[event_generator] Starting SSE stream for session_id=%s", session_id
        )

        # ------------------------------------------------------------------
        # Event 1: THREAD_INITIALIZED
        # ------------------------------------------------------------------
        yield format_sse_thread_initialized(
            session_id=session_id,
            user_input_preview=(
                payload.user_input[:120] + "..."
                if len(payload.user_input) > 120
                else payload.user_input
            ),
            token_budget_ceiling=initial_state.token_budget.session_token_ceiling,
        )

        logger.debug(
            "[event_generator] THREAD_INITIALIZED emitted for session_id=%s",
            session_id,
        )

        # Track the last known state for the WORKFLOW_COMPLETE summary
        last_state_snapshot: Dict[str, Any] = {}
        node_transition_count = 0

        try:
            # ------------------------------------------------------------------
            # Graph Execution Stream
            # ------------------------------------------------------------------
            # `astream()` is an async generator that yields one dictionary per
            # completed node. The dictionary key is the node name, and the value
            # is the partial state update returned by that node.
            # mode="updates" yields only the delta state from each node, not
            # the full accumulated state. This reduces payload size significantly.
            async for event in aegisflow_engine.astream(
                initial_state.model_dump(),
                config=thread_config,
                stream_mode="updates",
            ):
                node_transition_count += 1

                logger.debug(
                    "[event_generator] Graph event received. "
                    "node_transition_count=%d | event_keys=%s | session_id=%s",
                    node_transition_count,
                    list(event.keys()),
                    session_id,
                )

                # Each event dict has one key: the node name that just completed
                for node_name, node_output in event.items():
                    logger.info(
                        "[event_generator] NODE_TRANSITION: %s completed | session_id=%s",
                        node_name,
                        session_id,
                    )

                    # Store the latest snapshot for WORKFLOW_COMPLETE summary
                    if isinstance(node_output, dict):
                        last_state_snapshot.update(node_output)

                    # Update the active sessions registry with latest status
                    if session_id in app.state.active_sessions:
                        app.state.active_sessions[session_id]["last_node"] = node_name
                        app.state.active_sessions[session_id]["status"] = "RUNNING"
                        if isinstance(node_output, dict):
                            app.state.active_sessions[session_id]["validation_status"] = (
                                node_output.get("validation_status", "PENDING")
                            )

                    # Emit NODE_TRANSITION event to the frontend
                    yield format_sse_node_transition(
                        node_name=node_name,
                        node_output=node_output if isinstance(node_output, dict) else {},
                        session_id=session_id,
                    )

                    # Small yield to prevent buffering from blocking the connection
                    await asyncio.sleep(0)

        except GraphInterrupt as interrupt_exc:
            # ------------------------------------------------------------------
            # HITL Interrupt — graph has paused at human_validation node
            # ------------------------------------------------------------------
            logger.warning(
                "[event_generator] GraphInterrupt caught for session_id=%s. "
                "Graph paused at human_validation checkpoint.",
                session_id,
            )

            # Extract the interrupt payload from the exception.
            # LangGraph stores interrupt data in interrupt_exc.args[0] in most
            # versions; some versions use a `.value` attribute.
            interrupt_data: Any = None
            if interrupt_exc.args:
                interrupt_data = interrupt_exc.args[0]
                # If it's a sequence of Interrupt objects, extract the first value
                if isinstance(interrupt_data, (list, tuple)) and interrupt_data:
                    first_interrupt = interrupt_data[0]
                    interrupt_data = (
                        first_interrupt.value
                        if hasattr(first_interrupt, "value")
                        else first_interrupt
                    )

            # Update session registry to reflect paused state
            if session_id in app.state.active_sessions:
                app.state.active_sessions[session_id]["status"] = "PAUSED_AWAITING_HITL"
                app.state.active_sessions[session_id]["interrupt_data"] = (
                    str(interrupt_data)[:500] if interrupt_data else "HITL_TRIGGERED"
                )

            # Emit the HUMAN_INTERRUPT_REQUIRED SSE event
            yield format_sse_human_interrupt(
                session_id=session_id,
                interrupt_data=interrupt_data if interrupt_data else {
                    "action": "AWAITING_OPERATOR_APPROVAL",
                    "session_id": session_id,
                    "note": "Interrupt payload unavailable. Check server logs.",
                },
            )

            # Do NOT emit WORKFLOW_COMPLETE — the stream ends here for the
            # initial request. The client should listen for new events on
            # the /resume endpoint's response stream.
            logger.info(
                "[event_generator] SSE stream SUSPENDED at HITL checkpoint. "
                "Awaiting /resume call for session_id=%s.",
                session_id,
            )
            return

        except asyncio.CancelledError:
            # Client disconnected — clean up gracefully without logging as error
            logger.info(
                "[event_generator] SSE stream cancelled (client disconnected) "
                "for session_id=%s.",
                session_id,
            )
            if session_id in app.state.active_sessions:
                app.state.active_sessions[session_id]["status"] = "CLIENT_DISCONNECTED"
            return

        except Exception as exc:
            # ------------------------------------------------------------------
            # Unrecoverable error — emit CRITICAL_FAILURE and close stream
            # ------------------------------------------------------------------
            error_type = type(exc).__name__
            error_message = str(exc)

            logger.exception(
                "[event_generator] CRITICAL_FAILURE for session_id=%s | "
                "error_type=%s | error=%s",
                session_id,
                error_type,
                error_message,
            )

            if session_id in app.state.active_sessions:
                app.state.active_sessions[session_id]["status"] = "FAILED"
                app.state.active_sessions[session_id]["failure_reason"] = (
                    f"{error_type}: {error_message[:200]}"
                )

            yield format_sse_critical_failure(
                session_id=session_id,
                error_type=error_type,
                error_message=error_message,
                node_context=app.state.active_sessions.get(session_id, {}).get("last_node"),
            )
            return

        # ------------------------------------------------------------------
        # Workflow completed without interruption
        # ------------------------------------------------------------------
        logger.info(
            "[event_generator] Graph execution completed normally for session_id=%s. "
            "Total node transitions: %d",
            session_id,
            node_transition_count,
        )

        if session_id in app.state.active_sessions:
            app.state.active_sessions[session_id]["status"] = "COMPLETED"

        # Build the final state summary for the WORKFLOW_COMPLETE event
        final_summary: Dict[str, Any] = {
            "validation_status": last_state_snapshot.get(
                "validation_status", ValidationStatus.COMPLETED.value
            ),
            "active_step_index": last_state_snapshot.get("active_step_index", 0),
            "audit_event_count": len(last_state_snapshot.get("audit_trail", [])),
            "total_tokens_consumed": (
                last_state_snapshot.get("token_budget", {}).total_tokens_consumed
                if hasattr(last_state_snapshot.get("token_budget"), "total_tokens_consumed")
                else 0
            ),
            "execution_errors_count": len(last_state_snapshot.get("execution_errors", [])),
            "inference_route": last_state_snapshot.get("inference_route"),
        }

        yield format_sse_workflow_complete(
            session_id=session_id,
            final_state_summary=final_summary,
        )

        logger.info(
            "[event_generator] WORKFLOW_COMPLETE emitted and SSE stream closed "
            "for session_id=%s.",
            session_id,
        )

    # Return the StreamingResponse — FastAPI streams the generator output
    # as an HTTP chunked transfer encoding response with SSE media type.
    return StreamingResponse(
        content=event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",      # Disable nginx proxy buffering for SSE
            "Connection": "keep-alive",
            "X-Session-Id": session_id,     # Expose session_id in response header
            "Access-Control-Expose-Headers": "X-Session-Id",
        },
    )


# ---------------------------------------------------------------------------
# Endpoint 2: POST /api/v1/workflow/resume
# ---------------------------------------------------------------------------

@app.post(
    "/api/v1/workflow/resume",
    summary="Resume a paused HITL workflow checkpoint",
    description=(
        "Injects the human operator's validation decision into a paused "
        "LangGraph thread and resumes execution from the saved checkpoint. "
        "Must be called after receiving a HUMAN_INTERRUPT_REQUIRED SSE event."
    ),
    response_description="SSE stream of workflow execution events after HITL resume",
    status_code=status.HTTP_200_OK,
    tags=["Workflow Orchestration"],
)
async def resume_workflow(
    decision: HumanValidationDecision,
) -> StreamingResponse:
    """
    Human-in-the-Loop resume endpoint.

    When the graph's `human_validation` node triggers an interrupt(), the
    LangGraph thread is preserved in the MemorySaver checkpointer. This
    endpoint injects the operator's decision back into the paused thread
    by calling `astream(None, config)` — LangGraph passes `None` as the
    resume_input to the `interrupt()` call site in `human_validation`.

    Wait — actually, LangGraph expects the resume value to be passed via
    the `Command` object or via updating the state before resuming.
    The correct approach is: `astream(Command(resume=decision_dict), config)`.

    Args:
        decision: Validated HumanValidationDecision with session_id, operator
                  decision (APPROVE/EDIT/REJECT), optional feedback, and
                  edited_arguments if decision=EDIT.

    Returns:
        StreamingResponse with SSE events continuing from the checkpoint.
    """
    session_id = decision.session_id

    logger.info(
        "HITL resume request received for session_id=%s | decision='%s'",
        session_id,
        decision.decision,
    )

    # Verify the session exists in the active sessions registry
    session_record = app.state.active_sessions.get(session_id)
    if session_record is None:
        logger.error(
            "Resume requested for unknown session_id=%s. "
            "Session may have expired or never existed.",
            session_id,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "SESSION_NOT_FOUND",
                "message": (
                    f"No active session found for session_id='{session_id}'. "
                    f"The session may have expired, completed, or never existed. "
                    f"Start a new workflow session via POST /api/v1/workflow/run."
                ),
                "session_id": session_id,
            },
        )

    # Verify the session is actually paused at a HITL checkpoint
    if session_record.get("status") != "PAUSED_AWAITING_HITL":
        logger.warning(
            "Resume requested for session_id=%s but status='%s' (expected PAUSED_AWAITING_HITL).",
            session_id,
            session_record.get("status"),
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "SESSION_NOT_PAUSED",
                "message": (
                    f"Session '{session_id}' is not currently paused at a HITL checkpoint. "
                    f"Current status: '{session_record.get('status')}'. "
                    f"Only sessions with status 'PAUSED_AWAITING_HITL' can be resumed."
                ),
                "current_status": session_record.get("status"),
                "session_id": session_id,
            },
        )

    # Build the operator decision dictionary to inject as the interrupt() return value
    operator_decision_payload: Dict[str, Any] = {
        "decision": decision.decision.value if hasattr(decision.decision, "value") else decision.decision,
        "feedback_message": decision.feedback_message,
        "edited_arguments": decision.edited_arguments,
        "resume_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "decision_submitted_by": "human_operator",
    }

    logger.info(
        "Injecting operator decision for session_id=%s: %s",
        session_id,
        operator_decision_payload,
    )

    thread_config: Dict[str, Any] = {
        "configurable": {
            "thread_id": session_id,
        },
        "recursion_limit": 25,
    }

    # Update session registry status
    app.state.active_sessions[session_id]["status"] = "RESUMING"
    app.state.active_sessions[session_id]["operator_decision"] = decision.decision

    async def resume_event_generator() -> AsyncGenerator[str, None]:
        """
        Async generator that resumes the paused graph thread and streams
        subsequent execution events as SSE frames to the frontend.
        """
        # Emit an immediate acknowledgment event before resuming the graph
        yield format_sse_event(
            event_type="HITL_DECISION_RECEIVED",
            payload={
                "session_id": session_id,
                "decision": operator_decision_payload["decision"],
                "message": (
                    f"Operator decision '{operator_decision_payload['decision']}' received. "
                    f"Resuming graph execution from checkpoint..."
                ),
            },
        )

        await asyncio.sleep(0)  # Yield control to allow the acknowledgment to flush

        last_state_snapshot: Dict[str, Any] = {}
        node_transition_count = 0

        try:
            # ------------------------------------------------------------------
            # Resume the LangGraph thread via Command(resume=...)
            # ------------------------------------------------------------------
            # LangGraph uses Command(resume=value) to inject the operator's
            # decision as the return value of the paused interrupt() call.
            from langgraph.types import Command

            async for event in aegisflow_engine.astream(
                Command(resume=operator_decision_payload),
                config=thread_config,
                stream_mode="updates",
            ):
                node_transition_count += 1

                for node_name, node_output in event.items():
                    logger.info(
                        "[resume_event_generator] NODE_TRANSITION: %s | session_id=%s",
                        node_name,
                        session_id,
                    )

                    if isinstance(node_output, dict):
                        last_state_snapshot.update(node_output)

                    if session_id in app.state.active_sessions:
                        app.state.active_sessions[session_id]["last_node"] = node_name
                        app.state.active_sessions[session_id]["status"] = "RUNNING"

                    yield format_sse_node_transition(
                        node_name=node_name,
                        node_output=node_output if isinstance(node_output, dict) else {},
                        session_id=session_id,
                    )

                    await asyncio.sleep(0)

        except GraphInterrupt as interrupt_exc:
            # The graph paused again (multi-step workflows may have multiple HITL points)
            logger.warning(
                "[resume_event_generator] Secondary GraphInterrupt for session_id=%s.",
                session_id,
            )

            interrupt_data: Any = None
            if interrupt_exc.args:
                interrupt_data = interrupt_exc.args[0]
                if isinstance(interrupt_data, (list, tuple)) and interrupt_data:
                    first_interrupt = interrupt_data[0]
                    interrupt_data = (
                        first_interrupt.value
                        if hasattr(first_interrupt, "value")
                        else first_interrupt
                    )

            if session_id in app.state.active_sessions:
                app.state.active_sessions[session_id]["status"] = "PAUSED_AWAITING_HITL"

            yield format_sse_human_interrupt(
                session_id=session_id,
                interrupt_data=interrupt_data or {"action": "SECONDARY_HITL_REQUIRED"},
            )
            return

        except asyncio.CancelledError:
            logger.info(
                "[resume_event_generator] SSE stream cancelled for session_id=%s.",
                session_id,
            )
            if session_id in app.state.active_sessions:
                app.state.active_sessions[session_id]["status"] = "CLIENT_DISCONNECTED"
            return

        except Exception as exc:
            error_type = type(exc).__name__
            error_message = str(exc)
            logger.exception(
                "[resume_event_generator] CRITICAL_FAILURE for session_id=%s | %s: %s",
                session_id,
                error_type,
                error_message,
            )

            if session_id in app.state.active_sessions:
                app.state.active_sessions[session_id]["status"] = "FAILED"

            yield format_sse_critical_failure(
                session_id=session_id,
                error_type=error_type,
                error_message=error_message,
                node_context="post_resume_execution",
            )
            return

        # ------------------------------------------------------------------
        # Post-resume workflow completed
        # ------------------------------------------------------------------
        logger.info(
            "[resume_event_generator] Graph execution completed after HITL resume "
            "for session_id=%s. Transitions: %d",
            session_id,
            node_transition_count,
        )

        if session_id in app.state.active_sessions:
            app.state.active_sessions[session_id]["status"] = "COMPLETED"

        final_summary: Dict[str, Any] = {
            "validation_status": last_state_snapshot.get(
                "validation_status", ValidationStatus.COMPLETED.value
            ),
            "active_step_index": last_state_snapshot.get("active_step_index", 0),
            "audit_event_count": len(last_state_snapshot.get("audit_trail", [])),
            "total_tokens_consumed": 0,  # Calculated from token_budget if available
            "execution_errors_count": len(last_state_snapshot.get("execution_errors", [])),
            "inference_route": last_state_snapshot.get("inference_route"),
        }

        # Extract token consumption if token_budget is in the snapshot
        raw_budget = last_state_snapshot.get("token_budget")
        if hasattr(raw_budget, "total_tokens_consumed"):
            final_summary["total_tokens_consumed"] = raw_budget.total_tokens_consumed
        elif isinstance(raw_budget, dict):
            final_summary["total_tokens_consumed"] = (
                raw_budget.get("total_input_tokens", 0)
                + raw_budget.get("total_output_tokens", 0)
            )

        yield format_sse_workflow_complete(
            session_id=session_id,
            final_state_summary=final_summary,
        )

    return StreamingResponse(
        content=resume_event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
            "X-Session-Id": session_id,
            "Access-Control-Expose-Headers": "X-Session-Id",
        },
    )


# ---------------------------------------------------------------------------
# Endpoint 3: GET /api/v1/workflow/status/{session_id}
# ---------------------------------------------------------------------------

@app.get(
    "/api/v1/workflow/status/{session_id}",
    summary="Query the status of a running workflow session",
    description=(
        "Returns the current status of a workflow session from the in-memory "
        "active sessions registry. Does not query the LangGraph checkpointer "
        "directly — use the streaming endpoints for full state detail."
    ),
    response_model=WorkflowStatusResponse,
    status_code=status.HTTP_200_OK,
    tags=["Session Management"],
)
async def get_workflow_status(
    session_id: str = Path(
        description="UUID4 session identifier from the THREAD_INITIALIZED SSE event.",
        min_length=36,
        max_length=36,
    ),
) -> WorkflowStatusResponse:
    """
    Non-streaming status query endpoint for workflow session health checks.

    This endpoint queries the MemorySaver checkpointer to retrieve the last
    committed state snapshot for the requested session, returning a condensed
    WorkflowStatusResponse without streaming overhead.

    Args:
        session_id: The UUID4 session identifier for the workflow thread.

    Returns:
        WorkflowStatusResponse containing current validation_status, step index,
        token usage, and error counts.

    Raises:
        HTTPException 404: If no checkpoint exists for the given session_id.
    """
    logger.info("Status query for session_id=%s", session_id)

    thread_config: Dict[str, Any] = {
        "configurable": {"thread_id": session_id},
    }

    # Retrieve the latest checkpoint state from MemorySaver
    try:
        checkpoint_tuple = aegisflow_engine.get_state(config=thread_config)
    except Exception as exc:
        logger.error(
            "Failed to retrieve checkpoint for session_id=%s: %s",
            session_id,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "CHECKPOINT_RETRIEVAL_FAILED",
                "message": f"Failed to query checkpoint store: {exc}",
                "session_id": session_id,
            },
        )

    if checkpoint_tuple is None or checkpoint_tuple.values is None:
        logger.warning("No checkpoint found for session_id=%s", session_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "SESSION_NOT_FOUND",
                "message": (
                    f"No checkpoint found for session_id='{session_id}'. "
                    f"The session may have never started or may have been purged."
                ),
                "session_id": session_id,
            },
        )

    state_values = checkpoint_tuple.values

    # Extract token budget data safely
    raw_budget = state_values.get("token_budget", {})
    token_usage_summary: Dict[str, Any] = {
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_consumed": 0,
        "ceiling": 50_000,
        "recovery_attempts": 0,
        "confidence_score": 1.0,
    }

    if hasattr(raw_budget, "total_tokens_consumed"):
        token_usage_summary = {
            "total_input_tokens": raw_budget.total_input_tokens,
            "total_output_tokens": raw_budget.total_output_tokens,
            "total_consumed": raw_budget.total_tokens_consumed,
            "ceiling": raw_budget.session_token_ceiling,
            "budget_exhausted": raw_budget.is_budget_exhausted(),
            "recovery_attempts": raw_budget.recovery_attempt_count,
            "max_recovery_attempts": raw_budget.max_recovery_attempts,
            "confidence_score": raw_budget.confidence_score,
        }
    elif isinstance(raw_budget, dict):
        total = raw_budget.get("total_input_tokens", 0) + raw_budget.get("total_output_tokens", 0)
        token_usage_summary = {
            "total_input_tokens": raw_budget.get("total_input_tokens", 0),
            "total_output_tokens": raw_budget.get("total_output_tokens", 0),
            "total_consumed": total,
            "ceiling": raw_budget.get("session_token_ceiling", 50_000),
            "recovery_attempts": raw_budget.get("recovery_attempt_count", 0),
            "confidence_score": raw_budget.get("confidence_score", 1.0),
        }

    task_steps = state_values.get("task_steps", [])
    audit_trail = state_values.get("audit_trail", [])
    execution_errors = state_values.get("execution_errors", [])

    return WorkflowStatusResponse(
        session_id=session_id,
        validation_status=state_values.get("validation_status", ValidationStatus.PENDING.value),
        active_step_index=state_values.get("active_step_index", 0),
        total_steps=len(task_steps),
        inference_route=state_values.get("inference_route"),
        error_count=len(execution_errors),
        audit_event_count=len(audit_trail),
        token_usage=token_usage_summary,
    )


# ---------------------------------------------------------------------------
# Endpoint 4: GET /api/v1/health
# ---------------------------------------------------------------------------

@app.get(
    "/api/v1/health",
    summary="Server liveness health check",
    description=(
        "Simple health probe for load balancer and Kubernetes liveness checks. "
        "Returns 200 OK with a JSON body confirming the server is alive and "
        "the graph engine is loaded."
    ),
    status_code=status.HTTP_200_OK,
    tags=["Operations"],
)
async def health_check() -> Dict[str, Any]:
    """
    Liveness probe endpoint returning the server's operational status.

    Returns:
        JSON object with `status`, `timestamp`, `graph_engine_loaded`, and
        `active_sessions_count` fields.
    """
    active_count = len(getattr(app.state, "active_sessions", {}))
    engine_loaded = aegisflow_engine is not None

    logger.debug(
        "Health check requested. engine_loaded=%s | active_sessions=%d",
        engine_loaded,
        active_count,
    )

    return {
        "status": "HEALTHY" if engine_loaded else "DEGRADED",
        "service": "AegisFlow Backend Control Plane",
        "version": "1.0.0",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "graph_engine_loaded": engine_loaded,
        "active_sessions_count": active_count,
        "planes": {
            "client_ux": "Next.js (external)",
            "backend_control": "ACTIVE (this server)",
            "orchestration_recovery": "ACTIVE (LangGraph + MemorySaver)",
            "integration": "READY (MCP Gateway — production pending)",
        },
        "governance": {
            "hitl_enabled": True,
            "audit_trail_enabled": True,
            "token_budget_enforcement": True,
            "mutating_tool_registry": "ACTIVE",
        },
    }


# ---------------------------------------------------------------------------
# ASGI entry point for production deployment
# ---------------------------------------------------------------------------
# Run with Uvicorn in development:
#   uvicorn main:app --host 0.0.0.0 --port 8000 --reload
#
# Run in production with Gunicorn + Uvicorn workers:
#   gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
#
# Docker:
#   CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]

if __name__ == "__main__":
    import uvicorn

    logger.info("Starting AegisFlow server via __main__ entry point...")

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,       # Enable auto-reload in development
        log_level="info",
        access_log=True,
        use_colors=True,
    )
