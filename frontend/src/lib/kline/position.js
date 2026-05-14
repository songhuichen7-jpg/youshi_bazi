// 当前时间在大运 / 流年里的精确位置 — 月级精度。
// 头像就钉在这个点上。

function parseYmd(ymd) {
  if (!ymd || typeof ymd !== 'string') return null;
  const m = ymd.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!m) return null;
  return { year: Number(m[1]), month: Number(m[2]), day: Number(m[3]) };
}

/**
 * 计算"当前"在大运数组里的位置。
 *
 * 入参：
 *   dayun:    [{ startYear, endYear, years: [{ year, ... }] }, ...]
 *   todayYmd: '2026-05-10'
 *
 * 输出：null（未起运 / 已超出最末步），或：
 * {
 *   dayunIdx,           // 第几步大运（0-based）
 *   stepProgress,       // 在该大运里走了多少 [0, 1)
 *   yearIdx,            // 在该大运 years[] 里的索引
 *   yearProgress,       // 在该年里走了多少 [0, 1)
 *   absoluteProgress,   // 在整个 dayun 时间轴上的位置 [0, 1)
 *   age,                // 当前年龄（粗算：今年 - startYear + dayun[0].age）
 * }
 */
export function computeNowPosition({ dayun, todayYmd } = {}) {
  const today = parseYmd(todayYmd) || (() => {
    const d = new Date();
    return { year: d.getFullYear(), month: d.getMonth() + 1, day: d.getDate() };
  })();
  if (!Array.isArray(dayun) || dayun.length === 0) return null;

  const totalStart = dayun[0].startYear;
  const totalEnd = dayun[dayun.length - 1].endYear;
  if (today.year < totalStart) {
    // 未起运 — 头像贴在轴线最左端。
    return {
      dayunIdx: -1,
      stepProgress: 0,
      yearIdx: -1,
      yearProgress: 0,
      absoluteProgress: 0,
      preStart: true,
    };
  }
  if (today.year >= totalEnd) {
    return {
      dayunIdx: dayun.length - 1,
      stepProgress: 1,
      yearIdx: (dayun[dayun.length - 1].years || []).length - 1,
      yearProgress: 1,
      absoluteProgress: 1,
      postEnd: true,
    };
  }

  // 优先信任 engine 给的 `.current` flag（边界年份归属是 engine 的判断，
  // UI 不要二次判定）。再用 year 范围校准月级精度。
  const explicitIdx = dayun.findIndex((s) => s.current);
  const candidateIdx = explicitIdx >= 0
    ? explicitIdx
    : dayun.findIndex((step) => {
      // endYear 在本 engine 里是 inclusive 的（[startYear, endYear]）
      const stepEnd = step.endYear ?? (step.startYear + 9);
      return today.year >= step.startYear && today.year <= stepEnd;
    });

  if (candidateIdx < 0) return null;

  const step = dayun[candidateIdx];
  const stepEnd = step.endYear ?? (step.startYear + 9);
  // 全长按 [startYear, endYear+1) 算 — 每年走 12 个月
  const totalYears = (stepEnd + 1) - step.startYear;
  const monthsIntoStep = (today.year - step.startYear) * 12 + (today.month - 1) + (today.day - 1) / 30;
  const totalMonths = totalYears * 12;
  const stepProgress = Math.min(1, Math.max(0, monthsIntoStep / totalMonths));

  const years = step.years || [];
  const yearIdx = years.findIndex((y) => y.year === today.year);
  const yearProgress = Math.min(1, Math.max(0, ((today.month - 1) + (today.day - 1) / 30) / 12));

  const absoluteProgress = (candidateIdx + stepProgress) / dayun.length;

  const startAge = step.age || 0;
  const age = Math.floor(startAge + (today.year - step.startYear) + yearProgress);

  return {
    dayunIdx: candidateIdx,
    stepProgress,
    yearIdx,
    yearProgress,
    absoluteProgress,
    age,
  };
}

/**
 * 给定大运索引和当前位置，返回头像应当落在 stepProgress 内的位置 [0, 1]。
 * 如果当前不在该大运，返回 null。
 */
export function avatarInDayun(now, dayunIdx) {
  if (!now) return null;
  if (now.dayunIdx !== dayunIdx) return null;
  return now.stepProgress;
}

/**
 * 给定大运里的"流年视图"，头像应当落在哪个 yearIdx 的中段（按月）。
 * 输出： { yearIdx, fractionInYear } — 没在该大运返回 null。
 */
export function avatarInYears(now, dayunIdx) {
  if (!now) return null;
  if (now.dayunIdx !== dayunIdx) return null;
  return { yearIdx: now.yearIdx, fractionInYear: now.yearProgress };
}
