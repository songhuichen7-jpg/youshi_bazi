// frontend/src/components/landing/LandingHome.jsx
//
// 访客介绍页 — 编辑设计 / 留白主导 / 大字宋体 / 卡片作为"展品"。
//
// 一页式克制叙事：
//   1. Hero          命 · 盘 · 读 + 一个理性的命理工具 + 命盘档案双框 mockup
//   2. 二十种人格    给你的命盘一个名字 + 4 张卡片图鉴
//   3. 关系          你和 TA 是哪种搭子 + 合盘卡 + chip
//   4. 好玩问法      电影 / 音乐 / 花卡片
//   5. 起卦          一件具体的事，单独起一卦
//   6. 凭据          古籍真本 + 4 个数字
//   7. 数据安全      加密与隐私承诺
//   8. 时序收尾      万事有时 + CTA
//
// 设计语言: 超大宋体衬线 (Songti SC) + 黑/暖灰为主 + 暖米底 + 大留白.
// 卡片本身保留产品标志性的暖色, 但页面 chrome 几乎是黑白灰.
/* eslint-disable react-hooks/set-state-in-effect */
import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAppStore } from '../../store/useAppStore.js';
import { cardIllustrationSrc } from '../../lib/cardArt.js';
import { useWhiteBgRemovedImage } from '../../lib/useWhiteBgRemovedImage.js';
import { MediaCard } from '../MediaCard.jsx';
import GuaCard from '../GuaCard.jsx';
import { BrandLogo } from '../brand/BrandLogo.jsx';
import { HepanCardPreview } from './HepanCardPreview.jsx';
import { LandingHeroFan } from './LandingHeroFan.jsx';
import { readGuestToken } from '../../lib/guestToken.js';

// Hero mockup 轮播：左边一柱日干 + 日支 + 格局，右边配一句"有意思"的问题。
// 每条 scene 都展示产品的一种用法，让访客一眼看到能问什么。
const HERO_SCENES = [
  { gan: '丁', zhi: '酉', geju: '食神格', question: '用一首歌形容我这盘。' },
  { gan: '庚', zhi: '午', geju: '阳刃格', question: '用一部电影形容这种性格。' },
  { gan: '甲', zhi: '子', geju: '正印格', question: '我适合什么样的爱情节奏？' },
  { gan: '戊', zhi: '寅', geju: '偏官格', question: '今年的桃花会怎么开？' },
  { gan: '乙', zhi: '巳', geju: '伤官格', question: '我和 TA 是哪种搭子？' },
];
const HERO_SCENE_INTERVAL_MS = 4200;
const HERO_FADE_MS = 460;

// 二十种人格 —— 完整目录与 server/app/data/cards/types.json 对齐，
// 用于 hero 下面那条"无限左右轮播"。每条只用：传播名 + 短 tag +
// 主题色 + 真实插画文件名（来自 /static/cards/illustrations/）。
const PERSONA_POOL = [
  { id: '01', name: '春笋',   suffix: '参天型', theme: '#2D6A4F', illustration: '01-chunsun.png' },
  { id: '02', name: '橡子',   suffix: '扎根型', theme: '#1B4332', illustration: '02-xiangzi.png' },
  { id: '03', name: '萨摩耶', suffix: '绕指型', theme: '#52B788', illustration: '03-samoye.png' },
  { id: '04', name: '含羞草', suffix: '攀藤型', theme: '#2D7D53', illustration: '04-hanxiucao.png' },
  { id: '05', name: '火烈鸟', suffix: '自燃型', theme: '#F5A623', illustration: '05-huolieniao.png' },
  { id: '06', name: '热可可', suffix: '蓄光型', theme: '#C47D0E', illustration: '06-rekeke.png' },
  { id: '07', name: '萤火虫', suffix: '熔铸型', theme: '#4A9BE8', illustration: '07-yinghuochong.png' },
  { id: '08', name: '小夜灯', suffix: '守焰型', theme: '#2B6CB0', illustration: '08-xiaoyedeng.png' },
  { id: '09', name: '大象',   suffix: '砥柱型', theme: '#A0785A', illustration: '09-daxiang.png' },
  { id: '10', name: '松鼠',   suffix: '蓄土型', theme: '#7A5438', illustration: '10-songshu.png' },
  { id: '11', name: '多肉',   suffix: '慢养型', theme: '#D4A574', illustration: '11-duorou.png' },
  { id: '12', name: '树懒',   suffix: '稳田型', theme: '#A67C4E', illustration: '12-shulan.png' },
  { id: '13', name: '刺猬',   suffix: '锋刃型', theme: '#4A7BA8', illustration: '13-ciwei.png' },
  { id: '14', name: '河豚',   suffix: '藏锋型', theme: '#2C5282', illustration: '14-hetun.png' },
  { id: '15', name: '琉璃',   suffix: '通透型', theme: '#9B7AC4', illustration: '15-liuli.png' },
  { id: '16', name: '猫',     suffix: '柔水型', theme: '#6B4E99', illustration: '16-mao.png' },
  { id: '17', name: '水獭',   suffix: '游溪型', theme: '#1A759F', illustration: '17-shuita.png' },
  { id: '18', name: '章鱼',   suffix: '深潜型', theme: '#0D4F72', illustration: '18-zhangyu.png' },
  { id: '19', name: '水母',   suffix: '随流型', theme: '#4AC4C0', illustration: '19-shuimu.png' },
  { id: '20', name: '蒲公英', suffix: '播种型', theme: '#2A8F8C', illustration: '20-pugongying.png' },
];

const RELATION_CATEGORIES = [
  { mark: '01', label: '天作' },
  { mark: '02', label: '滋养' },
  { mark: '03', label: '火花' },
  { mark: '04', label: '镜像' },
  { mark: '05', label: '同频' },
];

const TRUST_METRICS = [
  { value: '20', label: '种基础人格' },
  { value: '200', label: '组人格细标签' },
  { value: '5', label: '部古籍真本' },
  { value: '210', label: '种关系组合' },
];

const PREVIEW_GUA = {
  symbol: '䷷',
  name: '旅卦',
  upper: '离',
  lower: '艮',
  guaci: '小亨，旅贞吉。',
  daxiang: '山上有火，旅；君子以明慎用刑，而不留狱。',
  question: '这件事现在要不要推进？',
  body: '起卦适合问一件具体的事。它看的是当下这一问的势、阻力和可动之处；长期性格、关系底色和行运，仍然回到命盘里看。',
};

const PLAY_CARDS = [
  {
    kind: 'movie',
    mark: 'MOVIE',
    prompt: '用一部电影形容我这盘。',
    title: '花样年华',
    subtitle: '王家卫',
    cta: '豆瓣搜索',
    note: '克制、绕远，但情绪一直在场。',
  },
  {
    kind: 'song',
    mark: 'MUSIC',
    prompt: '用一首歌形容我的关系模式。',
    title: '慢慢喜欢你',
    subtitle: '莫文蔚',
    cta: '网易云搜索',
    note: '不是一眼上头，是越相处越有温度。',
  },
  {
    kind: 'flower',
    mark: 'FLOWER',
    prompt: '用一种花形容我这盘。',
    title: '雨后玉兰',
    subtitle: '清白、慢开，有一点冷香',
    note: '不是热闹的盛放，是安静地把自己展开。',
  },
];

function Eyebrow({ children }) {
  return <p className="landing-eyebrow">{children}</p>;
}

function PlayCardPreview({ card }) {
  return (
    <article className={`landing-play-card landing-play-card-${card.kind}`}>
      <div className="landing-play-card-head">
        <span>{card.mark}</span>
        <span>有时</span>
      </div>
      <p className="landing-play-prompt">「{card.prompt}」</p>
      <div className="landing-play-object">
        <MediaCard kind={card.kind} title={card.title} subtitle={card.subtitle} />
      </div>
      <p className="landing-play-note">{card.note}</p>
    </article>
  );
}

function PersonaIllustration({ src, alt }) {
  const processedSrc = useWhiteBgRemovedImage(src);
  if (!processedSrc) return null;
  return (
    <img
      src={processedSrc}
      alt={alt}
      loading="eager"
      decoding="async"
      draggable="false"
    />
  );
}

// 二十种人格 — 无限左右轮播。轨道把 PERSONA_POOL 拼两遍 → translate
// 到 -50% 后回到原点，看不到接缝。每个 item 用 nth-child 拿到一个
// "lane"（0..4），不同 lane 走不同的 Y-bob / 旋转 / 入场延迟，整列
// 不再是一条直线，而是"五条略微错位的呼吸线"。中心 spotlight 由
// CSS 浮层负责，让经过中央的人格感官上更亮、更近。
function PersonaMarquee() {
  // 拼两遍以实现无缝循环；React 不参与动画，全交给 CSS。
  const looped = [...PERSONA_POOL, ...PERSONA_POOL];
  return (
    <div className="landing-persona-marquee" aria-hidden="true">
      {/* 中央 spotlight: 顶层一个柔光带，给经过中心的项视觉权重 */}
      <div className="landing-persona-spotlight" />
      <div className="landing-persona-track">
        {looped.map((p, i) => (
          <div
            key={`${p.id}-${i}`}
            className="landing-persona-item"
            style={{
              '--persona-accent': p.theme,
              // lane 0..4 — 每张图属于一条"高度线"，错峰 Y-bob
              '--lane': (i % 5),
            }}
          >
            <div className="landing-persona-halo">
              <div className="landing-persona-illust">
                <PersonaIllustration src={cardIllustrationSrc(p.illustration)} alt={p.name} />
              </div>
            </div>
            <div className="landing-persona-name serif">{p.name}</div>
            <div className="landing-persona-suffix">{p.suffix}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function LandingHome() {
  const navigate = useNavigate();

  // Hero 轮播：next idx 由定时器推进；displayIdx 通过 out → swap → in
  // 三步切换，避免 key remount 那种"硬切"。phase 控制 CSS 类。
  const [nextIdx, setNextIdx] = useState(0);
  const [displayIdx, setDisplayIdx] = useState(0);
  const [phase, setPhase] = useState('in');

  useEffect(() => {
    const id = setInterval(
      () => setNextIdx(i => (i + 1) % HERO_SCENES.length),
      HERO_SCENE_INTERVAL_MS,
    );
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (nextIdx === displayIdx) return;
    setPhase('out');
    const t = setTimeout(() => {
      setDisplayIdx(nextIdx);
      setPhase('in');
    }, HERO_FADE_MS);
    return () => clearTimeout(t);
  }, [nextIdx, displayIdx]);

  const scene = HERO_SCENES[displayIdx];

  // CTA 只负责进应用；登录态恢复 / 命盘同步统一交给 AppShell。
  // 这样接口慢时也会先切到过渡态，不会卡在落地页按钮上。
  function handleStart() {
    navigate('/app');
  }

  function handleDirectStart() {
    handleStart();
  }

  // 滚到第一个介绍 section (二十种人格)。
  //
  // 实现演进:
  //   v1 ease-in-out cubic     → "生硬",头部 4t³ 几乎不动
  //   v2 easeOutQuint          → "卡顿",头部 burst 后蜗行
  //   v3 cubic-bezier rAF       → "掉帧",主线程跟 hero/marquee 抢资源
  //   v4 native scrollIntoView  → 看着流畅但落点不稳:#intro 内有 lazy
  //                                <img> 在 scroll 期间逐张 decode 触发
  //                                layout shift,浏览器跟着 target 调,
  //                                结果停在"伪稳定点" (实测 scrollY=225,
  //                                目标 866,差 641px)
  //   v5 (本次) — window.scrollTo({top, behavior:'smooth'}) 用固定数值。
  //   target 是 click 瞬间快照下的绝对位置,中途 layout shift 不影响,
  //   compositor 还是合成线程跑 (跟 scrollIntoView 同套优化路径)。
  //
  // 落点上方留 24px 透气,跟 CSS 的 scroll-margin-top 行为一致。
  // reduced-motion 偏好下退回 behavior:'auto' (instant)。
  function scrollToIntro() {
    const target = document.getElementById('intro');
    if (!target) return;
    const top = Math.max(0, target.getBoundingClientRect().top + window.scrollY - 24);
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    window.scrollTo({ top, behavior: reduce ? 'auto' : 'smooth' });
  }

  // 返客 vs 新人分流:
  //   - 已经有 guest_token 或登录账户 → 直接 "继续我的命盘 →"
  //   - 全新访客 → primary CTA 改成"探索"调性 (看看「有时」怎么读你)
  //     先把人引到介绍区,旁边给一条 "或 直接开始排盘 →" 给已经
  //     知道想干嘛的人留出口。
  const user = useAppStore(s => s.user);
  const isReturning = !!user || !!readGuestToken();

  return (
    <main className="landing-home">

      {/* ── 1. Hero ────────────────────────────────────────────────── */}
      <section className="landing-hero">
        <div className="landing-brand-masthead">
          <BrandLogo showRoman className="landing-hero-logo" />
        </div>

        <Eyebrow>命 · 盘 · 读</Eyebrow>

        <h1 className="landing-display-title">
          一个<span className="landing-title-muted">理性</span>的命理工具
        </h1>

        <p className="landing-display-sub">
          万事都有它出现的时刻，<br />
          人也在自己的时序里慢慢展开。
        </p>

        {isReturning ? (
          // 返客:已经体验过 — 直接给"继续"入口,不绕介绍。
          <div className="landing-cta-stack">
            <div className="landing-cta-row">
              <button
                type="button"
                className="landing-cta-primary"
                onClick={handleStart}
              >
                继续我的命盘 →
              </button>
            </div>
          </div>
        ) : (
          // 新访客:primary CTA 是探索 (滚到介绍区),secondary
          // 是直接开始 — 让"想先看看"和"已知道想干嘛"两种人都
          // 有自己的入口,不互相打扰。
          <div className="landing-cta-stack">
            <div className="landing-cta-row">
              <button
                type="button"
                className="landing-cta-primary"
                onClick={handleDirectStart}
              >
                直接开始排盘 →
              </button>
            </div>
            <button
              type="button"
              className="landing-cta-secondary"
              onClick={scrollToIntro}
            >
              <span>或 先看看「有时」怎么读你</span>
              <span className="landing-cta-secondary-arrow" aria-hidden="true">→</span>
            </button>
          </div>
        )}

        {/* 命盘档案 + 对话 mockup — 双面板按 HERO_SCENES 同步轮播 */}
        <div className="landing-hero-mockup">
          <div className="landing-mockup-panel">
            <div className="landing-mockup-kicker">命 盘 档 案</div>
            <div className="landing-mockup-pillars" data-phase={phase}>
              <div className="landing-mockup-cell" style={{ '--cell-delay': '0ms' }}>{scene.gan}</div>
              <div className="landing-mockup-cell" style={{ '--cell-delay': '70ms' }}>{scene.zhi}</div>
              <div className="landing-mockup-cell landing-mockup-wide" style={{ '--cell-delay': '140ms' }}>{scene.geju}</div>
            </div>
            <div className="landing-mockup-lines" aria-hidden="true">
              <span /><span /><span style={{ width: '64%' }} />
            </div>
          </div>
          <div className="landing-mockup-panel">
            <div className="landing-mockup-kicker">对 话</div>
            <p className="landing-mockup-bubble" data-phase={phase}>
              {scene.question}
            </p>
          </div>
        </div>
      </section>

      {/* ── 2. 二十种人格 ──────────────────────────────────────────── */}
      <section id="intro" className="landing-section">
        <Eyebrow>二十种命盘人格</Eyebrow>
        <h2 className="landing-section-title">
          给你的命盘<br />
          一个名字
        </h2>
        <p className="landing-section-sub">
          参天木 → 春笋。烛灯火 → 小夜灯。<br />
          二十种意象，让命理结构变成可以被记住的人。
        </p>

        <div id="gallery">
          <LandingHeroFan />
        </div>
      </section>

      {/* ── 3. 关系 ─────────────────────────────────────────────────── */}
      <section className="landing-section">
        <Eyebrow>你和 TA 的关系</Eyebrow>
        <h2 className="landing-section-title">
          不是合不合<br />
          是哪种搭子
        </h2>

        <div className="landing-hepan-grid">
          <div className="landing-hepan-text">
            <p>
              天作 · 滋养 · 火花 · 镜像 · 同频 ——<br />
              五大类、二一〇种关系变体。<br />
              每一对，都有自己的相处方式。
            </p>
            <div className="landing-relation-chips">
              {RELATION_CATEGORIES.map(c => (
                <span key={c.label} className="landing-relation-chip">
                  <em>{c.mark}</em><span>{c.label}</span>
                </span>
              ))}
            </div>
          </div>
          <HepanCardPreview />
        </div>
      </section>

      {/* ── 4. 好玩问法 ─────────────────────────────────────────────── */}
      <section className="landing-section landing-play-section">
        <Eyebrow>对话里的小展品</Eyebrow>
        <h2 className="landing-section-title">
          把命盘问成<br />
          电影、音乐和花
        </h2>
        <p className="landing-section-sub">
          它不只给结论，也会把你的性格、关系和当下问题，<br />
          变成一张可以收藏的回答卡片。
        </p>

        <div className="landing-play-grid">
          {PLAY_CARDS.map(card => (
            <PlayCardPreview key={card.kind} card={card} />
          ))}
        </div>
      </section>

      {/* ── 5. 起卦 ─────────────────────────────────────────────────── */}
      <section className="landing-section landing-gua-section">
        <Eyebrow>起卦</Eyebrow>
        <h2 className="landing-section-title">
          一件具体的事，<br />
          单独起一卦
        </h2>
        <p className="landing-section-sub">
          命盘看长期底色，起卦看当下这一问。<br />
          它适合拿来判断一个具体选择，而不是替你的人生下总论。
        </p>

        <div className="landing-gua-grid">
          <div className="landing-gua-copy">
            <div className="landing-gua-block">
              <h3>什么问题适合起卦</h3>
              <p>
                要不要、该不该、能不能、是否推进。问题越具体，
                卦象给出的提醒越清楚。
              </p>
            </div>
            <div className="landing-gua-block">
              <h3>它和命盘的关系</h3>
              <p>
                命盘像底图，起卦像此刻的天气。先知道自己，再看眼前这一局。
              </p>
            </div>
          </div>

          <div className="landing-gua-card">
            <GuaCard data={PREVIEW_GUA} />
          </div>
        </div>
      </section>

      {/* ── 6. 凭据 ─────────────────────────────────────────────────── */}
      <section className="landing-section">
        <Eyebrow>凭 据</Eyebrow>
        <h2 className="landing-section-title">
          每一句古人说，<br />
          都查得到出处
        </h2>
        <p className="landing-section-sub">
          穷通宝鉴 · 子平真诠 · 滴天髓 ·<br />
          三命通会 · 渊海子平
        </p>

        <div className="landing-trust-grid">
          {TRUST_METRICS.map(m => (
            <div key={m.value} className="landing-metric">
              <div className="landing-metric-value">{m.value}</div>
              <div className="landing-metric-label">{m.label}</div>
            </div>
          ))}
        </div>

        <p className="landing-trust-note">
          来自哪本书、哪一章，都说清楚。
        </p>
      </section>

      {/* ── 7. 数据安全 ──────────────────────────────────────────────── */}
      <section className="landing-section landing-privacy-section">
        <Eyebrow>数 · 据 · 安 · 全</Eyebrow>
        <h2 className="landing-section-title">
          你的数据，<br />
          连我们也看不到
        </h2>
        <p className="landing-section-sub">
          命盘档案和 AI 对话，在服务器上均经过加密处理。<br />
          每位用户使用独立密钥，我们的后台无法解密，也无法读取你的任何内容。
        </p>

        <div className="landing-privacy-grid">
          <div className="landing-privacy-item">
            <div className="landing-privacy-icon" aria-hidden="true">△</div>
            <h3>命盘数据加密</h3>
            <p>你的命盘档案由每人专属的加密密钥（DEK）封装存储。主密钥从不解密用户数据，后台也无法直接读取你的出生信息或解读内容。</p>
          </div>
          <div className="landing-privacy-item">
            <div className="landing-privacy-icon" aria-hidden="true">○</div>
            <h3>对话内容加密</h3>
            <p>与 AI 的每条对话同样经过加密存储。我们看不到你和 AI 之间说了什么，不做人工审阅，也不用于模型训练。</p>
          </div>
          <div className="landing-privacy-item">
            <div className="landing-privacy-icon" aria-hidden="true">⊘</div>
            <h3>不出售，不共享</h3>
            <p>你的数据只用于为你生成解读，不会出售给第三方，也不用于广告投放。</p>
          </div>
          <div className="landing-privacy-item">
            <div className="landing-privacy-icon" aria-hidden="true">□</div>
            <h3>随时可彻底删除</h3>
            <p>你可以随时删除命盘档案和账户。注销时执行密钥销毁（crypto-shred），数据物理上再也无法还原。</p>
          </div>
        </div>

        <p className="landing-privacy-link-row">
          <Link to="/legal/privacy">阅读完整隐私政策 →</Link>
        </p>
      </section>

      {/* ── 8. 收尾 ─────────────────────────────────────────────────── */}
      <section className="landing-final">
        <Eyebrow>有 · 时</Eyebrow>
        <h2 className="landing-final-title">
          有时，<br />
          和自己的时间，<br />
          坐下来谈一谈。
        </h2>
        <div className="landing-final-cta">
          <button type="button" className="landing-cta-quiet" onClick={handleStart}>
            开始排盘 →
          </button>
        </div>
        <footer className="landing-final-footer">
          <div className="landing-final-brand">
            <BrandLogo className="landing-footer-logo" />
            <p>一个理性的命盘与关系解读工具</p>
          </div>
          <nav className="landing-final-links" aria-label="页脚链接">
            <Link to="/legal/about">关于</Link>
            <Link to="/legal/privacy">隐私政策</Link>
            <Link to="/legal/terms">服务条款</Link>
            <a href="mailto:songhuichen7@gmail.com?subject=有时%20·%20反馈">反馈</a>
          </nav>
        </footer>
      </section>

    </main>
  );
}
