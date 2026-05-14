// 公历生日输入的安全上下限——HTML <input type="date"> 默认允许 0001 ~
// 275760 年, 用户能打出 "202611-05-12" 这种 6 位数年份, 后端 paipan 直接
// 炸或者算出离谱命盘。这里给所有 birth-date 输入一个统一的 min/max:
//   · 下限 1900-01-01 — 跟后端 buildPartnerBirthPayload 校验对齐
//   · 上限 = 本机今天 — 不能出生在未来
// 调用方:
//   <input type="date" min={BIRTH_DATE_MIN} max={birthDateMax()} ... />

export const BIRTH_DATE_MIN = '1900-01-01';

export function birthDateMax() {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${dd}`;
}
