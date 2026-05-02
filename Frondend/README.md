# SmartMove — Next.js Agentic Frontend

A Next.js 14 (App Router) chatbot that drives the existing **SmartMove**
LangGraph human-in-the-loop agent (`trails/smartmove_hitl.py`).
It mirrors the original Streamlit app (`trails/3_test_streamlit.py`) but with a
modern, responsive chat UI and an agentic interactive experience:

- **Multilingual input** — English, Singlish → සිංහල (live conversion), and a
  Sinhala on-screen keyboard.
- **Interactive HITL follow-ups** — when the agent interrupts asking for
  origin / destination / departure time, an inline form is rendered.
- **Live agent state panel** — see what the agent extracted (intent, language,
  origin, destination, fare, transport type, …) plus raw JSON.
- **Multi-turn chat** with the LangGraph `MemorySaver` keyed by `thread_id`.

```
Frondend/
├── app/                  # Next.js App Router (layout, page, globals.css)
├── components/           # ChatApp, Composer, FollowUpForm, Sidebar, ...
├── lib/                  # API client + types
└── backend/              # FastAPI sidecar wrapping smartmove_hitl.build_app()
```

The Next.js app proxies `/api/*` to the FastAPI backend (configurable via
`SMARTMOVE_BACKEND_URL`, defaulting to `http://127.0.0.1:8000`).

## Prerequisites

- Node.js 18.18+ (or 20+)
- Python 3.13 (matches the parent project's `requires-python`)
- A `.env` at the repo root with at minimum:
  ```
  OPENAI_API_KEY=sk-...
  NEO4J_URI=neo4j+s://...
  NEO4J_USER=neo4j
  NEO4J_PASSWORD=...
  NEO4J_DATABASE=neo4j
  ```

## 1. Run the backend (FastAPI)

From the repo root:

```powershell
# activate the project venv (uv-managed)
.\.venv\Scripts\Activate.ps1

# install backend deps into the project venv (one-time)
uv pip install -r Frondend\backend\requirements.txt

# start the API on http://127.0.0.1:8000
python Frondend\backend\main.py
```

The backend imports `smartmove_hitl.build_app()` and `sinhala_input_helpers`
directly from `trails/`, so no code is duplicated.

> **Important — reloading `trails/` edits.** `python main.py` configures uvicorn
> to watch both `Frondend/backend/` **and** `trails/`. If you launch with the
> CLI instead, you must opt in explicitly, otherwise edits to
> `trails/smartmove_hitl.py` won't reload:
>
> ```powershell
> cd Frondend\backend
> uvicorn main:app --reload --reload-dir . --reload-dir ..\..\trails
> ```

### Endpoints

| Method | Path                      | Purpose                                              |
|-------:|---------------------------|------------------------------------------------------|
| `POST` | `/api/chat`               | Send a user message (creates a thread if missing).   |
| `POST` | `/api/resume`             | Resume a paused thread with follow-up answers.       |
| `POST` | `/api/singlish`           | Singlish → Sinhala conversion via OpenAI.            |
| `GET`  | `/api/keyboard`           | Sinhala on-screen keyboard rows.                     |
| `GET`  | `/api/state/{thread_id}`  | Last cached state (without messages) for a thread.   |
| `GET`  | `/api/health`             | Health check.                                        |

## 2. Run the frontend (Next.js)

In a second terminal:

```powershell
cd Frondend
npm install
npm run dev
```

Open <http://localhost:3000>.

## How the agentic loop works

1. The user types a message in any of the three input modes.
2. The frontend calls `POST /api/chat` with `{ message, thread_id? }`.
3. The backend invokes the LangGraph app. Two outcomes:
   - **Final response** — `{ type: "message", response, state }` is returned and
     rendered as an assistant bubble.
   - **Interrupt** — `{ type: "interrupt", interrupt: { question, missing_fields } }`
     is returned. The frontend renders an inline follow-up form (matched to the
     selected input mode), and on submit calls `POST /api/resume` with the
     collected updates. This may interrupt again until all required fields are
     present, then a final response arrives.
4. Each response also carries the latest agent `state` (everything except the
   message log) which is shown in the collapsible state panel.

## Customising

- Change the backend URL by setting `SMARTMOVE_BACKEND_URL` before
  `npm run dev` / `npm run build`.
- Add suggestion chips in `components/ChatApp.tsx` (`SUGGESTIONS`).
- Adjust theme colours in `tailwind.config.ts`.
