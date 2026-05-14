// frontend/tests/card-store.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { useCardStore } from '../src/store/useCardStore.js';

function resetStore() {
  useCardStore.setState({
    birth: { year: '', month: '', day: '', hour: -1, minute: 0, useTimeSegment: false, timeSegment: null },
    nickname: '',
    loading: false,
    error: null,
    card: null,
    preview: null,
    sourceChartId: null,
  });
}

test.beforeEach(resetStore);

test('setBirthField updates single field', () => {
  useCardStore.getState().setBirthField('year', 1998);
  assert.equal(useCardStore.getState().birth.year, 1998);
});

test('selectTimeSegment maps to correct hour', () => {
  useCardStore.getState().selectTimeSegment('下午');
  const b = useCardStore.getState().birth;
  assert.equal(b.hour, 14);
  assert.equal(b.useTimeSegment, true);
  assert.equal(b.timeSegment, '下午');
});

test('clearTimeSegment resets to unknown hour', () => {
  useCardStore.getState().selectTimeSegment('下午');
  useCardStore.getState().clearTimeSegment();
  assert.equal(useCardStore.getState().birth.hour, -1);
  assert.equal(useCardStore.getState().birth.useTimeSegment, false);
  assert.equal(useCardStore.getState().birth.timeSegment, null);
});

test('submitBirth calls API and stores card on success', async () => {
  const fakeCard = { type_id: '01', cosmic_name: '春笋', share_slug: 'c_abc' };
  useCardStore.setState({
    birth: { year: 1998, month: 7, day: 15, hour: 14, minute: 0, useTimeSegment: true, timeSegment: '下午' },
    nickname: '小满',
  });
  const result = await useCardStore.getState().submitBirth({
    postCardImpl: async () => fakeCard,
  });
  assert.deepEqual(useCardStore.getState().card, fakeCard);
  assert.equal(useCardStore.getState().error, null);
  assert.equal(useCardStore.getState().loading, false);
  assert.deepEqual(result, fakeCard);
});

test('submitBirth sets error on failure', async () => {
  useCardStore.setState({ birth: { year: 1800, month: 1, day: 1, hour: 0, minute: 0 } });
  const result = await useCardStore.getState().submitBirth({
    postCardImpl: async () => { const e = new Error('bad year'); e.status = 422; throw e; },
  });
  assert.match(useCardStore.getState().error, /bad year/);
  assert.equal(useCardStore.getState().card, null);
  assert.equal(useCardStore.getState().loading, false);
  assert.equal(result, null);
});

test('loadPreview fetches and stores preview', async () => {
  const fakePreview = { slug: 'c_abc', cosmic_name: '春笋', suffix: '天生享乐家' };
  await useCardStore.getState().loadPreview('c_abc', {
    getCardPreviewImpl: async () => fakePreview,
  });
  assert.deepEqual(useCardStore.getState().preview, fakePreview);
});

test('generateFromBirthInfo builds a card from the active chart birth info', async () => {
  const fakeCard = { type_id: '20', cosmic_name: '蒲公英', share_slug: 'c_chart' };
  let captured;

  const result = await useCardStore.getState().generateFromBirthInfo({
    chartId: 'chart-1',
    birthInfo: {
      date: '1998-07-15',
      time: '14:30',
      hourUnknown: false,
      city: '长沙',
    },
    nickname: '小满',
    postCardImpl: async (payload) => {
      captured = payload;
      return fakeCard;
    },
  });

  assert.deepEqual(captured, {
    birth: { year: 1998, month: 7, day: 15, hour: 14, minute: 30, city: '长沙' },
    nickname: '小满',
  });
  assert.deepEqual(result, fakeCard);
  assert.equal(useCardStore.getState().sourceChartId, 'chart-1');
});
