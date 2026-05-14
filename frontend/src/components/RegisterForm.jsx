import { useState } from 'react';
import { register } from '../lib/api';

export default function RegisterForm({ phone, requireInvite, onSuccess }) {
  const [code, setCode] = useState('');
  const [inviteCode, setInviteCode] = useState('');
  const [nickname, setNickname] = useState('');
  const [agreed, setAgreed] = useState(true);
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
    if (requireInvite && !inviteCode.trim()) {
      setError('请输入邀请码');
      return;
    }
    if (!agreed) {
      setError('请先同意使用说明');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const result = await register({
        phone: String(phone).trim(),
        code: code.trim(),
        invite_code: inviteCode.trim() || null,
        nickname: nickname.trim() || null,
        agreed_to_terms: agreed,
      });
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

      {requireInvite ? (
        <div className="form-row">
          <label className="form-label">邀请码</label>
          <input
            value={inviteCode}
            onChange={(event) => setInviteCode(event.target.value)}
            placeholder="输入邀请码"
          />
        </div>
      ) : null}

      <div className="form-row">
        <label className="form-label">昵称</label>
        <input
          value={nickname}
          onChange={(event) => setNickname(event.target.value)}
          placeholder="怎么称呼你"
          autoComplete="nickname"
        />
      </div>

      <label className="auth-terms">
        <input
          type="checkbox"
          checked={agreed}
          onChange={(event) => setAgreed(event.target.checked)}
          style={{ width: 'auto' }}
        />
        <span>我知道这是一份命理参考，不替代现实决策。</span>
      </label>

      {error ? (
        <div className="auth-inline-error">{error}</div>
      ) : null}

      <button className="btn-primary auth-submit-btn" type="submit" disabled={submitting}>
        {submitting ? '注册中…' : '注册并开始 →'}
      </button>
    </form>
  );
}
