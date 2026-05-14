import { useRef, useState, useCallback, useEffect } from 'react';
const RESET_CONFIRM_TIMEOUT_MS = 4000;
import { useAppStore } from '../store/useAppStore';
import Chart from './Chart';
import Force from './Force';
import { BirthHeader, MetaGrid } from './Meta';
import KLineChart from './kline/KLineChart';
import Chat from './Chat';
import { clearSession } from '../lib/persistence';
import ChartSwitcher from './ChartSwitcher';
import { buildChartVisibility } from '../lib/chartVisibility';
import ClassicsPanel from './ClassicsPanel';
import { CardWorkspace } from './card/CardWorkspace';
import { BrandLogo } from './brand/BrandLogo.jsx';

const MIN_RIGHT = 320;
const MAX_RIGHT = 900;
// 默认占比加大 — 用户主要在右侧聊天，左边命盘是参考、不是主舞台
const DEFAULT_RIGHT = 720;

export default function Shell() {
  const view = useAppStore(s => s.view);
  const setView = useAppStore(s => s.setView);
  const meta = useAppStore(s => s.meta);
  const force = useAppStore(s => s.force);
  const guards = useAppStore(s => s.guards);
  const reset = useAppStore(s => s.reset);
  const setAppNotice = useAppStore(s => s.setAppNotice);
  const startNewChart = useAppStore(s => s.startNewChart);
  const visibility = buildChartVisibility({ meta, force, guards });

  const [rightWidth, setRightWidth] = useState(DEFAULT_RIGHT);
  const [resetPending, setResetPending] = useState(false);
  const resetTimerRef = useRef(null);
  const dragging = useRef(false);
  const startX = useRef(0);
  const startWidth = useRef(DEFAULT_RIGHT);

  function clearResetPending() {
    if (resetTimerRef.current) clearTimeout(resetTimerRef.current);
    resetTimerRef.current = null;
    setResetPending(false);
  }
  useEffect(() => () => clearResetPending(), []);

  const onMouseDown = useCallback((e) => {
    dragging.current = true;
    startX.current = e.clientX;
    startWidth.current = rightWidth;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }, [rightWidth]);

  useEffect(() => {
    if (view !== 'chart' && view !== 'timing' && view !== 'card') {
      setView('chart');
    }
  }, [view, setView]);

  useEffect(() => {
    function onMouseMove(e) {
      if (!dragging.current) return;
      const delta = startX.current - e.clientX; // dragging left = wider right
      const next = Math.min(MAX_RIGHT, Math.max(MIN_RIGHT, startWidth.current + delta));
      setRightWidth(next);
    }
    function onMouseUp() {
      if (!dragging.current) return;
      dragging.current = false;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    }
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
    return () => {
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
    };
  }, []);

  // 这是把"全清空"做成"两段式"：第一次点 → 按钮变成"再点一次清空"
  // 倒计时 4 秒；4 秒内再点才真清空。比 confirm() 弹窗优雅，也保留
  // 对极端动作的二次确认。
  const onResetClick = () => {
    if (resetPending) {
      clearResetPending();
      clearSession({ onError: setAppNotice });
      reset();
      return;
    }
    setResetPending(true);
    resetTimerRef.current = setTimeout(() => clearResetPending(), RESET_CONFIRM_TIMEOUT_MS);
  };

  return (
    <div className="screen active">
      <div className="shell-layout" style={{ '--right-pane-width': `${rightWidth}px` }}>
        {/* LEFT PANE */}
        <div className="left-pane">
          <div className="left-topbar">
            <div className="left-topbar-inner">
              <BrandLogo size="small" className="shell-brand-logo" />
              <div className="view-switch">
                <button
                  type="button"
                  className={'view-item' + (view === 'chart' ? ' active' : '')}
                  aria-pressed={view === 'chart'}
                  onClick={() => setView('chart')}
                >命 盘</button>
                <button
                  type="button"
                  className={'view-item' + (view === 'timing' ? ' active' : '')}
                  aria-pressed={view === 'timing'}
                  onClick={() => setView('timing')}
                >流 年</button>
                <button
                  type="button"
                  className={'view-item' + (view === 'card' ? ' active' : '')}
                  aria-pressed={view === 'card'}
                  onClick={() => setView('card')}
                >卡 片</button>
              </div>
              <div style={{ display:'flex', gap:8, alignItems:'center' }}>
                <ChartSwitcher onNewChart={() => startNewChart()} />
                <button
                  className={'muted' + (resetPending ? ' shell-reset-pending' : '')}
                  style={{ fontSize: 11, ...(resetPending ? { color: '#c0653a' } : {}) }}
                  onClick={onResetClick}
                  title={resetPending ? '再点一次确认清空（4 秒内）' : '清空所有命盘'}
                  aria-label={resetPending ? '再点一次清空所有命盘和聊天记录' : '清空所有命盘和聊天记录'}
                >{resetPending ? '再点一次确认' : '×'}</button>
              </div>
            </div>
          </div>

          <div className="view" style={{ display: view === 'chart' ? 'block' : 'none' }}>
            <div className="left-content fade-in">
              <BirthHeader />
              <Chart />
              <MetaGrid />
              {visibility.showForce ? <div className="divider" /> : null}
              {visibility.showForce ? (
                <div>
                  <div className="section-num" style={{ marginBottom:18 }}>十神力量</div>
                  <Force />
                </div>
              ) : null}
              <div className="divider" />
              <ClassicsPanel />
              <div className="quote-mark">命 不 是 判 决 书 · 是 一 张 地 形 图</div>
            </div>
          </div>

          <div className="view" style={{ display: view === 'timing' ? 'block' : 'none' }}>
            <div className="left-content fade-in">
              <KLineChart />
            </div>
          </div>

          <div className="view" style={{ display: view === 'card' ? 'block' : 'none' }}>
            <div className="left-content card-content fade-in">
              <CardWorkspace />
            </div>
          </div>
        </div>

        {/* RESIZE HANDLE */}
        <div className="resize-handle" onMouseDown={onMouseDown} />

        <Chat />
      </div>
    </div>
  );
}
