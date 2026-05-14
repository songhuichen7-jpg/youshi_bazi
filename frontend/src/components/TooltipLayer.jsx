import { useEffect, useRef } from 'react';
import { GLOSSARY } from '../lib/baziGlossary.js';

/**
 * 命盘 tooltip 浮层 — 单实例，document 级 mouseover/touchstart 委托。
 *
 * 视觉语言：跟 chart 卡片同源（paper-tone 底、hairline border、衬线小标题），
 * 分上下两层：
 *   - term + plain（人话——"这对我是什么"）
 *   - hairline divider
 *   - desc（技术——"它在命理里如何被定义"）
 *
 * 摆位策略：先估高度（实测 tip 自身 rect），再决定 above / below；
 * 横向居中对齐 trigger，clamp 到视口；箭头 X 坐标跟随 trigger 中心，
 * 这样在卡片边缘的字也不会让箭头"指错地方"。
 */
export default function TooltipLayer() {
  const elRef = useRef(null);
  const termRef = useRef(null);
  const plainRef = useRef(null);
  const dividerRef = useRef(null);
  const descRef = useRef(null);
  const hideTimer = useRef(null);

  useEffect(() => {
    const el = elRef.current;
    if (!el) return;

    function findTip(target) {
      let node = target;
      while (node && node !== document.body) {
        if (node.dataset && node.dataset.tip) return { node, key: node.dataset.tip };
        node = node.parentElement;
      }
      return null;
    }

    function show(node, key) {
      const entry = GLOSSARY[key];
      if (!entry) { hide(); return; }

      termRef.current.textContent = entry.term;
      const hasPlain = !!entry.plain;
      plainRef.current.textContent = entry.plain || '';
      plainRef.current.style.display = hasPlain ? '' : 'none';
      dividerRef.current.style.display = hasPlain && entry.desc ? '' : 'none';
      descRef.current.textContent = entry.desc || '';
      descRef.current.style.display = entry.desc ? '' : 'none';

      // 先让 tip 进入 layout 但不可见，量出真实尺寸再决定摆位 — 避免
      // 以前 EST_H/MAX_W 拍脑袋猜导致的盖住自身锚点
      el.style.visibility = 'hidden';
      el.style.left = '0px';
      el.style.top = '0px';
      el.classList.add('is-visible');
      const tipRect = el.getBoundingClientRect();
      el.style.visibility = '';

      const tipW = tipRect.width;
      const tipH = tipRect.height;

      const rect = node.getBoundingClientRect();
      const GAP = 10;
      const vw = window.innerWidth;
      const vh = window.innerHeight;

      // above 优先；空间不够才退到 below
      const placeAbove = rect.top - GAP - tipH >= 8;
      const placement = placeAbove ? 'above' : 'below';
      let top = placeAbove ? rect.top - GAP - tipH : rect.bottom + GAP;
      top = Math.max(8, Math.min(top, vh - tipH - 8));

      // 横向居中对齐 trigger 中心，clamp 到视口边
      const triggerCenterX = rect.left + rect.width / 2;
      let left = triggerCenterX - tipW / 2;
      left = Math.max(8, Math.min(left, vw - tipW - 8));

      // 箭头位置（相对于 tip 左边缘）— 跟随 trigger 中心，clamp 到边内 12px
      let arrowX = triggerCenterX - left;
      arrowX = Math.max(14, Math.min(arrowX, tipW - 14));

      el.style.top = `${top}px`;
      el.style.left = `${left}px`;
      el.dataset.placement = placement;
      el.style.setProperty('--bz-tooltip-arrow-x', `${arrowX}px`);
    }

    function hide() {
      el.classList.remove('is-visible');
    }

    function onMouseOver(e) {
      const found = findTip(e.target);
      clearTimeout(hideTimer.current);
      if (found) {
        show(found.node, found.key);
      } else {
        hideTimer.current = setTimeout(hide, 80);
      }
    }

    function onTouchStart(e) {
      const found = findTip(e.target);
      clearTimeout(hideTimer.current);
      if (found) {
        show(found.node, found.key);
        hideTimer.current = setTimeout(hide, 2400);
      } else {
        hide();
      }
    }

    document.addEventListener('mouseover', onMouseOver);
    document.addEventListener('touchstart', onTouchStart, { passive: true });

    return () => {
      document.removeEventListener('mouseover', onMouseOver);
      document.removeEventListener('touchstart', onTouchStart, { passive: true });
      clearTimeout(hideTimer.current);
    };
  }, []);

  return (
    <div ref={elRef} className="bz-tooltip" aria-hidden="true" data-placement="above">
      <div ref={termRef} className="bz-tooltip-term" />
      <div ref={plainRef} className="bz-tooltip-plain" />
      <div ref={dividerRef} className="bz-tooltip-divider" />
      <div ref={descRef} className="bz-tooltip-desc" />
    </div>
  );
}
