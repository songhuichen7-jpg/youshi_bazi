import { useEffect, useMemo, useState } from 'react';
import {
  fetchAdminOperations,
  fetchAdminOverview,
  listAdminEvents,
  listAdminVisitors,
} from '../../lib/adminApi.js';

const TOKEN_KEY = 'youshi_admin_token';
const RANGE_OPTIONS = [
  { value: '24h', label: '24 小时' },
  { value: '7d', label: '7 天' },
  { value: '30d', label: '30 天' },
  { value: 'all', label: '全部' },
];
const CHART_COLORS = {
  teal: '#3f6f78',
  blue: '#5c6f99',
  gold: '#c38a3a',
  rose: '#b75d5a',
  violet: '#7b6aa8',
  moss: '#6f7f57',
  ink: '#1f2726',
};

const EVENT_LABELS = {
  page_view: '页面访问',
  page_performance: '访问性能',
  form_start: '开始填写',
  form_submit: '提交表单',
  form_error: '表单错误',
  chart_create_success: '命盘成功',
  chart_create_failed: '命盘失败',
  result_view: '查看结果',
  card_view: '卡片访问',
  card_save: '保存卡片',
  card_share: '分享卡片',
  hepan_invite_create: '发起合盘',
  hepan_view: '打开合盘',
  hepan_complete: '完成合盘',
  hepan_card_save: '保存合盘',
  report_view: '查看报告',
  report_generate_success: '报告成功',
  report_generate_failed: '报告失败',
  chat_start: '开始对话',
  chat_send: '发送消息',
  chat_done: '对话完成',
  chat_error: '对话错误',
  paywall_view: '付费墙',
  upgrade_click: '升级点击',
};

function readToken() {
  try { return localStorage.getItem(TOKEN_KEY) || ''; } catch { return ''; }
}

function writeToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch { /* storage may be unavailable */ }
}

function rangeWindow(range) {
  if (range === 'all') return {};
  const now = new Date();
  const hours = range === '24h' ? 24 : (range === '30d' ? 24 * 30 : 24 * 7);
  return { from: new Date(now.getTime() - hours * 3600 * 1000).toISOString(), to: now.toISOString() };
}

function fmtNumber(value) {
  return new Intl.NumberFormat('zh-CN').format(Number(value || 0));
}

function fmtCompact(value) {
  return new Intl.NumberFormat('zh-CN', {
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(Number(value || 0));
}

function fmtRate(value) {
  return `${Math.round(Number(value || 0) * 1000) / 10}%`;
}

function fmtDuration(value) {
  const ms = Number(value || 0);
  if (ms >= 1000) return `${Math.round(ms / 100) / 10}s`;
  return `${Math.round(ms)}ms`;
}

function fmtDataSize(kb) {
  const value = Number(kb || 0);
  if (value >= 1024) return `${Math.round(value / 102.4) / 10} MB`;
  return `${Math.round(value)} KB`;
}

function fmtTime(value) {
  if (!value) return '-';
  try {
    return new Intl.DateTimeFormat('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    }).format(new Date(value));
  } catch {
    return '-';
  }
}

function labelEvent(event) {
  return EVENT_LABELS[event] || event;
}

function Kpi({ label, value, hint }) {
  return (
    <div className="admin-kpi">
      <span>{label}</span>
      <strong>{value}</strong>
      {hint ? <small>{hint}</small> : null}
    </div>
  );
}

function RateRow({ label, value }) {
  const pct = Math.max(0, Math.min(100, Number(value || 0) * 100));
  return (
    <div className="admin-rate-row">
      <div className="admin-rate-label">
        <span>{label}</span>
        <strong>{fmtRate(value)}</strong>
      </div>
      <div className="admin-rate-track">
        <span style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function EventPill({ event }) {
  return <span className={`admin-event-pill admin-event-${String(event || '').replaceAll('_', '-')}`}>{labelEvent(event)}</span>;
}

function EmptyState({ children }) {
  return <div className="admin-empty">{children}</div>;
}

function tokenShare(row) {
  const prompt = Number(row?.prompt_tokens || 0);
  const completion = Number(row?.completion_tokens || 0);
  const total = prompt + completion;
  return {
    promptPct: total ? prompt / total * 100 : 0,
    completionPct: total ? completion / total * 100 : 0,
  };
}

function TokenTrendChart({ items }) {
  if (!items?.length) return <EmptyState>暂无 token 记录</EmptyState>;
  const max = Math.max(...items.map(item => Number(item.tokens || 0)), 1);
  const points = items.map((item, index) => {
    const x = items.length === 1 ? 50 : index / (items.length - 1) * 100;
    const y = 92 - Number(item.tokens || 0) / max * 76;
    return `${x},${y}`;
  }).join(' ');
  return (
    <div className="admin-trend-chart">
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-label="Token 消耗趋势">
        <polyline points={points} />
      </svg>
      <div className="admin-trend-bars">
        {items.map((item, index) => (
          <div className="admin-trend-day" key={item.bucket || index}>
            <span style={{ height: `${Math.max(6, Number(item.tokens || 0) / max * 100)}%` }} />
            <small>{String(item.bucket || '').slice(5) || '-'}</small>
          </div>
        ))}
      </div>
    </div>
  );
}

function PerformanceTrendChart({ items }) {
  if (!items?.length) return <EmptyState>暂无访问性能</EmptyState>;
  const max = Math.max(...items.map(item => Number(item.p95_load_ms || item.avg_load_ms || 0)), 1);
  return (
    <div className="admin-performance-trend">
      {items.map((item, index) => {
        const p95 = Number(item.p95_load_ms || 0);
        const avg = Number(item.avg_load_ms || 0);
        return (
          <div className="admin-performance-day" key={item.bucket || index}>
            <div>
              <i style={{ height: `${Math.max(5, p95 / max * 100)}%` }} />
              <span style={{ height: `${Math.max(5, avg / max * 100)}%` }} />
            </div>
            <strong>{fmtDuration(p95 || avg)}</strong>
            <small>{String(item.bucket || '').slice(5) || '-'}</small>
          </div>
        );
      })}
    </div>
  );
}

function RoutePerformanceList({ items }) {
  if (!items?.length) return <EmptyState>暂无慢页面记录</EmptyState>;
  const max = Math.max(...items.map(item => Number(item.p95_load_ms || 0)), 1);
  return (
    <div className="admin-route-performance">
      {items.map(item => (
        <div className="admin-route-row" key={item.route}>
          <div>
            <strong>{item.route}</strong>
            <span>{fmtNumber(item.samples)} 次 · TTFB {fmtDuration(item.avg_ttfb_ms)} · {fmtDataSize(item.total_transfer_kb)}</span>
          </div>
          <div className="admin-route-bar">
            <span style={{ width: `${Math.max(4, Number(item.p95_load_ms || 0) / max * 100)}%` }} />
          </div>
          <strong>{fmtDuration(item.p95_load_ms)}</strong>
        </div>
      ))}
    </div>
  );
}

function CostBreakdown({ items }) {
  if (!items?.length) return <EmptyState>暂无功能成本</EmptyState>;
  const max = Math.max(...items.map(item => Number(item.tokens || 0)), 1);
  return (
    <div className="admin-cost-list">
      {items.map(item => {
        const share = tokenShare(item);
        return (
          <div className="admin-cost-row" key={item.endpoint}>
            <div>
              <strong>{item.endpoint || 'unknown'}</strong>
              <span>{fmtNumber(item.calls)} 次 · 均值 {fmtCompact(item.avg_tokens)} token · {fmtDuration(item.avg_duration_ms)}</span>
            </div>
            <div className="admin-cost-bar" aria-label={`${item.endpoint} token`}>
              <i style={{ width: `${Number(item.tokens || 0) / max * 100}%` }}>
                <b style={{ width: `${share.promptPct}%` }} />
                <em style={{ width: `${share.completionPct}%` }} />
              </i>
            </div>
            <strong>{fmtCompact(item.tokens)}</strong>
          </div>
        );
      })}
    </div>
  );
}

function FunnelChart({ items }) {
  if (!items?.length) return <EmptyState>暂无漏斗数据</EmptyState>;
  const max = Math.max(...items.map(item => Number(item.count || 0)), 1);
  return (
    <div className="admin-funnel-chart">
      {items.map(item => (
        <div className="admin-funnel-row" key={item.key}>
          <div className="admin-funnel-label">
            <span>{item.label}</span>
            <strong>{fmtNumber(item.count)}</strong>
          </div>
          <div className="admin-funnel-track">
            <span style={{ width: `${Math.max(4, Number(item.count || 0) / max * 100)}%` }} />
          </div>
          <small>总转化 {fmtRate(item.rate)} · 上步 {fmtRate(item.step_rate)}</small>
        </div>
      ))}
    </div>
  );
}

function ModelDonut({ items }) {
  if (!items?.length) return <EmptyState>暂无模型数据</EmptyState>;
  const palette = [
    CHART_COLORS.teal,
    CHART_COLORS.gold,
    CHART_COLORS.blue,
    CHART_COLORS.rose,
    CHART_COLORS.moss,
    CHART_COLORS.violet,
  ];
  const total = items.reduce((sum, item) => sum + Number(item.tokens || 0), 0) || 1;
  const gradient = items.reduce((acc, item, index) => {
    const start = acc.cursor;
    const end = start + Number(item.tokens || 0) / total * 100;
    const color = palette[index % palette.length];
    return {
      cursor: end,
      stops: [...acc.stops, `${color} ${start}% ${end}%`],
    };
  }, { cursor: 0, stops: [] }).stops.join(', ');
  return (
    <div className="admin-model-donut-wrap">
      <div className="admin-model-donut" style={{ background: `conic-gradient(${gradient})` }}>
        <span>{fmtCompact(total)}</span>
      </div>
      <div className="admin-model-legend">
        {items.map((item, index) => (
          <div key={item.model}>
            <i style={{ background: palette[index % palette.length] }} />
            <span>{item.model}</span>
            <strong>{fmtCompact(item.tokens)}</strong>
          </div>
        ))}
      </div>
    </div>
  );
}

function TopUsersTable({ items }) {
  if (!items?.length) return <EmptyState>暂无高消耗用户</EmptyState>;
  return (
    <div className="admin-table-wrap">
      <table className="admin-table admin-compact-table">
        <thead>
          <tr>
            <th>用户</th>
            <th>Token</th>
            <th>调用</th>
            <th>均值</th>
            <th>错误</th>
          </tr>
        </thead>
        <tbody>
          {items.map(item => (
            <tr key={item.user_id}>
              <td className="admin-mono">{item.user_id}</td>
              <td>{fmtNumber(item.tokens)}</td>
              <td>{fmtNumber(item.calls)}</td>
              <td>{fmtCompact(item.avg_tokens)}</td>
              <td>{fmtNumber(item.error_count)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function AdminDashboard() {
  const [token, setToken] = useState(readToken);
  const [draftToken, setDraftToken] = useState(token);
  const [range, setRange] = useState('7d');
  const [tab, setTab] = useState('overview');
  const [overview, setOverview] = useState(null);
  const [operations, setOperations] = useState(null);
  const [visitors, setVisitors] = useState([]);
  const [events, setEvents] = useState([]);
  const [eventFilter, setEventFilter] = useState('');
  const [anonymousFilter, setAnonymousFilter] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [loadedAt, setLoadedAt] = useState(null);

  const windowParams = useMemo(() => rangeWindow(range), [range]);

  async function load({ anonymousId = anonymousFilter.trim(), eventName = eventFilter } = {}) {
    if (!token) return;
    setLoading(true);
    setError('');
    try {
      const [overviewData, operationsData, visitorData, eventData] = await Promise.all([
        fetchAdminOverview({ token, ...windowParams }),
        fetchAdminOperations({ token, ...windowParams }),
        listAdminVisitors({ token, anonymousId, ...windowParams, limit: 100 }),
        listAdminEvents({
          token,
          event: eventName,
          anonymousId,
          ...windowParams,
          limit: 100,
        }),
      ]);
      setOverview(overviewData);
      setOperations(operationsData);
      setVisitors(visitorData.items || []);
      setEvents(eventData.items || []);
      setLoadedAt(new Date());
    } catch (e) {
      setError(e.status === 401 ? '管理员口令无效' : (e.message || '后台数据加载失败'));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, [token, range]); // eslint-disable-line react-hooks/exhaustive-deps

  function submitToken(e) {
    e.preventDefault();
    const next = draftToken.trim();
    writeToken(next);
    setToken(next);
  }

  const counts = overview?.counts || {};
  const totals = overview?.totals || {};
  const rates = overview?.rates || {};
  const tokenStats = operations?.tokens || {};
  const topEvents = Object.entries(counts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 12);

  if (!token) {
    return (
      <main className="admin-auth-screen">
        <form className="admin-auth-box" onSubmit={submitToken}>
          <p className="admin-kicker">有时内测</p>
          <h1>数据后台</h1>
          <label htmlFor="admin-token">管理员口令</label>
          <input
            id="admin-token"
            type="password"
            value={draftToken}
            onChange={e => setDraftToken(e.target.value)}
            autoFocus
          />
          <button type="submit" className="admin-primary-button">进入后台</button>
        </form>
      </main>
    );
  }

  return (
    <main className="admin-shell">
      <header className="admin-topbar">
        <div>
          <p className="admin-kicker">有时内测</p>
          <h1>数据后台</h1>
        </div>
        <div className="admin-actions">
          <select value={range} onChange={e => setRange(e.target.value)} aria-label="时间范围">
            {RANGE_OPTIONS.map(option => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
          <button type="button" className="admin-secondary-button" onClick={() => void load()} disabled={loading}>
            {loading ? '刷新中' : '刷新'}
          </button>
          <button
            type="button"
            className="admin-secondary-button"
            onClick={() => {
              writeToken('');
              setToken('');
              setDraftToken('');
            }}
          >
            锁定
          </button>
        </div>
      </header>

      <nav className="admin-tabs" aria-label="后台视图">
        <button type="button" className={tab === 'overview' ? 'active' : ''} onClick={() => setTab('overview')}>概览</button>
        <button type="button" className={tab === 'visitors' ? 'active' : ''} onClick={() => setTab('visitors')}>匿名访客</button>
        <button type="button" className={tab === 'events' ? 'active' : ''} onClick={() => setTab('events')}>事件流</button>
      </nav>

      {error ? <div className="admin-error" role="alert">{error}</div> : null}

      <section className="admin-toolbar">
        <label>
          匿名 ID
          <input
            type="search"
            value={anonymousFilter}
            onChange={e => setAnonymousFilter(e.target.value)}
            placeholder="anonymous_id"
          />
        </label>
        <label>
          事件
          <select value={eventFilter} onChange={e => setEventFilter(e.target.value)}>
            <option value="">全部事件</option>
            {Object.keys(EVENT_LABELS).map(event => (
              <option key={event} value={event}>{labelEvent(event)}</option>
            ))}
          </select>
        </label>
        <button type="button" className="admin-primary-button" onClick={() => void load()} disabled={loading}>应用筛选</button>
        <span>{loadedAt ? `更新于 ${fmtTime(loadedAt.toISOString())}` : ''}</span>
      </section>

      {tab === 'overview' ? (
        <>
          <section className="admin-kpi-grid admin-ops-kpis" aria-label="运营指标">
            <Kpi
              label="Token 总消耗"
              value={fmtCompact(tokenStats.total)}
              hint={`Prompt ${fmtCompact(tokenStats.prompt)} / Completion ${fmtCompact(tokenStats.completion)}`}
            />
            <Kpi label="平均每次调用" value={fmtCompact(tokenStats.avg_per_call)} hint={`${fmtNumber(tokenStats.calls)} 次 LLM 调用`} />
            <Kpi label="平均每活跃用户" value={fmtCompact(tokenStats.avg_per_active_user)} hint={`${fmtNumber(tokenStats.active_users)} 个消耗用户`} />
            <Kpi label="P95 响应" value={fmtDuration(tokenStats.p95_duration_ms)} hint={`错误率 ${fmtRate(tokenStats.error_rate)}`} />
          </section>

          <section className="admin-kpi-grid admin-ops-kpis" aria-label="访问性能指标">
            <Kpi label="页面加载 P95" value={fmtDuration(operations?.performance?.p95_load_ms)} hint={`${fmtNumber(operations?.performance?.samples)} 个样本`} />
            <Kpi label="平均 TTFB" value={fmtDuration(operations?.performance?.avg_ttfb_ms)} hint="浏览器实测首字节" />
            <Kpi label="传输总量" value={fmtDataSize(operations?.performance?.total_transfer_kb)} hint={`均值 ${fmtDataSize(operations?.performance?.avg_transfer_kb)}`} />
            <Kpi label="平均资源数" value={fmtNumber(Math.round(Number(operations?.performance?.avg_resource_count || 0)))} hint="JS/CSS/图片等资源" />
          </section>

          <section className="admin-grid-two admin-ops-grid">
            <div className="admin-panel admin-chart-panel">
              <h2>Token 消耗趋势</h2>
              <TokenTrendChart items={operations?.series || []} />
            </div>
            <div className="admin-panel admin-chart-panel">
              <h2>功能成本排行</h2>
              <CostBreakdown items={operations?.endpoint_breakdown || []} />
            </div>
          </section>

          <section className="admin-grid-two">
            <div className="admin-panel admin-chart-panel">
              <h2>用户转化漏斗</h2>
              <FunnelChart items={operations?.funnel || []} />
            </div>
            <div className="admin-panel admin-chart-panel">
              <h2>模型占比</h2>
              <ModelDonut items={operations?.model_breakdown || []} />
            </div>
          </section>

          <section className="admin-grid-two">
            <div className="admin-panel admin-chart-panel">
              <h2>访问性能</h2>
              <PerformanceTrendChart items={operations?.performance_series || []} />
            </div>
            <div className="admin-panel admin-chart-panel">
              <h2>慢页面排行</h2>
              <RoutePerformanceList items={operations?.route_performance || []} />
            </div>
          </section>

          <section className="admin-panel">
            <h2>高消耗用户</h2>
            <TopUsersTable items={operations?.top_users || []} />
          </section>

          <section className="admin-kpi-grid" aria-label="核心指标">
            <Kpi label="匿名访客" value={fmtNumber(totals.anonymous_visitors)} hint="按 anonymous_id 去重" />
            <Kpi label="会话" value={fmtNumber(totals.sessions)} hint="按 session_id 去重" />
            <Kpi label="事件" value={fmtNumber(totals.events)} hint="当前时间范围" />
            <Kpi label="命盘成功" value={fmtNumber(counts.chart_create_success)} hint={`转化 ${fmtRate(rates.visit_to_chart)}`} />
            <Kpi label="分享卡片" value={fmtNumber(counts.card_share)} hint={`生成后 ${fmtRate(rates.chart_to_share)}`} />
            <Kpi label="合盘完成" value={fmtNumber(counts.hepan_complete)} hint={`完成率 ${fmtRate(rates.hepan_completion)}`} />
            <Kpi label="对话消息" value={fmtNumber(counts.chat_send)} hint={`错误率 ${fmtRate(rates.chat_error)}`} />
            <Kpi label="错误" value={fmtNumber((counts.chat_error || 0) + (counts.chart_create_failed || 0) + (counts.report_generate_failed || 0))} hint="关键失败事件" />
          </section>

          <section className="admin-grid-two">
            <div className="admin-panel">
              <h2>漏斗</h2>
              <RateRow label="访问 → 开始填写" value={rates.visit_to_form_start} />
              <RateRow label="访问 → 提交表单" value={rates.visit_to_form_submit} />
              <RateRow label="访问 → 命盘成功" value={rates.visit_to_chart} />
              <RateRow label="命盘成功 → 分享" value={rates.chart_to_share} />
              <RateRow label="合盘打开 → 完成" value={rates.hepan_completion} />
            </div>
            <div className="admin-panel">
              <h2>事件构成</h2>
              {topEvents.length ? (
                <div className="admin-event-bars">
                  {topEvents.map(([event, count]) => {
                    const max = Math.max(...topEvents.map(([, n]) => n), 1);
                    return (
                      <div className="admin-event-bar" key={event}>
                        <span>{labelEvent(event)}</span>
                        <div><i style={{ width: `${Math.max(4, count / max * 100)}%` }} /></div>
                        <strong>{fmtNumber(count)}</strong>
                      </div>
                    );
                  })}
                </div>
              ) : <EmptyState>暂无事件</EmptyState>}
            </div>
          </section>

          <section className="admin-panel">
            <h2>最近事件</h2>
            <EventTable items={overview?.recent_events || []} />
          </section>
        </>
      ) : null}

      {tab === 'visitors' ? (
        <section className="admin-panel">
          <h2>匿名访客</h2>
          <VisitorTable items={visitors} onPick={(id) => {
            setAnonymousFilter(id);
            setTab('events');
            void load({ anonymousId: id });
          }} />
        </section>
      ) : null}

      {tab === 'events' ? (
        <section className="admin-panel">
          <h2>事件流</h2>
          <EventTable items={events} />
        </section>
      ) : null}
    </main>
  );
}

function VisitorTable({ items, onPick }) {
  if (!items.length) return <EmptyState>暂无匿名访客</EmptyState>;
  return (
    <div className="admin-table-wrap">
      <table className="admin-table">
        <thead>
          <tr>
            <th>匿名 ID</th>
            <th>事件</th>
            <th>会话</th>
            <th>命盘</th>
            <th>分享</th>
            <th>合盘</th>
            <th>对话</th>
            <th>错误</th>
            <th>最后活跃</th>
          </tr>
        </thead>
        <tbody>
          {items.map(item => (
            <tr key={item.anonymous_id}>
              <td>
                <button type="button" className="admin-link-button" onClick={() => onPick?.(item.anonymous_id)}>
                  {item.anonymous_id}
                </button>
              </td>
              <td>{fmtNumber(item.event_count)}</td>
              <td>{fmtNumber(item.session_count)}</td>
              <td>{fmtNumber(item.chart_count)}</td>
              <td>{fmtNumber(item.share_count)}</td>
              <td>{fmtNumber(item.hepan_count)}</td>
              <td>{fmtNumber(item.chat_count)}</td>
              <td>{fmtNumber(item.error_count)}</td>
              <td>{fmtTime(item.last_seen_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function EventTable({ items }) {
  if (!items.length) return <EmptyState>暂无事件</EmptyState>;
  return (
    <div className="admin-table-wrap">
      <table className="admin-table">
        <thead>
          <tr>
            <th>时间</th>
            <th>事件</th>
            <th>匿名 ID</th>
            <th>会话</th>
            <th>来源</th>
            <th>详情</th>
          </tr>
        </thead>
        <tbody>
          {items.map(item => (
            <tr key={item.id}>
              <td>{fmtTime(item.created_at)}</td>
              <td><EventPill event={item.event} /></td>
              <td className="admin-mono">{item.anonymous_id || '-'}</td>
              <td className="admin-mono">{item.session_id || '-'}</td>
              <td>{item.from || item.channel || item.extra?.route || '-'}</td>
              <td className="admin-extra">{JSON.stringify(item.extra || {})}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
