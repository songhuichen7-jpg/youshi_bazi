// frontend/src/components/card/birthValidation.js
export function validateBirthInput({ year, month, day }) {
  if (!year || !month || !day) return { ok: false, error: '请填写完整的年份/月份/日期' };
  const y = Number(year), m = Number(month), d = Number(day);
  if (!Number.isInteger(y) || y < 1900 || y > 2100) return { ok: false, error: '年份范围 1900-2100' };
  if (!Number.isInteger(m) || m < 1 || m > 12) return { ok: false, error: '月份无效' };
  const daysInMonth = new Date(y, m, 0).getDate();
  if (!Number.isInteger(d) || d < 1 || d > daysInMonth) return { ok: false, error: `${y}年${m}月无此日期` };
  return { ok: true };
}
