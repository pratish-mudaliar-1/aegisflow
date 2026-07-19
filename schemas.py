"""
AegisFlow :: schemas.py
=======================
Orchestration & Recovery Plane — Pydantic v2 State Schema Layer

This module defines the canonical type-safe data contracts that flow through
every boundary of the AegisFlow execution graph. All field mutations are
validated at assignment time via `model_config = ConfigDict(validate_assignment=True)`,
ensuring that no corrupt state can silently propagate through the state machine.

Architecture Plane: III — Orchestration & Recovery Plane
Governance Controls:
  - Immutable session identity via frozen `session_id` descriptor
  - Literal-constrained `validation_status` prevents out-of-contract state transitions
  - `audit_trail` enforces append semantics via the `append_audit_event` helper
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Section 1: Enumerated governance constants
# ---------------------------------------------------------------------------

class ValidationStatus(str, Enum):
    """
    Finite-state enumeration for the validation lifecycle of a single tool
    invocation within the AegisFlow state machine. Using a `str` base allows
    direct JSON serialization without a custom encoder.

    PENDING   — Initial state when a tool has been proposed but not yet reviewed.
    APPROVE   — Human operator or policy engine has cleared execution.
    EDIT      — Operator has modified tool arguments; re-validation is required.
    REJECT    — Operator has denied the action; graph transitions to safe halt.
    FAILED    — Tool execution raised an unrecoverable runtime exception.
    COMPLETED — Execution finished successfully; step is sealed in audit trail.
    """
    PENDING   = "PENDING"
    APPROVE   = "APPROVE"
    EDIT      = "EDIT"
    REJECT    = "REJECT"
    FAILED    = "FAILED"
    COMPLETED = "COMPLETED"


class InferencePlane(str, Enum):
    """
    Routing token emitted by the hybrid intelligence router after complexity
    evaluation. The state machine uses this to select between the local
    Qwen inference service and cloud frontier APIs.
    """
    LOCAL_PLANE = "LOCAL_PLANE"
    CLOUD_PLANE = "CLOUD_PLANE"


class MutatingToolRegistry(str, Enum):
    """
    Registry of all enterprise tools that carry data-mutation or financial
    authorization risk. Any `proposed_tool` matching this registry will trigger
    an automatic `human_validation` transition in the execution graph.

    Extend this registry to add new high-risk tool endpoints as the Integration
    Plane grows. Do NOT inline these strings in graph.py — always reference
    this enum to maintain a single source of truth for governance policy.
    """
    SEND_ENTERPRISE_EMAIL    = "send_enterprise_email"
    EXECUTE_DB_MUTATION      = "execute_db_mutation"
    AUTHORIZE_BUDGET         = "authorize_budget"
    WRITE_FILESYSTEM         = "write_filesystem"
    SCHEDULE_CALENDAR_INVITE = "schedule_calendar_invite"
    REVOKE_ACCESS_TOKEN      = "revoke_access_token"
    PUBLISH_EXTERNAL_WEBHOOK = "publish_external_webhook"


# ---------------------------------------------------------------------------
# Section 2: Audit event schema
# ---------------------------------------------------------------------------

class AuditEvent(BaseModel):
    """
    A single, immutable ledger entry in the append-only `audit_trail`. Each
    event captures a structured snapshot of what occurred, when, who/what
    triggered it, and a SHA-256 integrity fingerprint of its own payload.

    The `fingerprint` field enables external audit systems (e.g., PostgreSQL
    immutable audit tables) to verify that no event was silently modified after
    it was written into the in-memory state.
    """

    model_config = ConfigDict(frozen=True)  # Events are truly immutable once created

    event_type: str = Field(
        description=(
            "Category label for this audit entry. Examples: 'NODE_ENTRY', "
            "'TOOL_PROPOSED', 'VALIDATION_DECISION', 'TOOL_EXECUTED', "
            "'ROUTING_DECISION', 'SELF_HEALING_ATTEMPT', 'FATAL_ERROR'."
        )
    )
    node_name: str = Field(
        description="Name of the LangGraph node that generated this event."
    )
    timestamp_utc: str = Field(
        description="ISO 8601 UTC timestamp at event creation time."
    )
    payload: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Structured key-value context relevant to this event. "
            "May include: token counts, tool names, error messages, routing "
            "decisions, argument diffs, or operator feedback text."
        )
    )
    fingerprint: str = Field(
        description=(
            "SHA-256 hex digest of the serialized (event_type + node_name + "
            "timestamp_utc + payload) to guarantee immutability. Computed "
            "during event construction via `build_event`."
        )
    )

    @classmethod
    def build_event(
        cls,
        event_type: str,
        node_name: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> "AuditEvent":
        """
        Factory constructor that captures the current UTC timestamp, serializes
        the payload deterministically, and computes a SHA-256 fingerprint for
        tamper detection before constructing the frozen AuditEvent instance.

        Args:
            event_type: Category label string (see `event_type` field docs).
            node_name:  Name of the emitting graph node.
            payload:    Optional structured context dictionary.

        Returns:
            A validated, frozen AuditEvent ready for appending to audit_trail.
        """
        safe_payload = payload or {}
        ts = datetime.now(timezone.utc).isoformat()

        # Deterministic serialization ensures stable fingerprints across Python
        # interpreter restarts. Sort keys so dict ordering doesn't affect hash.
        raw_bytes = json.dumps(
            {
                "event_type": event_type,
                "node_name": node_name,
                "timestamp_utc": ts,
                "payload": safe_payload,
            },
            sort_keys=True,
            default=str,  # Safely coerce non-serializable objects to string
        ).encode("utf-8")

        fingerprint = hashlib.sha256(raw_bytes).hexdigest()

        return cls(
            event_type=event_type,
            node_name=node_name,
            timestamp_utc=ts,
            payload=safe_payload,
            fingerprint=fingerprint,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain dictionary representation for JSON serialization."""
        return self.model_dump()


# ---------------------------------------------------------------------------
# Section 3: Token budget tracking schema
# ---------------------------------------------------------------------------

class TokenBudgetTracker(BaseModel):
    """
    Implements the self-healing budget constraint formalized in the blueprint:

        B_token >= SUM(I_i + O_i)  for i in 1..n,  where n <= N_max

    This schema is embedded in AgentTaskState and updated after every LLM
    invocation. When `is_budget_exhausted()` returns True, the graph must
    immediately route to human_validation rather than attempt another recovery.
    """

    model_config = ConfigDict(validate_assignment=True)

    session_token_ceiling: int = Field(
        default=50_000,
        ge=1_000,
        description=(
            "Hard ceiling B_token — the absolute maximum tokens (input + output "
            "combined) permitted across the entire workflow session."
        )
    )
    total_input_tokens: int = Field(
        default=0,
        ge=0,
        description="Running sum of all input tokens consumed in this session."
    )
    total_output_tokens: int = Field(
        default=0,
        ge=0,
        description="Running sum of all output tokens produced in this session."
    )
    recovery_attempt_count: int = Field(
        default=0,
        ge=0,
        description=(
            "Current retry index n. The self-healing loop increments this on "
            "each correction attempt. When this reaches N_max (4), the graph "
            "must stop and raise a human validation interrupt."
        )
    )
    max_recovery_attempts: int = Field(
        default=4,
        ge=1,
        le=10,
        description="N_max — maximum number of self-healing correction attempts."
    )
    confidence_score: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description=(
            "Theta — confidence score computed by the critic diagnostic step. "
            "Must remain above theta_min (0.85) to continue automated recovery."
        )
    )
    confidence_threshold: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        description="theta_min — minimum acceptable confidence to bypass HITL."
    )

    @property
    def total_tokens_consumed(self) -> int:
        """Returns the combined input + output token count for this session."""
        return self.total_input_tokens + self.total_output_tokens

    def is_budget_exhausted(self) -> bool:
        """
        Returns True if the cumulative token usage has met or exceeded
        `session_token_ceiling`, indicating that no further LLM calls should
        be made without explicit human approval.
        """
        return self.total_tokens_consumed >= self.session_token_ceiling

    def is_recovery_limit_reached(self) -> bool:
        """
        Returns True if the self-healing engine has already made N_max
        correction attempts, requiring escalation to human-in-the-loop.
        """
        return self.recovery_attempt_count >= self.max_recovery_attempts

    def is_confidence_below_threshold(self) -> bool:
        """
        Returns True if the critic's confidence score has dropped below
        theta_min, triggering a mandatory human validation checkpoint.
        """
        return self.confidence_score < self.confidence_threshold

    def should_escalate_to_human(self) -> bool:
        """
        Composite check combining all three budget constraints. If any single
        constraint is violated, the graph must escalate to human validation.
        """
        return (
            self.is_budget_exhausted()
            or self.is_recovery_limit_reached()
            or self.is_confidence_below_threshold()
        )

    def record_invocation(self, input_tokens: int, output_tokens: int) -> None:
        """
        Update token counters after a single LLM API call completes.

        Args:
            input_tokens:  Number of tokens in the prompt payload.
            output_tokens: Number of tokens in the completion response.
        """
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens

    def increment_recovery_attempt(self) -> None:
        """Advance the recovery counter by one after each self-healing cycle."""
        self.recovery_attempt_count += 1


# ---------------------------------------------------------------------------
# Section 4: Primary state machine context
# ---------------------------------------------------------------------------

class AgentTaskState(BaseModel):
    """
    The canonical state container for a single AegisFlow workflow session.

    This object is the single source of truth passed between every LangGraph
    node in the execution graph. It is initialized once per user request and
    mutated via node return dictionaries — LangGraph merges partial updates
    into the running state object using its internal reducer logic.

    Pydantic v2's `validate_assignment=True` configuration ensures that every
    field update is type-checked at runtime, preventing any corrupted state
    from propagating downstream to tool invocations or audit systems.

    Governance Design Notes:
    ========================
    - `session_id` is immutable post-construction (validated by `frozen_session_id`).
    - `audit_trail` is append-only in practice; nodes MUST use `append_audit_event()`
      rather than directly replacing the list.
    - `validation_status` is constrained to the `ValidationStatus` enum literals.
    - `token_budget` enforces the blueprint's self-healing cost constraints.
    """

    model_config = ConfigDict(
        validate_assignment=True,
        use_enum_values=True,   # Store enum values (strings) not enum members
        populate_by_name=True,  # Allow field population by both alias and name
    )

    # ------------------------------------------------------------------
    # Identity & Input
    # ------------------------------------------------------------------

    session_id: str = Field(
        description=(
            "Unique UUID4 string assigned at session initialization. Acts as the "
            "LangGraph thread_id for checkpoint persistence and cross-request "
            "state recovery. Must not be mutated after the session is opened."
        )
    )

    original_input: str = Field(
        description=(
            "The raw, unformatted natural language command exactly as submitted "
            "by the human operator. Preserved verbatim throughout the graph "
            "lifecycle for audit and self-healing reference."
        )
    )

    # ------------------------------------------------------------------
    # Task decomposition tracking
    # ------------------------------------------------------------------

    task_steps: List[Dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Ordered array of decomposed execution plan steps. Each dict should "
            "contain at minimum: 'step_id' (int), 'description' (str), "
            "'status' ('pending'|'running'|'completed'|'failed'), and "
            "'tool_name' (Optional[str]). Populated by the `parse_input` node."
        )
    )

    active_step_index: int = Field(
        default=0,
        ge=0,
        description=(
            "Zero-based pointer into `task_steps` identifying the current "
            "execution target. Incremented by `execute_tool` upon successful "
            "step completion. Never decremented — steps are always forward-only."
        )
    )

    # ------------------------------------------------------------------
    # Tool invocation context
    # ------------------------------------------------------------------

    proposed_tool: Optional[str] = Field(
        default=None,
        description=(
            "The exact tool identifier string selected by the routing agent "
            "for the current execution step. Matched against MutatingToolRegistry "
            "to determine if human validation is required before execution."
        )
    )

    tool_arguments: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Strict JSON-serializable argument payload for the proposed tool. "
            "Must conform to the target tool's MCP JSON-RPC parameter schema. "
            "May be modified by the human_validation node if the operator "
            "selects 'EDIT' action."
        )
    )

    # ------------------------------------------------------------------
    # Validation lifecycle
    # ------------------------------------------------------------------

    validation_status: str = Field(
        default=ValidationStatus.PENDING.value,
        description=(
            "Current phase of the tool validation lifecycle. Must be one of: "
            "PENDING, APPROVE, EDIT, REJECT, FAILED, COMPLETED. "
            "Constrained to ValidationStatus enum values."
        )
    )

    user_feedback: str = Field(
        default="",
        description=(
            "Free-text annotation provided by the human operator during a "
            "human_validation intercept. Captured during EDIT or REJECT "
            "decisions and written to audit_trail for compliance records."
        )
    )

    # ------------------------------------------------------------------
    # Self-healing & error tracking
    # ------------------------------------------------------------------

    execution_errors: List[str] = Field(
        default_factory=list,
        description=(
            "Chronological list of runtime error strings encountered during "
            "this session. Each entry is a structured error representation: "
            "'[TIMESTAMP] [NODE_NAME] ErrorType: message'. "
            "Fed into the critic diagnostic parser during self-healing loops."
        )
    )

    token_budget: TokenBudgetTracker = Field(
        default_factory=TokenBudgetTracker,
        description=(
            "Embedded token budget controller enforcing the blueprint's "
            "self-healing cost constraints (B_token, N_max, theta_min)."
        )
    )

    # ------------------------------------------------------------------
    # Routing state
    # ------------------------------------------------------------------

    inference_route: Optional[str] = Field(
        default=None,
        description=(
            "The routing decision emitted by `determine_inference_route()`. "
            "Either 'LOCAL_PLANE' (Qwen3-Coder local inference) or "
            "'CLOUD_PLANE' (Claude 3.5 Sonnet / GPT-4o frontier API)."
        )
    )

    # ------------------------------------------------------------------
    # Append-only audit ledger
    # ------------------------------------------------------------------

    audit_trail: List[Dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Absolute, append-only history ledger for this workflow session. "
            "Each entry is a serialized AuditEvent dictionary containing: "
            "event_type, node_name, timestamp_utc, payload, fingerprint. "
            "CRITICAL: Nodes must ONLY add to this list, never remove or replace. "
            "Use the `append_audit_event()` helper to guarantee correct semantics."
        )
    )

    # ------------------------------------------------------------------
    # Field validators
    # ------------------------------------------------------------------

    @field_validator("session_id")
    @classmethod
    def session_id_must_be_nonempty(cls, v: str) -> str:
        """Ensure session_id is a non-empty string. UUIDs are validated length."""
        stripped = v.strip()
        if not stripped:
            raise ValueError(
                "session_id must be a non-empty string. "
                "Provide a UUID4 generated via `str(uuid.uuid4())`."
            )
        return stripped

    @field_validator("original_input")
    @classmethod
    def original_input_must_be_nonempty(cls, v: str) -> str:
        """Reject empty or whitespace-only user queries at schema boundary."""
        stripped = v.strip()
        if not stripped:
            raise ValueError(
                "original_input cannot be empty or whitespace-only. "
                "The workflow requires a valid human command to operate."
            )
        return stripped

    @field_validator("validation_status")
    @classmethod
    def validation_status_must_be_valid(cls, v: str) -> str:
        """
        Ensure validation_status is constrained to the ValidationStatus enum.
        Provides a descriptive error listing all valid states on rejection.
        """
        valid_values = {s.value for s in ValidationStatus}
        if v not in valid_values:
            raise ValueError(
                f"validation_status '{v}' is not a valid state. "
                f"Must be one of: {sorted(valid_values)}. "
                f"Consult ValidationStatus enum in schemas.py."
            )
        return v

    @model_validator(mode="after")
    def active_step_index_within_bounds(self) -> "AgentTaskState":
        """
        After full model construction, ensure active_step_index is within the
        bounds of the task_steps array (or 0 if steps are not yet populated).
        This validator runs after all fields are set.
        """
        if self.task_steps and self.active_step_index >= len(self.task_steps):
            raise ValueError(
                f"active_step_index ({self.active_step_index}) exceeds the "
                f"number of task_steps ({len(self.task_steps)}). "
                f"The step pointer must remain within array bounds."
            )
        return self

    # ------------------------------------------------------------------
    # Audit trail helper methods
    # ------------------------------------------------------------------

    def append_audit_event(
        self,
        event_type: str,
        node_name: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> "AgentTaskState":
        """
        Construct a new AuditEvent and append its dictionary representation to
        `audit_trail`. This is the ONLY sanctioned way to write audit records.

        The method returns `self` to allow for a fluent chaining pattern in
        node functions, though nodes must still return state dicts to LangGraph.

        Args:
            event_type: Category string (e.g., 'NODE_ENTRY', 'TOOL_PROPOSED').
            node_name:  Name of the emitting LangGraph node.
            payload:    Optional context dict (token counts, error strings, etc).

        Returns:
            self — mutated in place with the new audit event appended.
        """
        event = AuditEvent.build_event(
            event_type=event_type,
            node_name=node_name,
            payload=payload,
        )
        # Direct list append preserves the existing references; we do NOT
        # reassign the field (which would trigger the validator unnecessarily).
        self.audit_trail.append(event.to_dict())
        return self

    def record_execution_error(
        self,
        node_name: str,
        error_type: str,
        error_message: str,
    ) -> None:
        """
        Append a structured error string to `execution_errors` and simultaneously
        write a FATAL_ERROR audit event to `audit_trail`.

        Args:
            node_name:     Name of the node where the error occurred.
            error_type:    Exception class name (e.g., 'httpx.ConnectError').
            error_message: Full exception message string.
        """
        ts = datetime.now(timezone.utc).isoformat()
        structured_error = f"[{ts}] [{node_name}] {error_type}: {error_message}"
        self.execution_errors.append(structured_error)

        self.append_audit_event(
            event_type="EXECUTION_ERROR",
            node_name=node_name,
            payload={
                "error_type": error_type,
                "error_message": error_message,
                "total_errors_in_session": len(self.execution_errors),
            },
        )


# ---------------------------------------------------------------------------
# Section 5: API request/response schemas
# ---------------------------------------------------------------------------

class RunWorkflowRequest(BaseModel):
    """
    Validated request payload for the POST /api/v1/workflow/run endpoint.

    FastAPI automatically deserializes and validates the JSON request body
    against this schema, returning a structured 422 Unprocessable Entity
    response if any field fails validation — before the endpoint handler runs.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    user_input: str = Field(
        min_length=1,
        max_length=16_000,
        description=(
            "Raw natural language command from the human operator. Maximum "
            "16,000 characters to prevent token budget exhaustion at ingestion."
        )
    )

    proposed_tool_override: Optional[str] = Field(
        default=None,
        description=(
            "Optional: Pre-specify a tool for testing/debugging. When provided, "
            "the graph will evaluate this tool for approval gating rather than "
            "waiting for the routing agent to select one."
        )
    )

    token_budget_override: Optional[int] = Field(
        default=None,
        ge=1_000,
        le=200_000,
        description=(
            "Optional: Override the default 50,000-token session ceiling. "
            "Useful for long-running document synthesis tasks requiring "
            "the full Qwen3-Coder 256K context window."
        )
    )


class WorkflowStatusResponse(BaseModel):
    """
    Structured response body for non-streaming status queries.
    Returned by GET /api/v1/workflow/status/{session_id}.
    """

    session_id: str = Field(description="The workflow thread identifier.")
    validation_status: str = Field(description="Current validation lifecycle state.")
    active_step_index: int = Field(description="Index of the step currently executing.")
    total_steps: int = Field(description="Total number of decomposed task steps.")
    inference_route: Optional[str] = Field(description="Routing decision (LOCAL/CLOUD).")
    error_count: int = Field(description="Number of execution errors in this session.")
    audit_event_count: int = Field(description="Total audit events logged to trail.")
    token_usage: Dict[str, Any] = Field(description="Token budget summary dictionary.")


class HumanValidationDecision(BaseModel):
    """
    Request payload for POST /api/v1/workflow/resume — used to inject the
    human operator's decision back into a paused graph thread.

    This schema is consumed by the /resume endpoint after a HUMAN_INTERRUPT_REQUIRED
    event has been streamed to the frontend.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    session_id: str = Field(description="Thread ID of the paused workflow to resume.")

    decision: ValidationStatus = Field(
        description=(
            "The operator's validation decision. Must be APPROVE, EDIT, or REJECT. "
            "PENDING, FAILED, and COMPLETED are not valid operator inputs."
        )
    )

    feedback_message: str = Field(
        default="",
        max_length=4_000,
        description="Optional explanation or audit note from the operator."
    )

    edited_arguments: Optional[Dict[str, Any]] = Field(
        default=None,
        description=(
            "Required when decision is EDIT. Must contain the full, corrected "
            "argument payload to replace the original `tool_arguments`."
        )
    )

    @model_validator(mode="after")
    def edited_arguments_required_on_edit(self) -> "HumanValidationDecision":
        """Enforce that EDIT decisions always supply a corrected arguments dict."""
        if self.decision == ValidationStatus.EDIT and not self.edited_arguments:
            raise ValueError(
                "When decision is 'EDIT', you must supply 'edited_arguments' "
                "containing the corrected tool parameter payload."
            )
        return self
