// frontend/src/lib/cardApi.js
const DEFAULT_BASE = '';  // same-origin

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

export async function postCard(payload, { fetchImpl = fetch, baseUrl = DEFAULT_BASE } = {}) {
  const resp = await fetchImpl(`${baseUrl}/api/card`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new ApiError(data.detail || `request failed (${resp.status})`, resp.status);
  return data;
}

export async function getCardPreview(slug, { fetchImpl = fetch, baseUrl = DEFAULT_BASE } = {}) {
  const resp = await fetchImpl(`${baseUrl}/api/card/${encodeURIComponent(slug)}`);
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new ApiError(data.detail || `request failed (${resp.status})`, resp.status);
  return data;
}
