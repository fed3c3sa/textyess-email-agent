# textyess-email-agent
An agent that given a website or document copies the brand identity to craft emails

## Architecture

### Backend graph

```mermaid
flowchart TD
    USER["User messages<br/>(chat, URL, uploaded docs)"] --> ORCH

    ORCH{{"Orchestrator<br/>(setup flow + studio flow)"}}

    subgraph SETUP["Setup flow: learn the brand"]
        direction TB
        SCRAPER["Brand scraper agent<br/>agent + filesystem<br/>multimodal model (reads docs and images)"]
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

    subgraph STUDIO["Studio flow: write and edit emails"]
        EMAIL["Produces email<br/>HTML, ready to send<br/>(reads the whole design system JSON)"]
    end

    ORCH -- "calls (URL / docs)" --> SCRAPER
    CONF -- "website and PDF disagree" --> ORCH
    ORCH -. "asks the user, writes the chosen value" .-> USER

    ORCH -- "prompt + design system" --> EMAIL
    DS --> ORCH
    ASSETS --> EMAIL
    EMAIL -- "email HTML" --> USER
    EMAIL --> STORE

    USER -. "confirms 'keep this for future emails'" .-> ORCH
    ORCH -- "appends user_notes[]" --> DS

    subgraph STORAGE["Storage"]
        STORE[("SQLite<br/>chat sessions + email versions<br/>(LangGraph SqliteSaver)")]
        FILES[("Files on disk<br/>brands/&lt;id&gt;/design_system.json<br/>brands/&lt;id&gt;/assets/")]
    end
    DS --- FILES
    ASSETS --- FILES
    ORCH --- STORE
```
