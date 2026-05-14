import { useState, useRef } from 'react';
import { useAppStore } from '../store/useAppStore';
import { rerollNickname, updateProfile, uploadAvatar } from '../lib/api';
import { AVATAR_ACCEPT } from '../lib/avatarUpload.js';
import { invalidateHepanMine } from '../lib/hepanApi.js';
import { AvatarBadge } from './AvatarBadge.jsx';

// 进站后第一次的引导 modal — user.onboarded_at == null 时弹一次。
// 用户可以：
//   · 改昵称（默认值 = server 池里的随机名；右侧 ↻ reroll 按一次抽新的）
//   · 上传头像（点击或拖拽，可选）
//   · 点 "完成" — PATCH /me 写 nickname/avatar + mark_onboarded
//   · 点 "稍后再说" — PATCH /me 只写 mark_onboarded（保留默认）
// 任一动作完成都让 onboarded_at 非空 → 永不再弹。
export default function OnboardingModal({ onClose }) {
  const user = useAppStore(s => s.user);
  const patchUser = useAppStore(s => s.patchUser);

  const [nickname, setNickname] = useState(user?.nickname || '');
  const [avatarUrl, setAvatarUrl] = useState(user?.avatar_url || null);
  const [rerolling, setRerolling] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const fileInputRef = useRef(null);

  const trimmed = nickname.trim();
  const canSubmit = trimmed.length >= 2 && trimmed.length <= 12 && !submitting;
  const seed = user?.id || 'guest';

  async function handleReroll() {
    if (rerolling) return;
    setError('');
    setRerolling(true);
    try {
      const updated = await rerollNickname();
      setNickname(updated.nickname || '');
      patchUser({ nickname: updated.nickname });
      invalidateHepanMine();
    } catch (e) {
      setError(e?.message || '换名失败，再试一次');
    } finally {
      setRerolling(false);
    }
  }

  async function handleUpload(file) {
    if (!file || uploading) return;
    setError('');
    setUploading(true);
    try {
      const updated = await uploadAvatar(file);
      setAvatarUrl(updated.avatar_url || null);
      patchUser({ avatar_url: updated.avatar_url });
      invalidateHepanMine();
    } catch (e) {
      setError(e?.message || '上传失败');
    } finally {
      setUploading(false);
    }
  }

  function onFilePick(e) {
    const f = e.target.files?.[0];
    if (f) handleUpload(f);
    e.target.value = '';
  }

  function onDrop(e) {
    e.preventDefault();
    const f = e.dataTransfer.files?.[0];
    if (f) handleUpload(f);
  }

  async function handleSubmit() {
    if (!canSubmit) return;
    setError('');
    setSubmitting(true);
    try {
      const payload = { mark_onboarded: true };
      if (trimmed && trimmed !== user?.nickname) payload.nickname = trimmed;
      const updated = await updateProfile(payload);
      patchUser(updated);
      invalidateHepanMine();
      onClose();
    } catch (e) {
      setError(e?.message || '保存失败');
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDismiss() {
    if (submitting) return;
    setError('');
    setSubmitting(true);
    try {
      const updated = await updateProfile({ mark_onboarded: true });
      patchUser(updated);
      onClose();
    } catch (e) {
      setError(e?.message || '保存失败');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="onboarding-modal-backdrop" role="dialog" aria-modal="true">
      <div className="onboarding-modal">
        <header className="onboarding-modal-head">
          <h2 className="onboarding-modal-title">取一个名字 给自己</h2>
          <p className="onboarding-modal-sub">你来到「有时」的命盘世界</p>
        </header>

        <div
          className="onboarding-modal-avatar-area"
          onDragOver={e => e.preventDefault()}
          onDrop={onDrop}
          onClick={() => fileInputRef.current?.click()}
          role="button"
          tabIndex={0}
        >
          <AvatarBadge size={56} seed={seed} name={trimmed || '游'} avatarUrl={avatarUrl} />
          <span className="onboarding-modal-avatar-hint">
            {uploading ? '上传中…' : '上传头像'}
          </span>
          <input
            ref={fileInputRef}
            type="file"
            accept={AVATAR_ACCEPT}
            style={{ display: 'none' }}
            onChange={onFilePick}
          />
        </div>

        <div className="onboarding-modal-nick-row">
          <input
            className="onboarding-modal-nick-input"
            type="text"
            maxLength={12}
            placeholder="2 - 12 字符"
            value={nickname}
            onChange={e => setNickname(e.target.value)}
          />
          <button
            type="button"
            className="onboarding-modal-reroll"
            onClick={handleReroll}
            disabled={rerolling}
            title="再随机抽一个"
          >
            ↻ {rerolling ? '换中…' : '换一个'}
          </button>
        </div>

        {error ? <p className="onboarding-modal-error" role="alert">{error}</p> : null}

        <div className="onboarding-modal-actions">
          <button
            type="button"
            className="btn-primary onboarding-modal-submit"
            onClick={handleSubmit}
            disabled={!canSubmit}
          >完成</button>
          <button
            type="button"
            className="onboarding-modal-dismiss"
            onClick={handleDismiss}
            disabled={submitting}
          >稍后再说</button>
        </div>

        <p className="onboarding-modal-foot muted">
          之后随时在左下角个人中心修改
        </p>
      </div>
    </div>
  );
}
