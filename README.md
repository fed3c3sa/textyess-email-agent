# textyess-email-agent
An agent that given a website or document copies the brand identity to craft emails

## Architecture

### Backend graph

```mermaid
flowchart TB
    SETUPUI(["<b>Entry 1: Setup screen</b><br/>URL + uploaded docs"])
    CHAT(["<b>Entry 2: Studio chat</b><br/>user messages"])

    SCRAPER{{"<b>Brand scraper subagent</b><br/>multimodal model: reads docs and images"}}
    ORCH{{"<b>Orchestrator agent</b> (LLM)<br/>reads the whole design system<br/>the user can do everything from chat"}}

    FSMW["Agent filesystem<br/>deepagents FilesystemMiddleware"]
    WEB["Web browsing<br/>HTML + CSS + assets"]
    PDF["PDF tools<br/>assets"]

    LEARN["learn_brand<br/>(url, docs)"]
    SECT["add / update / remove section<br/>email = list of sections + reasoning<br/>streamed to the chat (SSE)"]
    NOTE["save_note<br/>after the user confirms"]

    RET{{"Scraper returns"}}
    DS[("Design system JSON<br/>structured output")]
    ASSETS[/"Assets dir"/]
    CONF>"conflicts[]<br/>transient, never stored<br/>resolved by the user on the Setup screen<br/>or by the orchestrator in the chat"]

    STORE[("SQLite<br/>chat sessions, current email, email versions<br/>LangGraph SqliteSaver")]
    FILES[("Files on disk<br/>brands/&lt;id&gt;/design_system.json<br/>brands/&lt;id&gt;/assets/")]

    SP1[" "]
    SP2[" "]
    SETUPUI --- SP1
    SP1 -- "direct, bypasses the orchestrator" --- SP2
    SP2 --> SCRAPER
    CHAT --> ORCH

    ORCH --> LEARN
    ORCH --> SECT
    ORCH --> NOTE
    LEARN -- "calls" --> SCRAPER

    SCRAPER --> FSMW
    SCRAPER --> WEB
    SCRAPER --> PDF
    FSMW --> RET
    WEB --> RET
    PDF --> RET

    RET --> DS
    RET --> ASSETS
    RET --> CONF

    NOTE -- "appends user_notes[]" --> DS
    ORCH -. "reads" .-> DS
    SECT --> STORE
    DS --- FILES
    ASSETS --- FILES

    classDef hidden fill:none,stroke:none,color:none
    classDef entry fill:#dbeafe,stroke:#1d4ed8,stroke-width:2px,color:#1e3a8a
    classDef agent fill:#ede9fe,stroke:#6d28d9,stroke-width:2px,color:#4c1d95
    classDef tool fill:#fef9c3,stroke:#a16207,color:#713f12
    classDef data fill:#dcfce7,stroke:#15803d,color:#14532d
    classDef warn fill:#fee2e2,stroke:#b91c1c,color:#7f1d1d
    class SETUPUI,CHAT entry
    class ORCH,SCRAPER,RET agent
    class LEARN,SECT,NOTE,FSMW,WEB,PDF tool
    class DS,ASSETS,STORE,FILES data
    class CONF warn
    class SP1,SP2 hidden
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
