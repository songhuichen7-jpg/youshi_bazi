// frontend/tests/card-api.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { postCard, getCardPreview } from '../src/lib/cardApi.js';

test('postCard POSTs birth + nickname and returns json', async () => {
  let capturedBody;
  const mockFetch = async (url, opts) => {
    capturedBody = JSON.parse(opts.body);
    return {
      ok: true, status: 200,
      json: async () => ({ type_id: '01', cosmic_name: '春笋', share_slug: 'c_abc' }),
    };
  };
  const result = await postCard({
    birth: { year: 1998, month: 7, day: 15, hour: 14, minute: 0 },
    nickname: '小满',
  }, { fetchImpl: mockFetch });
  assert.equal(result.type_id, '01');
  assert.equal(capturedBody.nickname, '小满');
  assert.equal(capturedBody.birth.year, 1998);
});

test('postCard throws structured error on 422', async () => {
  const mockFetch = async () => ({
    ok: false, status: 422,
    json: async () => ({ detail: 'bad input' }),
  });
  await assert.rejects(
    () => postCard({ birth: { year: 1800, month: 1, day: 1, hour: 0, minute: 0 } }, { fetchImpl: mockFetch }),
    err => err.status === 422 && /bad input/.test(err.message),
  );
});

test('getCardPreview fetches preview endpoint', async () => {
  let capturedUrl;
  const mockFetch = async (url) => {
    capturedUrl = url;
    return {
      ok: true, status: 200,
      json: async () => ({ slug: 'c_abc', cosmic_name: '春笋', suffix: '天生享乐家', illustration_url: '/...' }),
    };
  };
  await getCardPreview('c_abc', { fetchImpl: mockFetch });
  assert.match(capturedUrl, /\/api\/card\/c_abc$/);
});
