import test from 'node:test';
import assert from 'node:assert/strict';
import { postHepanInvite, postHepanComplete, getHepan } from '../src/lib/hepanApi.js';

function fakeFetch(handler) {
  return async (url, init) => handler(url, init || {});
}

test('postHepanInvite POSTs JSON to /api/hepan/invite', async () => {
  let captured;
  const fetchImpl = fakeFetch((url, init) => {
    captured = { url, init };
    return {
      ok: true,
      status: 200,
      json: async () => ({ slug: 'h_abc12345', a: { type_id: '01' }, invite_url: '/hepan/h_abc12345' }),
    };
  });
  const out = await postHepanInvite(
    { birth: { year: 1995, month: 5, day: 12, hour: -1, minute: 0 }, nickname: '小满' },
    { fetchImpl },
  );
  assert.equal(captured.url, '/api/hepan/invite');
  assert.equal(captured.init.method, 'POST');
  assert.equal(captured.init.headers['Content-Type'], 'application/json');
  assert.deepEqual(JSON.parse(captured.init.body).nickname, '小满');
  assert.equal(out.slug, 'h_abc12345');
});

test('postHepanComplete includes slug in URL', async () => {
  let captured;
  const fetchImpl = fakeFetch((url, init) => {
    captured = { url, init };
    return {
      ok: true,
      status: 200,
      json: async () => ({ slug: 'h_xyz', status: 'completed', a: {}, b: {}, category: '天作搭子' }),
    };
  });
  const out = await postHepanComplete(
    'h_xyz',
    { birth: { year: 1990, month: 1, day: 1, hour: 12, minute: 0 }, nickname: null },
    { fetchImpl },
  );
  assert.equal(captured.url, '/api/hepan/h_xyz/complete');
  assert.equal(captured.init.method, 'POST');
  assert.equal(out.status, 'completed');
});

test('getHepan reads /api/hepan/{slug}', async () => {
  const fetchImpl = fakeFetch(() => ({
    ok: true,
    status: 200,
    json: async () => ({ slug: 'h_abc', status: 'pending', a: { cosmic_name: '春笋' } }),
  }));
  const out = await getHepan('h_abc', { fetchImpl });
  assert.equal(out.status, 'pending');
  assert.equal(out.a.cosmic_name, '春笋');
});

test('hepan API surfaces server error detail on non-2xx', async () => {
  const fetchImpl = fakeFetch(() => ({
    ok: false,
    status: 404,
    json: async () => ({ detail: 'invite not found' }),
  }));
  await assert.rejects(
    () => getHepan('h_missing', { fetchImpl }),
    e => e.message === 'invite not found' && e.status === 404,
  );
});
