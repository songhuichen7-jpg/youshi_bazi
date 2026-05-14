// frontend/src/lib/removeWhiteBg.js
//
// Pixel-level white background removal for illustrations.
// Loads an image, scans every pixel, and sets alpha to 0
// for near-white regions (brightness > 240), with a 30-level
// gradient for the 210-240 transition zone.

export function removeWhiteBg(imgElement) {
  const w = imgElement.naturalWidth;
  const h = imgElement.naturalHeight;
  const canvas = document.createElement('canvas');
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext('2d');
  ctx.drawImage(imgElement, 0, 0);
  const imageData = ctx.getImageData(0, 0, w, h);
  const px = imageData.data;
  for (let i = 0; i < px.length; i += 4) {
    const brightness = (px[i] + px[i + 1] + px[i + 2]) / 3;
    if (brightness > 240) {
      px[i + 3] = 0;
    } else if (brightness > 210) {
      px[i + 3] = Math.round(255 * (240 - brightness) / 30);
    }
  }
  ctx.putImageData(imageData, 0, 0);
  return canvas.toDataURL('image/png');
}
