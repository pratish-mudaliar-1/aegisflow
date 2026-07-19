"""
AegisFlow Smoke Test
Runs: health check, low-risk workflow, high-risk HITL workflow + resume
"""
import httpx
import json

BASE = "http://localhost:8000"


def print_sse_event(ev: dict, capture_id: list) -> None:
    event_type = ev.get("event", "?")
    print(f"  [{event_type}]", end="")
    if ev.get("node_completed"):
        print(f" node={ev['node_completed']}", end="")
    if ev.get("final_validation_status"):
        print(f" final_status={ev['final_validation_status']}", end="")
    if ev.get("inference_route"):
        print(f" route={ev['inference_route']}", end="")
    sid = ev.get("session_id")
    if sid and not capture_id:
        capture_id.append(sid)
    if event_type == "HUMAN_INTERRUPT_REQUIRED":
        print(f" => PAUSED for approval", end="")
    if event_type == "CRITICAL_FAILURE":
        print(f" ERROR={ev.get('error_message', '')[:80]}", end="")
    print()


# ── 1. Health ────────────────────────────────────────────────────────────────
print("=" * 60)
print("1. GET /api/v1/health")
print("=" * 60)
r = httpx.get(f"{BASE}/api/v1/health", timeout=5)
data = r.json()
print(f"  status:          {data['status']}")
print(f"  graph_loaded:    {data['graph_engine_loaded']}")
print(f"  active_sessions: {data['active_sessions_count']}")
print()

# ── 2. Low-risk workflow ─────────────────────────────────────────────────────
print("=" * 60)
print("2. POST /run  [low-risk: text summarization]")
print("=" * 60)
with httpx.stream(
    "POST",
    f"{BASE}/api/v1/workflow/run",
    json={"user_input": "Summarize the quarterly sales report and extract key metrics"},
    timeout=30,
) as resp:
    for line in resp.iter_lines():
        if line.startswith("data:"):
            ev = json.loads(line[5:])
            print_sse_event(ev, [])
print()

# ── 3. High-risk workflow (HITL) ─────────────────────────────────────────────
print("=" * 60)
print("3. POST /run  [high-risk: authorize_budget => HITL expected]")
print("=" * 60)
capture_id: list = []
with httpx.stream(
    "POST",
    f"{BASE}/api/v1/workflow/run",
    json={
        "user_input": "Authorize the Q4 budget of 50000 USD for the marketing campaign",
        "proposed_tool_override": "authorize_budget",
    },
    timeout=30,
) as resp:
    for line in resp.iter_lines():
        if line.startswith("data:"):
            ev = json.loads(line[5:])
            print_sse_event(ev, capture_id)

session_id = capture_id[0] if capture_id else None
print(f"\n  Captured session_id: {session_id}")
print()

# ── 4. Resume with APPROVE ───────────────────────────────────────────────────
if session_id:
    print("=" * 60)
    print("4. POST /resume  [APPROVE decision]")
    print("=" * 60)
    with httpx.stream(
        "POST",
        f"{BASE}/api/v1/workflow/resume",
        json={
            "session_id": session_id,
            "decision": "APPROVE",
            "feedback_message": "Approved after manual budget review by CFO.",
        },
        timeout=30,
    ) as resp:
        for line in resp.iter_lines():
            if line.startswith("data:"):
                ev = json.loads(line[5:])
                print_sse_event(ev, [])
    print()

# ── 5. Status query ──────────────────────────────────────────────────────────
if session_id:
    print("=" * 60)
    print("5. GET /status/{session_id}")
    print("=" * 60)
    r = httpx.get(f"{BASE}/api/v1/workflow/status/{session_id}", timeout=5)
    if r.status_code == 200:
        s = r.json()
        print(f"  validation_status:  {s['validation_status']}")
        print(f"  active_step_index:  {s['active_step_index']}")
        print(f"  total_steps:        {s['total_steps']}")
        print(f"  inference_route:    {s['inference_route']}")
        print(f"  audit_events:       {s['audit_event_count']}")
        print(f"  errors:             {s['error_count']}")
        print(f"  tokens_consumed:    {s['token_usage'].get('total_consumed', '?')}")
    else:
        print(f"  HTTP {r.status_code}: {r.text[:200]}")

print()
print("SMOKE TEST COMPLETE")
