import { useState } from 'react';
import { buildPartnerBirthPayload, EMPTY_PARTNER_FORM } from './partnerBirthValidation.js';
import { BIRTH_DATE_MIN, birthDateMax } from '../../lib/dateBounds.js';

// 共享“对方命盘”录入表单。两处用：
//   · CardWorkspace 内联展开 — A 直接帮 B 填，提交跑 invite + complete
//   · HepanScreen pending 状态 — B 通过链接打开自己填，提交跑 complete
//
// 字段：生日 / 时间 / 时辰未知 / 出生地 / 性别 / 昵称
// 校验：buildPartnerBirthPayload — 抛 Error 时把 message 显成 inline error
//
// props:
//   submitLabel  按钮文字（"生成合盘卡片" / "提交"）
//   onSubmit     async ({ birth, nickname }) => void  提交时调用，throw 即把 message 显示为 error
//   onCancel?    显示“取消”按钮；点击时调用
//   initial?     初始 form 状态（部分覆盖 EMPTY_PARTNER_FORM）
//   busy         禁用按钮 + "...中" 文案
//
export function PartnerBirthForm({
  submitLabel = '提交',
  onSubmit,
  onCancel,
  initial,
  busy = false,
  idPrefix = 'partner',
}) {
  const [form, setForm] = useState(() => ({ ...EMPTY_PARTNER_FORM, ...(initial || {}) }));
  const [error, setError] = useState('');

  function update(field, value) {
    setForm(prev => ({ ...prev, [field]: value }));
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (busy) return;
    setError('');
    let birth;
    try {
      birth = buildPartnerBirthPayload(form);
    } catch (e) {
      setError(e.message || '请检查表单。');
      return;
    }
    try {
      await onSubmit({ birth, nickname: (form.nickname || '').trim() || null });
    } catch (e) {
      setError(e?.message || '提交失败，再试一次。');
    }
  }

  return (
    <form className="partner-birth-form" onSubmit={handleSubmit} noValidate>
      <label className="partner-field partner-field-date">
        <span>生日</span>
        <input
          id={`${idPrefix}-date`}
          aria-label="对方公历生日"
          type="date"
          min={BIRTH_DATE_MIN}
          max={birthDateMax()}
          value={form.date}
          onChange={e => update('date', e.target.value)}
        />
      </label>

      <label className="partner-field partner-field-time">
        <span>时间</span>
        <input
          id={`${idPrefix}-time`}
          aria-label="对方出生时间"
          type="time"
          value={form.time}
          disabled={form.hourUnknown}
          onChange={e => update('time', e.target.value)}
        />
      </label>

      <label className="partner-field-checkbox">
        <input
          type="checkbox"
          checked={form.hourUnknown}
          onChange={e => setForm(prev => ({
            ...prev,
            hourUnknown: e.target.checked,
            time: e.target.checked ? '' : prev.time,
          }))}
        />
        时辰未知
      </label>

      <label className="partner-field partner-field-city">
        <span>出生地</span>
        <input
          id={`${idPrefix}-city`}
          aria-label="对方出生地"
          type="text"
          placeholder="可选"
          maxLength={20}
          value={form.city}
          onChange={e => update('city', e.target.value)}
        />
      </label>

      <label className="partner-field partner-field-gender">
        <span>性别</span>
        <select
          aria-label="对方性别"
          value={form.gender}
          onChange={e => update('gender', e.target.value)}
        >
          <option value="">可选</option>
          <option value="female">女</option>
          <option value="male">男</option>
        </select>
      </label>

      <label className="partner-field partner-field-nickname">
        <span>昵称</span>
        <input
          id={`${idPrefix}-nickname`}
          aria-label="对方昵称"
          type="text"
          placeholder="可选"
          maxLength={12}
          value={form.nickname}
          onChange={e => update('nickname', e.target.value)}
        />
      </label>

      {error ? <div className="partner-form-error" role="alert">{error}</div> : null}

      <div className="partner-form-actions">
        <button type="submit" className="btn-primary" disabled={busy}>
          {busy ? '提交中…' : submitLabel}
        </button>
        {onCancel ? (
          <button type="button" className="btn-inline" onClick={onCancel} disabled={busy}>
            取消
          </button>
        ) : null}
      </div>
    </form>
  );
}
