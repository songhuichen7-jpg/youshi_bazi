// 命局能量曲线 — 替换原 大运/流年 叙事面板。
// 默认大运视图（8–9 根 K），点 K 钻入流年（10 根 K）。所有点击 → 给右侧 chat 注入上下文。
//
// 视觉选型：
//   - 单 SVG + HTML overlay（头像 / chip / tooltip）
//   - 五档色带不画填充，只画 hairlines + 左侧标签 — 走文人 almanac 路子，不走股票图路子
//   - 已走过实色，未来虚线 + 半透 — 强调"未来是 projection 不是 prediction"
//   - 头像月级精度，过去 / 当前 / 未来三段语气不同
//
// 评分由 lib/kline/score.js 确定性产出，本组件只渲染。

import { useMemo, useState, useRef, useLayoutEffect } from 'react';
import { useAppStore } from '../../store/useAppStore';
import { scoreAllDayun } from '../../lib/kline/score';
import { computeNowPosition } from '../../lib/kline/position';
import { buildLiunianPrefill, buildDayunPrefill } from '../../lib/kline/chatBridge';
import { GAN_WX } from '../../lib/kline/wuxing';

const VBOX_W = 1000;
const VBOX_H = 520;
const PAD_L = 64;
const PAD_R = 24;
const PAD_T = 64;
const PAD_B = 96;
const INNER_W = VBOX_W - PAD_L - PAD_R;
const INNER_H = VBOX_H - PAD_T - PAD_B;

// y 从高到低（图表上：top=高分 → bottom=低分）。第一项是顶端线，每一项之间的
// 间隔区是一档；最末项 extreme-low 在底端线下面那一档不写额外 marker。
const BAND_DEFS = [
  { name: 'top-edge',     label: null,    y: 3 },
  { name: 'extreme-high', label: '极 佳', y: 1.8 },
  { name: 'high',         label: '顺',    y: 0.6 },
  { name: 'mid',          label: '平',    y: -0.6 },
  { name: 'low',          label: '阻',    y: -1.8 },
  { name: 'extreme-low',  label: '极 险', y: -3 },
];

const WX_COLOR = {
  '木': '#5a7a4b',
  '火': '#a44a3f',
  '土': '#8a6e3c',
  '金': '#7a7a82',
  '水': '#3a5970',
};

function yFromScore(score) {
  const clamped = Math.max(-3, Math.min(3, score));
  const t = (3 - clamped) / 6;
  return PAD_T + t * INNER_H;
}

function xForSlot(idx, total) {
  if (total <= 0) return PAD_L;
  return PAD_L + (idx + 0.5) * (INNER_W / total);
}

function detectCongGe(meta) {
  const geju = String(meta?.geju || '');
  const strength = String(meta?.dayStrength || '');
  return /从/.test(geju) || /极弱|极强|从/.test(strength);
}

function avatarFallback({ meta, user }) {
  // 后端字段是 snake_case avatar_url，user 对象上原样保留 — 别拼成 avatarUrl 取空值。
  const url = String(user?.avatar_url || '').trim();
  if (url) return { type: 'image', url };
  const ganChar = (meta?.rizhuGan || '').charAt(0);
  const wx = GAN_WX[ganChar] || '';
  return {
    type: 'glyph',
    glyph: ganChar || '·',
    color: WX_COLOR[wx] || '#5a5650',
  };
}

export default function KLineChart() {
  const paipan = useAppStore((s) => s.paipan);
  const meta = useAppStore((s) => s.meta);
  const dayun = useAppStore((s) => s.dayun);
  const user = useAppStore((s) => s.user);
  const setChatPrefill = useAppStore((s) => s.setChatPrefill);

  const [drillIdx, setDrillIdx] = useState(null); // null = dayun view, else dayun index
  const [hover, setHover] = useState(null);       // { left, top, transform, content, onClick }
  const canvasRef = useRef(null);
  const [canvasSize, setCanvasSize] = useState({ w: VBOX_W, h: VBOX_H });
  // Hover bridge: 离开 candle 后给 ~180ms 缓冲，期间鼠标进 tooltip 就保持。
  // 让用户能够把鼠标从 candle 移到 tooltip 上读 / 点 CTA，而不被立刻收掉。
  const hoverTimerRef = useRef(null);
  const clearHoverTimer = () => {
    if (hoverTimerRef.current) {
      clearTimeout(hoverTimerRef.current);
      hoverTimerRef.current = null;
    }
  };
  const showHover = (payload) => {
    clearHoverTimer();
    setHover(payload);
  };
  const dismissHover = () => {
    clearHoverTimer();
    hoverTimerRef.current = setTimeout(() => {
      setHover(null);
      hoverTimerRef.current = null;
    }, 180);
  };

  // SVG renders in viewBox space; HTML overlay needs pixel space → measure.
  useLayoutEffect(() => {
    const el = canvasRef.current;
    if (!el) return undefined;
    const measure = () => {
      const rect = el.getBoundingClientRect();
      setCanvasSize({ w: rect.width, h: rect.height });
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const allScored = useMemo(
    () => scoreAllDayun({ paipan, meta, dayun }),
    [paipan, meta, dayun],
  );

  const now = useMemo(
    () => computeNowPosition({ dayun, todayYmd: meta?.today?.ymd }),
    [dayun, meta?.today?.ymd],
  );

  const congGe = detectCongGe(meta);
  const avatar = avatarFallback({ meta, user });

  // 没有命盘 / 没有大运 → 渲染一个安静的占位。
  if (!paipan || !Array.isArray(dayun) || dayun.length === 0 || allScored.length === 0) {
    return (
      <div className="kline-root">
        <div className="kline-empty">
          先排一张命盘，能量曲线就出来了。
        </div>
      </div>
    );
  }

  const inDrill = drillIdx !== null && allScored[drillIdx];
  const drillScored = inDrill ? allScored[drillIdx] : null;

  // viewBox 坐标 → 屏幕像素，给 avatar / 现在线 等 overlay 用。
  const vboxToPx = (x, y) => ({
    left: (x / VBOX_W) * canvasSize.w,
    top: (y / VBOX_H) * canvasSize.h,
  });

  // tooltip 位置：居中为主 + 按需偏移；最后对 box 顶/底做 clamp，强制不出画布。
  //
  //   1. 决定方向（上/下）：上下空间评估，优先向上；都装不下选空间多的一边
  //   2. 算 box 顶 y（已含 8px gap + dot 偏移）
  //   3. clamp 到 [−TOP_BUFFER + 6, canvasSize.h − HEIGHT − 6]
  //      即使两边都不够也不会越出（极端短屏会跟 dot 重叠，但绝不溢出裁切）
  //   4. 用 inline style 直接写绝对位置，不再叠 transform 算 y
  const computeTooltipPos = (vx, vy) => {
    const dotLeft = (vx / VBOX_W) * canvasSize.w;
    const dotTop = (vy / VBOX_H) * canvasSize.h;
    const HALF = 120;
    const HEIGHT = 145;       // 估容量上限（实测 119–138 range）
    const GAP = 8;
    const m = 6;
    const TOP_BUFFER = 40;    // canvas clip-path: inset(-40px ...) 顶部 buffer

    // 横向：居中为主，按需偏移
    const minLeft = HALF + m;
    const maxLeft = canvasSize.w - HALF - m;
    let xShift = 0;
    if (dotLeft < minLeft) xShift = minLeft - dotLeft;
    else if (dotLeft > maxLeft) xShift = -(dotLeft - maxLeft);

    // 垂直方向决策
    const fitsUp = dotTop - 12 - GAP - HEIGHT >= -TOP_BUFFER;
    const fitsDown = dotTop + 12 + GAP + HEIGHT <= canvasSize.h;
    let flipDown;
    if (fitsUp) flipDown = false;
    else if (fitsDown) flipDown = true;
    else flipDown = (canvasSize.h - dotTop) > dotTop;

    // 算 box 顶 y
    let boxTop = flipDown
      ? dotTop + 12 + GAP
      : dotTop - 12 - GAP - HEIGHT;

    // Clamp — 兜底, 极端情况下也不让它越出
    const minBoxTop = -TOP_BUFFER + m;
    const maxBoxTop = canvasSize.h - HEIGHT - m;
    boxTop = Math.max(minBoxTop, Math.min(maxBoxTop, boxTop));

    return {
      left: dotLeft,
      top: boxTop,
      transform: `translateX(calc(-50% + ${xShift}px))`,
    };
  };

  function handleDayunClick(idx) {
    setDrillIdx(idx);
    setHover(null);
  }

  function handleAskDayun(idx) {
    const sc = allScored[idx];
    if (!sc) return;
    const todayYear = Number(meta?.today?.ymd?.slice(0, 4)) || 9999;
    const isCurrent = sc.current;
    const isPast = !isCurrent && sc.endYear < todayYear;
    const payload = buildDayunPrefill({
      paipan, meta, scored: sc,
      isPast, isCurrent,
    });
    // 注入到 chat 即可，**不**切 view —— 用户在 K 线上点"问这一运"
    // 是想保持在曲线视图、右侧追问；切回 chart 反而把他拉走了。
    if (payload) setChatPrefill(payload);
  }

  function handleYearClick(yearIdx) {
    if (!drillScored) return;
    const sc = drillScored.yearScores[yearIdx];
    const yearObj = dayun[drillIdx]?.years?.[yearIdx];
    if (!sc || !yearObj) return;
    const todayYear = Number(meta?.today?.ymd?.slice(0, 4)) || 9999;
    const isPast = yearObj.year < todayYear;
    const isCurrent = yearObj.year === todayYear;
    const payload = buildLiunianPrefill({
      paipan, meta, scored: sc, year: yearObj,
      dayunStep: dayun[drillIdx],
      isPast, isCurrent,
    });
    if (payload) {
      setChatPrefill(payload);
    }
  }

  return (
    <div className="kline-root">
      <header className="kline-header">
        <div className="kline-header-left">
          {inDrill ? (
            <button
              type="button"
              className="kline-back"
              onClick={() => { setDrillIdx(null); setHover(null); }}
              aria-label="返回大运视图"
            >
              <span aria-hidden="true">◀</span> 返回大运
            </button>
          ) : null}
          <div className="kline-title-block">
            <div className="kline-kicker">命 局 能 量 曲 线</div>
            <h2 className="kline-title">
              {inDrill
                ? <>{drillScored.gz} 大运 <span className="kline-title-meta">· {drillScored.startYear}–{drillScored.endYear} · {drillScored.age}岁起</span></>
                : <>纵观一生 <span className="kline-title-meta">· 出生到 {dayun[dayun.length - 1]?.endYear || ''}</span></>}
            </h2>
          </div>
        </div>
        <div className="kline-header-right">
          {inDrill ? (
            <button
              type="button"
              className="kline-ask-link"
              onClick={() => handleAskDayun(drillIdx)}
            >
              问这一运 →
            </button>
          ) : (
            now ? (
              <button
                type="button"
                className="kline-ask-link"
                onClick={() => {
                  if (now.dayunIdx >= 0) setDrillIdx(now.dayunIdx);
                }}
                aria-label="回到当前大运"
              >
                ⌖ 回到当下
              </button>
            ) : null
          )}
        </div>
      </header>

      {congGe ? (
        <div className="kline-banner" role="note">
          <span className="kline-banner-mark" aria-hidden="true">⚠</span>
          <span>
            你的命局可能为<b>{(meta?.geju || '从格')}</b>，曲线按正格的扶抑算法生成，仅供参考。
            建议在右侧追问"我是否从格"以校准。
          </span>
        </div>
      ) : null}

      <div className="kline-canvas" ref={canvasRef}>
        <svg
          className="kline-svg"
          viewBox={`0 0 ${VBOX_W} ${VBOX_H}`}
          preserveAspectRatio="none"
          role="img"
          aria-label={inDrill ? '流年能量曲线' : '大运能量曲线'}
        >
          <defs>
            <pattern id="kline-paper" patternUnits="userSpaceOnUse" width="120" height="120">
              {/* 朱砂米格 — 极极轻的网格，模拟宣纸；过强会喧宾夺主 */}
              <path d="M0 0 L120 0 L120 120 L0 120 Z" fill="none" />
            </pattern>
          </defs>

          {/* 五档底色 — 极轻的暖金 / 朱砂染色，让 候差感 (高分 / 低分) 有
            * "海拔"。色阶很轻 (4-8% alpha)，避免做成 stock chart 配色。
            * 平 区留白；顺 / 极佳 走暖金；阻 / 极险 走淡朱砂。 */}
          {(() => {
            const tints = [
              { from: 3, to: 1.8, color: 'rgba(239, 191, 89, 0.10)' },     // 极佳 — 较深暖金
              { from: 1.8, to: 0.6, color: 'rgba(239, 191, 89, 0.05)' },   // 顺 — 浅暖金
              // 平 (0.6 → -0.6) 不染
              { from: -0.6, to: -1.8, color: 'rgba(180, 67, 67, 0.04)' },  // 阻 — 浅朱砂
              { from: -1.8, to: -3, color: 'rgba(180, 67, 67, 0.08)' },    // 极险 — 较深朱砂
            ];
            return tints.map((t, i) => {
              const yTop = yFromScore(t.from);
              const yBot = yFromScore(t.to);
              return (
                <rect
                  key={i}
                  x={PAD_L} y={yTop}
                  width={VBOX_W - PAD_L - PAD_R}
                  height={yBot - yTop}
                  fill={t.color}
                  className="kline-band-tint"
                />
              );
            });
          })()}

          {/* 五档分隔线 + 居中标签。每条线把"上下两档"分开，标签贴在线
            * 与下一条线之间的中点上 — 这样标签描述的是线**之下**那一档。 */}
          {BAND_DEFS.map((band, i) => {
            const y = yFromScore(band.y);
            const next = BAND_DEFS[i + 1];
            const isMidLine = band.name === 'mid' || band.name === 'high';
            return (
              <g key={band.name} className={`kline-band kline-band-${band.name}`}>
                <line
                  x1={PAD_L} x2={VBOX_W - PAD_R}
                  y1={y} y2={y}
                  className={isMidLine ? 'kline-band-line kline-band-line-mid' : 'kline-band-line'}
                />
                {next && next.label ? (
                  <text
                    x={PAD_L - 14}
                    y={(y + yFromScore(next.y)) / 2 + 4}
                    className="kline-band-label"
                    textAnchor="end"
                  >{next.label}</text>
                ) : null}
              </g>
            );
          })}

          {/* "现在"竖线 — 头像挂在它顶 */}
          {now && !now.preStart && !now.postEnd ? (() => {
            const x = inDrill && drillIdx === now.dayunIdx
              ? xForSlot(now.yearIdx + (now.yearProgress - 0.5), 10)
              : (inDrill ? null : PAD_L + now.absoluteProgress * INNER_W);
            if (x === null) return null;
            return (
              <line
                x1={x} x2={x}
                y1={PAD_T - 12} y2={VBOX_H - PAD_B + 8}
                className="kline-now-line"
              />
            );
          })() : null}

          {/* 主体：candle 序列 + 连线
            * onShowHover / onDismissHover：经过 hover bridge，鼠标可以从 candle
            * 移到 tooltip 上而不被立刻收掉；computeTooltipPos 算出居中为主 +
            * 只按需偏移的 transform。 */}
          {inDrill ? (
            <YearSeries
              scored={drillScored.yearScores}
              years={dayun[drillIdx].years}
              onClick={handleYearClick}
              onShowHover={showHover}
              onDismissHover={dismissHover}
              computeTooltipPos={computeTooltipPos}
            />
          ) : (
            <DayunSeries
              scored={allScored}
              dayun={dayun}
              onClick={handleDayunClick}
              onAskRun={handleAskDayun}
              onShowHover={showHover}
              onDismissHover={dismissHover}
              computeTooltipPos={computeTooltipPos}
            />
          )}
        </svg>

        {/* 头像 overlay（HTML, 跟随 viewBox 缩放） */}
        {now && !now.preStart && !now.postEnd ? (() => {
          const total = inDrill ? 10 : allScored.length;
          let x;
          let yScore;
          if (inDrill) {
            if (drillIdx !== now.dayunIdx) return null; // 钻入了别的大运 — 不画
            x = xForSlot(now.yearIdx + (now.yearProgress - 0.5), total);
            const sc = drillScored.yearScores[now.yearIdx];
            yScore = sc ? sc.score : 0;
          } else {
            x = PAD_L + now.absoluteProgress * INNER_W;
            const sc = allScored[now.dayunIdx];
            yScore = sc ? sc.score : 0;
          }
          const y = yFromScore(yScore);
          const px = vboxToPx(x, y);
          return (
            <div
              className="kline-avatar-wrap"
              style={{ left: px.left, top: px.top }}
            >
              <div className="kline-avatar-chip">
                {meta?.today?.ymd?.slice(0, 4) || '今年'} ·
                {' '}{(now.dayunIdx >= 0 ? allScored[now.dayunIdx]?.gz : '')} 运
                {inDrill ? '' : ` · 走 ${Math.round((now.stepProgress || 0) * 10)}/10 年`}
              </div>
              <div
                className={'kline-avatar' + (avatar.type === 'glyph' ? ' is-glyph' : '')}
                style={avatar.type === 'glyph' ? { color: avatar.color } : null}
                aria-label="你现在的位置"
              >
                {avatar.type === 'image' ? (
                  <img src={avatar.url} alt="" />
                ) : (
                  <span className="serif">{avatar.glyph}</span>
                )}
              </div>
            </div>
          );
        })() : null}

        {/* tooltip overlay
          * pointer-events: auto — 鼠标可以从 candle 移上来读 / 点 CTA 而不被收。
          * onMouseEnter 取消刚才的 dismiss 计时；onMouseLeave 才真的 dismiss。
          * onClick = 同 candle click（让"点 → 进入流年视图"这块文字真的可点）。 */}
        {hover ? (
          <div
            className={'kline-tooltip' + (hover.onClick ? ' kline-tooltip-clickable' : '')}
            style={{ left: hover.left, top: hover.top, transform: hover.transform }}
            role={hover.onClick ? 'button' : 'status'}
            onMouseEnter={clearHoverTimer}
            onMouseLeave={dismissHover}
            onClick={hover.onClick}
          >
            {hover.content}
          </div>
        ) : null}
      </div>

      {/* 底部图例 */}
      <footer className="kline-legend">
        <span className="kline-legend-item">
          <span className="kline-legend-swatch is-past" /> 已走过
        </span>
        <span className="kline-legend-item">
          <span className="kline-legend-swatch is-future" /> 未来
        </span>
        <span className="kline-legend-item">
          <span className="kline-legend-swatch is-current" /> 当下
        </span>
        <span className="kline-legend-spacer" />
        <span className="kline-legend-hint">
          {inDrill ? '点流年 → 在右侧追问这一年' : '点大运 → 进入流年；点"问这一运" → 直接追问'}
        </span>
      </footer>
    </div>
  );
}

// ── 大运序列 ─────────────────────────────────────────────────────
function DayunSeries({ scored, dayun, onClick, onAskRun, onShowHover, onDismissHover, computeTooltipPos }) {
  const todayYear = (() => {
    // 从 dayun 里找 current 步推算当前年；不是必需的精确值
    const cur = dayun.find((d) => d.current);
    if (cur) return cur.startYear;
    return new Date().getFullYear();
  })();

  const total = scored.length;
  const points = scored.map((sc, i) => ({
    x: xForSlot(i, total),
    y: yFromScore(sc.score),
    sc,
    step: dayun[i],
    isPast: dayun[i].endYear <= todayYear,
    isFuture: dayun[i].startYear > todayYear,
    isCurrent: dayun[i].current,
  }));

  const past = points.filter((p) => !p.isFuture);
  const future = points.filter((p) => p.isFuture);
  const linkPoint = past[past.length - 1] || null;
  const futureWithLink = linkPoint ? [linkPoint, ...future] : future;

  return (
    <g className="kline-series kline-series-dayun">
      {/* 已走过的实线 */}
      {past.length >= 2 ? (
        <polyline
          className="kline-line kline-line-past"
          points={past.map((p) => `${p.x},${p.y}`).join(' ')}
        />
      ) : null}
      {/* 未来的虚线 */}
      {futureWithLink.length >= 2 ? (
        <polyline
          className="kline-line kline-line-future"
          points={futureWithLink.map((p) => `${p.x},${p.y}`).join(' ')}
        />
      ) : null}

      {/* 每个 candle */}
      {points.map((p, i) => {
        const volH = (p.sc.range / 6) * INNER_H * 0.5; // 年内反差 → 影线长度
        const yTop = Math.max(PAD_T, p.y - volH);
        const yBot = Math.min(VBOX_H - PAD_B, p.y + volH);
        const labelY = VBOX_H - PAD_B + 18;
        const ageY = VBOX_H - PAD_B + 38;
        const className = 'kline-candle'
          + (p.isPast ? ' is-past' : '')
          + (p.isFuture ? ' is-future' : '')
          + (p.isCurrent ? ' is-current' : '');

        return (
          <g
            key={i}
            className={className}
            onClick={() => onClick(i)}
            onMouseEnter={() => {
              onShowHover({
                ...computeTooltipPos(p.x, p.y),
                onClick: () => onClick(i),
                content: (
                  <>
                    <div className="kline-tooltip-title serif">
                      {p.step.gz}
                      <span className="kline-tooltip-meta">{p.step.ss}</span>
                      {p.sc.isPeak ? <span className="kline-tooltip-peak"> ▲ 此运最旺</span> : null}
                    </div>
                    <div className="kline-tooltip-row">{p.step.startYear}–{p.step.endYear} · {p.step.age}岁起</div>
                    <div className="kline-tooltip-row">能量 <b>{p.sc.score.toFixed(2)}</b> · 反差 {p.sc.range.toFixed(2)}</div>
                    {p.sc.shensha.length ? (
                      <div className="kline-tooltip-row">主导神煞：{p.sc.shensha.join('、')}</div>
                    ) : null}
                    {/* 两条 CTA: 主区点击 = 进入流年; 单独按钮 = 直接问这一运
                      * (stopPropagation, 不触发主区 drill) */}
                    <div className="kline-tooltip-cta-row">
                      <span className="kline-tooltip-cta">点 → 进入流年</span>
                      <button
                        type="button"
                        className="kline-tooltip-cta-btn"
                        onClick={(e) => {
                          e.stopPropagation();
                          onAskRun?.(i);
                        }}
                      >→ 问这一运</button>
                    </div>
                  </>
                ),
              });
            }}
            onMouseLeave={onDismissHover}
            role="button"
            aria-label={`大运 ${p.step.gz} ${p.step.startYear}到${p.step.endYear}`}
          >
            {/* 影线 */}
            <line className="kline-whisker" x1={p.x} x2={p.x} y1={yTop} y2={yBot} />
            {/* 主点 */}
            <circle className="kline-dot" cx={p.x} cy={p.y} r={p.isCurrent ? 6 : 4} />
            {/* 干支标签 */}
            <text className="kline-x-label serif" x={p.x} y={labelY} textAnchor="middle">
              {p.step.gz}
            </text>
            {/* 年龄区间 */}
            <text className="kline-x-sub" x={p.x} y={ageY} textAnchor="middle">
              {p.step.age}–{Math.round(Number(p.step.age) + 10)}岁
            </text>
            {/* marker (神煞) — 朱砂 */}
            {p.sc.marker ? (
              <text
                className="kline-marker"
                x={p.x} y={yTop - 8}
                textAnchor="middle"
                aria-label={p.sc.marker.name}
              >{p.sc.marker.glyph}</text>
            ) : null}
            {/* 主峰标记 — 暖金 ▲，放在 神煞 marker 上方避免叠 */}
            {p.sc.isPeak ? (
              <text
                className="kline-peak-mark"
                x={p.x}
                y={p.sc.marker ? yTop - 22 : yTop - 10}
                textAnchor="middle"
                aria-label="此运最旺"
              >▲</text>
            ) : null}
            {/* 大点击区 — 透明矩形，扩大命中面积 */}
            <rect
              className="kline-hit"
              x={p.x - (INNER_W / scored.length) / 2 + 4}
              y={PAD_T}
              width={(INNER_W / scored.length) - 8}
              height={INNER_H}
              fill="transparent"
            />
          </g>
        );
      })}
    </g>
  );
}

// ── 流年序列（drill 进单步大运） ─────────────────────────────────
function YearSeries({ scored, years, onClick, onShowHover, onDismissHover, computeTooltipPos }) {
  const todayYear = (() => {
    const cur = years.find((y) => y.current);
    if (cur) return cur.year;
    return new Date().getFullYear();
  })();

  const total = scored.length;
  const points = scored.map((sc, i) => ({
    x: xForSlot(i, total),
    y: yFromScore(sc.score),
    sc,
    year: years[i],
    isPast: years[i].year < todayYear,
    isFuture: years[i].year > todayYear,
    isCurrent: years[i].year === todayYear,
  }));

  const past = points.filter((p) => !p.isFuture);
  const future = points.filter((p) => p.isFuture);
  const linkPoint = past[past.length - 1] || null;
  const futureWithLink = linkPoint ? [linkPoint, ...future] : future;

  return (
    <g className="kline-series kline-series-year">
      {past.length >= 2 ? (
        <polyline
          className="kline-line kline-line-past"
          points={past.map((p) => `${p.x},${p.y}`).join(' ')}
        />
      ) : null}
      {futureWithLink.length >= 2 ? (
        <polyline
          className="kline-line kline-line-future"
          points={futureWithLink.map((p) => `${p.x},${p.y}`).join(' ')}
        />
      ) : null}

      {points.map((p, i) => {
        const volH = p.sc.volatility * INNER_H * 0.18;
        const yTop = Math.max(PAD_T, p.y - volH);
        const yBot = Math.min(VBOX_H - PAD_B, p.y + volH);
        const labelY = VBOX_H - PAD_B + 18;
        const yearY = VBOX_H - PAD_B + 38;
        const className = 'kline-candle'
          + (p.isPast ? ' is-past' : '')
          + (p.isFuture ? ' is-future' : '')
          + (p.isCurrent ? ' is-current' : '');

        return (
          <g
            key={i}
            className={className}
            onClick={() => onClick(i)}
            onMouseEnter={() => {
              onShowHover({
                ...computeTooltipPos(p.x, p.y),
                onClick: () => onClick(i),
                content: (
                  <>
                    <div className="kline-tooltip-title serif">{p.year.year} <span className="kline-tooltip-meta serif">{p.year.gz}</span></div>
                    <div className="kline-tooltip-row">{p.year.ss}</div>
                    <div className="kline-tooltip-row">能量 <b>{p.sc.score.toFixed(2)}</b>{p.sc.volatility >= 0.5 ? ' · 大波动' : p.sc.volatility >= 0.2 ? ' · 中波动' : ''}</div>
                    {p.sc.relations.length ? (
                      <div className="kline-tooltip-row">{p.sc.relations.slice(0, 2).map((r) => r.text).join('；')}</div>
                    ) : null}
                    {p.sc.shensha.length ? (
                      <div className="kline-tooltip-row">神煞：{p.sc.shensha.join('、')}</div>
                    ) : null}
                    <div className="kline-tooltip-cta">点 → 在右侧追问这一年</div>
                  </>
                ),
              });
            }}
            onMouseLeave={onDismissHover}
            role="button"
            aria-label={`流年 ${p.year.year} ${p.year.gz}`}
          >
            <line className="kline-whisker" x1={p.x} x2={p.x} y1={yTop} y2={yBot} />
            <circle className="kline-dot" cx={p.x} cy={p.y} r={p.isCurrent ? 6 : 4} />
            <text className="kline-x-label serif" x={p.x} y={labelY} textAnchor="middle">
              {p.year.gz}
            </text>
            <text className="kline-x-sub" x={p.x} y={yearY} textAnchor="middle">
              {p.year.year}
            </text>
            {p.sc.marker ? (
              <text
                className="kline-marker"
                x={p.x} y={yTop - 8}
                textAnchor="middle"
                aria-label={p.sc.marker.name}
              >{p.sc.marker.glyph}</text>
            ) : null}
            <rect
              className="kline-hit"
              x={p.x - (INNER_W / scored.length) / 2 + 4}
              y={PAD_T}
              width={(INNER_W / scored.length) - 8}
              height={INNER_H}
              fill="transparent"
            />
          </g>
        );
      })}
    </g>
  );
}
