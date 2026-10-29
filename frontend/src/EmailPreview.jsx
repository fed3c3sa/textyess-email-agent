// The email as the reader will see it, rebuilt from its sections at every event,
// plus why each part is the way it is. Clicking a part makes the next message about it.

import { useState } from "react";

function escape(text) {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// The same envelope as the backend's render_email(): the sections in a centered 600px column.
export function emailHtml(sections) {
  const text = (id) => sections.find((s) => s.id === id)?.content ?? "";
  const body = sections
    .filter((s) => s.id !== "subject" && s.id !== "preheader")
    .map((s) => s.content)
    .join("\n");
  return `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${escape(text("subject"))}</title>
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
  const html = emailHtml(sections);

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
          {sections.length ? <iframe title="Email preview" srcDoc={html} /> : <p className="muted empty">The email appears here, part by part.</p>}
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
