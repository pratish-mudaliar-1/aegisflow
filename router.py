"""
AegisFlow :: router.py
======================
Orchestration & Recovery Plane — Hybrid Intelligence Inference Router

This module implements the asynchronous routing layer that dynamically selects
between the local Qwen3-Coder MoE inference plane and cloud frontier APIs
(Claude 3.5 Sonnet / GPT-4o) based on a real-time complexity evaluation of
the incoming task profile.

Design Philosophy:
==================
The router acts as the cost-control gateway of the AegisFlow system. By
intercepting every task before LLM invocation and categorizing it as SIMPLE
or COMPLEX, it prevents low-value operations from consuming expensive cloud
API budget — directly addressing the "Unconstrained API Costs & Token Bloat"
enterprise failure mode described in the blueprint.

Routing Logic:
==============
  SIMPLE (LOCAL_PLANE):  Text extraction, document summarization, note synthesis,
                         file content parsing, format conversion, code generation
                         for deterministic tasks. Routes to local Qwen3-Coder.

  COMPLEX (CLOUD_PLANE): Multi-party calendar coordination, financial transaction
                         authorization, external legal/compliance reasoning,
                         cross-system negotiation protocols, high-ambiguity
                         natural language understanding. Routes to cloud frontier.

  DEFAULT (CLOUD_PLANE): Any routing evaluation failure — network timeout,
                         malformed response, model unavailability — defaults
                         to the cloud plane for workload continuity.

Architecture Plane: III — Orchestration & Recovery Plane
Dependencies:
  - httpx (>=0.27.0): Async HTTP client for Ollama REST API calls
  - schemas.py: AgentTaskState, AuditEvent for structured logging
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict

import httpx

from schemas import AgentTaskState, AuditEvent, InferencePlane

# ---------------------------------------------------------------------------
# Module-level logger — all routing decisions are logged at INFO and WARN
# levels so that the system feed in the Client UX Plane can surface them.
# ---------------------------------------------------------------------------
logger = logging.getLogger("aegisflow.router")
logger.setLevel(logging.DEBUG)

# ---------------------------------------------------------------------------
# Router configuration constants
# ---------------------------------------------------------------------------

OLLAMA_BASE_URL: str = "http://localhost:11434/api/generate"
"""
Ollama REST API endpoint for local inference. Routing classification uses
the lightweight qwen3:0.6b model for instant SIMPLE/COMPLEX decisions.
Falls back to CLOUD_PLANE if this endpoint is unreachable.
"""

LOCAL_MODEL_NAME: str = "qwen3:0.6b"
"""
Lightweight 0.6B Qwen3 model for binary routing classification.
Fast (<1s on CPU) and sufficient for SIMPLE/COMPLEX binary outputs.
For actual task execution, the larger qwen3:8b or qwen3:14b is used.
"""

# ---------------------------------------------------------------------------
# Cloud plane configuration (Groq — free tier, no payment required)
# ---------------------------------------------------------------------------
# Groq offers 30 req/min free on Llama-3.3-70B-Versatile with no card needed.
# Sign up at https://console.groq.com → API Keys → Create key
# Set the env var: GROQ_API_KEY=gsk_...
GROQ_API_BASE: str = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL: str = "llama-3.3-70b-versatile"

# Gemini Flash as fallback (15 req/min free, no card needed)
# Get key at https://aistudio.google.com/apikey
# Set the env var: GEMINI_API_KEY=AIza...
GEMINI_API_BASE: str = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
GEMINI_MODEL: str = "gemini-2.0-flash"

ROUTER_REQUEST_TIMEOUT_SECONDS: float = 8.0
"""
Maximum time in seconds to wait for the local inference service to respond
to the complexity evaluation prompt. Set conservatively to 8 seconds to
prevent slow routing from blocking the overall workflow latency SLA.
If the timeout is exceeded, the router defaults to CLOUD_PLANE.
"""

COMPLEXITY_PROMPT_TEMPLATE: str = """
You are a task complexity classifier for an enterprise AI orchestration system.

Analyze the following user task and classify it as either SIMPLE or COMPLEX.

Classification Criteria:
- SIMPLE: Local text processing, document reading, file extraction, note synthesis,
  code generation for deterministic scripts, format conversion, summarization.
  These tasks do NOT involve external parties, financial authorization, or
  mutating production database records.

- COMPLEX: Multi-party calendar scheduling requiring negotiation, financial
  transaction authorization (budget approval, invoice processing), cross-system
  legal or compliance reasoning, external email coordination with named parties,
  high-ambiguity queries requiring deep world knowledge or judgment.

User Task:
-----------
{task_description}
-----------

Tool Proposed (if known): {proposed_tool}

Respond with exactly one word: SIMPLE or COMPLEX.
Do not provide any explanation. Your entire response must be only the word SIMPLE or COMPLEX.
""".strip()

# High-risk tool names that should always be classified as COMPLEX regardless
# of the LLM's routing evaluation. This list mirrors MutatingToolRegistry and
# provides a hard-coded safety net in case the model makes an incorrect
# classification decision.
ALWAYS_COMPLEX_TOOLS: frozenset = frozenset({
    "send_enterprise_email",
    "execute_db_mutation",
    "authorize_budget",
    "revoke_access_token",
    "publish_external_webhook",
    "schedule_calendar_invite",
})

# Keywords in the raw user input that signal high-risk operations requiring
# cloud-tier reasoning, regardless of the LLM's classification output.
COMPLEX_KEYWORD_SIGNALS: tuple = (
    "budget",
    "authorize",
    "payment",
    "transfer funds",
    "approve invoice",
    "send email to",
    "calendar invite",
    "schedule meeting with",
    "database migration",
    "delete records",
    "drop table",
    "revoke access",
    "gdpr erasure",
    "compliance report",
    "legal review",
)


# ---------------------------------------------------------------------------
# Core routing function
# ---------------------------------------------------------------------------

async def determine_inference_route(state: AgentTaskState) -> str:
    """
    Asynchronous hybrid intelligence router that determines whether a given
    workflow task should be handled by the local Qwen3-Coder MoE service
    (LOCAL_PLANE) or escalated to cloud frontier LLM APIs (CLOUD_PLANE).

    The routing algorithm operates in three tiers:
    1. Hard-coded signal detection: Immediately returns CLOUD_PLANE for tools
       registered in ALWAYS_COMPLEX_TOOLS or tasks containing COMPLEX_KEYWORD_SIGNALS.
       This bypass ensures governance policy is enforced without LLM involvement.
    2. Local LLM classification: Sends a structured prompt to the Ollama endpoint
       requesting a binary SIMPLE/COMPLEX classification. The model must respond
       with exactly one word.
    3. Secure default fallback: Any exception (connection refused, timeout,
       malformed JSON, parsing failure) causes an immediate CLOUD_PLANE return
       to guarantee workload availability even when local inference is offline.

    After every routing decision — including failures — a structured AuditEvent
    is appended to `state.audit_trail` recording the decision rationale.

    Args:
        state: The current AgentTaskState containing `original_input`,
               `proposed_tool`, and `audit_trail` fields.

    Returns:
        "LOCAL_PLANE" — Task is classified as low-risk; use local Qwen3-Coder.
        "CLOUD_PLANE" — Task is classified as complex or high-risk; use frontier API.
    """
    node_name = "determine_inference_route"

    logger.info(
        "[%s] Initiating routing evaluation for session_id=%s | "
        "proposed_tool=%s | input_length=%d chars",
        node_name,
        state.session_id,
        state.proposed_tool,
        len(state.original_input),
    )

    # ------------------------------------------------------------------
    # Tier 1: Hard-coded governance bypass — high-risk signal detection
    # ------------------------------------------------------------------
    # Check if the proposed tool is in the always-complex registry.
    # This check executes synchronously and does not make any network calls,
    # ensuring zero latency overhead for high-risk tool interceptions.
    if state.proposed_tool and state.proposed_tool in ALWAYS_COMPLEX_TOOLS:
        route = InferencePlane.CLOUD_PLANE.value
        reason = (
            f"Proposed tool '{state.proposed_tool}' is registered in "
            f"ALWAYS_COMPLEX_TOOLS governance registry. Bypassing LLM "
            f"classification and routing directly to CLOUD_PLANE."
        )
        logger.warning("[%s] %s", node_name, reason)
        _write_routing_audit_event(
            state=state,
            route=route,
            classification_source="GOVERNANCE_BYPASS_TOOL_REGISTRY",
            reason=reason,
        )
        return route

    # Check raw input text for known complex operation keywords.
    # Case-insensitive matching catches natural language variations.
    lowered_input = state.original_input.lower()
    matched_keyword = next(
        (kw for kw in COMPLEX_KEYWORD_SIGNALS if kw in lowered_input),
        None,
    )
    if matched_keyword:
        route = InferencePlane.CLOUD_PLANE.value
        reason = (
            f"Input contains complexity keyword signal: '{matched_keyword}'. "
            f"Bypassing LLM classification and routing to CLOUD_PLANE."
        )
        logger.warning("[%s] %s", node_name, reason)
        _write_routing_audit_event(
            state=state,
            route=route,
            classification_source="GOVERNANCE_BYPASS_KEYWORD_SIGNAL",
            reason=reason,
        )
        return route

    # ------------------------------------------------------------------
    # Tier 2: Local LLM complexity classification via Ollama REST API
    # ------------------------------------------------------------------
    # Build the structured classification prompt with task context.
    complexity_prompt = COMPLEXITY_PROMPT_TEMPLATE.format(
        task_description=state.original_input,
        proposed_tool=state.proposed_tool if state.proposed_tool else "Not yet determined",
    )

    logger.debug(
        "[%s] Sending complexity classification prompt to local inference at %s",
        node_name,
        OLLAMA_BASE_URL,
    )

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=3.0,           # Connection timeout: 3s
                read=ROUTER_REQUEST_TIMEOUT_SECONDS,  # Read timeout: 8s
                write=3.0,             # Write timeout: 3s
                pool=2.0,              # Pool acquisition timeout: 2s
            )
        ) as client:
            response = await client.post(
                OLLAMA_BASE_URL,
                json={
                    "model": LOCAL_MODEL_NAME,
                    "prompt": complexity_prompt,
                    "stream": False,        # Disable streaming for a single classification token
                    "options": {
                        "temperature": 0.0,  # Deterministic output — no creativity needed
                        "num_predict": 5,    # Limit output to 5 tokens (SIMPLE or COMPLEX)
                        "stop": ["\n", ".", " "],  # Halt after the first word
                    },
                },
            )

        # Validate HTTP response status before parsing body
        if response.status_code != 200:
            raise httpx.HTTPStatusError(
                message=(
                    f"Ollama inference service returned HTTP {response.status_code}. "
                    f"Response body: {response.text[:300]}"
                ),
                request=response.request,
                response=response,
            )

        response_body: Dict[str, Any] = response.json()
        raw_decision: str = response_body.get("response", "").strip().upper()

        logger.debug(
            "[%s] Local inference classification response: '%s'",
            node_name,
            raw_decision,
        )

        # Validate that the model produced a usable classification token.
        # Accept variations like 'SIMPLE.' or 'COMPLEX\n' by checking prefix.
        if raw_decision.startswith("SIMPLE"):
            route = InferencePlane.LOCAL_PLANE.value
            reason = (
                f"Local Qwen3-Coder classified task as SIMPLE. "
                f"Routing to LOCAL_PLANE (Ollama) for zero-cost inference."
            )
            logger.info("[%s] Routing decision: LOCAL_PLANE", node_name)
        elif raw_decision.startswith("COMPLEX"):
            route = InferencePlane.CLOUD_PLANE.value
            reason = (
                f"Local Qwen3-Coder classified task as COMPLEX. "
                f"Routing to CLOUD_PLANE (frontier LLM) for high-tier reasoning."
            )
            logger.info("[%s] Routing decision: CLOUD_PLANE (COMPLEX classification)", node_name)
        else:
            # Ambiguous or unexpected response — escalate to cloud for safety
            route = InferencePlane.CLOUD_PLANE.value
            reason = (
                f"Local inference returned ambiguous classification token: "
                f"'{raw_decision[:50]}'. Cannot determine complexity safely. "
                f"Defaulting to CLOUD_PLANE for workload protection."
            )
            logger.warning("[%s] Ambiguous classification response. %s", node_name, reason)

        _write_routing_audit_event(
            state=state,
            route=route,
            classification_source="LOCAL_LLM_CLASSIFICATION",
            reason=reason,
        )
        return route

    except httpx.ConnectError as exc:
        # Local Ollama service is offline or not reachable on localhost:11434
        error_message = (
            f"Cannot connect to local Ollama inference service at {OLLAMA_BASE_URL}. "
            f"Ensure Ollama is running with 'ollama serve' and the model "
            f"'{LOCAL_MODEL_NAME}' is loaded via 'ollama pull {LOCAL_MODEL_NAME}'. "
            f"Connection error: {exc}"
        )
        logger.error("[%s] ConnectError: %s", node_name, error_message)
        return _fallback_to_cloud_plane(
            state=state,
            node_name=node_name,
            error_type="httpx.ConnectError",
            error_message=error_message,
        )

    except httpx.TimeoutException as exc:
        # Local inference exceeded the configured timeout budget
        error_message = (
            f"Local inference service at {OLLAMA_BASE_URL} did not respond within "
            f"{ROUTER_REQUEST_TIMEOUT_SECONDS}s timeout budget. The model may be "
            f"under load or the network path may be congested. "
            f"Timeout error: {exc}"
        )
        logger.error("[%s] TimeoutException: %s", node_name, error_message)
        return _fallback_to_cloud_plane(
            state=state,
            node_name=node_name,
            error_type="httpx.TimeoutException",
            error_message=error_message,
        )

    except httpx.HTTPStatusError as exc:
        # Ollama returned a non-200 HTTP status
        error_message = (
            f"Ollama service returned error HTTP status {exc.response.status_code}. "
            f"Response body preview: {exc.response.text[:200]}. "
            f"Full error: {exc}"
        )
        logger.error("[%s] HTTPStatusError: %s", node_name, error_message)
        return _fallback_to_cloud_plane(
            state=state,
            node_name=node_name,
            error_type="httpx.HTTPStatusError",
            error_message=error_message,
        )

    except (KeyError, ValueError, TypeError) as exc:
        # JSON parsing failed or response structure was unexpected
        error_message = (
            f"Failed to parse classification response from local inference service. "
            f"The response body may not be valid JSON or the 'response' key "
            f"may be missing. Parse error: {exc}"
        )
        logger.error("[%s] ResponseParseError: %s", node_name, error_message)
        return _fallback_to_cloud_plane(
            state=state,
            node_name=node_name,
            error_type="ResponseParseError",
            error_message=error_message,
        )

    except Exception as exc:
        # Catch-all for unexpected exceptions — never let routing crash the graph
        error_message = (
            f"Unexpected exception during routing evaluation. "
            f"Exception type: {type(exc).__name__}. Details: {exc}"
        )
        logger.critical("[%s] UNEXPECTED_EXCEPTION: %s", node_name, error_message)
        return _fallback_to_cloud_plane(
            state=state,
            node_name=node_name,
            error_type=type(exc).__name__,
            error_message=error_message,
        )


# ---------------------------------------------------------------------------
# Cloud LLM execution (Groq free tier → Gemini Flash fallback)
# ---------------------------------------------------------------------------

async def _call_cloud_llm(
    messages: list,
    max_tokens: int = 2048,
    temperature: float = 0.3,
) -> str:
    """
    Execute a chat completion against a free cloud LLM.

    Priority:
    1. Groq API (Llama-3.3-70B-Versatile) — 30 req/min free, no credit card
       Sign up: https://console.groq.com → API Keys → Create Key
       Set env: GROQ_API_KEY=gsk_...

    2. Google Gemini Flash — 15 req/min free, no credit card
       Get key: https://aistudio.google.com/apikey
       Set env: GEMINI_API_KEY=AIza...

    3. OpenRouter free models — no card needed for free-tier models
       Set env: OPENROUTER_API_KEY=sk-or-...

    Args:
        messages:    OpenAI-format chat message list.
        max_tokens:  Maximum tokens in the response.
        temperature: Sampling temperature.

    Returns:
        The assistant message content string.

    Raises:
        RuntimeError if all providers fail.
    """
    import os

    headers_base = {"Content-Type": "application/json"}

    # ── Provider 1: Groq ─────────────────────────────────────────────
    groq_key = os.getenv("GROQ_API_KEY", "")
    if groq_key:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
                resp = await client.post(
                    GROQ_API_BASE,
                    headers={**headers_base, "Authorization": f"Bearer {groq_key}"},
                    json={
                        "model": GROQ_MODEL,
                        "messages": messages,
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                    },
                )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            logger.info("[_call_cloud_llm] Groq responded. tokens=%s",
                        data.get("usage", {}).get("total_tokens"))
            return content
        except Exception as exc:
            logger.warning("[_call_cloud_llm] Groq failed (%s). Trying Gemini.", exc)

    # ── Provider 2: Gemini Flash ─────────────────────────────────────
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    if gemini_key:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
                resp = await client.post(
                    f"{GEMINI_API_BASE}?key={gemini_key}",
                    headers=headers_base,
                    json={
                        "model": GEMINI_MODEL,
                        "messages": messages,
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                    },
                )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            logger.info("[_call_cloud_llm] Gemini responded.")
            return content
        except Exception as exc:
            logger.warning("[_call_cloud_llm] Gemini failed (%s). Trying OpenRouter.", exc)

    # ── Provider 3: OpenRouter free tier ─────────────────────────────
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
    if openrouter_key:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
                resp = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        **headers_base,
                        "Authorization": f"Bearer {openrouter_key}",
                        "HTTP-Referer": "http://localhost:3001",
                        "X-Title": "AegisFlow",
                    },
                    json={
                        "model": "meta-llama/llama-3.1-8b-instruct:free",  # Free model
                        "messages": messages,
                        "max_tokens": max_tokens,
                    },
                )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            logger.info("[_call_cloud_llm] OpenRouter responded.")
            return content
        except Exception as exc:
            logger.warning("[_call_cloud_llm] OpenRouter failed (%s).", exc)

    raise RuntimeError(
        "All cloud LLM providers failed or no API keys configured. "
        "Set GROQ_API_KEY, GEMINI_API_KEY, or OPENROUTER_API_KEY."
    )


# ---------------------------------------------------------------------------
# Private helper functions
# ---------------------------------------------------------------------------

def _fallback_to_cloud_plane(
    state: AgentTaskState,
    node_name: str,
    error_type: str,
    error_message: str,
) -> str:
    """
    Secure default fallback that returns CLOUD_PLANE when any routing error
    occurs. Also records the error in `state.execution_errors` and writes
    a structured audit event for operational observability.

    This function implements the blueprint's requirement:
      'provide robust try/except coverage that logs issues and defaults
       securely to CLOUD_PLANE to protect workload availability.'

    Args:
        state:         Current AgentTaskState (mutated in place for audit trail).
        node_name:     Name of the calling context for the audit record.
        error_type:    Exception class name for structured error log.
        error_message: Full exception message for diagnostic purposes.

    Returns:
        "CLOUD_PLANE" — always.
    """
    route = InferencePlane.CLOUD_PLANE.value

    # Record in execution_errors for self-healing engine consumption
    state.record_execution_error(
        node_name=node_name,
        error_type=error_type,
        error_message=error_message,
    )

    _write_routing_audit_event(
        state=state,
        route=route,
        classification_source="FALLBACK_ON_ERROR",
        reason=(
            f"Routing evaluation failed due to {error_type}. "
            f"Defaulting to CLOUD_PLANE for workload continuity. "
            f"Error: {error_message[:200]}"
        ),
    )

    logger.warning(
        "[%s] Fallback routing decision: CLOUD_PLANE (due to %s)",
        node_name,
        error_type,
    )
    return route


def _write_routing_audit_event(
    state: AgentTaskState,
    route: str,
    classification_source: str,
    reason: str,
) -> None:
    """
    Write a ROUTING_DECISION audit event to the state's audit trail, capturing
    the full decision context for compliance and operational review.

    Args:
        state:                  Current AgentTaskState to append the event to.
        route:                  The routing decision string (LOCAL_PLANE/CLOUD_PLANE).
        classification_source:  How the decision was made (e.g., 'LOCAL_LLM_CLASSIFICATION').
        reason:                 Human-readable explanation of the routing decision.
    """
    state.append_audit_event(
        event_type="ROUTING_DECISION",
        node_name="determine_inference_route",
        payload={
            "selected_route": route,
            "classification_source": classification_source,
            "reason": reason,
            "proposed_tool": state.proposed_tool,
            "input_preview": state.original_input[:150] + "..."
            if len(state.original_input) > 150
            else state.original_input,
            "routing_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        },
    )
