// Screen 1, Setup: a website URL and files in, the brand's design system out.
// Learning streams progress events, then a "brand_ready" event with the design system
// and the conflicts between the website and the documents.

import { useEffect, useState } from "react";
import { createBrand, getDesignSystem, learnBrand, uploadFiles } from "./api.js";
import DesignSystem from "./DesignSystem.jsx";

export default function Setup({ brandId, onBrand, onLearned, onOpenStudio }) {
  const [url, setUrl] = useState("");
  const [files, setFiles] = useState([]);
  const [pastedHtml, setPastedHtml] = useState(""); // a past email, pasted as HTML
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState([]);
  const [designSystem, setDesignSystem] = useState(null);
  const [conflicts, setConflicts] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (brandId) getDesignSystem(brandId).then(setDesignSystem);
  }, [brandId]);

  async function learn(event) {
    event.preventDefault();
    setRunning(true);
    setProgress([]);
    setConflicts([]);
    setError(null);
    try {
      const id = brandId ?? (await createBrand()).brand_id;
      onBrand(id);
      // A pasted email is uploaded like any other document, as a file in the brand's uploads.
      const pasted = pastedHtml.trim() ? [new File([pastedHtml], "past-email.html", { type: "text/html" })] : [];
      if (files.length || pasted.length) await uploadFiles(id, [...files, ...pasted]);

      for await (const event of learnBrand(id, url)) {
        if (event.type === "status") setProgress((lines) => [...lines, event.text]);
        if (event.type === "brand_ready") {
          setDesignSystem(event.design_system);
          setConflicts(event.conflicts);
        }
        if (event.type === "done") setProgress((lines) => [...lines, `Done in ${event.seconds} s, $${event.cost_usd}`]);
        if (event.type === "error") setError(event.message);
      }
      onLearned();
    } catch (failure) {
      setError(failure.message);
    }
    setRunning(false);
  }

  return (
    <div className="page">
      <h1>Learn a brand</h1>
      <p className="muted">Give a website, documents, or both. The agent reads them and builds the brand's design system.</p>

      <form className="card form" onSubmit={learn}>
        <label>
          Website
          <input type="url" placeholder="https://www.brand.com" value={url} onChange={(e) => setUrl(e.target.value)} />
        </label>
        <label>
          Documents
          <input
            type="file"
            multiple
            accept=".pdf,.html,.htm,image/*"
            onChange={(e) => setFiles([...e.target.files])}
          />
          <span className="hint">A brand guideline PDF, images, or a past email as an HTML file.</span>
        </label>
        <label>
          Past email (HTML)
          <textarea
            rows={5}
            placeholder="Or paste the HTML of an email the brand has already sent..."
            value={pastedHtml}
            onChange={(e) => setPastedHtml(e.target.value)}
          />
          <span className="hint">Its colors, fonts and blocks are often the best source: they are already email-ready.</span>
        </label>
        <button className="primary" disabled={running || (!url && !files.length && !pastedHtml.trim())}>
          {running ? "Learning..." : "Learn the brand"}
        </button>
      </form>

      {progress.length > 0 && (
        <ul className="card progress">
          {progress.map((line, index) => (
            <li key={index}>{line}</li>
          ))}
          {running && <li className="typing">Working</li>}
        </ul>
      )}
      {error && <p className="card error">{error}</p>}

      {conflicts.length > 0 && (
        <div className="card">
          <h2>Website and documents disagree</h2>
          <p className="muted">The document value is used. You can change it from the Studio chat.</p>
          <ul>
            {conflicts.map((conflict) => (
              <li key={conflict.field}>
                <strong>{conflict.field}</strong>: website {conflict.website_value}, document {conflict.document_value}
              </li>
            ))}
          </ul>
        </div>
      )}

      {designSystem && (
        <>
          <div className="row">
            <h1>Design system</h1>
            <button className="primary" onClick={onOpenStudio}>
              Open the Studio
            </button>
          </div>
          <DesignSystem brandId={brandId} designSystem={designSystem} />
        </>
      )}
    </div>
  );
}
