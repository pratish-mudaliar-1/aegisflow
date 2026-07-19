<div align="center">

# ⚡ AegisFlow

### Enterprise-Grade AI Workflow Orchestration Platform

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111+-009688?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.x-FF6B6B?style=flat)](https://langchain-ai.github.io/langgraph/)
[![Next.js](https://img.shields.io/badge/Next.js-15-000000?style=flat&logo=next.js&logoColor=white)](https://nextjs.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

*A production-ready, human-in-the-loop AI orchestration system with hybrid local/cloud inference routing, real-time SSE streaming, encrypted secrets vault, and enterprise governance controls.*

</div>

---

## 🧠 What is AegisFlow?

AegisFlow is a full-stack AI workflow execution platform designed to solve the core enterprise AI failure modes: **unconstrained API costs**, **missing human oversight**, and **zero audit trails**.

It combines a **LangGraph state machine** for deterministic workflow execution with a **hybrid intelligence router** that dynamically selects between a local Ollama model (zero cost) and cloud frontier APIs (Groq / Gemini) based on real-time task complexity evaluation — ensuring you only pay for cloud inference when it's actually necessary.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    CLIENT UX PLANE                          │
│             Next.js 15  ·  TypeScript  ·  SSE              │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTP / SSE
┌────────────────────────▼────────────────────────────────────┐
│                 BACKEND CONTROL PLANE                       │
│              FastAPI  ·  Uvicorn  ·  SQLite                 │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│            ORCHESTRATION & RECOVERY PLANE                   │
│         LangGraph StateGraph  ·  MemorySaver                │
│                                                             │
│  parse_input → route_task → [HITL checkpoint] → execute     │
└──────────┬──────────────────────────┬───────────────────────┘
           │                          │
    LOCAL PLANE                  CLOUD PLANE
   Ollama + Qwen3             Groq (Llama-3.3-70B)
   (free, on-device)          Gemini 2.0 Flash (fallback)
```

### Core Planes

| Plane | Tech | Responsibility |
|-------|------|---------------|
| **Client UX** | Next.js 15, TypeScript | Real-time dashboard, SSE event streaming |
| **Backend Control** | FastAPI, Uvicorn | HTTP gateway, session management |
| **Orchestration** | LangGraph, MemorySaver | State machine, HITL checkpointing |
| **Inference Router** | Ollama, Groq, Gemini | Hybrid cost-aware LLM routing |
| **Persistence** | SQLite | Jobs, sessions, encrypted notes, audit log |

---

## ✨ Key Features

- 🔀 **Hybrid Inference Router** — Classifies tasks as SIMPLE/COMPLEX and routes to local (free) or cloud LLMs automatically
- 🛑 **Human-in-the-Loop (HITL)** — LangGraph `interrupt()` pauses high-risk operations for operator review before execution
- 🔐 **Encrypted Notes Vault** — AES-256-GCM encrypted secrets storage with zero plaintext exposure
- 📊 **Real-time SSE Streaming** — Live workflow status, node transitions, and telemetry pushed to the UI
- 🗂️ **Scheduler** — Cron-based job management with run history and audit logging
- 💰 **Token Budget Tracking** — Per-session token metering with monthly budget controls
- 📋 **Full Audit Trail** — Every routing decision, tool invocation, and HITL decision is immutably logged
- 🏛️ **Governance Registry** — `MutatingToolRegistry` enforces HITL approval for any data-mutating operations

---

## 🛠️ Tech Stack

**Backend**
- [FastAPI](https://fastapi.tiangolo.com) — Web framework with OpenAPI auto-docs
- [LangGraph](https://langchain-ai.github.io/langgraph/) — Stateful multi-agent workflow engine
- [Pydantic v2](https://docs.pydantic.dev) — Type-safe data validation throughout
- [SQLite](https://sqlite.org) — Zero-config embedded database
- [Ollama](https://ollama.com) — Local LLM inference (Qwen3)
- [httpx](https://www.python-httpx.org) — Async HTTP client for cloud API calls

**Frontend**
- [Next.js 15](https://nextjs.org) — React framework with App Router
- [TypeScript](https://typescriptlang.org) — Full type safety
- Custom SSE hooks for real-time streaming

**Cloud APIs (Free Tier)**
- [Groq](https://console.groq.com) — Llama-3.3-70B (30 req/min free)
- [Google Gemini Flash](https://aistudio.google.com) — Fallback (15 req/min free)

---

## 🚀 Getting Started

### Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.11+ | |
| Node.js | 18+ | |
| [Ollama](https://ollama.com/download) | Latest | For local inference |
| Groq API Key | — | Free at [console.groq.com](https://console.groq.com) |

### 1. Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/aegisflow.git
cd aegisflow
```

### 2. Pull the Local Model

```bash
ollama pull qwen3:0.6b
```

### 3. Backend Setup

```bash
cd backend
pip install -r requirements.txt
```

Create a `.env` file in the backend directory:

```env
GROQ_API_KEY=gsk_your_key_here
GEMINI_API_KEY=AIza_your_key_here   # optional fallback
```

Start the backend:

```bash
python main.py
```

> Backend runs at **http://localhost:8000** · Swagger docs at **http://localhost:8000/docs**

### 4. Frontend Setup

```bash
cd frontend
npm install
```

Create `.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Start the frontend:

```bash
npm run dev
```

> Frontend runs at **http://localhost:3000**

---

## 📡 API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/workflow/run` | Launch a new workflow session (SSE stream) |
| `POST` | `/api/v1/workflow/resume` | Resume a paused HITL checkpoint |
| `GET` | `/api/v1/workflow/status/{session_id}` | Query workflow status |
| `GET` | `/api/v1/health` | Liveness probe |
| `GET` | `/docs` | Interactive Swagger UI |

### SSE Event Types

| Event | Description |
|-------|-------------|
| `THREAD_INITIALIZED` | Session started, metadata emitted |
| `NODE_TRANSITION` | A LangGraph node completed |
| `HUMAN_INTERRUPT_REQUIRED` | Workflow paused — awaiting operator decision |
| `WORKFLOW_COMPLETE` | Execution finished successfully |
| `CRITICAL_FAILURE` | Unrecoverable error — workflow terminated |

---

## 🔒 Governance & Safety

AegisFlow enforces **three-tier governance** on every task:

1. **Hard-coded bypass** — Tools in `MutatingToolRegistry` (email, DB writes, budget auth, webhooks) always route through HITL regardless of LLM classification
2. **Keyword detection** — Keywords like `budget`, `authorize`, `delete records`, `send email to` trigger CLOUD_PLANE routing and HITL review
3. **LLM classification** — Local Qwen3 model classifies all remaining tasks as `SIMPLE` or `COMPLEX`

---

## 📁 Project Structure

```
aegisflow/
├── backend/
│   ├── main.py          # FastAPI app & SSE gateway
│   ├── graph.py         # LangGraph state machine
│   ├── router.py        # Hybrid inference router
│   ├── schemas.py       # Pydantic v2 data contracts
│   ├── db.py            # SQLite persistence layer
│   ├── smoke_test.py    # Integration tests
│   └── requirements.txt
│
└── frontend/
    ├── app/
    │   ├── page.tsx              # Main dashboard
    │   └── layout.tsx            # App shell
    ├── components/
    │   ├── TaskCommandInput.tsx       # Workflow trigger UI
    │   ├── HitlInterceptPanel.tsx     # HITL approval interface
    │   ├── TelemetryFeed.tsx          # Live event stream
    │   ├── StateGraphVisualizer.tsx   # Graph state visualizer
    │   ├── MetricsBadge.tsx           # Token/cost metrics
    │   ├── SidebarNav.tsx             # Navigation
    │   └── StatusIndicator.tsx        # Status badge
    ├── hooks/
    │   └── useWorkflowSession.ts      # SSE streaming hook
    └── lib/
        ├── api.ts           # API client
        └── types.ts         # Shared TypeScript types
```

---

## 🧪 Running Tests

```bash
cd backend
python smoke_test.py
```

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Commit your changes: `git commit -m 'feat: add your feature'`
4. Push and open a Pull Request

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

<div align="center">

**Built for the AI Productivity Hackathon**

*AegisFlow — Because enterprise AI needs guardrails, not just capabilities.*

</div>
