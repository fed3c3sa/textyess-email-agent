// Every call to the backend lives here. The two long operations (learning a brand,
// a chat turn) answer with Server-Sent Events over POST: `readEvents` turns that
// stream into a loop over plain event objects, e.g. { type: "section_added", ... }.

export const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function request(method, path, body) {
  const response = await fetch(`${API_URL}${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) throw new Error(`${method} ${path} failed: ${response.status}`);
  return response.json();
}

// POST a JSON body and yield the events of the SSE answer, one by one.
async function* readEvents(path, body) {
  const response = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`POST ${path} failed: ${response.status}`);

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) return;
    buffer += value;
    const blocks = buffer.split("\n\n"); // an SSE event ends with an empty line
    buffer = blocks.pop(); // the last block may still be incomplete
    for (const block of blocks) {
      const data = block.split("\n").find((line) => line.startsWith("data: ")); // ": ping" lines are skipped
      if (data) yield JSON.parse(data.slice("data: ".length));
    }
  }
}

export const createBrand = () => request("POST", "/brands");
export const getDesignSystem = (brandId) => request("GET", `/brands/${brandId}`);
export const createSession = (brandId) => request("POST", `/brands/${brandId}/sessions`);
export const getEmail = (brandId, sessionId) => request("GET", `/brands/${brandId}/sessions/${sessionId}/email`);

export async function uploadFiles(brandId, files) {
  const form = new FormData();
  for (const file of files) form.append("files", file);
  const response = await fetch(`${API_URL}/brands/${brandId}/uploads`, { method: "POST", body: form });
  if (!response.ok) throw new Error(`Upload failed: ${response.status}`);
  return response.json();
}

export const learnBrand = (brandId, url) => readEvents(`/brands/${brandId}/learn`, { url: url || null });

export const sendMessage = (brandId, sessionId, text, selectedSection) =>
  readEvents(`/brands/${brandId}/sessions/${sessionId}/messages`, {
    text,
    selected_section: selectedSection || null,
  });

// An asset pointer is a public URL, or a path in the brand folder ('/assets/logo.png').
export const assetUrl = (brandId, pointer) =>
  pointer.startsWith("/") ? `${API_URL}/brands/${brandId}/files${pointer}` : pointer;
