import { getAnonymousId } from './anonymousId.js';

let _fetchImpl = (typeof fetch !== 'undefined') ? fetch : null;
export function __setTrackFetch(f) { _fetchImpl = f; }

function collectContext() {
  if (typeof window === 'undefined') return {};
  const ctx = {
    anonymous_id: getAnonymousId(),
    user_agent: navigator.userAgent,
    viewport: `${window.innerWidth}x${window.innerHeight}`,
  };
  try {
    let sid = sessionStorage.getItem('youshi_sid');
    if (!sid) {
      sid = `s_${Math.random().toString(36).slice(2, 14)}`;
      sessionStorage.setItem('youshi_sid', sid);
    }
    ctx.session_id = sid;
  } catch { /* sessionStorage may be unavailable */ }
  return ctx;
}

export async function track(event, properties = {}) {
  if (!_fetchImpl) return;
  try {
    await _fetchImpl('/api/track', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        event,
        properties: { ...collectContext(), ...properties },
      }),
    });
  } catch { /* silent */ }
}

export async function trackPageView({ page, route, search = '', from } = {}) {
  return track('page_view', {
    page: page || 'unknown',
    route: route || '/',
    search: search || undefined,
    from: from || undefined,
  });
}

function metricNumber(value) {
  const n = Number(value || 0);
  return Number.isFinite(n) && n >= 0 ? Math.round(n) : 0;
}

function collectPerformanceMetrics() {
  if (typeof window === 'undefined' || !window.performance) return null;
  const perf = window.performance;
  const nav = perf.getEntriesByType?.('navigation')?.[0];
  const resources = perf.getEntriesByType?.('resource') || [];
  if (!nav && !resources.length) return null;

  const transferSize = resources.reduce((sum, item) => sum + metricNumber(item.transferSize), metricNumber(nav?.transferSize));
  const encodedBodySize = resources.reduce((sum, item) => sum + metricNumber(item.encodedBodySize), metricNumber(nav?.encodedBodySize));
  const imageTransferSize = resources
    .filter((item) => ['img', 'image', 'css'].includes(item.initiatorType))
    .reduce((sum, item) => sum + metricNumber(item.transferSize), 0);

  return {
    load_ms: metricNumber(nav?.duration),
    ttfb_ms: metricNumber(nav ? nav.responseStart - nav.requestStart : 0),
    dom_interactive_ms: metricNumber(nav?.domInteractive),
    transfer_size: transferSize,
    encoded_body_size: encodedBodySize,
    image_transfer_size: imageTransferSize,
    resource_count: resources.length,
  };
}

export async function trackPagePerformance({ page, route, metrics } = {}) {
  const measured = metrics || collectPerformanceMetrics();
  if (!measured) return;
  return track('page_performance', {
    page: page || 'unknown',
    route: route || '/',
    ...measured,
  });
}
