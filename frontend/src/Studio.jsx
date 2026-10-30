// Screen 2, Studio: the chat on the left, the email preview on the right.
// A chat turn streams events: the reply's text, progress, and every section the agent
// writes, which lands in the preview at once. If there is no brand or session yet,
// the first message creates them, so the user can start straight from the chat.

import { useEffect, useRef, useState } from "react";
import { createBrand, createSession, getEmail, sendMessage, uploadFiles } from "./api.js";
import { Icon } from "./App.jsx";
import EmailPreview from "./EmailPreview.jsx";

const EXAMPLES = [
  "Black Friday email, 20% off, make it feel urgent",
  "Welcome email for new customers",
  "Announce our new collection",
];

// The sections with `section` written in at `index`, replacing the one with the same id.
function placeSection(sections, section, index) {
  const others = sections.filter((s) => s.id !== section.id);
  return [...others.slice(0, index), section, ...others.slice(index)];
}

function Reply({ reply, working }) {
  return (
    <div className="reply">
      <span className="avatar">
        <Icon name="studio" />
      </span>
      <div className="reply-body">
      {reply.status.map((line, index) => (
        <p className="status" key={index}>
          {line}
        </p>
      ))}
      {reply.steps.length > 0 && (
        <details className="reasoning">
          <summary>Reasoning ({reply.steps.length})</summary>
          <ul>
            {reply.steps.map((step, index) => (
              <li key={index}>
                <span className="check">✓</span>
                <strong>{step.id}</strong>: {step.reasoning}
              </li>
            ))}
          </ul>
        </details>
      )}
      {reply.text && <p className="text">{reply.text}</p>}
      {working && <p className="typing">Writing</p>}
      {reply.error && <p className="error">{reply.error}</p>}
      {reply.meta && <p className="meta">{reply.meta}</p>}
      </div>
    </div>
  );
}

export default function Studio({ brandId, sessionId, onBrand, onSession, onLearned }) {
  const [messages, setMessages] = useState([]); // user messages and agent replies, in order
  const [sections, setSections] = useState([]); // the current email
  const [selected, setSelected] = useState(null); // the section the next message is about
  const [input, setInput] = useState("");
  const [files, setFiles] = useState([]); // images and PDFs to attach to the next message
  const [busy, setBusy] = useState(false);
  const bottom = useRef(null);

  useEffect(() => {
    if (brandId && sessionId) getEmail(brandId, sessionId).then((answer) => setSections(answer.email.sections));
  }, []);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Change the last message, which is the reply being streamed.
  function updateReply(change) {
    setMessages((list) => [...list.slice(0, -1), change(list.at(-1))]);
  }

  function handle(event) {
    switch (event.type) {
      case "message":
        updateReply((reply) => ({ ...reply, text: reply.text + event.text }));
        break;
      case "status":
        updateReply((reply) => ({ ...reply, status: [...reply.status, event.text] }));
        break;
      case "section_draft": // written by the model, its tool confirms it a moment later
        setSections((list) =>
          list.some((s) => s.id === event.section.id)
            ? list.map((s) => (s.id === event.section.id ? event.section : s))
            : [...list, event.section],
        );
        break;
      case "section_added":
      case "section_updated":
        setSections((list) => placeSection(list, event.section, event.index));
        updateReply((reply) => ({ ...reply, steps: [...reply.steps, event.section] }));
        break;
      case "section_removed":
        setSections((list) => list.filter((s) => s.id !== event.section_id));
        break;
      case "email_replaced":
        setSections(event.email.sections);
        break;
      case "done":
        updateReply((reply) => ({ ...reply, meta: `${event.seconds} s · $${event.cost_usd}` }));
        onLearned(); // the agent may have learned or corrected the brand
        break;
      case "error":
        updateReply((reply) => ({ ...reply, error: event.message }));
        break;
    }
  }

  async function send(formEvent, example) {
    formEvent?.preventDefault();
    const text = (example ?? input).trim();
    if (!text || busy) return;
    const attached = files;
    setInput("");
    setFiles([]);
    setBusy(true);
    setMessages((list) => [
      ...list,
      { role: "user", text, section: selected, files: attached.map((file) => file.name) },
      { role: "agent", text: "", status: [], steps: [] },
    ]);
    try {
      const brand = brandId ?? (await createBrand()).brand_id;
      if (!brandId) onBrand(brand);
      const session = sessionId ?? (await createSession(brand)).session_id;
      if (!sessionId) onSession(session);
      const uploaded = attached.length ? (await uploadFiles(brand, attached)).files : [];
      for await (const event of sendMessage(brand, session, text, selected, uploaded)) handle(event);
    } catch (failure) {
      updateReply((reply) => ({ ...reply, error: failure.message }));
    }
    setSelected(null);
    setBusy(false);
  }

  return (
    <div className="studio">
      <section className="card chat">
        <div className="messages">
          {messages.length === 0 && (
            <div className="welcome">
              <span className="avatar big">
                <Icon name="studio" />
              </span>
              <h2>What email do you need?</h2>
              <p className="muted">Describe it, and watch it appear on the right, part by part.</p>
              {EXAMPLES.map((example) => (
                <button key={example} className="example" onClick={() => send(null, example)}>
                  {example}
                </button>
              ))}
            </div>
          )}
          {messages.map((message, index) =>
            message.role === "user" ? (
              <div className="bubble" key={index}>
                {message.section && <span className="chip">{message.section}</span>}
                {message.text}
                {message.files?.map((name) => (
                  <span className="file-chip" key={name}>
                    {name}
                  </span>
                ))}
              </div>
            ) : (
              <Reply key={index} reply={message} working={busy && index === messages.length - 1} />
            ),
          )}
          <div ref={bottom} />
        </div>

        <form className="composer" onSubmit={send}>
          {selected && (
            <p className="selected">
              Editing <strong>{selected}</strong>
              <button type="button" onClick={() => setSelected(null)}>
                ×
              </button>
            </p>
          )}
          {files.length > 0 && (
            <p className="attached">
              {files.map((file) => (
                <span className="file-chip" key={file.name}>
                  {file.name}
                  <button type="button" onClick={() => setFiles((list) => list.filter((f) => f !== file))}>
                    ×
                  </button>
                </span>
              ))}
            </p>
          )}
          <div className="input-row">
            <label className="attach" title="Attach images or PDFs">
              <Icon name="attach" />
              <input
                type="file"
                multiple
                accept="image/*,.pdf"
                onChange={(e) => {
                  setFiles((list) => [...list, ...e.target.files]);
                  e.target.value = ""; // lets the same file be picked again
                }}
              />
            </label>
            <input placeholder="Write a message, or attach an image or a PDF..." value={input} onChange={(e) => setInput(e.target.value)} />
            <button className="primary" disabled={busy || !input.trim()}>
              Send
            </button>
          </div>
        </form>
      </section>

      <EmailPreview sections={sections} selected={selected} onSelect={setSelected} />
    </div>
  );
}
