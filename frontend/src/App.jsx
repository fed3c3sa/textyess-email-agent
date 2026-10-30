// The app shell: an indigo sidebar with the two screens, and a top bar with the brand picker.
// The brand and the chat session live in the URL (?brand=...&session=...), so a reload keeps them.

import { useEffect, useState } from "react";
import { createBrand, listBrands } from "./api.js";
import Setup from "./Setup.jsx";
import Studio from "./Studio.jsx";

// Small line icons, drawn like the ones in the textyess dashboard.
const ICONS = {
  setup: "M4 6h16M4 12h10M4 18h7M17 15l3 3-3 3",
  studio: "M12 3l1.8 4.6L18.5 9l-4.7 1.6L12 15l-1.8-4.4L5.5 9l4.7-1.4L12 3zM18 15l.9 2.1 2.1.9-2.1.9L18 21l-.9-2.1L15 18l2.1-.9L18 15z",
  attach: "M21 11.5l-8.6 8.6a5 5 0 01-7.1-7.1l8.6-8.6a3.3 3.3 0 014.7 4.7l-8.6 8.6a1.7 1.7 0 01-2.4-2.4l7.9-7.9",
};

export function Icon({ name }) {
  return (
    <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d={ICONS[name]} />
    </svg>
  );
}

function readUrl(name) {
  return new URLSearchParams(window.location.search).get(name);
}

function writeUrl(values) {
  const params = new URLSearchParams();
  for (const [name, value] of Object.entries(values)) if (value) params.set(name, value);
  window.history.replaceState(null, "", `?${params}`);
}

export default function App() {
  const [brands, setBrands] = useState([]); // [{ brand_id, name }], newest first
  const [brandId, setBrandId] = useState(readUrl("brand"));
  const [sessionId, setSessionId] = useState(readUrl("session"));
  const [screen, setScreen] = useState(readUrl("brand") ? "studio" : "setup");

  function refreshBrands() {
    listBrands().then(setBrands);
  }

  useEffect(() => {
    refreshBrands();
  }, []);

  function chooseBrand(id, nextScreen = screen) {
    setBrandId(id);
    setSessionId(null); // a new brand starts a new chat
    setScreen(nextScreen);
    writeUrl({ brand: id });
  }

  function chooseSession(id) {
    setSessionId(id);
    writeUrl({ brand: brandId, session: id });
  }

  async function newBrand() {
    const { brand_id } = await createBrand();
    chooseBrand(brand_id, "setup");
    refreshBrands();
  }

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brandmark">
          <img src="/textyess-logo.jpeg" alt="textyess" />
          <span>emails</span>
        </div>

        <nav>
          <button className={screen === "setup" ? "nav active" : "nav"} onClick={() => setScreen("setup")}>
            <Icon name="setup" /> Setup
          </button>
          <button className={screen === "studio" ? "nav active" : "nav"} onClick={() => setScreen("studio")}>
            <Icon name="studio" /> Studio
          </button>
        </nav>

      </aside>

      <main className="main">
        <header className="topbar">
          <label className="brand-picker">
            <span className="muted">Brand</span>
            <select
              value={brandId ?? ""}
              onChange={(e) => (e.target.value === "new" ? newBrand() : chooseBrand(e.target.value))}
            >
              {!brandId && <option value="">Choose a brand</option>}
              {brands.map((brand) => (
                <option key={brand.brand_id} value={brand.brand_id}>
                  {brand.name || "Unnamed brand"}
                </option>
              ))}
              <option value="new">+ New brand</option>
            </select>
          </label>
          <span className="muted">{screen === "setup" ? "Learn the brand" : "Write emails"}</span>
        </header>
        {screen === "setup" ? (
          <Setup
            key={brandId}
            brandId={brandId}
            onBrand={(id) => chooseBrand(id, "setup")}
            onLearned={refreshBrands}
            onOpenStudio={() => setScreen("studio")}
          />
        ) : (
          <Studio
            key={brandId}
            brandId={brandId}
            sessionId={sessionId}
            onBrand={(id) => chooseBrand(id, "studio")}
            onSession={chooseSession}
            onLearned={refreshBrands}
          />
        )}
      </main>
    </div>
  );
}
