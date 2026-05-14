import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { deleteHepanInvite, getHepanMine, getHepanMineCached } from '../../lib/hepanApi.js';
import { formatYearMonthDay } from '../../lib/userMenu.js';
import { AvatarBadge } from '../AvatarBadge.jsx';

// 我的合盘列表 — 用在 CardWorkspace 合盘 tab 里。
//
// props:
//   onAsk(item)            点击"追问"行内动作（仅 completed）
//   onCopy(item)           复制邀请链接
//   onView(slug)           点击"查看"——浮窗打开 HepanCardModal,不再跳页
//                          (传 null 走老路由 fallback)
//   reloadKey              外部 bump 一下让列表强刷（例如新建后）
//
export function HepanList({ onAsk, onCopy, onView, reloadKey = 0 }) {
  const cached = getHepanMineCached();
  const [items, setItems] = useState(cached?.items || null);
  const [error, setError] = useState('');
  const [busySlug, setBusySlug] = useState(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await getHepanMine({ force: reloadKey > 0 });
        if (!cancelled) setItems(data?.items || []);
      } catch (e) {
        if (cancelled) return;
        if (e?.status === 401) { setItems([]); return; }
        setError(e?.message || '拉取失败');
      }
    })();
    return () => { cancelled = true; };
  }, [reloadKey]);

  async function handleDelete(slug) {
    if (busySlug) return;
    if (!window.confirm('删除这条邀请？删除后链接立即失效。')) return;
    setBusySlug(slug);
    setError('');
    try {
      await deleteHepanInvite(slug);
      setItems(prev => (prev || []).filter(it => it.slug !== slug));
    } catch (e) {
      setError(e?.message || '删除失败');
    } finally {
      setBusySlug(null);
    }
  }

  if (items === null) {
    return <p className="hepan-list-loading muted">正在加载…</p>;
  }

  const pending = items.filter(it => it.status === 'pending');
  const completed = items.filter(it => it.status === 'completed');

  if (items.length === 0) {
    return (
      <div className="hepan-list-empty">
        <p>还没有合盘记录。</p>
        <p className="muted">点上面"+ 新建合盘"开始你的第一条。</p>
      </div>
    );
  }

  return (
    <div className="hepan-list">
      {error ? <div className="hepan-list-error" role="alert">{error}</div> : null}
      {pending.length > 0 ? (
        <Group title="等回复" count={pending.length}
               hint="对方还没填生日 — 链接还能再复制一次发出去。">
          {pending.map(it => (
            <PendingRow
              key={it.slug}
              item={it}
              busy={busySlug === it.slug}
              onCopy={() => onCopy(it)}
              onDelete={() => handleDelete(it.slug)}
            />
          ))}
        </Group>
      ) : null}
      {completed.length > 0 ? (
        <Group title="已合" count={completed.length}
               hint="点'追问'打开这条合盘的专属对话。">
          {completed.map(it => (
            <CompletedRow
              key={it.slug}
              item={it}
              busy={busySlug === it.slug}
              onAsk={() => onAsk(it)}
              onCopy={() => onCopy(it)}
              onView={onView ? () => onView(it.slug) : null}
              onDelete={() => handleDelete(it.slug)}
            />
          ))}
        </Group>
      ) : null}
    </div>
  );
}

function Group({ title, count, hint, children }) {
  return (
    <section className="hepan-list-group">
      <header className="hepan-list-group-head">
        <h3 className="hepan-list-group-title">{title}</h3>
        <span className="hepan-list-group-count muted">{count}</span>
        <p className="hepan-list-group-hint muted">{hint}</p>
      </header>
      <ul className="hepan-list-rows">{children}</ul>
    </section>
  );
}

function PendingRow({ item, busy, onCopy, onDelete }) {
  const aName = item.a_cosmic_name || item.a_nickname || '我';
  return (
    <li
      className="hepan-row hepan-row-pending"
      style={item.pair_theme_color ? { '--pair-theme': item.pair_theme_color } : undefined}
    >
      <div className="hepan-row-text">
        <span className="hepan-row-name serif">
          <AvatarBadge
            size={24}
            seed={`${item.slug}-a`}
            name={aName}
            avatarUrl={item.a_avatar_url}
            className="hepan-row-avatar"
          />
          {aName}
        </span>
        <span className="hepan-row-meta muted">
          @{item.a_nickname || aName} 邀请 · 发于 {formatYearMonthDay(item.created_at)}
          {item.share_count > 0 ? ` · 访问 ${item.share_count} 次` : ''}
        </span>
      </div>
      <div className="hepan-row-actions">
        <button type="button" className="user-center-link" onClick={onCopy}>复制链接</button>
        <button
          type="button"
          className="user-center-link hepan-row-delete"
          onClick={onDelete} disabled={busy}
        >{busy ? '删除中…' : '删除'}</button>
      </div>
    </li>
  );
}

function CompletedRow({ item, busy, onAsk, onCopy, onView, onDelete }) {
  const aName = item.a_cosmic_name || '我';
  const bName = item.b_cosmic_name || '对方';
  return (
    <li
      className="hepan-row hepan-row-completed"
      style={item.pair_theme_color ? { '--pair-theme': item.pair_theme_color } : undefined}
    >
      <div className="hepan-row-text">
        <span className="hepan-row-name serif">
          <AvatarBadge
            size={24}
            seed={`${item.slug}-a`}
            name={aName}
            avatarUrl={item.a_avatar_url}
            className="hepan-row-avatar"
          />
          {aName}
          <span className="hepan-row-x">×</span>
          <AvatarBadge
            size={24}
            seed={`${item.slug}-b`}
            name={bName}
            avatarUrl={item.b_avatar_url}
            className="hepan-row-avatar"
          />
          {bName}
        </span>
        {item.label ? <span className="hepan-row-label">「{item.label}」</span> : null}
        <span className="hepan-row-meta muted">
          {formatYearMonthDay(item.created_at)}
          {item.message_count > 0
            ? ` · 对话 ${Math.ceil(item.message_count / 2)} 轮`
            : ' · 还没追问过'}
          {item.has_reading ? ' · 完整解读 已生成' : ''}
        </span>
      </div>
      <div className="hepan-row-actions">
        <button type="button" className="btn-primary hepan-row-ask" onClick={onAsk}>追问</button>
        {onView ? (
          <button type="button" className="user-center-link" onClick={onView}>查看</button>
        ) : (
          <Link className="user-center-link" to={`/hepan/${item.slug}`}>查看</Link>
        )}
        <button type="button" className="user-center-link" onClick={onCopy}>复制</button>
        <button
          type="button"
          className="user-center-link hepan-row-delete"
          onClick={onDelete} disabled={busy}
        >{busy ? '删除中…' : '删除'}</button>
      </div>
    </li>
  );
}
