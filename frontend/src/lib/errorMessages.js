function rawMessage(error) {
  if (!error) return '';
  if (typeof error === 'string') return error.trim();
  return String(error.message || error).trim();
}

function hasAny(haystack, needles) {
  return needles.some((needle) => haystack.includes(needle));
}

function result(title, detail, retryable, cta) {
  // cta = { label, to }   to 是 react-router 内部路径，调用方拿来塞 navigate /
  // <Link>。配额错误用它指向 /pricing；普通错误不带这个字段。
  return {
    title,
    detail: detail && detail !== title ? detail : '',
    retryable,
    ...(cta ? { cta } : {}),
  };
}

function isNetwork(lower) {
  return hasAny(lower, [
    'failed to fetch',
    'networkerror',
    'network request failed',
    'load failed',
    'fetch failed',
    'err_network',
    'offline',
  ]);
}

function isTimeout(lower) {
  return hasAny(lower, ['timeout', 'timed out', 'first_delta_timeout', 'empty stream']);
}

function isAuth(lower) {
  return hasAny(lower, [
    '401',
    '403',
    'invalid api key',
    'unauthorized',
    'forbidden',
    'deepseek_api_key missing',
    'deepseek_api_key not configured',
    'llm_api_key missing',
    'llm_api_key not configured',
    'mimo_api_key missing',
    'mimo_api_key not configured',
  ]);
}

function isRateLimit(lower) {
  return hasAny(lower, ['429', 'rate limit', 'too many requests']);
}

function isServer(lower) {
  return hasAny(lower, [
    'http 500',
    'http 502',
    'http 503',
    'http 504',
    'llm 500',
    'llm 502',
    'llm 503',
    'bad gateway',
    'service unavailable',
    'internal server error',
  ]);
}

function isFormat(lower) {
  return hasAny(lower, [
    'json',
    'parseable',
    'did not return json object',
    'verdict explain results incomplete',
    'verdict picks insufficient',
    'empty response',
    'empty content',
    'unexpected token',
    'unexpected end of json input',
  ]);
}

function isMissing(lower) {
  return hasAny(lower, ['tree missing', 'lookup failed', 'not found']);
}

function isSseDisconnect(lower) {
  return hasAny(lower, ['stream', 'aborted', 'socket hang up', 'econnreset', 'premature close', 'connection closed']);
}

function isPaipanInput(lower) {
  return hasAny(lower, [
    'wrong solar',
    'wrong lunar',
    'wrong month',
    'wrong day',
    'wrong hour',
    'wrong minute',
    'wrong second',
    'wrong years',
    'wrong days',
  ]);
}

function isStorageQuota(lower) {
  return hasAny(lower, [
    'quotaexceeded',
    'quota exceeded',
    'storage quota',
    'failed to execute setitem on storage',
  ]);
}

function isStorageUnavailable(lower) {
  return hasAny(lower, [
    'access is denied',
    'securityerror',
    'storage is disabled',
    'the operation is insecure',
    'localstorage is not available',
    'localstorage is not defined',
  ]);
}

// 7 个 daily-reset kind 的中文名 — 跟 server core/quotas.py 的 key 一一对应。
// 命盘是累计型（不在 daily QuotaResponse 里），但前端配额超限对话也可能涉及。
const QUOTA_KIND_LABEL = {
  chat_message: '对话',
  gua: '起卦',
  chart: '命盘',
  section_regen: '解读重写',
  verdicts_regen: '判语重写',
  dayun_regen: '大运重写',
  liunian_regen: '流年重写',
  sms_send: '短信发送',
};

const PAYWALL_CTA = { label: '查看订阅方案', to: '/pricing' };

function tryQuotaExceeded(error) {
  // 后端把 ServiceError(code='QUOTA_EXCEEDED') 映射成 HTTP 429，
  // payload 形如 { detail: { code, message, details: { kind, limit, resets_at? } } }。
  // ChartLimitExceeded 也走 ServiceError 路径，code='CHART_LIMIT_EXCEEDED'。
  // 这两类错误都走 paywall — result() 上挂一个 cta，外面的 toast / inline
  // 渲染器看到就追加一个"查看订阅方案"按钮，链向 /pricing。
  const code = error?.payload?.detail?.code || '';
  if (code === 'QUOTA_EXCEEDED') {
    const kind = error?.payload?.detail?.details?.kind;
    const label = QUOTA_KIND_LABEL[kind] || '操作';
    return result(
      `今日${label}额度用完了`,
      '北京 0 点重置 · 或升级到更高档位',
      false,
      PAYWALL_CTA,
    );
  }
  if (code === 'CHART_LIMIT_EXCEEDED') {
    const limit = error?.payload?.detail?.details?.limit;
    const cap = limit ? `${limit} 张` : '';
    return result(
      `命盘已达${cap}上限`,
      '可以删一张再开新盘，或升级到更高档位',
      false,
      PAYWALL_CTA,
    );
  }
  if (code === 'PLAN_UPGRADE_REQUIRED') {
    // 后端 PlanUpgradeRequiredError 给的 details: { feature, required_plan }
    const required = error?.payload?.detail?.details?.required_plan || 'standard';
    const feature = error?.payload?.detail?.details?.feature || '此功能';
    const plan_zh = required === 'pro' ? 'Pro' : '标准';
    return result(
      `${feature}需要升级`,
      `升级到 ${plan_zh} 档位即可解锁`,
      false,
      PAYWALL_CTA,
    );
  }
  return null;
}

export function friendlyError(error, context) {
  const ctx = typeof context === 'string' ? { kind: context } : (context || {});
  const detail = rawMessage(error);
  const lower = detail.toLowerCase();

  // 配额错误优先 — 它的 status 也是 429，普通 isRateLimit 会把它误判成
  // "现在使用的人有点多，再试一次"，文案不准。
  const quotaResult = tryQuotaExceeded(error);
  if (quotaResult) return quotaResult;

  // 401 / 403 在 status code 上比 message 字符串可靠多了 — 后端可能返回
  // 中文 "未登录"，老版本 isAuth 列表只匹英文 keyword (401/unauthorized)，
  // 中文落到下面 paipan 兜底变成 "请检查出生日期和城市"，把"鉴权问题"
  // 误导成"输入问题"，B 从 hepan funnel 跳到 /app 后撞到这里就懵了。
  // 在这一档统一拦截，给明确文案 + 引到首页让用户走登录流。
  if (error?.status === 401) {
    return result(
      '请先登录再继续',
      detail,
      false,
      { label: '去登录 →', to: '/' },
    );
  }
  if (error?.status === 403) {
    return result('权限不够', detail, false);
  }

  if (ctx.kind === 'storage_load') {
    if (isStorageUnavailable(lower)) return result('本地记录暂时读不了', detail, false);
    return result('本地记录读不出来了', detail, false);
  }

  if (ctx.kind === 'storage_save' || ctx.kind === 'storage_clear') {
    if (isStorageQuota(lower)) return result('浏览器存储空间不足', detail, false);
    if (isStorageUnavailable(lower)) return result('浏览器存储不可用', detail, false);
    return result('本地记录暂时存不住', detail, false);
  }

  if (ctx.kind === 'paipan' && isPaipanInput(lower)) {
    return result('请检查出生日期和城市', detail, false);
  }

  if (ctx.kind === 'profile') {
    if (lower.includes('昵称') || lower.includes('nickname')) {
      return result(detail || '昵称不合法', detail, false);
    }
    if (lower.includes('头像') || lower.includes('上传') || lower.includes('upload')) {
      return result(detail || '头像上传失败', detail, true);
    }
    if (lower.includes('图片') || lower.includes('image') || lower.includes('webp') || lower.includes('jpg')) {
      return result(detail || '图片不合法', detail, false);
    }
    if (lower.includes('4mb') || lower.includes('文件')) {
      return result(detail || '上传文件有问题', detail, false);
    }
  }

  if (isNetwork(lower)) return result('网络连接有点问题', detail, true);
  if (isTimeout(lower)) return result('AI 响应慢了一点', detail, true);
  if (isAuth(lower)) return result('服务暂时不可用', detail, false);
  if (isRateLimit(lower)) return result('现在使用的人有点多', detail, true);
  if (isMissing(lower)) return result('功能暂时不可用', detail, false);
  if (isFormat(lower)) return result('这次 AI 没按规矩输出', detail, true);
  if (isSseDisconnect(lower)) return result('连接断开了，再试一次', detail, true);
  if (isServer(lower)) return result('模型服务偶尔调皮', detail, true);

  if (ctx.kind === 'paipan') {
    return result('请检查出生日期和城市', detail, false);
  }

  return result('出了点小问题，再试一次', detail, true);
}
