// Shared validator/builder for "对方命盘" forms.
// Used by CardWorkspace (A 直接帮 B 填) and HepanScreen pending state (B 自己填).
//
// form shape:
//   { date: 'YYYY-MM-DD', time: 'HH:MM' | '', hourUnknown: bool,
//     city: string, gender: '' | 'female' | 'male', nickname: string }
//
// Throws Error with a Chinese user-facing message on the first invalid field.
export function buildPartnerBirthPayload(form) {
  if (!form?.date) {
    throw new Error('请输入对方的出生日期。');
  }
  const [year, month, day] = form.date.split('-').map(s => parseInt(s, 10));
  if (!year || !month || !day) {
    throw new Error('对方生日格式不完整。');
  }
  if (year < 1900 || year > 2100) throw new Error('出生年份要在 1900-2100 之间。');
  if (month < 1 || month > 12) throw new Error('月份要在 1-12 之间。');
  const daysInMonth = new Date(year, month, 0).getDate();
  if (day < 1 || day > daysInMonth) throw new Error(`${year}年${month}月没有这一天。`);

  let hour = -1;
  let minute = 0;
  if (!form.hourUnknown) {
    if (!form.time) {
      throw new Error('请输入出生时间，或勾选“时辰未知”。');
    }
    const [parsedHour, parsedMinute] = form.time.split(':').map(s => parseInt(s, 10));
    if (!Number.isFinite(parsedHour) || parsedHour < 0 || parsedHour > 23) {
      throw new Error('出生时间格式不对。');
    }
    hour = parsedHour;
    minute = Number.isFinite(parsedMinute) ? parsedMinute : 0;
  }
  return {
    year,
    month,
    day,
    hour,
    minute,
    gender: form.gender || null,
    city: (form.city || '').trim() || null,
  };
}

export const EMPTY_PARTNER_FORM = {
  date: '',
  time: '',
  hourUnknown: false,
  nickname: '',
  gender: '',
  city: '',
};
