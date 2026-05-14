let _fetchImpl = (typeof fetch !== 'undefined') ? fetch : null;
export function __setAdminFetch(f) { _fetchImpl = f; }

function withParams(path, params = {}) {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue;
    qs.set(key, String(value));
  }
  const tail = qs.toString();
  return tail ? `${path}?${tail}` : path;
}

async function getAdminJSON(path, { token, ...params } = {}) {
  if (!_fetchImpl) throw new Error('fetch unavailable');
  const response = await _fetchImpl(withParams(path, params), {
    headers: { 'X-Admin-Token': token || '' },
  });
  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try {
      const payload = await response.json();
      message = payload?.detail?.message || payload?.detail || payload?.message || message;
    } catch { /* keep HTTP status */ }
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return response.json();
}

export async function fetchAdminOverview({ token, from, to } = {}) {
  return getAdminJSON('/api/admin/overview', { token, from_: from, to });
}

export async function fetchAdminOperations({ token, from, to } = {}) {
  return getAdminJSON('/api/admin/operations', { token, from_: from, to });
}

export async function listAdminVisitors({ token, anonymousId, from, to, limit = 100 } = {}) {
  return getAdminJSON('/api/admin/visitors', {
    token,
    anonymous_id: anonymousId,
    from_: from,
    to,
    limit,
  });
}

export async function listAdminEvents({ token, event, anonymousId, sessionId, from, to, limit = 100 } = {}) {
  return getAdminJSON('/api/admin/events', {
    token,
    event,
    anonymous_id: anonymousId,
    session_id: sessionId,
    from_: from,
    to,
    limit,
  });
}
