import html2canvas from 'html2canvas';

// Spec: PM/specs/03_卡片与分享系统.md
//   1080×1440 (3:4 portrait, @2x) — best fit for 朋友圈
const TARGET_WIDTH = 1080;

export function isMobileUserAgent(ua = (typeof navigator !== 'undefined' ? navigator.userAgent : '')) {
  return /iPhone|iPad|iPod|Android/i.test(ua);
}

// 卡片样式表里大量用了 oklch() 和 color-mix(in oklch, ...) — 现代浏览器
// 支持这两个色彩函数，但 html2canvas@1.4.x 的色彩解析器不认识它们，
// 一调就抛 "Attempting to parse an unsupported color function 'oklch'"，
// 整个保存图片功能就废了。
//
// 修法：导出前把 DOM 子树里所有出现 oklch / color-mix(in oklch) 的色值
// 用一个 1×1 canvas 走一遍像素，强制让浏览器把它光栅化成 sRGB，再读回
// rgb(...) / rgba(...) 串以 inline style 写回元素。html2canvas 在
// getComputedStyle 拿到的就是 rgb 了，能正常画。
//
// replaceOklchInValue 把单个 CSS 值字符串里所有 oklch(...) /
// color-mix(in oklch, ...) 调用整段替换成 resolver 返回的串。color-mix
// 整段交给 resolver — 让 canvas 把 mix 也一次算干净，比把内部 oklch 拆出
// 来再回填更稳。其他 color-mix 模式（in srgb 等）html2canvas 能识别，
// 不处理免得反伤。
export function replaceOklchInValue(value, resolve) {
  if (!value || typeof value !== 'string') return value;
  // 没出现 oklch 字样就 0 成本回避（占大多数情况）
  if (value.indexOf('oklch') === -1) return value;
  const len = value.length;
  let out = '';
  let i = 0;
  while (i < len) {
    // 找下一个 oklch( 或 color-mix(in oklch
    const oklchIdx = value.indexOf('oklch(', i);
    const cmixIdx = value.indexOf('color-mix(', i);
    let start = -1;
    let funcLen = 0;
    if (cmixIdx >= 0 && (oklchIdx < 0 || cmixIdx < oklchIdx)) {
      // 仅 in oklch 的 color-mix 走整段替换；其他 (in srgb, in lab 等)
      // 跳过，让 html2canvas 自己处理（多数版本它都能解 in srgb）。
      const tail = value.slice(cmixIdx);
      const m = tail.match(/^color-mix\(\s*in\s+oklch[\s,)]/i);
      if (m) {
        start = cmixIdx;
        funcLen = 'color-mix('.length;
      } else {
        // 跳过这个 color-mix(开头继续找下一个
        out += value.slice(i, cmixIdx + 'color-mix('.length);
        i = cmixIdx + 'color-mix('.length;
        continue;
      }
    } else if (oklchIdx >= 0) {
      start = oklchIdx;
      funcLen = 'oklch('.length;
    } else {
      out += value.slice(i);
      break;
    }
    // 找匹配的右括号（计 paren depth，处理嵌套 oklch / calc 等）
    let depth = 0;
    let end = -1;
    for (let j = start + funcLen - 1; j < len; j++) {
      const ch = value[j];
      if (ch === '(') depth++;
      else if (ch === ')') {
        depth--;
        if (depth === 0) { end = j; break; }
      }
    }
    if (end < 0) {
      // 括号没闭合，保守 — 输出剩余字面退出
      out += value.slice(i);
      break;
    }
    out += value.slice(i, start);
    out += resolve(value.slice(start, end + 1));
    i = end + 1;
  }
  return out;
}

// 用 1×1 canvas 把任何 CSS 颜色串（含 oklch / color-mix in oklch）渲染
// 一遍，从 getImageData 读出像素的 rgba，返回 "rgb(r, g, b)" 或
// "rgba(r, g, b, a)" 串。Canvas 内部走完整的 CSS 颜色管线，所以输出
// 必定是 sRGB 三元组，不会再含 oklch。
function makeCanvasColorResolver() {
  if (typeof document === 'undefined') return null;
  const cv = document.createElement('canvas');
  cv.width = cv.height = 1;
  const ctx = cv.getContext('2d');
  if (!ctx) return null;
  return (cssColor) => {
    ctx.clearRect(0, 0, 1, 1);
    // 兜底背景透明，让带 alpha 的 oklch 能正确读回 alpha
    ctx.fillStyle = 'rgba(0,0,0,0)';
    try {
      ctx.fillStyle = cssColor;
    } catch {
      return cssColor;
    }
    ctx.fillRect(0, 0, 1, 1);
    let pixel;
    try {
      pixel = ctx.getImageData(0, 0, 1, 1).data;
    } catch {
      return cssColor;
    }
    const [r, g, b, a] = pixel;
    if (a === 255) return `rgb(${r}, ${g}, ${b})`;
    return `rgba(${r}, ${g}, ${b}, ${(a / 255).toFixed(3)})`;
  };
}

// 这些 CSS 属性可能含色彩函数，需要 resolve 后用 inline style 写回元素，
// 让 html2canvas 在 getComputedStyle 时拿到的是 rgb。
const COLOR_BEARING_PROPS = [
  'color',
  'background-color',
  'border-top-color',
  'border-right-color',
  'border-bottom-color',
  'border-left-color',
  'outline-color',
  'caret-color',
  'text-decoration-color',
  'box-shadow',
  'text-shadow',
  'background-image',
  'fill',
  'stroke',
];

function inlineResolvedColors(root) {
  if (!root || typeof window === 'undefined') return;
  const resolve = makeCanvasColorResolver();
  if (!resolve) return;
  const elements = [root, ...root.querySelectorAll('*')];
  for (const el of elements) {
    if (!(el instanceof HTMLElement) && !(el instanceof SVGElement)) continue;
    const cs = window.getComputedStyle(el);
    for (const prop of COLOR_BEARING_PROPS) {
      const value = cs.getPropertyValue(prop);
      if (!value || value.indexOf('oklch') === -1) continue;
      const replaced = replaceOklchInValue(value, resolve);
      if (replaced !== value) {
        el.style.setProperty(prop, replaced);
      }
    }
  }
}

export async function renderCardToDataUrl(node) {
  const p5Canvas = node.querySelector('.card-front-dust canvas');
  let tempImg = null;

  if (p5Canvas) {
    const dataUrl = p5Canvas.toDataURL('image/png');
    tempImg = document.createElement('img');
    tempImg.src = dataUrl;
    tempImg.style.cssText = p5Canvas.style.cssText;
    p5Canvas.style.display = 'none';
    p5Canvas.parentNode.appendChild(tempImg);
  }

  // html2canvas cannot render CSS 3D transforms. For 3D cards, clone the
  // visible face into a flat temporary wrapper so html2canvas gets a simple
  // absolutely-positioned stack with explicit dimensions.
  const is3d = node.classList.contains('card-scene');
  const isHepan3d = node.classList.contains('hepan-scene');
  let target = node;

  if (is3d || isHepan3d) {
    const rect = node.getBoundingClientRect();
    let face;
    if (is3d) {
      face = node.querySelector('.card-front');
    } else {
      const body = node.querySelector('.hepan-body');
      face = body?.classList.contains('is-flipped')
        ? node.querySelector('.hepan-back-face')
        : node.querySelector('.hepan-front');
    }
    const wrapper = document.createElement('div');
    wrapper.style.cssText = `position:fixed;left:-9999px;top:0;width:${rect.width}px;height:${rect.height}px;overflow:hidden;border-radius:16px;`;
    const cs = getComputedStyle(node);
    for (const prop of ['--card-bg', '--card-bg-light', '--glow', '--theme', '--theme-a', '--theme-b']) {
      wrapper.style.setProperty(prop, cs.getPropertyValue(prop));
    }
    const clone = face.cloneNode(true);
    clone.style.position = 'absolute';
    clone.style.inset = '0';
    clone.style.backfaceVisibility = 'visible';
    wrapper.appendChild(clone);
    document.body.appendChild(wrapper);
    target = wrapper;
  }

  // html2canvas@1.4.x 不识别 oklch() / color-mix(in oklch)；先把整个
  // 目标子树里相关属性的色值转成 rgb 写回 inline style 再喂给它。
  inlineResolvedColors(target);

  const rect = target.getBoundingClientRect();
  const scale = rect.width > 0 ? TARGET_WIDTH / rect.width : 2;
  const canvas = await html2canvas(target, {
    scale,
    useCORS: true,
    backgroundColor: null,
    logging: false,
  });

  if (is3d || isHepan3d) {
    target.remove();
  }

  if (tempImg) {
    tempImg.remove();
    p5Canvas.style.display = '';
  }

  return canvas.toDataURL('image/png');
}

export function triggerDownload(dataUrl, filename) {
  const a = document.createElement('a');
  a.href = dataUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
}

export function showLongPressOverlay(dataUrl) {
  const overlay = document.createElement('div');
  overlay.className = 'save-overlay';
  overlay.innerHTML = `
    <div class="save-overlay-inner">
      <img src="${dataUrl}" alt="长按保存" />
      <p>长按图片保存到相册</p>
      <button type="button" class="close">关闭</button>
    </div>
  `;
  overlay.querySelector('.close').addEventListener('click', () => overlay.remove());
  overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });
  document.body.appendChild(overlay);
}

export async function saveCardAsImage(node, { typeId, cosmicName, onTrack } = {}) {
  const dataUrl = await renderCardToDataUrl(node);
  if (isMobileUserAgent()) {
    showLongPressOverlay(dataUrl);
  } else {
    triggerDownload(dataUrl, `youshi-${typeId || ''}-${cosmicName || ''}.png`);
  }
  if (onTrack) onTrack();
}
