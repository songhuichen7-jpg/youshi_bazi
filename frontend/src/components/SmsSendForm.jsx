import { useEffect, useState } from 'react';
import { sendSmsCode } from '../lib/api';

export default function SmsSendForm({ phone, onPhoneChange, purpose, onSent }) {
  const [sending, setSending] = useState(false);
  const [secondsLeft, setSecondsLeft] = useState(0);
  const [error, setError] = useState(null);
  const [devCode, setDevCode] = useState('');

  useEffect(() => {
    if (secondsLeft <= 0) return undefined;
    const timer = setInterval(() => {
      setSecondsLeft((value) => (value > 1 ? value - 1 : 0));
    }, 1000);
    return () => clearInterval(timer);
  }, [secondsLeft]);

  async function onSubmit(event) {
    event.preventDefault();
    if (!String(phone || '').trim()) {
      setError('请输入手机号');
      return;
    }
    setSending(true);
    setError(null);
    try {
      const result = await sendSmsCode(String(phone).trim(), purpose);
      setDevCode(result.__devCode || '');
      setSecondsLeft(60);
      onSent?.(result);
    } catch (e) {
      setError(e.message || String(e));
    } finally {
      setSending(false);
    }
  }

  return (
    <form onSubmit={onSubmit}>
      <div className="form-row auth-inline-row">
        <div>
          <label className="form-label">手机号</label>
          <input
            type="tel"
            value={phone}
            onChange={(event) => onPhoneChange?.(event.target.value)}
            placeholder="13800138001"
            inputMode="numeric"
            autoComplete="tel"
          />
        </div>
        <button className="btn-primary auth-send-btn" type="submit" disabled={sending || secondsLeft > 0}>
          {secondsLeft > 0 ? `${secondsLeft}s` : (sending ? '发送中…' : '发送验证码')}
        </button>
      </div>
      {error ? (
        <div className="auth-inline-error">{error}</div>
      ) : null}
      {devCode ? (
        <div className="auth-dev-code">
          {/* TODO: only surface the dev code in import.meta.env.DEV once prod auth QA is complete. */}
          [DEV] code: {devCode}
        </div>
      ) : null}
    </form>
  );
}
