// The app shell: an indigo sidebar with the two screens, and a header with the brand.
// The brand and the chat session live in the URL (?brand=...&session=...), so a reload keeps them.

import { useEffect, useState } from "react";
import { getDesignSystem } from "./api.js";
import Setup from "./Setup.jsx";
import Studio from "./Studio.jsx";

function readUrl(name) {
  return new URLSearchParams(window.location.search).get(name);
}

function writeUrl(values) {
  const params = new URLSearchParams(window.location.search);
  for (const [name, value] of Object.entries(values)) params.set(name, value);
  window.history.replaceState(null, "", `?${params}`);
}

export default function App() {
  const [brandId, setBrandId] = useState(readUrl("brand"));
  const [sessionId, setSessionId] = useState(readUrl("session"));
  const [brandName, setBrandName] = useState(null);
  const [screen, setScreen] = useState(readUrl("brand") ? "studio" : "setup");

  function chooseBrand(id) {
    setBrandId(id);
    writeUrl({ brand: id });
  }

  function chooseSession(id) {
    setSessionId(id);
    writeUrl({ session: id });
  }

  function refreshBrandName() {
    if (brandId) getDesignSystem(brandId).then((ds) => setBrandName(ds.identity.name));
  }

  useEffect(() => {
    refreshBrandName();
  }, [brandId]);

  return (
    <div className="app">
      <aside className="sidebar">
        <img className="logo" src="/textyess-logo.jpeg" alt="textyess" />
        <nav>
          <button className={screen === "setup" ? "nav active" : "nav"} onClick={() => setScreen("setup")}>
            Setup
          </button>
          <button className={screen === "studio" ? "nav active" : "nav"} onClick={() => setScreen("studio")}>
            Studio
          </button>
        </nav>
      </aside>

      <main className="main">
        <header className="topbar">
          <span className="muted">Brand:</span> <strong>{brandName || (brandId ? "Unnamed brand" : "No brand yet")}</strong>
        </header>
        {screen === "setup" ? (
          <Setup
            brandId={brandId}
            onBrand={chooseBrand}
            onLearned={refreshBrandName}
            onOpenStudio={() => setScreen("studio")}
          />
        ) : (
          <Studio
            brandId={brandId}
            sessionId={sessionId}
            onBrand={chooseBrand}
            onSession={chooseSession}
            onLearned={refreshBrandName}
          />
        )}
      </main>
    </div>
  );
}
