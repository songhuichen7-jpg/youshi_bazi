// frontend/src/lib/classics.js
//
// 把后端 PersonaQuote / VerdictQuote 原始 JSON 转成视图模型（display item）。
// 后端字段都是 snake_case，视图模型沿用同名字段不做换名 — 减少前端 mental
// translation 成本。这里只做：null 防御 + 空字符串归一化 + 字段裁剪。

function _emptyOrTrim(value) {
  if (typeof value !== 'string') return '';
  return value.trim();
}

export function buildPersonaDisplay(persona) {
  if (!persona || typeof persona !== 'object') return null;
  const quote = _emptyOrTrim(persona.quote);
  if (!quote) return null;  // 没正文不展示
  return {
    quote,
    plain: _emptyOrTrim(persona.plain),
    book: _emptyOrTrim(persona.book),
    chapter: _emptyOrTrim(persona.chapter),
    section: _emptyOrTrim(persona.section) || null,
    tier: persona.tier === 'case' ? 'case' : 'general',
    fit_note: _emptyOrTrim(persona.fit_note),
  };
}

export function buildVerdictDisplay(verdict) {
  if (!verdict || typeof verdict !== 'object') return null;
  const quote = _emptyOrTrim(verdict.quote);
  if (!quote) return null;
  return {
    quote,
    book: _emptyOrTrim(verdict.book),
    chapter: _emptyOrTrim(verdict.chapter),
  };
}
