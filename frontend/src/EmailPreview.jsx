// The email as the reader will see it, rebuilt from its sections at every event,
// plus why each part is the way it is. Clicking a part makes the next message about it.

import { useState } from "react";

function escape(text) {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

// Preview only: hovering a section outlines it and shows why the agent made it that way.
const WHY_ON_HOVER = `<style>
[data-why] { position: relative; }
[data-why]:hover { outline: 2px solid #503adb; outline-offset: -2px; }
[data-why]:hover::after {
  content: "Why: " attr(data-why);
  position: absolute; top: 8px; left: 8px; right: 8px; z-index: 10;
  padding: 8px 12px; border-radius: 10px;
  background: rgba(80, 58, 219, 0.95); color: #fff;
  font: 500 12px/1.45 Inter, system-ui, sans-serif; text-align: left;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.18);
  pointer-events: none;
}
</style>`;

// The same envelope as the backend's render_email(): the sections in a centered 600px column.
// With `whyOnHover`, each section is wrapped so hovering it shows its reasoning (preview only:
// the HTML to send stays clean).
export function emailHtml(sections, whyOnHover = false) {
  const text = (id) => sections.find((s) => s.id === id)?.content ?? "";
  const body = sections
    .filter((s) => s.id !== "subject" && s.id !== "preheader")
    .map((s) => (whyOnHover ? `<div data-why="${escape(s.reasoning)}">${s.content}</div>` : s.content))
    .join("\n");
  return `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${escape(text("subject"))}</title>
${whyOnHover ? WHY_ON_HOVER : ""}
</head>
<body style="margin:0; padding:0;">
<div style="display:none; max-height:0; overflow:hidden;">${escape(text("preheader"))}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr><td align="center">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" style="width:100%; max-width:600px;"><tr><td>
${body}
</td></tr></table>
</td></tr></table>
</body>
</html>`;
}

export default function EmailPreview({ sections, selected, onSelect }) {
  const [tab, setTab] = useState("preview");
  const subject = sections.find((s) => s.id === "subject");
  const html = emailHtml(sections); // what a person sends: shown in the HTML tab
  const preview = emailHtml(sections, true); // the same, plus the reasoning on hover

  return (
    <section className="card preview">
      <div className="row">
        <p className="subject">
          <span className="muted">Subject:</span> {subject ? subject.content : "—"}
        </p>
        <div className="tabs">
          <button className={tab === "preview" ? "active" : ""} onClick={() => setTab("preview")}>
            Preview
          </button>
          <button className={tab === "html" ? "active" : ""} onClick={() => setTab("html")}>
            HTML
          </button>
        </div>
      </div>

      {tab === "preview" ? (
        <div className="frame">
          {sections.length ? <iframe title="Email preview" srcDoc={preview} /> : <p className="muted empty">The email appears here, part by part.</p>}
        </div>
      ) : (
        <pre className="code">{html}</pre>
      )}

      {sections.length > 0 && (
        <>
          <h3>Why each part</h3>
          <ul className="parts">
            {sections.map((section) => (
              <li key={section.id} className={section.id === selected ? "selected" : ""}>
                <button onClick={() => onSelect(section.id)} title="Make the next message about this part">
                  {section.id}
                </button>
                <span>{section.reasoning}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
