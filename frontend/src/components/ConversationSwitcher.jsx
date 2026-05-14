import { useEffect, useRef, useState } from 'react';
import { useAppStore } from '../store/useAppStore';
import { getConversationDisplayLabel } from '../lib/conversationDisplay.js';

const PENDING_DELETE_TIMEOUT_MS = 4000;

export default function ConversationSwitcher({ disabled }) {
  const conversations = useAppStore(s => s.conversations) || [];
  const currentId = useAppStore(s => s.currentConversationId);
  const currentChartId = useAppStore(s => s.currentId);
  const newConversationOnServer = useAppStore(s => s.newConversationOnServer);
  const selectConversation = useAppStore(s => s.selectConversation);
  const deleteConversationOnServer = useAppStore(s => s.deleteConversationOnServer);
  const renameConversationOnServer = useAppStore(s => s.renameConversationOnServer);

  const [open, setOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [editingLabel, setEditingLabel] = useState('');
  // 正在等待二次确认删除的 conv id（同时只能有一个）。3 秒不点会自动取消。
  const [pendingDeleteId, setPendingDeleteId] = useState(null);
  const pendingTimerRef = useRef(null);
  const rootRef = useRef(null);

  function clearPendingDelete() {
    if (pendingTimerRef.current) clearTimeout(pendingTimerRef.current);
    pendingTimerRef.current = null;
    setPendingDeleteId(null);
  }
  useEffect(() => () => clearPendingDelete(), []);

  const current = conversations.find(c => c.id === currentId);
  const currentLabel = current ? getConversationDisplayLabel(current) : '默认对话';

  useEffect(() => {
    if (!open) return;
    function onDocClick(e) {
      if (rootRef.current && !rootRef.current.contains(e.target)) {
        setOpen(false);
        clearPendingDelete();
      }
    }
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, [open]);

  async function onNew(e) {
    e?.stopPropagation?.();
    if (!currentChartId) return;
    const count = conversations.length;
    setOpen(false);
    await newConversationOnServer(currentChartId, `对话 ${count + 1}`);
  }

  async function onSwitch(id) {
    if (id === currentId) { setOpen(false); return; }
    await selectConversation(id);
    setOpen(false);
  }

  function askDelete(e, id) {
    e.stopPropagation();
    if (!currentChartId) return;
    // 第一次点 → 进入"待确认"态；4 秒不再点击就自动取消，避免误触挂单。
    if (pendingTimerRef.current) clearTimeout(pendingTimerRef.current);
    setPendingDeleteId(id);
    pendingTimerRef.current = setTimeout(
      () => clearPendingDelete(),
      PENDING_DELETE_TIMEOUT_MS,
    );
  }

  async function confirmDelete(e, id) {
    e.stopPropagation();
    if (!currentChartId) return;
    clearPendingDelete();
    await deleteConversationOnServer(currentChartId, id);
  }

  function cancelDelete(e) {
    e.stopPropagation();
    clearPendingDelete();
  }

  function startRename(e, conv) {
    e.stopPropagation();
    setEditingId(conv.id);
    setEditingLabel(conv.label || '');
  }

  async function commitRename() {
    if (editingId && editingLabel.trim()) {
      await renameConversationOnServer(editingId, editingLabel.trim());
    }
    setEditingId(null);
    setEditingLabel('');
  }

  return (
    <div className="conv-switcher" ref={rootRef}>
      <button
        className="conv-trigger"
        onClick={() => setOpen(v => !v)}
        disabled={disabled}
        title="切换对话"
      >
        <span className="conv-trigger-label">{currentLabel}</span>
        <span className="conv-trigger-caret">▾</span>
      </button>
      {open && (
        <div className="conv-dropdown">
          <button className="conv-new" onClick={onNew} disabled={disabled}>
            + 新建对话
          </button>
          <div className="conv-list">
            {conversations.slice().reverse().map(c => {
              const isActive = c.id === currentId;
              const isEditing = editingId === c.id;
              const isPending = pendingDeleteId === c.id;
              const isLast = conversations.length <= 1;
              const preview = '';   // server items don't ship preview; out of scope for Plan 6
              return (
                <div
                  key={c.id}
                  className={
                    'conv-item'
                    + (isActive ? ' active' : '')
                    + (isPending ? ' conv-item-pending' : '')
                  }
                  onClick={() => !isEditing && !isPending && onSwitch(c.id)}
                >
                  {isPending ? (
                    <div className="conv-confirm-strip" onClick={(e) => e.stopPropagation()}>
                      <span className="conv-confirm-text">
                        {isLast ? '删除最后一个对话？会自动开一个新的。' : '删除这个对话？30 天内可恢复。'}
                      </span>
                      <button
                        className="conv-confirm-btn conv-confirm-yes"
                        onClick={(e) => confirmDelete(e, c.id)}
                        aria-label="确认删除"
                      >删除</button>
                      <button
                        className="conv-confirm-btn"
                        onClick={cancelDelete}
                        aria-label="取消删除"
                      >取消</button>
                    </div>
                  ) : (
                    <>
                      <div className="conv-item-main">
                        {isEditing ? (
                          <input
                            className="conv-rename-input"
                            autoFocus
                            value={editingLabel}
                            onChange={e => setEditingLabel(e.target.value)}
                            onKeyDown={e => {
                              if (e.key === 'Enter') commitRename();
                              else if (e.key === 'Escape') { setEditingId(null); setEditingLabel(''); }
                            }}
                            onBlur={commitRename}
                            onClick={e => e.stopPropagation()}
                          />
                        ) : (
                          <div className="conv-item-label">{getConversationDisplayLabel(c)}</div>
                        )}
                        <div className="conv-item-preview">{String(preview).slice(0, 30)}</div>
                      </div>
                      <div className="conv-item-actions" onClick={e => e.stopPropagation()}>
                        <button className="conv-icon" title="重命名" aria-label="重命名对话" onClick={(e) => startRename(e, c)}>✎</button>
                        <button className="conv-icon conv-icon-danger" title="删除" aria-label="删除对话" onClick={(e) => askDelete(e, c.id)}>×</button>
                      </div>
                    </>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
