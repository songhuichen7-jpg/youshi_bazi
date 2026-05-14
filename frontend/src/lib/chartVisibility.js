function hasValue(value) {
  if (value == null) return false;
  const text = String(value).trim();
  return text !== '' && text !== '—';
}

export function buildChartVisibility({ meta, force } = {}) {
  const dayMaster = hasValue(meta?.rizhu) ? String(meta.rizhu).trim() : '';
  const dayStrength = hasValue(meta?.dayStrength) ? String(meta.dayStrength).trim() : '';
  const geju = hasValue(meta?.geju) ? String(meta.geju).trim() : '';
  const yongshen = hasValue(meta?.yongshen) ? String(meta.yongshen).trim() : '';
  const gejuNote = hasValue(meta?.gejuNote) ? String(meta.gejuNote).trim() : '';
  const readingHeadline = [dayMaster, geju].filter(Boolean).join(' · ') || dayMaster;
  const readingSummary = [
    dayMaster ? `日主 ${dayMaster}` : '',
    dayStrength,
    yongshen ? `用神 ${yongshen}` : '',
    gejuNote,
  ].filter(Boolean).join(' · ');

  return {
    showDayStrengthDetails: !!dayStrength,
    showGeju: !!geju,
    showYongshen: !!yongshen,
    showForce: Array.isArray(force) && force.length > 0,
    showGuards: false,
    dayMasterText: [dayMaster, dayStrength].filter(Boolean).join(' · ') || dayMaster,
    readingHeadline,
    readingSummary,
  };
}
