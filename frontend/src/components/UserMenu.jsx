import { useEffect, useReducer, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAppStore } from '../store/useAppStore';
import {
  buildUserMenuProfile,
  formatYearMonth,
  downloadJsonBlob,
  planLabelWithExpiry,
  pickUserCenterQuotaRows,
  quotaKindLabel,
} from '../lib/userMenu';
import {
  bindPhone,
  deleteAccount,
  exportMyData,
  sendSmsCode,
  updateProfile,
  uploadAvatar,
} from '../lib/api';
import { ALLOWED_AVATAR_MIME, AVATAR_ACCEPT } from '../lib/avatarUpload.js';
import { invalidateHepanMine } from '../lib/hepanApi.js';
import { friendlyError } from '../lib/errorMessages';

// 用户中心是个有点东西的弹层 — view 切换走 reducer 的 action.type，
// 跟"是否打开"是同一个状态机；switch_view 调用方传 `to` 字段。
function reduceMenu(state, action) {
  if (action?.type === 'toggle') return { ...state, open: !state.open, view: 'main' };
  if (action?.type === 'outside' || action?.type === 'logout' || action?.type === 'close') {
    return { open: false, view: 'main' };
  }
  if (action?.type === 'switch_view') return { ...state, view: action.to || 'main' };
  return state;
}

export default function UserMenu() {
  const user = useAppStore((s) => s.user);
  const patchUser = useAppStore((s) => s.patchUser);
  const logout = useAppStore((s) => s.logout);
  const chartCount = useAppStore((s) => Object.keys(s.charts || {}).length);
  const conversationCount = useAppStore((s) => (s.conversations || []).length);
  const quotaSnapshot = useAppStore((s) => s.quotaSnapshot);
  const refreshQuotaSnapshot = useAppStore((s) => s.refreshQuotaSnapshot);
  const navigate = useNavigate();

  const rootRef = useRef(null);
  const fileInputRef = useRef(null);

  // 旧 reducer 只跟踪 open；现在还要跟 view（main / bind / delete）一起。
  const [{ open, view }, dispatch] = useReducer(reduceMenu, { open: false, view: 'main' });

  // 顶层的瞬时状态 — 下面的子区块共享。每次关菜单都会清掉。
  const [editingName, setEditingName] = useState(false);
  const [draftName, setDraftName] = useState('');
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  useEffect(() => {
    if (!open) {
      setEditingName(false);
      setDraftName('');
      setErrorMsg('');
      return undefined;
    }
    // 打开菜单时调一次 — store 里有 5 分钟 TTL，5 分钟内重复打开不会真发请求。
    // 乐观自增（bumpQuotaUsage）已经在 chat / gua 完成时落到 store 上，
    // 所以即便缓存还热，用量条也是准的。
    void refreshQuotaSnapshot();
    function onDocClick(event) {
      if (rootRef.current && !rootRef.current.contains(event.target)) {
        dispatch({ type: 'outside' });
      }
    }
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, [open, refreshQuotaSnapshot]);

  if (!user) return null;

  const profile = buildUserMenuProfile(user);
  const memberSince = formatYearMonth(user.created_at);

  // ── 子操作 ─────────────────────────────────────────────────────────────

  function startRename() {
    setDraftName(user.nickname || '');
    setErrorMsg('');
    setEditingName(true);
  }

  async function commitRename() {
    const next = draftName.trim();
    if (next === (user.nickname || '').trim()) {
      setEditingName(false);
      return;
    }
    setSaving(true);
    setErrorMsg('');
    try {
      const updated = await updateProfile({ nickname: next });
      patchUser({ nickname: updated.nickname, avatar_url: updated.avatar_url });
      invalidateHepanMine();
      setEditingName(false);
    } catch (e) {
      setErrorMsg(friendlyError(e, 'profile').title);
    } finally {
      setSaving(false);
    }
  }

  function cancelRename() {
    setEditingName(false);
    setDraftName('');
    setErrorMsg('');
  }

  async function applyAvatarFile(file) {
    if (!file) return;
    if (!ALLOWED_AVATAR_MIME.includes(file.type)) {
      setErrorMsg('请上传 PNG / JPG / WebP / GIF / HEIC 图片');
      return;
    }
    setUploading(true);
    setErrorMsg('');
    try {
      const updated = await uploadAvatar(file);
      patchUser({ nickname: updated.nickname, avatar_url: updated.avatar_url });
      invalidateHepanMine();
    } catch (e) {
      setErrorMsg(friendlyError(e, 'profile').title);
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  }

  function onAvatarDragOver(event) {
    event.preventDefault();
    if (uploading) return;
    setDragOver(true);
  }

  function onAvatarDragLeave(event) {
    event.preventDefault();
    setDragOver(false);
  }

  async function onAvatarDrop(event) {
    event.preventDefault();
    setDragOver(false);
    if (uploading) return;
    const file = event.dataTransfer?.files?.[0];
    if (file) await applyAvatarFile(file);
  }

  async function onExport() {
    if (exporting) return;
    setExporting(true);
    setErrorMsg('');
    try {
      const data = await exportMyData();
      const fileBase = profile.isGuest ? 'youshi-guest' : `youshi-${profile.maskedPhone ? user.phone_last4 || 'data' : 'data'}`;
      downloadJsonBlob(data, fileBase);
    } catch (e) {
      setErrorMsg(friendlyError(e, 'profile').title);
    } finally {
      setExporting(false);
    }
  }

  // ── 渲染 ────────────────────────────────────────────────────────────────

  return (
    <div className="user-menu" ref={rootRef}>
      <button
        className="user-menu-trigger"
        onClick={() => dispatch({ type: 'toggle' })}
        aria-expanded={open}
        title={profile.displayName}
      >
        <span className="user-avatar">
          {profile.avatarUrl ? (
            <img src={profile.avatarUrl} alt="" draggable="false" />
          ) : (
            profile.avatarLabel
          )}
        </span>
      </button>

      {open ? (
        <div className="user-menu-dropdown user-center" role="dialog" aria-label="用户中心">
          {view === 'main' ? (
            <MainView
              profile={profile}
              memberSince={memberSince}
              chartCount={chartCount}
              conversationCount={conversationCount}
              quotaSnapshot={quotaSnapshot}
              uploading={uploading}
              dragOver={dragOver}
              fileInputRef={fileInputRef}
              onAvatarDragOver={onAvatarDragOver}
              onAvatarDragLeave={onAvatarDragLeave}
              onAvatarDrop={onAvatarDrop}
              onAvatarFile={applyAvatarFile}
              editingName={editingName}
              draftName={draftName}
              setDraftName={setDraftName}
              saving={saving}
              startRename={startRename}
              commitRename={commitRename}
              cancelRename={cancelRename}
              errorMsg={errorMsg}
              exporting={exporting}
              onExport={onExport}
              onBindPhone={() => dispatch({ type: 'switch_view', to: 'bind' })}
              onDeleteAccount={() => dispatch({ type: 'switch_view', to: 'delete' })}
              onLogout={async () => {
                dispatch({ type: 'logout' });
                await logout();
                navigate('/', { replace: true });
              }}
            />
          ) : null}

          {view === 'bind' ? (
            <BindPhoneView
              onBack={() => dispatch({ type: 'switch_view', to: 'main' })}
              onSuccess={(updated, typedPhone) => {
                // 后端只回 phone_last4；本地补一份 raw phone 给 isGuest 检测用，
                // 同时如果还挂着默认 '游客' 昵称就清掉，让 displayName 走"尾号 1234"。
                const patch = {
                  phone_last4: updated.phone_last4,
                  phone: typedPhone,
                };
                if ((user.nickname || '').trim() === '游客') patch.nickname = null;
                patchUser(patch);
                dispatch({ type: 'switch_view', to: 'main' });
              }}
            />
          ) : null}

          {view === 'delete' ? (
            <DeleteAccountView
              profile={profile}
              onBack={() => dispatch({ type: 'switch_view', to: 'main' })}
              onConfirmed={async () => {
                // 后端 shred 后已经清掉 cookie；前端 logout() 顺手清 store + storage。
                dispatch({ type: 'logout' });
                await logout();
                navigate('/', { replace: true });
              }}
            />
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

// ── Main view ───────────────────────────────────────────────────────────────

function MainView(props) {
  const {
    profile, memberSince, chartCount, conversationCount,
    quotaSnapshot,
    uploading, dragOver, fileInputRef,
    onAvatarDragOver, onAvatarDragLeave, onAvatarDrop, onAvatarFile,
    editingName, draftName, setDraftName, saving, startRename, commitRename, cancelRename,
    errorMsg, exporting, onExport, onBindPhone, onDeleteAccount, onLogout,
  } = props;

  const planText = planLabelWithExpiry(profile.plan, profile.planExpiresAt);
  const quotaRows = pickUserCenterQuotaRows(quotaSnapshot);

  return (
    <>
      <div className="user-center-head">
        <label
          className={
            'user-center-avatar'
            + (uploading ? ' is-uploading' : '')
            + (dragOver ? ' is-dragover' : '')
          }
          onDragOver={onAvatarDragOver}
          onDragLeave={onAvatarDragLeave}
          onDrop={onAvatarDrop}
        >
          {profile.avatarUrl ? (
            <img src={profile.avatarUrl} alt="头像" draggable="false" />
          ) : (
            <span className="user-center-avatar-fallback">{profile.avatarLabel}</span>
          )}
          <span className="user-center-avatar-overlay">
            {uploading ? '上传中…' : (dragOver ? '松手即换' : '换头像')}
          </span>
          <input
            ref={fileInputRef}
            type="file"
            accept={AVATAR_ACCEPT}
            onChange={(e) => onAvatarFile(e.target.files?.[0])}
            hidden
          />
        </label>
        <div className="user-center-head-meta">
          {editingName ? (
            <div className="user-center-name-edit">
              <input
                className="user-center-name-input"
                autoFocus
                value={draftName}
                onChange={(e) => setDraftName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') void commitRename();
                  if (e.key === 'Escape') cancelRename();
                }}
                placeholder="给自己起个名字"
                maxLength={40}
                disabled={saving}
              />
              <div className="user-center-name-actions">
                <button
                  type="button"
                  className="btn-inline"
                  onClick={() => void commitRename()}
                  disabled={saving}
                >{saving ? '保存中…' : '保存'}</button>
                <button
                  type="button"
                  className="user-center-link"
                  onClick={cancelRename}
                  disabled={saving}
                >取消</button>
              </div>
            </div>
          ) : (
            <div className="user-center-name">
              <span className="user-center-name-text">{profile.displayName}</span>
              <button
                type="button"
                className="user-center-name-edit-btn"
                onClick={startRename}
                title="编辑昵称"
                aria-label="编辑昵称"
              >✎</button>
            </div>
          )}
          <div className="user-center-tags">
            <span className={'user-center-tag tag-' + profile.plan}>{planText}</span>
            {profile.role === 'admin' ? (
              <span className="user-center-tag tag-admin">Admin</span>
            ) : null}
            {memberSince ? (
              <span className="user-center-tag tag-muted">加入于 {memberSince}</span>
            ) : null}
          </div>
        </div>
      </div>

      {profile.maskedPhone ? (
        <div className="user-center-phone muted">{profile.maskedPhone}</div>
      ) : (
        profile.isGuest ? (
          <div className="user-center-phone muted">访客模式 · 数据只在这台设备</div>
        ) : null
      )}

      <div className="user-center-overview muted">
        共 {chartCount} 张命盘
        {conversationCount > 0 ? <> · 当前盘 {conversationCount} 个对话</> : null}
      </div>

      {quotaRows.length ? (
        <div className="user-center-quota">
          <div className="user-center-quota-head-row">
            <span className="user-center-quota-head muted">本日用量</span>
            <Link className="user-center-quota-upgrade" to="/pricing">升级方案 →</Link>
          </div>
          {quotaRows.map((row) => (
            <QuotaBar key={row.kind} row={row} />
          ))}
        </div>
      ) : null}

      {errorMsg ? (
        <div className="user-center-error" role="alert">{errorMsg}</div>
      ) : null}

      <div className="user-menu-sep" />

      <div className="user-center-actions">
        {profile.isGuest ? (
          <button
            type="button"
            className="user-center-action"
            onClick={onBindPhone}
            title="绑定手机号 — 命盘 / 对话不丢"
          >
            <span className="user-center-action-icon">→</span>
            <span className="user-center-action-text">
              <span>绑定手机号</span>
              <span className="user-center-action-hint">升级正式账号，命盘 / 对话保留</span>
            </span>
          </button>
        ) : null}
        <Link className="user-center-action" to="/hepan/mine">
          <span className="user-center-action-icon">↔</span>
          <span className="user-center-action-text">
            <span>我的合盘</span>
            <span className="user-center-action-hint">已邀请过的人 + 完整解读</span>
          </span>
        </Link>
        <button
          type="button"
          className="user-center-action"
          onClick={onExport}
          disabled={exporting}
        >
          <span className="user-center-action-icon">↓</span>
          <span className="user-center-action-text">
            <span>{exporting ? '正在打包…' : '导出我的数据'}</span>
            <span className="user-center-action-hint">命盘 + 对话 + 消息（JSON）</span>
          </span>
        </button>
      </div>

      <div className="user-menu-sep" />

      <div className="user-center-foot">
        {/* 同一标签页跳进 /legal/:slug — 旧版用 target=_blank 是错的：
            返回按钮调 navigate(-1) 但新标签没有历史，按了等于哑火。
            mailto 是协议跳转，留 <a>。*/}
        <Link className="user-center-foot-link" to="/legal/about">关于</Link>
        <span className="user-center-foot-dot">·</span>
        <Link className="user-center-foot-link" to="/legal/terms">服务条款</Link>
        <span className="user-center-foot-dot">·</span>
        <Link className="user-center-foot-link" to="/legal/privacy">隐私</Link>
        <span className="user-center-foot-dot">·</span>
        <a className="user-center-foot-link" href="mailto:songhuichen7@gmail.com?subject=有时%20·%20反馈">反馈</a>
      </div>

      <div className="user-menu-sep" />

      <div className="user-center-danger">
        <button className="user-menu-logout" onClick={onLogout}>退出登录</button>
        <button
          type="button"
          className="user-center-danger-link"
          onClick={onDeleteAccount}
        >注销账号</button>
      </div>
    </>
  );
}

// ── Quota bar ───────────────────────────────────────────────────────────────

function QuotaBar({ row }) {
  const used = Math.max(0, Number(row.used) || 0);
  const limit = Math.max(1, Number(row.limit) || 1);   // 防 0 除
  const ratio = Math.min(1, used / limit);
  const percent = Math.round(ratio * 100);
  const tone =
    ratio >= 1   ? 'full'
    : ratio >= 0.85 ? 'warn'
    : 'ok';
  const label = quotaKindLabel(row.kind);
  const hint = row.periodic
    ? '北京 0 点重置'
    : '累计上限';
  return (
    <div className={'user-center-quota-row tone-' + tone}>
      <div className="user-center-quota-row-head">
        <span className="user-center-quota-row-label">{label}</span>
        <span className="user-center-quota-row-count">{used} / {limit}</span>
      </div>
      <div className="user-center-quota-bar">
        <div
          className="user-center-quota-bar-fill"
          style={{ width: `${Math.max(2, percent)}%` }}
        />
      </div>
      <div className="user-center-quota-row-hint">{hint}</div>
    </div>
  );
}

// ── Bind-phone view ────────────────────────────────────────────────────────

function BindPhoneView({ onBack, onSuccess }) {
  const [phone, setPhone] = useState('');
  const [code, setCode] = useState('');
  const [secondsLeft, setSecondsLeft] = useState(0);
  const [sending, setSending] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [devCode, setDevCode] = useState('');

  useEffect(() => {
    if (secondsLeft <= 0) return undefined;
    const t = setInterval(() => setSecondsLeft((v) => (v > 1 ? v - 1 : 0)), 1000);
    return () => clearInterval(t);
  }, [secondsLeft]);

  async function onSendCode() {
    const trimmed = String(phone).trim();
    if (!trimmed) {
      setError('请输入手机号');
      return;
    }
    setSending(true);
    setError('');
    try {
      const result = await sendSmsCode(trimmed, 'register');
      setDevCode(result.__devCode || '');
      setSecondsLeft(60);
    } catch (e) {
      setError(e.message || String(e));
    } finally {
      setSending(false);
    }
  }

  async function onSubmit(event) {
    event.preventDefault();
    if (submitting) return;
    const trimmedPhone = String(phone).trim();
    const trimmedCode = String(code).trim();
    if (!trimmedPhone || !/^\d{6}$/.test(trimmedCode)) {
      setError('请输入手机号和 6 位验证码');
      return;
    }
    setSubmitting(true);
    setError('');
    try {
      const updated = await bindPhone({ phone: trimmedPhone, code: trimmedCode });
      onSuccess(updated, trimmedPhone);
    } catch (e) {
      setError(friendlyError(e, 'profile').title || (e.message || String(e)));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="user-center-subview">
      <div className="user-center-subview-head">
        <button type="button" className="user-center-link" onClick={onBack}>← 返回</button>
        <h3 className="user-center-subview-title">绑定手机号</h3>
      </div>
      <p className="user-center-subview-desc">
        绑定后，你现在的命盘 / 对话 / 古籍记录全部保留 — 只是从访客升级成正式账号，
        换设备也能登录。
      </p>

      <form onSubmit={onSubmit} className="user-center-form">
        <div className="user-center-form-row">
          <input
            type="tel"
            inputMode="numeric"
            autoComplete="tel"
            placeholder="13800138000"
            maxLength={15}
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            disabled={submitting}
          />
          <button
            type="button"
            className="btn-inline"
            onClick={() => void onSendCode()}
            disabled={sending || secondsLeft > 0 || submitting}
          >
            {secondsLeft > 0 ? `${secondsLeft}s` : (sending ? '发送中…' : '发送验证码')}
          </button>
        </div>
        <input
          className="user-center-form-input"
          type="text"
          inputMode="numeric"
          autoComplete="one-time-code"
          placeholder="6 位验证码"
          maxLength={6}
          value={code}
          onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
          disabled={submitting}
        />
        {devCode ? (
          <div className="auth-dev-code">[DEV] code: {devCode}</div>
        ) : null}
        {error ? <div className="user-center-error" role="alert">{error}</div> : null}
        <button
          type="submit"
          className="btn-primary user-center-form-submit"
          disabled={submitting}
        >
          {submitting ? '绑定中…' : '绑定手机号'}
        </button>
      </form>
    </div>
  );
}

// ── Delete-account view ─────────────────────────────────────────────────────

const DELETE_PHRASE = 'DELETE MY ACCOUNT';

function DeleteAccountView({ profile, onBack, onConfirmed }) {
  const [phrase, setPhrase] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const matches = phrase.trim() === DELETE_PHRASE;

  async function onSubmit(event) {
    event.preventDefault();
    if (!matches || submitting) return;
    setSubmitting(true);
    setError('');
    try {
      await deleteAccount();
      await onConfirmed();
    } catch (e) {
      setError(friendlyError(e, 'profile').title || (e.message || String(e)));
      setSubmitting(false);
    }
  }

  return (
    <div className="user-center-subview">
      <div className="user-center-subview-head">
        <button type="button" className="user-center-link" onClick={onBack}>← 返回</button>
        <h3 className="user-center-subview-title danger">注销账号</h3>
      </div>
      <p className="user-center-subview-desc">
        这是不可恢复的操作。一旦确认：
      </p>
      <ul className="user-center-bullets">
        <li>所有命盘 / 对话 / 古籍记录立即不可读</li>
        <li>账号上的加密密钥被销毁（crypto-shred）— 即使数据库被备份也无法恢复</li>
        <li>同一手机号 30 天内不能用于注册</li>
      </ul>

      <form onSubmit={onSubmit} className="user-center-form">
        <label className="user-center-form-label">
          请在下方输入 <code>{DELETE_PHRASE}</code> 以确认：
        </label>
        <input
          className="user-center-form-input"
          type="text"
          autoComplete="off"
          placeholder={DELETE_PHRASE}
          value={phrase}
          onChange={(e) => setPhrase(e.target.value)}
          disabled={submitting}
        />
        {error ? <div className="user-center-error" role="alert">{error}</div> : null}
        <button
          type="submit"
          className="btn-danger user-center-form-submit"
          disabled={!matches || submitting}
          title={profile.isGuest ? '访客账号也会被一并清空' : ''}
        >
          {submitting ? '注销中…' : '永久注销账号'}
        </button>
      </form>
    </div>
  );
}
