import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { cancelSubscription, fetchBilling, startCheckout } from '../lib/api';
import { friendlyError } from '../lib/errorMessages';

// 三档参数硬编码 — 这是产品事实，不该在 runtime 拉。后端 core/quotas.py
// 是真相之源；这里把它转译成可阅读的中文卖点；改动后别忘了同步。
const TIERS = [
  {
    plan: 'lite',
    name: '免费体验',
    price: '¥0',
    cadence: '永久免费',
    rows: [
      ['对话', '30 / 天'],
      ['起卦', '3 / 天'],
      ['命盘', '2 张'],
      ['古籍 / 大运 / 流年', '基础'],
    ],
    note: '让你先把产品摸熟。',
  },
  {
    plan: 'standard',
    name: '标准',
    price: '¥19',
    cadence: '/ 月',
    rows: [
      ['对话', '150 / 天 (5×)'],
      ['起卦', '15 / 天'],
      ['命盘', '5 张'],
      ['古籍 / 大运 / 流年', '完整'],
    ],
    note: '一个家庭、几张盘聊得起。',
    highlighted: false,
  },
  {
    plan: 'pro',
    name: 'Pro',
    price: '¥69',
    cadence: '/ 月',
    rows: [
      ['对话', '600 / 天 (20×)'],
      ['起卦', '60 / 天'],
      ['命盘', '20 张'],
      ['模型档位', '高级 + 优先队列'],
    ],
    note: '重度使用 / 命理实践者。',
    highlighted: true,
  },
];


export default function PricingPage() {
  const navigate = useNavigate();
  const [billing, setBilling] = useState(null);   // 后端 GET /api/billing/me
  const [busyPlan, setBusyPlan] = useState(null); // 'standard' / 'pro'
  const [errorMsg, setErrorMsg] = useState('');

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const result = await fetchBilling();
        if (!cancelled) setBilling(result);
      } catch { /* 未登录 / 离线 — 让 billing 为 null 继续渲染 */ }
    })();
    return () => { cancelled = true; };
  }, []);

  function goBack() {
    const idx = typeof window !== 'undefined' ? window.history.state?.idx : undefined;
    if (typeof idx === 'number' && idx > 0) navigate(-1);
    else navigate('/', { replace: true });
  }

  async function onUpgrade(plan) {
    if (busyPlan) return;
    setBusyPlan(plan);
    setErrorMsg('');
    try {
      const result = await startCheckout({ plan, period: 'monthly' });
      handleInstructions(result.instructions);
    } catch (e) {
      const ui = friendlyError(e, 'billing');
      setErrorMsg(ui.title + (ui.detail ? ` · ${ui.detail}` : ''));
    } finally {
      setBusyPlan(null);
    }
  }

  async function onCancel() {
    if (busyPlan) return;
    if (!window.confirm('取消后当前周期到期前仍可使用，到期后自动降回 lite。确认？')) return;
    setBusyPlan('cancel');
    setErrorMsg('');
    try {
      await cancelSubscription({ reason: 'user_cancel' });
      // 重新拉一遍最新订阅状态
      const result = await fetchBilling();
      setBilling(result);
    } catch (e) {
      const ui = friendlyError(e, 'billing');
      setErrorMsg(ui.title + (ui.detail ? ` · ${ui.detail}` : ''));
    } finally {
      setBusyPlan(null);
    }
  }

  return (
    <div className="screen active pricing-screen">
      <div className="pricing-wrap">
        <button className="legal-back" type="button" onClick={goBack}>← 返回</button>
        <div className="legal-eyebrow">套 餐 · 用 量</div>
        <h1 className="serif legal-title">三档方案</h1>
        <p className="pricing-lede">
          三档共享同一个产品 — 区别只在你能用得多少。<br />
          有时不卖功能，卖的是<em>陪你想清楚</em>这件事的容量。
        </p>

        {errorMsg ? <div className="pricing-error" role="alert">{errorMsg}</div> : null}

        <div className="pricing-grid">
          {TIERS.map((tier) => (
            <PricingCard
              key={tier.plan}
              tier={tier}
              isCurrent={billing?.plan === tier.plan}
              hasActiveSub={!!billing?.active_subscription}
              busy={busyPlan === tier.plan}
              onUpgrade={() => onUpgrade(tier.plan)}
              onCancel={onCancel}
            />
          ))}
        </div>

        <div className="pricing-foot">
          <p>
            {billing?.payment_provider === 'manual'
              ? <>内测期间没有在线支付通道。点"立即升级"会自动打开邮件，作者收到后人工开通；通常 24 小时内生效。</>
              : <>支付完成后通常几秒内升级到位；如果 5 分钟还没生效，请联系作者：<a className="user-center-foot-link" href="mailto:songhuichen7@gmail.com?subject=有时%20·%20支付未生效">songhuichen7@gmail.com</a></>}
          </p>
          <p className="muted">
            订阅按自然月计费；用量按北京日界（每天 0 点）重置。
          </p>
        </div>
      </div>
    </div>
  );
}


// ── Single tier card ───────────────────────────────────────────────────────

function PricingCard({ tier, isCurrent, hasActiveSub, busy, onUpgrade, onCancel }) {
  return (
    <div className={
      'pricing-card'
      + (tier.highlighted ? ' is-highlighted' : '')
      + (isCurrent ? ' is-current' : '')
    }>
      <div className="pricing-card-name">{tier.name}</div>
      <div className="pricing-card-price">
        <span className="pricing-card-amount serif">{tier.price}</span>
        <span className="pricing-card-cadence muted">{tier.cadence}</span>
      </div>
      <ul className="pricing-card-rows">
        {tier.rows.map(([k, v]) => (
          <li key={k}>
            <span className="pricing-card-row-key muted">{k}</span>
            <span className="pricing-card-row-val">{v}</span>
          </li>
        ))}
      </ul>
      <div className="pricing-card-note muted">{tier.note}</div>
      <div className="pricing-card-cta">
        <CardCta
          tier={tier}
          isCurrent={isCurrent}
          hasActiveSub={hasActiveSub}
          busy={busy}
          onUpgrade={onUpgrade}
          onCancel={onCancel}
        />
      </div>
    </div>
  );
}

function CardCta({ tier, isCurrent, hasActiveSub, busy, onUpgrade, onCancel }) {
  if (isCurrent) {
    if (tier.plan !== 'lite' && hasActiveSub) {
      // 当前付费档位 + 还没主动取消 — 显示取消按钮
      return (
        <button
          type="button"
          className="btn-inline"
          disabled={busy}
          onClick={onCancel}
        >{busy ? '处理中…' : '取消订阅'}</button>
      );
    }
    return <button type="button" className="btn-inline" disabled>当前所在档位</button>;
  }
  if (tier.plan === 'lite') {
    return <span className="muted" style={{ fontSize: 12 }}>无需开通</span>;
  }
  return (
    <button
      type="button"
      className="btn-primary"
      disabled={busy}
      onClick={onUpgrade}
    >{busy ? '处理中…' : '立即升级'}</button>
  );
}


// ── Provider-specific instructions handler ─────────────────────────────────

function handleInstructions(instructions) {
  if (!instructions || !instructions.kind) return;
  const { kind, payload } = instructions;

  if (kind === 'mailto') {
    const { to, subject, body } = payload || {};
    const url = `mailto:${to}?subject=${encodeURIComponent(subject || '')}&body=${encodeURIComponent(body || '')}`;
    window.location.href = url;
    return;
  }
  if (kind === 'redirect') {
    if (payload?.redirect_url) window.location.href = payload.redirect_url;
    return;
  }
  if (kind === 'qr_code') {
    // 微信 Native 支付：把 code_url 渲染成二维码。这里先开新窗口给个占位
    // 页面（接入正式渠道时换成 modal + qrcode-svg 渲染）。
    if (payload?.code_url) window.open(payload.code_url, '_blank');
    return;
  }
  if (kind === 'sdk_params') {
    // SDK 拼装参数 — 后端把 SDK 需要的 prepay_id / signature / package 都打包好；
    // 接入时换成实际的 wx.chooseWXPay() 之类调用。
    console.warn('[billing] sdk_params handler not implemented yet', payload);
    return;
  }
  console.warn('[billing] unknown instructions kind', kind);
}
