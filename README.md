# textyess-email-agent
An agent that given a website or document copies the brand identity to craft emails

## Architecture

### Backend graph

```mermaid
flowchart TD
    SETUPUI["Setup screen<br/>URL + uploaded docs"]
    CHAT["Studio chat<br/>user messages"]

    ORCH{{"Orchestrator agent (LLM)<br/>the user can do everything from chat<br/>reads the whole design system JSON"}}

    subgraph TOOLSORCH["Orchestrator tools"]
        direction LR
        LEARN["learn_brand(url, docs)"]
        SECT["add_section / update_section / remove_section<br/>(email = list of sections with reasoning)"]
        NOTE["save_note<br/>(after user confirms)"]
    end

    subgraph SCRAPE["Brand scraper subagent"]
        direction TB
        SCRAPER["Agent + filesystem<br/>(deepagents FilesystemMiddleware)<br/>multimodal model (reads docs and images)"]
        subgraph TOOLS["Tools"]
            direction LR
            WEB["Web browsing<br/>extracts HTML + CSS + assets"]
            PDF["PDF tools<br/>extracts assets"]
        end
        SCRAPER -- uses --> TOOLS
        SCRAPER --> RET["Returns"]
        RET --> DS[("Design system JSON<br/>structured output")]
        RET --> ASSETS[/"Assets dir"/]
        RET --> CONF["conflicts[]<br/>(transient)"]
    end

    SETUPUI -- "direct, bypasses the orchestrator" --> SCRAPER
    CONF -- "setup: user resolves on the Setup screen" --> SETUPUI

    CHAT --> ORCH
    ORCH --> TOOLSORCH
    LEARN --> SCRAPER
    CONF -- "chat: orchestrator asks the user" --> ORCH
    DS -- "read" --> ORCH
    ASSETS --> ORCH
    SECT -- "email sections (streamed)" --> CHAT
    ORCH -. "asks the user to confirm 'keep this for future emails'" .-> CHAT
    NOTE -- "appends user_notes[]" --> DS

    subgraph STORAGE["Storage"]
        STORE[("SQLite<br/>chat sessions + current email + email versions<br/>(LangGraph SqliteSaver)")]
        FILES[("Files on disk<br/>brands/&lt;id&gt;/design_system.json<br/>brands/&lt;id&gt;/assets/")]
    end
    ORCH --- STORE
    DS --- FILES
    ASSETS --- FILES
```

### Stack

| Piece | Choice |
| --- | --- |
| Runtime | Python 3.14, `venv` + `pip`, `pytest` |
| API | FastAPI |
| Streaming transport | SSE over POST (`fastapi.sse.EventSourceResponse`) |
| Orchestration and state | LangChain + LangGraph, `AsyncSqliteSaver` checkpointer |
| Models | OpenRouter through LangChain's OpenAI-compatible client; start with `z-ai/glm-5.3-flash` for all steps |
| Data models | Pydantic v2 |
| Scraper browsing | Playwright (async) |
| PDF | PyMuPDF |
| Agent filesystem | `deepagents` `FilesystemMiddleware`, `FilesystemBackend(root_dir=brands/<id>, virtual_mode=True)` |
| Email HTML | `css-inline` |
| Storage | SQLite + files on disk |

### Design choices

| Choice | Why |
|---|---|
| Design system JSON is the single source of truth; the email step reads all of it | No skill generation, no drift between a view and its source |
| Chat learning is written to `user_notes[]` only after the user confirms | One-off requests don't become brand rules; a re-scrape never overwrites notes |
| The email is a list of sections `{id, kind, html, reasoning}` edited with tools (`add_section`, `update_section`, `remove_section`) | Parts stream in one by one, follow-up edits patch by id, reasoning is shown per part |
| Conflicts between website and PDF use LangGraph `interrupt()` | The graph pauses, the user answers in chat, the run resumes with the chosen value |
| The design system is stored in its own file, not in checkpoints | Checkpoints only hold the chat and the current email |
| SSE events are a typed Pydantic union (`status`, `reasoning`, `section_added`, `section_updated`, `question`, `done`, `error`) | The frontend develops against a fixed contract |
| Token usage and OpenRouter cost are recorded per run | The README must report cost and time |
