// What the agent understood about the brand: one card per part of the design system.

import { assetUrl } from "./api.js";

function List({ items }) {
  if (!items.length) return <p className="muted">Nothing found.</p>;
  return (
    <ul>
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}

export default function DesignSystem({ brandId, designSystem: ds }) {
  return (
    <div className="grid">
      <section className="card">
        <h2>Identity</h2>
        <p>
          <strong>{ds.identity.name || "No name found"}</strong>
          {ds.identity.language && <span className="chip">{ds.identity.language}</span>}
        </p>
        <p className="muted">{ds.identity.description}</p>
      </section>

      <section className="card">
        <h2>Colors</h2>
        <div className="swatches">
          {ds.colors.map((color, index) => (
            <div className="swatch" key={index}>
              <span style={{ background: color.hex }} />
              <strong>{color.hex}</strong>
              <small className="muted">{color.role}</small>
            </div>
          ))}
        </div>
      </section>

      <section className="card">
        <h2>Fonts</h2>
        {ds.fonts.map((font) => (
          <p key={font.role} style={{ fontFamily: `${font.family}, sans-serif` }}>
            <span className="muted">{font.role}:</span> {font.family}
          </p>
        ))}
      </section>

      <section className="card">
        <h2>Voice</h2>
        <p>
          {ds.voice.tone.map((word) => (
            <span className="chip" key={word}>
              {word}
            </span>
          ))}
        </p>
        <h3>Do</h3>
        <List items={ds.voice.dos} />
        <h3>Don't</h3>
        <List items={ds.voice.donts} />
        <h3>In their words</h3>
        <List items={ds.voice.sample_phrases.map((phrase) => `“${phrase}”`)} />
      </section>

      <section className="card wide">
        <h2>Images</h2>
        <div className="assets">
          {ds.assets.map((asset) => (
            <figure key={asset.pointer}>
              <img src={assetUrl(brandId, asset.pointer)} alt={asset.description} />
              <figcaption>
                <span className="chip">{asset.role}</span> {asset.description}
              </figcaption>
            </figure>
          ))}
        </div>
      </section>

      <section className="card wide">
        <h2>Brand blocks</h2>
        <div className="examples">
          {ds.html_examples.map((example, index) => (
            <figure key={index}>
              <figcaption className="muted">{example.kind}</figcaption>
              <iframe title={example.kind} srcDoc={example.html} />
            </figure>
          ))}
        </div>
      </section>

      <section className="card">
        <h2>Guidelines</h2>
        <p>{ds.guidelines || <span className="muted">Nothing found.</span>}</p>
      </section>

      <section className="card">
        <h2>Email rules</h2>
        <List items={ds.email_constraints} />
        <h3>Your notes</h3>
        <List items={ds.user_notes} />
      </section>
    </div>
  );
}
