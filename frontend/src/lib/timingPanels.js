function splitTimingParagraphs(text) {
  return String(text || '')
    .replace(/\r\n/g, '\n')
    .split(/\n\s*\n/)
    .map((part) => part.trim())
    .filter(Boolean);
}

export function buildDayunPanel(step, text) {
  return {
    kicker: '大运总览',
    title: step?.gz ? `${step.gz}大运` : '大运总览',
    meta: step?.age != null
      ? `${step.age}岁起${step?.ss ? ` · ${step.ss}` : ''}`
      : (step?.ss || null),
    paragraphs: splitTimingParagraphs(text),
  };
}

export function buildLiunianPanel(year, text) {
  return {
    kicker: '流年细看',
    title: [year?.year, year?.gz].filter(Boolean).join(' ') || '流年细看',
    meta: null,
    paragraphs: splitTimingParagraphs(text),
  };
}
