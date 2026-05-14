import { useState, useRef, useEffect } from 'react';
import { useAppStore } from '../store/useAppStore';
import { clearSession } from '../lib/persistence';
import { MAX_CHARTS } from '../lib/constants';

export default function ChartSwitcher({ onNewChart }) {
  const charts = useAppStore(s => s.charts);
  const currentId = useAppStore(s => s.currentId);
  const switchChart = useAppStore(s => s.switchChart);
  const deleteChart = useAppStore(s => s.deleteChart);
  const renameChart = useAppStore(s => s.renameChart);
  const setAppNotice = useAppStore(s => s.setAppNotice);

  const [open, setOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [editVal, setEditVal] = useState('');
  const [pendingDeleteId, setPendingDeleteId] = useState(null);
  const pendingTimerRef = useRef(null);
  const ref = useRef(null);

  function clearPendingDelete() {
    if (pendingTimerRef.current) clearTimeout(pendingTimerRef.current);
    pendingTimerRef.current = null;
    setPendingDeleteId(null);
  }
  useEffect(() => () => clearPendingDelete(), []);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e) => {
      if (ref.current && !ref.current.contains(e.target)) {
        setOpen(false);
        clearPendingDelete();
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  const current = charts[currentId];
  const sortedIds = Object.keys(charts).sort((a, b) => (charts[b].createdAt||0) - (charts[a].createdAt||0));
  const atLimit = sortedIds.length >= MAX_CHARTS;

  function startRename(id) {
    setEditingId(id);
    setEditVal(charts[id]?.label || '');
  }
  function commitRename(id) {
    if (editVal.trim()) renameChart(id, editVal.trim());
    setEditingId(null);
  }

  function askDelete(id, e) {
    e.stopPropagation();
    if (pendingTimerRef.current) clearTimeout(pendingTimerRef.current);
    setPendingDeleteId(id);
    pendingTimerRef.current = setTimeout(() => clearPendingDelete(), 4000);
  }

  function confirmDeleteChart(id, e) {
    e.stopPropagation();
    clearPendingDelete();
    if (Object.keys(charts).length === 1) clearSession({ onError: setAppNotice });
    deleteChart(id);
    setOpen(false);
  }

  function cancelDeleteChart(e) {
    e.stopPropagation();
    clearPendingDelete();
  }

  return (
    <div ref={ref} style={{ position:'relative', display:'inline-block' }}>
      <button
        className="chart-switcher-btn"
        onClick={() => setOpen(v => !v)}
        style={{ display:'flex', alignItems:'center', gap:4, fontSize:12, cursor:'pointer',
                 background:'none', border:'1px solid var(--line)', padding:'4px 10px',
                 minHeight:44, color:'var(--ink)' }}
      >
        <span style={{ maxWidth:120, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
          {current?.label || '—'}
        </span>
        <span style={{ opacity:.5 }}>{open ? '▾' : '▸'}</span>
      </button>

      {open && (
        <div style={{
          position:'absolute', top:'100%', right:0, zIndex:100,
          background:'#fff', border:'1px solid var(--line)', minWidth:220,
          maxHeight:'60vh', overflowY:'auto',
          boxShadow:'0 4px 16px rgba(0,0,0,.1)',
        }}>
          {/* + 新建 */}
          <div
            onClick={() => {
              if (atLimit) {
                setAppNotice({
                  title: `最多先留 ${MAX_CHARTS} 份命盘`,
                  detail: '请先删除一份，再新建新的命盘。',
                  retryable: false,
                });
                return;
              }
              setOpen(false);
              onNewChart?.();
            }}
            style={{
              padding:'12px 16px', borderBottom:'1px solid var(--line)',
              cursor:'pointer', fontSize:13, color: atLimit ? '#999' : 'var(--ink)',
              display:'flex', alignItems:'center', gap:8, minHeight:44,
            }}
          >
            <span>＋ 新建命盘</span>
            {atLimit && <span style={{ fontSize:11, color:'#c66' }}>（已达上限 {MAX_CHARTS}）</span>}
          </div>

          {sortedIds.map(id => {
            const c = charts[id];
            const isCur = id === currentId;
            const isPending = pendingDeleteId === id;
            return (
              <div
                key={id}
                onClick={() => {
                  if (editingId !== id && !isPending) { switchChart(id); setOpen(false); }
                }}
                className={isPending ? 'chart-item-pending' : ''}
                style={{
                  padding:'10px 14px', cursor: isPending ? 'default' : 'pointer', minHeight:44,
                  background: isPending ? '#fdf3f1' : (isCur ? '#f7f5f0' : '#fff'),
                  borderLeft: isPending ? '2px solid #c0653a' : (isCur ? '2px solid var(--ink)' : '2px solid transparent'),
                  borderBottom:'1px solid var(--line)',
                  display:'flex', alignItems:'center', gap:8,
                  position:'relative', overflow:'hidden',
                }}
              >
                {isPending ? (
                  <div onClick={e => e.stopPropagation()}
                       style={{ display:'flex', alignItems:'center', gap:8, width:'100%' }}>
                    <span style={{ flex:1, fontSize:12, color:'#6b3a26', lineHeight:1.4 }}>
                      删除"{c.label}"？此命盘和它的所有对话都会被清空。
                    </span>
                    <button
                      type="button"
                      onClick={e => confirmDeleteChart(id, e)}
                      style={{
                        border:'1px solid #c0653a', background:'#c0653a', color:'#fff',
                        fontSize:11, padding:'3px 10px', borderRadius:2, cursor:'pointer',
                      }}
                    >删除</button>
                    <button
                      type="button"
                      onClick={cancelDeleteChart}
                      style={{
                        border:'1px solid #d4a48d', background:'transparent', color:'#6b3a26',
                        fontSize:11, padding:'3px 10px', borderRadius:2, cursor:'pointer',
                      }}
                    >取消</button>
                  </div>
                ) : editingId === id ? (
                  <input
                    autoFocus
                    value={editVal}
                    onChange={e => setEditVal(e.target.value)}
                    onBlur={() => commitRename(id)}
                    onKeyDown={e => {
                      if (e.key === 'Enter') commitRename(id);
                      if (e.key === 'Escape') setEditingId(null);
                    }}
                    onClick={e => e.stopPropagation()}
                    style={{ flex:1, border:'1px solid var(--line)', padding:'2px 6px', fontSize:13 }}
                  />
                ) : (
                  <>
                    <div style={{ flex:1, overflow:'hidden' }}>
                      <div style={{ fontSize:13, fontWeight: isCur ? 600 : 400,
                                    overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
                        {isCur && <span style={{ marginRight:5 }}>●</span>}{c.label}
                      </div>
                      <div style={{ fontSize:10, color:'var(--mute)', marginTop:2 }}>
                        {c.createdAt ? new Date(c.createdAt).toLocaleDateString('zh-CN') : ''}
                      </div>
                    </div>
                    <button
                      type="button"
                      onDoubleClick={e => { e.stopPropagation(); startRename(id); }}
                      onClick={e => { e.stopPropagation(); startRename(id); }}
                      title="双击重命名"
                      aria-label="重命名命盘"
                      style={{ background:'none', border:'none', cursor:'pointer', fontSize:13, opacity:.4, padding:'2px 4px', minHeight:28 }}
                    >✎</button>
                    <button
                      type="button"
                      onClick={e => askDelete(id, e)}
                      aria-label="删除命盘"
                      style={{ background:'none', border:'none', cursor:'pointer', fontSize:13, opacity:.4, padding:'2px 4px', color:'#c66', minHeight:28 }}
                    >×</button>
                  </>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
