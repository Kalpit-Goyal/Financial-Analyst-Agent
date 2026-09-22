# Improvement Report — Financial Analyst Agent

Static analysis of the full project (backend, MCP server, frontend, git history, installed
packages, and configuration). Findings are grouped by severity. Each item includes the
problem, the affected file, and a concrete fix suggestion.

---

## Summary Table

| # | Severity | Area | Issue |
|---|----------|------|-------|
| 1 | Critical | Security | Real production secrets stored in `.env` |
| 2 | Critical | Backend | CORS origin does not match the deployed frontend (and is misspelled) |
| 3 | High | Backend | MCP tool path is relative; breaks when launched from another working dir |
| 4 | High | Architecture | No conversation memory — every question is answered in isolation |
| 5 | High | Backend | `ticker = "not available"` still reaches the LLM (hallucination risk) |
| 6 | High | Backend | No recursion limit / max tool-call budget on the graph |
| 7 | Medium | Backend | Dead state fields `financial_data`, `web_data`, `artifacts` never populated |
| 8 | Medium | Backend | `initial_state` in `state.py` unused; raw dicts fed to `add_messages` reducer |
| 9 | Medium | MCP | Tool output can be non-JSON / huge; serialization and context-bloat risk |
| 10 | Medium | Backend | Unhandled yfinance errors in ticker lookup and all MCP tools |
| 11 | Medium | Performance | LLM + MCP client rebuilt per request / per tool-loop iteration |
| 12 | Medium | Backend | No error handling, validation, or timeout on `/analyze` |
| 13 | Medium | MCP | `sys.executable` assumption breaks with a different Python interpreter |
| 14 | Low | Dependencies | `fastapi` / `uvicorn` unpinned in `requirements.txt` |
| 15 | Medium | Frontend | No streaming/timeout; no way to switch company |
| 16 | Medium | Frontend | Unsafe read of `data.messages[last].content` |
| 17 | Low | Frontend | `frontend/.env` silently points local dev at the production API |
| 18 | Low | Frontend | Leftover Vite scaffold files and generic `<title>` |
| 19 | Low | Frontend | `ChatMessage` missing `<pre>` styling; cosmetic code-block issue |
| 20 | Low | Frontend | Missing `aria-label` for textarea / icon-only send button |
| 21 | Low | Docs | README is stale/wrong in several places |
| 22 | Medium | Testing | No tests, no CI for backend or frontend |
| 23 | Low | Housekeeping | `.gitignore` misses common files/dirs |

---

## Critical / Security

### 1. Real production secrets in `.env`
- **Severity:** Critical
- **Files:** `.env`, `frontend/.env`
- **Problem:** `.env` contains a live `api_key`, `LANGSMITH_API_KEY`, and a third-party
  base URL. The files are currently gitignored (verified with `git check-ignore`), but any
  accidental push, screenshot, or repo sharing exposes the keys. The committed git history
  also contains old code with the same base URL and model hardcoded.
- **Fix:**
  - Rotate the leaked keys as a precaution.
  - Do **not** apply in this repo for local dev, but commit a `.env.example` with
    placeholder values and document every required variable.
  - Consider moving the LLM key to a secret manager / environment variable on the host
    rather than relying on a committed-adjacent `.env` file.

### 2. CORS origin does not match the deployed frontend (and is misspelled)
- **Severity:** Critical
- **Files:** `main.py:13-14`, `frontend/.env`
- **Problem:** The backend allows only `https://finanacial-analyst.onrender.com`, while the
  frontend calls `https://finanacial-analyst-agent.onrender.com`. Both misspell "financial"
  as "finanacial", and neither matches the other. Browser requests from the real deployed
  frontend will be blocked by CORS, or requests will hit the wrong deployment.
- **Fix:**
  - Resolve the real deployed origins for the backend and frontend.
  - Add the frontend's actual origin (and `http://localhost:5173`) to
    `allow_origins` and fix the spelling.
  - Alternatively use `allow_origin_regex` or an environment-driven origin list so the
    correct value comes from deployment config, not hardcoded code.

---

## Bugs / Correctness

### 3. MCP tool path is relative — breaks from other working directories
- **Severity:** High
- **File:** `graph.py:18`
- **Problem:** `args: ["mcp_server/financial_tools.py"]` is relative to the process CWD.
  On Render, systemd, or when launched from another folder, the subprocess fails to find
  the file and tool discovery returns nothing.
- **Fix:** Build the absolute path from the module location:
  ```python
  from pathlib import Path
  server_path = Path(__file__).resolve().parent / "mcp_server" / "financial_tools.py"
  args: [str(server_path)]
  ```

### 4. No conversation memory — every question is answered in isolation
- **Severity:** High
- **Files:** `ChatWindow.jsx:30-43`, `main.py:36-48`
- **Problem:** The frontend keeps full history in local state, but each `/analyze` request
  sends only the single new question and the backend constructs a fresh graph/state.
  The system prompt in `analyst.py:34` says "Use the conversation history to understand
  context", but no history is ever passed. Follow-up questions ("give me more revenue detail",
  "and what about last year?") lose all context.
- **Fix:**
  - Send the accumulated message history from the frontend in the request payload and seed
    the graph state with it, or maintain a per-company/session conversation store on the
    backend keyed by a session/company id.

### 5. `ticker = "not available"` still reaches the LLM
- **Severity:** High
- **Files:** `user_input.py:13,23`, `graph.py:40-52`
- **Problem:** When no equity ticker is found, `get_ticker` returns `"not available"` but the
  graph flows straight into `analyst`. The LLM is then free to answer (and invent data)
  without tools.
- **Fix:** Route to a terminal node before `analyst` when the ticker is unresolved and return
  a clear user-facing message such as "Could not find a ticker for <company>."

### 6. No recursion limit / max tool-call budget on the graph
- **Severity:** High
- **File:** `graph.py:54`
- **Problem:** The compiled graph has no bound on how many times the analyst can request
  tools. A misbehaving model (or repeated tool/transport errors) can loop indefinitely,
  consuming tokens and API budget.
- **Fix:** Set `recursion_limit` in the `ainvoke` config and/or add a counter node that
  terminates after N tool rounds. Consider using LangGraph's `interrupt_after` guards.

### 7. Dead state fields `financial_data`, `web_data`, `artifacts`
- **Severity:** Medium
- **Files:** `state.py:9-11`, `main.py:45-48`
- **Problem:** The three result buckets are declared in `AgentState` and initialized on every
  request but are never written by any node. Tool results reach the LLM only as `ToolMessage`
  text. The README claims these buckets store results — they never do.
- **Fix:** Either populate them from the ToolNode (e.g., a `save_tool_results` node that
  stores tool outputs into `financial_data`) or remove them from the state and README.

### 8. `initial_state` unused; raw dicts fed to the `add_messages` reducer
- **Severity:** Medium
- **Files:** `state.py:14-21`, `main.py:38-45`
- **Problem:** `state.py` defines a module-level `initial_state` that nothing imports.
  Separately, `main.py` seeds `messages` with plain dicts (`{"role": "user", ...}`) while the
  state reducer (`Annotated[list, add_messages]`) is designed for LangChain message objects.
  This works with current lib versions by coercion, but is fragile and inconsistent.
- **Fix:** Remove the dead `initial_state`; construct `HumanMessage(request.question)` in
  `main.py` so the state always contains real message objects.

### 9. Tool output can be non-JSON / huge
- **Severity:** Medium
- **Files:** `mcp_server/financial_tools.py:7-33`
- **Problem:**
  - `income_statement.to_dict()` and `balance_sheet.to_dict()` produce nested dicts that can
    contain `NaN` (Starlette's `JSONResponse` serializes with `allow_nan=False`, so any such
    value forwarded to the HTTP response raises `ValueError`) and pandas `Timestamp` keys.
  - `stock.info` can contain non-serializable objects and is several thousand fields.
  - Whichever of these reaches the LLM risks either a crash or a massively oversized tool
    message that bloats context and token cost.
- **Fix:**
  - In each tool, convert results to JSON-safe structures: `df.dropna(how="all")`, cast the
    index columns to strings/dates, and `json.loads(json.dumps(..., default=...))` with a
    `default` that stringifies unknown objects.
  - Truncate/summarize large payloads (e.g., return recent quarters, drop empty rows, cap
    number of elements) before returning to the model.

### 10. Unhandled yfinance errors
- **Severity:** Medium
- **Files:** `user_input.py:8-9`, `mcp_server/financial_tools.py:10-33`
- **Problem:** `yf.Search(...)`, `yf.Ticker(...)`, `income_stmt`, `balance_sheet`, and
  `stock.info` can all raise on network failure, rate limits, or delisted/unknown tickers.
  Nothing catches these, so a failed ticker lookup crashes the whole request, and failing
  tools can push the model into repeated retry loops.
- **Fix:** Wrap every yfinance call in try/except and return a structured tool error
  (`{"error": ..., "ticker": ...}`) or an empty result so the LLM can react gracefully; short-
  circuit `get_ticker` failures with a clear message.

---

## Reliability / Performance

### 11. LLM + MCP client rebuilt per request and per tool-loop iteration
- **Severity:** Medium
- **Files:** `analyst.py:12-16`, `graph.py:12-24`
- **Problem:** `create_graph()` runs on every request, and `analyst_node` constructs a fresh
  `ChatOpenAI` every call — i.e., every tool-loop iteration. The MCP client (`MultiServerMCPClient`)
  also starts a new subprocess-backed session per tool call. None of this is cached or reused,
  adding seconds of latency to each request.
- **Fix:**
  - Build the graph once and reuse it (make the request state, not the graph, per-request).
  - Cache the LLM client globally and pass it into the node instead of re-creating it.
  - Prefer the HTTP MCP transport (long-lived single process) over spawning stdio per call.

### 12. No error handling, validation, or timeout on `/analyze`
- **Severity:** Medium
- **File:** `main.py:31-59`
- **Problem:** An empty `company`/`question` passes straight through to `yf.Search` and the
  LLM; any exception (LLM outage, yfinance failure, serialization error) returns a bare 500
  with no logging; there is no request timeout so a hung LLM call ties up the worker.
- **Fix:**
  - Add `min_length` validators (or `field_validator`) to `AnalysisRequest`.
  - Wrap the endpoint body in try/except and return a structured error response
    (e.g., `{"error": ...}` with HTTP 4xx/5xx) and `logger.exception`.
  - Pass a timeout to the LLM client and/or the `ainvoke` call.

### 13. MCP server relies on `sys.executable`
- **Severity:** Medium
- **File:** `graph.py:17`
- **Problem:** The MCP subprocess is launched with the backend's own interpreter. If the
  runtime that serves the app differs from the one that has `mcp`/`yfinance` installed
  (virtualenv vs. system Python under some deploy setups), tool discovery fails.
- **Fix:** Derive the interpreter explicitly (env var override), and fail fast at startup with
  a clear message if `mcp`/`yfinance` are importable in that interpreter.

### 14. Unpinned `fastapi` / `uvicorn`
- **Severity:** Low
- **File:** `requirements.txt:11-12`
- **Problem:** `fastapi` and `uvicorn` are unpinned while everything else is pinned. Future
  installs can silently upgrade to incompatible versions, breaking reproducibility.
- **Fix:** Pin versions, e.g. `fastapi==0.141.1` / `uvicorn==0.52.3` (or lock to current), and
  prefer a `requirements.txt` + lock strategy for deploys.

---

## Frontend

### 15. No streaming, no timeout, no way to switch company
- **Severity:** Medium
- **Files:** `ChatWindow.jsx:30-43`, `App.jsx:14-22`
- **Problem:**
  - Responses can take tens of seconds (LLM + multiple MCP tool calls) but the UI only shows
    an indefinite bouncing-dots animation; there is no streaming, `AbortController`, or
    timeout to cancel a stuck request.
  - There is no "new company" / back button once analysis starts, and no retry for failed
    requests beyond re-typing the question.
- **Fix:**
  - Implement streaming (SSE or streaming WebSocket) or at least a timeout with a retry UI.
  - Add a header action to restart with a new company and a visible error state with a Retry
    button.

### 16. Unsafe read of the last message in the response state
- **Severity:** Medium
- **File:** `ChatWindow.jsx:52-60`
- **Problem:** `data.messages[data.messages.length - 1].content` assumes the last message is
  an assistant message with a string `content`. If the graph ends on a tool message, a tool
  call with empty content, or an unexpected shape, this throws or renders `undefined`.
- **Fix:** Find the last message with `role === "assistant"` and guard `content`:
  ```js
  const lastAssistant = [...data.messages].reverse().find(m => m.role === "assistant");
  const content = lastAssistant?.content ?? "No response generated.";
  ```

### 17. `frontend/.env` silently points local dev at the production API
- **Severity:** Low
- **File:** `frontend/.env`
- **Problem:** The committed-adjacent `.env` (gitignored here, but shared manually) sets
  `VITE_API_URL=https://finanacial-analyst-agent.onrender.com`. Running `npm run dev` will
  talk to the deployed backend instead of a local instance, and the misspelled/incorrect
  domain may silently fail. README says to create this file for localhost, contradicting reality.
- **Fix:** Use `.env.development` (`http://localhost:8000`) and `.env.production`
  (deployed URL), commit `.env.example`, and correct the spelling. Do not ship a prod URL in
  the default dev environment.

### 18. Leftover Vite scaffold files and generic page title
- **Severity:** Low
- **Files:** `frontend/index.html:7`, `frontend/src/App.css`, `frontend/src/assets/hero.png`,
  `frontend/src/assets/react.svg`, `frontend/src/assets/vite.svg`, `frontend/public/favicon.svg`,
  `frontend/public/icons.svg`, `frontend/README.md`
- **Problem:** The `<title>` is the generic "frontend". `App.css` is the default Vite counter
  style (never imported), the three bundled `src/assets` images are unused, and the public
  SVGs and `frontend/README.md` are untouched template artifacts. README even claims
  `frontend/src/assets` is "currently empty".
- **Fix:** Set a proper title and favicon for the product; delete unused scaffold
  files/assets; replace `frontend/README.md` with project-specific content.

### 19. `ChatMessage` missing `pre` handling
- **Severity:** Low
- **File:** `ChatMessage.jsx:142-147`
- **Problem:** Only the `code` component is customized, so multi-line code blocks render
  inside a default `<pre>` whose inner `code` gets inline-code padding/background — formatted
  as a single confusing run-on block.
- **Fix:** Add a `pre` renderer with block styling (e.g., `bg-slate-950 p-4 rounded-lg
  overflow-x-auto`) and wrap it in `code` without the inline styles.

### 20. Missing `aria-label` on interactive controls
- **Severity:** Low
- **Files:** `ChatWindow.jsx:309-324`, `CompanySetup.jsx:47-53`
- **Problem:** The send button is an icon-only `↑` and the message textarea has only a
  placeholder; both lack accessible names for screen readers.
- **Fix:** Add `aria-label="Send message"` to the button and `aria-label` (or a visually
  hidden `<label>`) for the textarea; add `aria-live` to the message list for better a11y.

---

## Docs / Housekeeping

### 21. Stale / inaccurate README
- **Severity:** Low
- **File:** `README.md`
- **Problem:** Several statements do not match the code:
  - Env vars section documents only `api_key`, but the current `analyst.py` also requires
    `model` and `base_url` (the uncommitted change makes them env-driven), plus optional
    LangSmith vars.
  - Backend setup says `python -m venv .venv`, but the repo uses `venv` and `.gitignore`
    only lists `venv/`.
  - "Project Structure" says `frontend/src/assets/` is "currently empty" (it has 3 files).
  - State section claims result buckets store financial/web/artifact data — they never do
    (see issue 7).
  - No mention of the `recurse_limit`, ticker-failure path, or error/edge cases.
- **Fix:** Update the README to match the actual code, document all env vars (with a
  `.env.example`), correct the venv name/assets note, and drop the misleading result-bucket
  claims (or implement them first).

### 22. No tests, no CI
- **Severity:** Medium
- **Files:** whole repo
- **Problem:** There are zero test files for the backend (FastAPI endpoints, `get_ticker`,
  analyst loop, MCP tools) and zero for the frontend. There is no CI pipeline. Regressions
  (like the CORS/deploy changes) go undetected.
- **Fix:**
  - Add pytest tests for `user_input.get_ticker`, MCP tool output shape/JSON-safety, and an
    `httpx`/`TestClient` test for `/analyze` (mocking the LLM and yfinance).
  - Add Vitest/Testing-Library tests for `ChatWindow` (message send, error path) and
    `CompanySetup`.
  - Wire a GitHub Actions workflow to run backend tests, `npm run lint`, and `npm run build`.

### 23. `.gitignore` gaps
- **Severity:** Low
- **File:** `.gitignore`
- **Problem:** Missing common entries: `.venv/` (README variant), `.env.*`, `*.log`,
  `.DS_Store`, `node_modules/` (only covered by `frontend/.gitignore`), `.pytest_cache/`,
  `.mypy_cache/`, `dist/`.
- **Fix:** Expand `.gitignore` to cover `.venv/`, `.env.*` (but not `.env.example`), logs,
  caches, and `.DS_Store`.

---

## Notes / Scope

- Analysis was static (no live API/network calls) plus inspection of installed package
  versions and git history.
- The working tree contains an uncommitted change to `analyst.py` that switches the LLM
  `model`/`base_url` to environment variables; all findings already reflect this current
  state.
- Items marked "Medium/Critical" are ordered by likely impact on the running app (mostly
  CORS, relative MCP path, missing memory, and unbounded loops).