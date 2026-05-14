import { useState } from 'react';
import { login } from '../lib/api';

export default function LoginForm({ phone, onSuccess }) {
  const [code, setCode] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  async function onSubmit(event) {
    event.preventDefault();
    if (!String(phone || '').trim()) {
      setError('请先填写手机号并发送验证码');
      return;
    }
    if (!code.trim()) {
      setError('请输入验证码');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const result = await login({ phone: String(phone).trim(), code: code.trim() });
      await onSuccess?.(result.user);
    } catch (e) {
      setError(e.message || String(e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={onSubmit}>
      <div className="auth-phone-note">验证码将发送到 {phone || '你填写的手机号'}</div>

      <div className="form-row">
        <label className="form-label">验证码</label>
        <input
          value={code}
          onChange={(event) => setCode(event.target.value)}
          inputMode="numeric"
          placeholder="6 位验证码"
          autoComplete="one-time-code"
        />
      </div>

      {error ? (
        <div className="auth-inline-error">{error}</div>
      ) : null}

      <button className="btn-primary auth-submit-btn" type="submit" disabled={submitting}>
        {submitting ? '登录中…' : '登录并继续 →'}
      </button>
    </form>
  );
}
