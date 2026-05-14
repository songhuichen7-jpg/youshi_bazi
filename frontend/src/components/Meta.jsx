import { useAppStore } from '../store/useAppStore';
import { buildChartVisibility } from '../lib/chartVisibility';

export function BirthHeader() {
  const meta = useAppStore(s => s.meta);
  if (!meta) return null;
  const solar = meta.solarCorrected || '';
  const lunar = meta.lunar || '';
  const zao = meta.input?.gender === 'female' ? '坤造' : '乾造';
  const hourUnknown = meta.hourUnknown === true;
  // 只有真的跑过真太阳时修正才打"（真太阳时）"标签；时辰未知 / 城市未识别时不加
  const hasTrueSolar = (meta.corrections || []).some(c => c?.type === 'true_solar_time');
  const warnings = meta.warnings || [];
  return (
    <div style={{ marginBottom:32 }}>
      <div className="muted" style={{ fontSize:11, lineHeight:1.8 }}>
        {solar && !hourUnknown && <>{solar}{hasTrueSolar && '（真太阳时）'}<br/></>}
        {hourUnknown && <>{(meta.input?.year || '')}-{String(meta.input?.month||'').padStart(2,'0')}-{String(meta.input?.day||'').padStart(2,'0')} · 时辰未知<br/></>}
        {lunar ? `${lunar} · ${zao}` : zao}
      </div>
      {warnings.length > 0 && (
        <div style={{ marginTop:10, padding:'8px 10px', borderLeft:'2px solid #c8a24b', background:'#faf6ec', fontSize:11, color:'#6a5a2a', lineHeight:1.7 }}>
          {warnings.map((w, i) => <div key={i}>· {w}</div>)}
        </div>
      )}
    </div>
  );
}

export function MetaGrid() {
  const meta = useAppStore(s => s.meta);
  if (!meta) return null;
  const visibility = buildChartVisibility({ meta });
  const dayStrength = meta?.dayStrength ? String(meta.dayStrength).trim() : '';
  return (
    <div className="meta-grid">
      <div className="meta-item">
        <div className="section-num" style={{ marginBottom:6 }} data-tip="meta.日主">日 主</div>
        <div
          className="meta-big"
          data-tip={dayStrength ? `meta.${dayStrength}` : undefined}
        >{visibility.dayMasterText}</div>
        {visibility.showDayStrengthDetails ? (
          <div className="meta-small">
            同类 {meta.sameSideScore?.toFixed?.(1) ?? '?'} / 异类 {meta.otherSideScore?.toFixed?.(1) ?? '?'}
          </div>
        ) : null}
      </div>
      {visibility.showGeju ? (
        <div className="meta-item">
          <div className="section-num" style={{ marginBottom:6 }} data-tip="meta.格局">格 局</div>
          <div className="meta-big">{meta.geju}</div>
          <div className="meta-small">{meta.gejuNote || ''}</div>
        </div>
      ) : null}
      {visibility.showYongshen ? (
        <div className="meta-item">
          <div className="section-num" style={{ marginBottom:6 }} data-tip="meta.用神">用 神</div>
          <div className="meta-big">{meta.yongshen}</div>
          <div className="meta-small">{''}</div>
        </div>
      ) : null}
    </div>
  );
}

export function ReadingHeader() {
  const meta = useAppStore(s => s.meta);
  if (!meta) return null;
  const visibility = buildChartVisibility({ meta });
  return (
    <div>
      <div className="section-num" style={{ marginBottom:10 }}>解 读</div>
      <h2 className="reading-headline">{visibility.readingHeadline || '命盘解读'}</h2>
      <p className="reading-summary">{visibility.readingSummary || '正在整理命盘要点……'}</p>
    </div>
  );
}
