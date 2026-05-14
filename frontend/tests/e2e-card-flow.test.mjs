// frontend/tests/e2e-card-flow.test.mjs
// Run manually against a live backend:
//   cd server && uv run uvicorn app.main:app --port 8000 &
//   cd frontend && E2E_API=http://localhost:8000 node --test tests/e2e-card-flow.test.mjs
// Skipped by default when E2E_API is not set.
import test from 'node:test';
import assert from 'node:assert/strict';

const BASE = process.env.E2E_API;
const skip = !BASE;

test('POST /api/card → GET /api/card/:slug round trip', { skip }, async () => {
  const createResp = await fetch(`${BASE}/api/card`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      birth: { year: 1998, month: 7, day: 15, hour: 14, minute: 0 },
      nickname: 'e2e-tester',
    }),
  });
  assert.equal(createResp.status, 200);
  const card = await createResp.json();
  assert.ok(card.type_id);
  assert.ok(card.share_slug.startsWith('c_'));

  const previewResp = await fetch(`${BASE}/api/card/${card.share_slug}`);
  assert.equal(previewResp.status, 200);
  const preview = await previewResp.json();
  assert.equal(preview.cosmic_name, card.cosmic_name);
  assert.equal(preview.suffix, card.suffix);
});

test('POST /api/track with card_view writes event', { skip }, async () => {
  const resp = await fetch(`${BASE}/api/track`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      event: 'card_view',
      properties: { type_id: '01', from: 'direct' },
    }),
  });
  assert.equal(resp.status, 204);
});
