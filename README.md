# textyess-email-agent
An agent that given a website or document copies the brand identity to craft emails

## Architecture

### Backend graph

```mermaid
flowchart TB
    SETUPUI(["<b>Entry 1: Setup screen</b><br/>URL + uploaded docs"])
    CHAT(["<b>Entry 2: Studio chat</b><br/>user messages"])

    SCRAPER{{"<b>3. Brand scraper subagent</b><br/>multimodal model, one run<br/>all images in its first message"}}
    ORCH{{"<b>Orchestrator agent</b> (LLM)<br/>reads the whole design system<br/>asks the user when information is missing<br/>the user can do everything from chat"}}

    FSMW["Read-only file tools<br/>deepagents FilesystemMiddleware<br/>search the saved text"]
    WEB["<b>1. Website</b> (Firecrawl)<br/>branding, text, HTML, screenshot, images"]
    PDF["<b>2. PDFs</b> (PyMuPDF)<br/>pages as images for the model<br/>logos and photos into assets"]

    LEARN["learn_brand<br/>(url, docs)"]
    SECT["add / update / remove section<br/>email = list of sections + reasoning<br/>(subject, preheader, body parts)<br/>streamed to the chat (SSE)<br/>full HTML built by render_email()"]
    NOTE["save_note<br/>after the user confirms"]
    UPDATE["update_design_system<br/>(field, value)<br/>conflict answers and corrections"]

    RET{{"Scraper returns"}}
    DS[("Design system JSON<br/>structured output, all fields optional<br/>styles as inline CSS in html_examples")]
    ASSETS[/"Assets dir"/]
    CONF>"conflicts[]<br/>transient, never stored<br/>design system is saved with the PDF values<br/>(documents win over the website)<br/>user can override on the Setup screen or in the chat"]

    STORE[("SQLite<br/>LangGraph SqliteSaver checkpoints<br/>chat, current email, undo from history")]
    FILES[("Files on disk<br/>brands/&lt;id&gt;/design_system.json<br/>brands/&lt;id&gt;/assets/<br/>brands/&lt;id&gt;/raw/ (website text, HTML, screenshot, PDF pages)<br/>brands/&lt;id&gt;/uploads/ (user files)")]

    SP1[" "]
    SP2[" "]
    SETUPUI --- SP1
    SP1 -- "direct, bypasses the orchestrator" --- SP2
    SP2 --> WEB
    CHAT --> ORCH

    ORCH --> LEARN
    ORCH --> SECT
    ORCH --> NOTE
    ORCH --> UPDATE
    LEARN -- "calls" --> WEB

    WEB --> PDF
    PDF --> SCRAPER
    SCRAPER -- "uses" --> FSMW
    SCRAPER --> RET

    RET --> DS
    RET --> ASSETS
    RET --> CONF

    NOTE -- "appends user_notes[]" --> DS
    UPDATE -- "writes the chosen value" --> DS
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
    class LEARN,SECT,NOTE,UPDATE,FSMW,WEB,PDF tool
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
| Models | OpenRouter through `langchain-openrouter` (`ChatOpenRouter`, reports cost per call); start with `z-ai/glm-5.3-flash` for all steps |
| Data models | Pydantic v2 |
| Website scraping | Firecrawl `scrape` with the `branding`, `markdown`, `rawHtml`, `images` and `screenshot` formats (1 credit per page, no local browser) |
| PDF | PyMuPDF |
| Agent filesystem | `deepagents` `FilesystemMiddleware`, `FilesystemBackend(root_dir=brands/<id>, virtual_mode=True)` |
| Email HTML | `css-inline` |
| Storage | SQLite + files on disk |

### Design choices

| Choice | Why |
|---|---|
| Design system JSON is the single source of truth; the orchestrator reads all of it | No skill generation, no drift between a view and its source |
| Documents win over the website; the design system is saved immediately and the conflicts are shown to the user | A brand guideline is deliberate, a website carries old styles; the user can override any value |
| Chat learning is written to `user_notes[]` only after the user says yes in the chat | One-off requests don't become brand rules; a re-scrape never overwrites notes |
| The email is a list of sections `{id, kind, reasoning, content}`, subject and preheader included, edited with tools (`add_section`, `update_section`, `remove_section`) | Parts stream in one by one, follow-up edits patch by id, every part carries its reasoning |
| `reasoning` is written before `content` | The model decides why before it writes the HTML |
| Email HTML is responsive: fluid tables and images, a `stack` class for columns on phones | Most marketing email is read on a phone |
| Undo reads the previous email from the LangGraph checkpoint history | No separate version storage |
| Website images are used through their original public URL; the downloaded copy is only for the scraper to look at | The reader's email app loads them from the brand's site, so they work in a real inbox |
| Images from PDFs and uploads are preview-only: the API serves them from `localhost`, which a reader's email app cannot reach | Making them work for readers means hosting them publicly (S3, a CDN, or the email platform's image hosting), which is deployment and out of scope |
| A PDF is sent to the model as rendered page images, not as a file | Images carry the brand's look better (fonts, swatches, layout, button examples). Models like GLM 5.3 Flash accept images but not PDF files: OpenRouter would run OCR on the PDF and send text, and the model would lose the fonts and the visual style |
| The design system is stored in its own file, not in checkpoints | It belongs to the brand and is shared by every chat session |
| SSE events are a typed Pydantic union (`status`, `message`, `section_added`, `section_updated`, `section_removed`, `email_replaced`, `done`, `error`) | The frontend develops against a fixed contract |
| Token usage and OpenRouter cost are recorded per run | The README must report cost and time |
