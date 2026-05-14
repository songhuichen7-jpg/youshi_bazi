import test from 'node:test';
import assert from 'node:assert/strict';

import {
  AVATAR_ACCEPT,
  SERVER_AVATAR_MAX_BYTES,
  prepareAvatarUpload,
} from '../src/lib/avatarUpload.js';
import { uploadAvatar } from '../src/lib/api.js';

test('prepareAvatarUpload keeps small backend-supported images unchanged', async () => {
  const file = new File(['small'], 'small.jpg', { type: 'image/jpeg' });
  let resized = false;

  const prepared = await prepareAvatarUpload(file, {
    resizeImageFile: async () => {
      resized = true;
      return file;
    },
  });

  assert.equal(prepared, file);
  assert.equal(resized, false);
});

test('prepareAvatarUpload compresses large images before upload', async () => {
  const file = new File([new Uint8Array(SERVER_AVATAR_MAX_BYTES + 20)], 'phone.jpg', {
    type: 'image/jpeg',
  });
  const compressed = new File(['webp'], 'phone.webp', { type: 'image/webp' });

  const prepared = await prepareAvatarUpload(file, {
    resizeImageFile: async (input) => {
      assert.equal(input, file);
      return compressed;
    },
  });

  assert.equal(prepared, compressed);
});

test('prepareAvatarUpload tries to convert HEIC/HEIF instead of sending them to backend', async () => {
  assert.match(AVATAR_ACCEPT, /image\/heic/);
  assert.match(AVATAR_ACCEPT, /image\/heif/);

  const file = new File(['heic'], 'phone.heic', { type: 'image/heic' });
  const converted = new File(['webp'], 'phone.webp', { type: 'image/webp' });

  const prepared = await prepareAvatarUpload(file, {
    resizeImageFile: async () => converted,
  });

  assert.equal(prepared, converted);
});

test('prepareAvatarUpload fails fast when a big image cannot be compressed under backend limit', async () => {
  const file = new File([new Uint8Array(SERVER_AVATAR_MAX_BYTES + 20)], 'huge.jpg', {
    type: 'image/jpeg',
  });
  const stillHuge = new File([new Uint8Array(SERVER_AVATAR_MAX_BYTES + 10)], 'huge.webp', {
    type: 'image/webp',
  });

  await assert.rejects(
    () => prepareAvatarUpload(file, { resizeImageFile: async () => stillHuge }),
    /压缩后仍然超过/,
  );
});

test('uploadAvatar sends the prepared file in multipart form data', async () => {
  const originalFetch = globalThis.fetch;
  const original = new File([new Uint8Array(SERVER_AVATAR_MAX_BYTES + 20)], 'phone.jpg', {
    type: 'image/jpeg',
  });
  const compressed = new File(['webp'], 'phone.webp', { type: 'image/webp' });
  let captured;

  globalThis.fetch = async (url, opts) => {
    captured = { url, opts, file: opts.body.get('file') };
    return { ok: true, status: 200, json: async () => ({ avatar_url: '/static/avatars/u.webp' }) };
  };

  try {
    await uploadAvatar(original, { resizeImageFile: async () => compressed });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(captured.url, '/api/auth/avatar');
  assert.equal(captured.opts.method, 'POST');
  assert.equal(captured.opts.credentials, 'include');
  assert.equal(captured.file.name, 'phone.webp');
  assert.equal(captured.file.type, 'image/webp');
  assert.equal(captured.file.size, compressed.size);
  assert.equal(await captured.file.text(), await compressed.text());
});

test('uploadAvatar explains local file pages cannot reach the API', async () => {
  const originalLocation = Object.getOwnPropertyDescriptor(globalThis, 'location');
  Object.defineProperty(globalThis, 'location', {
    configurable: true,
    value: { protocol: 'file:' },
  });

  try {
    await assert.rejects(
      () => uploadAvatar(new File(['small'], 'small.jpg', { type: 'image/jpeg' })),
      /本地文件页面不能连接服务器/,
    );
  } finally {
    if (originalLocation) Object.defineProperty(globalThis, 'location', originalLocation);
    else delete globalThis.location;
  }
});

test('uploadAvatar wraps fetch failures with an avatar-specific message', async () => {
  const originalFetch = globalThis.fetch;
  const originalLocation = Object.getOwnPropertyDescriptor(globalThis, 'location');
  Object.defineProperty(globalThis, 'location', {
    configurable: true,
    value: { protocol: 'https:' },
  });
  globalThis.fetch = async () => {
    throw new TypeError('Failed to fetch');
  };

  try {
    await assert.rejects(
      () => uploadAvatar(new File(['small'], 'small.jpg', { type: 'image/jpeg' })),
      /头像上传请求没有发出去/,
    );
  } finally {
    globalThis.fetch = originalFetch;
    if (originalLocation) Object.defineProperty(globalThis, 'location', originalLocation);
    else delete globalThis.location;
  }
});
