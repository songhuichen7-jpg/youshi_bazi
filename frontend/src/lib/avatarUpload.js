export const SERVER_AVATAR_MAX_BYTES = 4 * 1024 * 1024;
export const AVATAR_COMPRESS_TRIGGER_BYTES = 1536 * 1024;
export const AVATAR_TARGET_BYTES = 1024 * 1024;
export const AVATAR_MAX_SOURCE_BYTES = 25 * 1024 * 1024;
export const AVATAR_MAX_DIMENSION = 1024;

export const BACKEND_AVATAR_MIME = ['image/png', 'image/jpeg', 'image/webp', 'image/gif'];
export const ALLOWED_AVATAR_MIME = [
  ...BACKEND_AVATAR_MIME,
  'image/heic',
  'image/heif',
];
export const AVATAR_ACCEPT = ALLOWED_AVATAR_MIME.join(',');

function normaliseMime(type) {
  return String(type || '').trim().toLowerCase();
}

function avatarError(message) {
  return new Error(message);
}

function isBackendSupported(file) {
  return BACKEND_AVATAR_MIME.includes(normaliseMime(file?.type));
}

function isAllowedSource(file) {
  return ALLOWED_AVATAR_MIME.includes(normaliseMime(file?.type));
}

function outputName(name, type) {
  const base = String(name || 'avatar').replace(/\.[^.]*$/, '') || 'avatar';
  const ext = normaliseMime(type) === 'image/jpeg' ? 'jpg' : 'webp';
  return `${base}.${ext}`;
}

function blobToFile(blob, originalName, type) {
  const finalType = blob.type || type || 'image/webp';
  return new File([blob], outputName(originalName, finalType), { type: finalType });
}

async function decodeImage(file, env = globalThis) {
  if (typeof env.createImageBitmap === 'function') {
    return env.createImageBitmap(file);
  }
  if (typeof env.Image !== 'function' || !env.URL?.createObjectURL) {
    throw avatarError('当前浏览器暂时不能压缩这张图片');
  }
  return new Promise((resolve, reject) => {
    const url = env.URL.createObjectURL(file);
    const img = new env.Image();
    img.onload = () => {
      env.URL.revokeObjectURL(url);
      resolve(img);
    };
    img.onerror = () => {
      env.URL.revokeObjectURL(url);
      reject(avatarError('图片读取失败'));
    };
    img.src = url;
  });
}

function canvasToBlob(canvas, type, quality) {
  return new Promise((resolve) => {
    canvas.toBlob((blob) => resolve(blob), type, quality);
  });
}

export async function resizeAvatarImage(file, options = {}) {
  const env = options.env || globalThis;
  const image = await decodeImage(file, env);
  const sourceWidth = image.width || image.naturalWidth;
  const sourceHeight = image.height || image.naturalHeight;
  if (!sourceWidth || !sourceHeight) {
    throw avatarError('图片读取失败');
  }

  const canvas = env.document?.createElement?.('canvas');
  const ctx = canvas?.getContext?.('2d');
  if (!canvas || !ctx) {
    throw avatarError('当前浏览器暂时不能压缩这张图片');
  }

  const maxDimension = options.maxDimension || AVATAR_MAX_DIMENSION;
  const targetBytes = options.targetBytes || AVATAR_TARGET_BYTES;
  const dimensions = [maxDimension, 768, 512];
  const qualities = [0.86, 0.76, 0.66];
  const outputTypes = ['image/webp', 'image/jpeg'];
  let bestBlob = null;

  for (const dimension of dimensions) {
    const scale = Math.min(1, dimension / Math.max(sourceWidth, sourceHeight));
    canvas.width = Math.max(1, Math.round(sourceWidth * scale));
    canvas.height = Math.max(1, Math.round(sourceHeight * scale));
    ctx.fillStyle = '#fff';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(image, 0, 0, canvas.width, canvas.height);

    for (const type of outputTypes) {
      for (const quality of qualities) {
        const blob = await canvasToBlob(canvas, type, quality);
        if (!blob) continue;
        if (!bestBlob || blob.size < bestBlob.size) bestBlob = blob;
        if (blob.size <= targetBytes) {
          image.close?.();
          return blobToFile(blob, file.name, blob.type || type);
        }
      }
    }
  }

  image.close?.();
  if (!bestBlob) {
    throw avatarError('图片压缩失败，请换一张试试');
  }
  return blobToFile(bestBlob, file.name, bestBlob.type || 'image/webp');
}

export async function prepareAvatarUpload(file, options = {}) {
  if (!file) {
    throw avatarError('请选择一张图片');
  }
  if (!isAllowedSource(file)) {
    throw avatarError('请上传 PNG / JPG / WebP / GIF / HEIC 图片');
  }
  if (file.size > AVATAR_MAX_SOURCE_BYTES) {
    throw avatarError('图片太大，请先裁剪后再上传');
  }

  const needsConversion = !isBackendSupported(file);
  const needsCompression = file.size > AVATAR_COMPRESS_TRIGGER_BYTES;
  if (!needsConversion && !needsCompression) {
    return file;
  }

  const resizeImageFile = options.resizeImageFile || resizeAvatarImage;
  let prepared;
  try {
    prepared = await resizeImageFile(file, options);
  } catch (err) {
    if (needsConversion) {
      throw avatarError('这张图片格式暂时不能直接上传，请换成 JPG / PNG / WebP');
    }
    if (file.size <= SERVER_AVATAR_MAX_BYTES) {
      return file;
    }
    throw avatarError(err?.message || '图片压缩失败，请换一张试试');
  }

  if (!prepared || !prepared.size) {
    throw avatarError('图片压缩失败，请换一张试试');
  }
  if (!isBackendSupported(prepared)) {
    throw avatarError('图片压缩失败，请换一张试试');
  }
  if (prepared.size > SERVER_AVATAR_MAX_BYTES) {
    throw avatarError('图片压缩后仍然超过 4MB，请先裁剪后再上传');
  }
  return prepared;
}
