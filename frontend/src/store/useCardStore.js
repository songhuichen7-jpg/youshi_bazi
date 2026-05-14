// frontend/src/store/useCardStore.js
import { create } from 'zustand';
import { postCard as realPostCard, getCardPreview as realGetCardPreview } from '../lib/cardApi.js';

const TIME_SEGMENT_TO_HOUR = {
  '凌晨': 2, '早上': 6, '上午': 10, '下午': 14, '傍晚': 18, '深夜': 22,
};

const initialState = {
  birth: { year: '', month: '', day: '', hour: -1, minute: 0, useTimeSegment: false, timeSegment: null },
  nickname: '',
  loading: false,
  error: null,
  card: null,
  preview: null,
  sourceChartId: null,
};

function birthInfoToCardBirth(birthInfo = {}) {
  const [year, month, day] = String(birthInfo.date || '').split('-').map(Number);
  let hour = -1;
  let minute = 0;
  if (!birthInfo.hourUnknown && birthInfo.time) {
    const parts = String(birthInfo.time).split(':').map(Number);
    hour = Number.isFinite(parts[0]) ? parts[0] : -1;
    minute = Number.isFinite(parts[1]) ? parts[1] : 0;
  }
  return {
    year,
    month,
    day,
    hour,
    minute,
    ...(birthInfo.city ? { city: birthInfo.city } : {}),
  };
}

export const useCardStore = create((set, get) => ({
  ...initialState,

  setBirthField(field, value) {
    set(s => ({ birth: { ...s.birth, [field]: value } }));
  },

  setNickname(v) { set({ nickname: v }); },

  selectTimeSegment(label) {
    const hour = TIME_SEGMENT_TO_HOUR[label];
    if (hour === undefined) return;
    set(s => ({ birth: { ...s.birth, useTimeSegment: true, timeSegment: label, hour, minute: 0 } }));
  },

  clearTimeSegment() {
    set(s => ({ birth: { ...s.birth, useTimeSegment: false, timeSegment: null, hour: -1, minute: 0 } }));
  },

  async submitBirth({ postCardImpl = realPostCard } = {}) {
    const { birth, nickname } = get();
    set({ loading: true, error: null });
    try {
      const payload = {
        birth: {
          year: Number(birth.year),
          month: Number(birth.month),
          day: Number(birth.day),
          hour: birth.hour,
          minute: birth.minute,
        },
        nickname: nickname || null,
      };
      const card = await postCardImpl(payload);
      set({ card, loading: false, sourceChartId: null });
      return card;
    } catch (err) {
      set({ error: err.message || 'unknown error', loading: false });
      return null;
    }
  },

  async loadPreview(slug, { getCardPreviewImpl = realGetCardPreview } = {}) {
    set({ loading: true, error: null });
    try {
      const preview = await getCardPreviewImpl(slug);
      set({ preview, loading: false });
    } catch (err) {
      set({ error: err.message, loading: false });
    }
  },

  async generateFromBirthInfo({
    chartId,
    birthInfo,
    nickname,
    postCardImpl = realPostCard,
  } = {}) {
    set({ loading: true, error: null });
    try {
      const payload = {
        birth: birthInfoToCardBirth(birthInfo),
        nickname: nickname || null,
      };
      const card = await postCardImpl(payload);
      set({ card, loading: false, sourceChartId: chartId || null });
      return card;
    } catch (err) {
      set({ error: err.message || 'unknown error', loading: false });
      return null;
    }
  },

  reset() { set(initialState); },
}));
