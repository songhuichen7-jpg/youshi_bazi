const BENQI = {
  '子': '癸', '丑': '己', '寅': '甲', '卯': '乙', '辰': '戊',
  '巳': '丙', '午': '丁', '未': '己', '申': '庚', '酉': '辛',
  '戌': '戊', '亥': '壬',
};

const SS_ORDER = ['比肩','劫财','食神','伤官','正财','偏财','正官','七杀','正印','偏印'];

const GAN_YANG = {
  '甲': true, '乙': false, '丙': true, '丁': false, '戊': true,
  '己': false, '庚': true, '辛': false, '壬': true, '癸': false,
};

const GAN_WX = {
  '甲': '木', '乙': '木', '丙': '火', '丁': '火', '戊': '土',
  '己': '土', '庚': '金', '辛': '金', '壬': '水', '癸': '水',
};

function wxRelation(from, to) {
  if (!from || !to) return 'same';
  if (from === to) return 'same';
  if (
    (from === '木' && to === '火') ||
    (from === '火' && to === '土') ||
    (from === '土' && to === '金') ||
    (from === '金' && to === '水') ||
    (from === '水' && to === '木')
  ) return 'sheng';
  if (
    (from === '木' && to === '土') ||
    (from === '土' && to === '水') ||
    (from === '水' && to === '火') ||
    (from === '火' && to === '金') ||
    (from === '金' && to === '木')
  ) return 'ke';
  if (
    (to === '木' && from === '火') ||
    (to === '火' && from === '土') ||
    (to === '土' && from === '金') ||
    (to === '金' && from === '水') ||
    (to === '水' && from === '木')
  ) return 'shengBy';
  return 'keBy';
}

function ssLookup(dayGan, otherGan) {
  const a = GAN_WX[dayGan];
  const b = GAN_WX[otherGan];
  const samePolarity = GAN_YANG[dayGan] === GAN_YANG[otherGan];
  switch (wxRelation(a, b)) {
    case 'same':
      return samePolarity ? '比肩' : '劫财';
    case 'sheng':
      return samePolarity ? '食神' : '伤官';
    case 'ke':
      return samePolarity ? '偏财' : '正财';
    case 'keBy':
      return samePolarity ? '七杀' : '正官';
    case 'shengBy':
      return samePolarity ? '偏印' : '正印';
    default:
      return '';
  }
}

function todayYear(rawChart) {
  const year = Number(String(rawChart?.todayYmd || '').slice(0, 4));
  return Number.isFinite(year) && year > 0 ? year : new Date().getFullYear();
}

function buildBirthLabel(birthInfo) {
  if (!birthInfo) return '未命名命盘';
  const gender = birthInfo.gender === 'female' ? '女' : '男';
  const date = birthInfo.date || '';
  const time = birthInfo.hourUnknown ? '' : (birthInfo.time || '');
  return `${gender} · ${date}${time ? ' ' + time : ''}`;
}

export function birthInputToBirthInfo(birthInput = {}) {
  const hourUnknown = birthInput.hour === -1;
  const minute = Number.isFinite(birthInput.minute) ? birthInput.minute : 0;
  const hour = Number.isFinite(birthInput.hour) ? birthInput.hour : 0;
  return {
    date: [
      birthInput.year,
      String(birthInput.month || '').padStart(2, '0'),
      String(birthInput.day || '').padStart(2, '0'),
    ].join('-'),
    time: hourUnknown ? '' : `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`,
    hourUnknown,
    city: birthInput.city || '',
    gender: birthInput.gender || 'male',
    ziConvention: birthInput.ziConvention || 'early',
    trueSolar: birthInput.useTrueSolarTime !== false,
  };
}

function buildDayun(rawChart) {
  const dayGan = rawChart?.rizhu || rawChart?.sizhu?.day?.[0] || '';
  const list = rawChart?.dayun?.list || [];
  const currentYear = todayYear(rawChart);
  return list.map((step) => {
    const gz = step?.ganzhi || '';
    const gan = gz[0] || '';
    const zhi = gz[1] || '';
    const liunian = step?.liunian || [];
    const years = liunian.map((year) => {
      const yearGz = year?.ganzhi || '';
      const yearGan = yearGz[0] || '';
      const yearZhi = yearGz[1] || '';
      return {
        year: year?.year,
        gz: yearGz,
        ss: `${ssLookup(dayGan, yearGan)}/${ssLookup(dayGan, BENQI[yearZhi] || yearGan)}`,
        current: year?.year === currentYear,
      };
    });
    return {
      age: step?.startAge,
      gz,
      ss: `${ssLookup(dayGan, gan)}/${ssLookup(dayGan, BENQI[zhi] || gan)}`,
      startYear: step?.startYear,
      endYear: step?.endYear ?? ((step?.startYear ?? currentYear) + 10),
      current: years.some((year) => year.current),
      years,
    };
  });
}

function buildForceRows(rawChart) {
  const scores = rawChart?.force?.scores;
  if (!scores || typeof scores !== 'object' || Object.keys(scores).length === 0) {
    return [];
  }
  return SS_ORDER.map((name) => ({
    name,
    val: Math.max(0, Math.min(10, Number(scores[name] || 0))),
  }));
}

function buildGuards(rawChart) {
  const guards = [];

  for (const note of rawChart?.notes || []) {
    if (note?.type === 'pair_mismatch' && note?.message) {
      guards.push({ type: 'pair_mismatch', note: note.message });
    }
  }

  const seenLiuHe = new Set();
  for (const lh of rawChart?.zhiRelations?.liuHe || []) {
    const key = [lh?.a || '', lh?.b || ''].sort().join('');
    if (!key || seenLiuHe.has(key)) continue;
    seenLiuHe.add(key);
    const note = lh?.wuxing
      ? `${lh.a}${lh.b} 六合 化 ${lh.wuxing}`
      : `${lh.a}${lh.b} 六合（合日月，不化）`;
    guards.push({ type: 'liuhe', note });
  }

  const seenChong = new Set();
  for (const ch of rawChart?.zhiRelations?.chong || []) {
    const pair = ch?.a && ch?.b ? `${ch.a}${ch.b}` : '';
    const key = pair.split('').sort().join('');
    if (!pair || seenChong.has(key)) continue;
    seenChong.add(key);
    guards.push({ type: 'chong', note: `${pair} 相冲` });
  }

  const seenSanHe = new Set();
  for (const relation of rawChart?.zhiRelations?.sanHe || []) {
    const zhi = Array.isArray(relation?.zhi) ? relation.zhi.filter(Boolean) : [];
    const key = `${zhi.join('')}:${relation?.wuxing || ''}:${relation?.type || ''}`;
    if (zhi.length !== 3 || !key || seenSanHe.has(key)) continue;
    seenSanHe.add(key);
    guards.push({ type: 'sanhe', note: `三合 ${zhi.join('')} 化 ${relation.wuxing || ''}`.trim() });
  }

  const seenBanHe = new Set();
  for (const relation of rawChart?.zhiRelations?.banHe || []) {
    const zhi = Array.isArray(relation?.zhi) ? relation.zhi.filter(Boolean) : [];
    const key = `${zhi.join('')}:${relation?.wuxing || ''}`;
    if (zhi.length !== 2 || !relation?.wuxing || seenBanHe.has(key)) continue;
    seenBanHe.add(key);
    guards.push({ type: 'banhe', note: `半合 ${zhi.join('')} → ${relation.wuxing}` });
  }

  const seenSanHui = new Set();
  for (const relation of rawChart?.zhiRelations?.sanHui || []) {
    const zhi = Array.isArray(relation?.zhi) ? relation.zhi.filter(Boolean) : [];
    const dirWuxing = relation?.dir && relation?.wuxing ? `${relation.dir}方${relation.wuxing}` : '';
    const key = `${zhi.join('')}:${dirWuxing}`;
    if (zhi.length !== 3 || !dirWuxing || seenSanHui.has(key)) continue;
    seenSanHui.add(key);
    guards.push({ type: 'sanhui', note: `三会 ${zhi.join('')} ${dirWuxing}` });
  }

  return guards;
}

export function chartListItemToEntry(item = {}) {
  return {
    id: item.id,
    label: item.label || '未命名命盘',
    createdAt: item.created_at ? Date.parse(item.created_at) : Date.now(),
    updatedAt: item.updated_at ? Date.parse(item.updated_at) : Date.now(),
    loaded: false,
  };
}

export function chartResponseToEntry(response = {}) {
  const detail = response.chart || {};
  const rawChart = detail.paipan || {};
  const birthInfo = birthInputToBirthInfo(detail.birth_input || {});
  const force = buildForceRows(rawChart);
  const guards = buildGuards(rawChart);
  const geju = rawChart.geju || rawChart.geJu?.mainCandidate?.name || '';
  const dayStrength = rawChart.dayStrength || rawChart.force?.dayStrength || '';
  return {
    id: detail.id,
    label: detail.label || buildBirthLabel(birthInfo),
    createdAt: detail.created_at ? Date.parse(detail.created_at) : Date.now(),
    updatedAt: detail.updated_at ? Date.parse(detail.updated_at) : Date.now(),
    birthInfo,
    paipan: {
      sizhu: rawChart.sizhu || {},
      shishen: rawChart.shishen || {},
      cangGan: rawChart.cangGan || {},
    },
    force,
    guards,
    dayun: buildDayun(rawChart),
    meta: {
      rizhu: rawChart.sizhu?.day || '',
      rizhuGan: rawChart.rizhu || rawChart.sizhu?.day?.[0] || '',
      dayStrength,
      sameSideScore: rawChart.force?.sameSideScore ?? null,
      otherSideScore: rawChart.force?.otherSideScore ?? null,
      geju,
      gejuNote: rawChart.geJu?.decisionNote || '',
      yongshen: rawChart.yongshen || '',
      // 用神细节（K 线评分 Phase 2 用）：含 candidates[] = [{method, name, ...}]，
      // method 取值 '调候' / '扶抑' / '通关' / '病药' / '格局' 等。前端按 method
      // 给每个 yongshen 元素一个**差异化 floor**（病药 / 调候 / 通关 高于扶抑）。
      yongshenDetail: rawChart.yongshenDetail || null,
      lunar: rawChart.lunar || '',
      solarCorrected: rawChart.solarCorrected || '',
      warnings: rawChart.warnings || [],
      corrections: rawChart.meta?.corrections || [],
      jieqiCheck: rawChart.meta?.jieqiCheck || null,
      hourUnknown: rawChart.hourUnknown === true,
      today: {
        ymd: rawChart.todayYmd || '',
        yearGz: rawChart.todayYearGz || '',
        monthGz: rawChart.todayMonthGz || '',
        dayGz: rawChart.todayDayGz || '',
      },
      input: {
        ...(rawChart.meta?.input || {}),
        gender: detail.birth_input?.gender || 'male',
        city: detail.birth_input?.city || '',
      },
    },
    loaded: true,
  };
}
