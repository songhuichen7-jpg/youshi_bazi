// frontend/src/components/landing/LandingHeroFan.jsx
//
// 首页 section 2 (二十种命盘人格) 的手牌扇。9 张真实命盘卡按扇形铺开,
// 中心最亮、两边渐淡, 暗示背后是 20 种人格的整套牌。
//
// 动画行为:
//   1. Deal-in (一次性): 卡从中心叠成一摞 → 错峰展开到各自位置。用
//      IntersectionObserver gating, 等 section 2 滚进视口才触发, 不然
//      用户滚下来时动画早播完了, 看不到。
//   2. Reduced-motion: 全部跳过, 直接落终态。
//
// 排版用 transform-origin 在卡片下方虚拟点 (50% 200%), 旋转后自然成扇。
// 外层 .landing-fan-card 定位, 内层 .landing-fan-card-inner 旋转 + 透明
// 度 (deal-in 动画作用在这一层, 跟外层定位互不干扰)。
import { useEffect, useRef, useState } from 'react';
import { cardIllustrationSrc } from '../../lib/cardArt.js';
import { useWhiteBgRemovedImage } from '../../lib/useWhiteBgRemovedImage.js';
import { plateNumeral } from '../../lib/cardBinomials.js';

// 9 张取色 / 形态差异最大的卡 — 暖红橙 / 冷蓝 / 绿 / 紫, 视觉上不挤一个调。
// pos 对应 .landing-fan-card[data-pos="..."] 的旋转 / 透明度 / 模糊 阶梯。
const FAN_CARDS = [
  { id: '13', name: '刺猬',   suffix: '锋刃型', theme: '#4A7BA8', illustration: '13-ciwei.png',      pos: -4 },
  { id: '11', name: '多肉',   suffix: '慢养型', theme: '#D4A574', illustration: '11-duorou.png',     pos: -3 },
  { id: '20', name: '蒲公英', suffix: '播种型', theme: '#2A8F8C', illustration: '20-pugongying.png', pos: -2 },
  { id: '05', name: '火烈鸟', suffix: '自燃型', theme: '#F5A623', illustration: '05-huolieniao.png', pos: -1 },
  { id: '01', name: '春笋',   suffix: '参天型', theme: '#2D6A4F', illustration: '01-chunsun.png',    pos:  0 },
  { id: '08', name: '小夜灯', suffix: '守焰型', theme: '#2B6CB0', illustration: '08-xiaoyedeng.png', pos:  1 },
  { id: '15', name: '琉璃',   suffix: '通透型', theme: '#9B7AC4', illustration: '15-liuli.png',      pos:  2 },
  { id: '03', name: '萨摩耶', suffix: '绕指型', theme: '#52B788', illustration: '03-samoye.png',     pos:  3 },
  { id: '16', name: '猫',     suffix: '柔水型', theme: '#6B4E99', illustration: '16-mao.png',       pos:  4 },
];

function FanCardArt({ src, alt }) {
  const processed = useWhiteBgRemovedImage(src);
  if (!processed) return null;
  return (
    <img
      src={processed}
      alt={alt}
      loading="eager"
      decoding="async"
      draggable="false"
    />
  );
}

function FanCard({ card, pos }) {
  const plate = plateNumeral(card.id);
  return (
    <div
      className="landing-fan-card"
      data-pos={pos}
      style={{ '--card-accent': card.theme }}
    >
      <div className="landing-fan-card-inner">
        <div className="landing-fan-face">
          <div className="landing-fan-top">
            <span>PLATE {plate}</span>
            <span>NO. {card.id}</span>
          </div>
          <div className="landing-fan-art">
            <FanCardArt src={cardIllustrationSrc(card.illustration)} alt={card.name} />
          </div>
          <div className="landing-fan-name serif">{card.name}</div>
          <div className="landing-fan-suffix">{card.suffix}</div>
          <div className="landing-fan-foot">
            <span className="landing-fan-foot-brand">有時</span>
            <span>NO. {card.id}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

export function LandingHeroFan() {
  const rootRef = useRef(null);
  // 是否已被 IntersectionObserver 标记为可见 — 控制 deal-in 触发。
  // 一次触发后保持 true 不再回退, 同一 session 内只播一次入场。
  const [dealtIn, setDealtIn] = useState(false);

  useEffect(() => {
    const el = rootRef.current;
    if (!el) return;
    if (typeof IntersectionObserver !== 'function') {
      setDealtIn(true);
      return;
    }
    const obs = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setDealtIn(true);
          obs.disconnect();
        }
      },
      { threshold: 0.18, rootMargin: '0px 0px -10% 0px' },
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  return (
    <div
      ref={rootRef}
      className={`landing-hero-fan${dealtIn ? ' is-dealt' : ''}`}
      aria-hidden="true"
    >
      <div className="landing-fan-stage">
        {FAN_CARDS.map((card) => (
          <FanCard key={card.id} card={card} pos={card.pos} />
        ))}
      </div>
    </div>
  );
}
