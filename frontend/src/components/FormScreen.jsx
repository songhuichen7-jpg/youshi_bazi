/* eslint-disable react-hooks/set-state-in-effect */
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAppStore, generateChartLabel } from '../store/useAppStore';
import { fetchCities, createChart } from '../lib/api';
import { MAX_CHARTS } from '../lib/constants';
import { friendlyError } from '../lib/errorMessages';
import { track } from '../lib/analytics';
import { BIRTH_DATE_MIN, birthDateMax } from '../lib/dateBounds';

const LOADING_STAGES = ['真太阳时校正','四柱排定','藏干展开','力量擂台','格局识别'];

export default function FormScreen() {
  const birthInfo   = useAppStore(s => s.birthInfo);
  const formError   = useAppStore(s => s.formError);
  const setFormError = useAppStore(s => s.setFormError);
  const setScreen   = useAppStore(s => s.setScreen);
  const setBirthInfo = useAppStore(s => s.setBirthInfo);
  const openChartFromResponse = useAppStore(s => s.openChartFromResponse);
  const setSections = useAppStore(s => s.setSections);
  const setSectionsLoading = useAppStore(s => s.setSectionsLoading);
  const setSectionsError = useAppStore(s => s.setSectionsError);
  const charts = useAppStore(s => s.charts);
  const ensureConversation = useAppStore(s => s.ensureConversation);

  const [date, setDate]     = useState(birthInfo?.date || '');
  const [time, setTime]     = useState(birthInfo?.time || '');
  const [hourUnknown, setHU] = useState(birthInfo?.hourUnknown || false);
  const [city, setCity]     = useState(birthInfo?.city || '');
  const [gender, setGender] = useState(birthInfo?.gender || '');
  const [zi, setZi]         = useState(birthInfo?.ziConvention || 'early');
  const [trueSolar, setTS]  = useState(birthInfo?.trueSolar !== false);
  const [privacyAgreed, setPrivacyAgreed] = useState(false);
  const [cities, setCities] = useState([]);

  useEffect(() => {
    fetchCities().then(j => setCities(j.cities || [])).catch(() => {});
    track('form_start', { flow: 'app' });
  }, []);

  function rejectForm(message, field) {
    setFormError(message);
    track('form_error', { flow: 'app', field });
  }

  async function onSubmit() {
    setFormError(null);
    if (!privacyAgreed) return rejectForm('请先阅读并同意用户协议和隐私政策', 'privacy_agreement');
    if (!date) return rejectForm('请输入出生日期', 'date');
    if (!city.trim()) return rejectForm('请输入出生地', 'city');
    if (!gender) return rejectForm('请选择性别', 'gender');
    const [y, mo, d] = date.split('-').map(Number);
    let h = -1, mi = 0;
    if (!hourUnknown) {
      if (!time) return rejectForm('请输入出生时间或勾选"时辰未知"', 'time');
      [h, mi] = time.split(':').map(Number);
    }
    const payload = {
      year: y, month: mo, day: d, hour: h, minute: mi,
      city: city.trim(), gender, ziConvention: zi, useTrueSolarTime: trueSolar,
    };
    const birth = { date, time, hourUnknown, city: city.trim(), gender, ziConvention: zi, trueSolar };
    setBirthInfo(birth);

    // Check chart limit before proceeding
    if (Object.keys(charts).length >= MAX_CHARTS) {
      return rejectForm(`最多保存 ${MAX_CHARTS} 份命盘，请先在右上角删除一份再新建。`, 'chart_limit');
    }

    track('form_submit', {
      flow: 'app',
      has_time: !hourUnknown,
      gender,
      zi_convention: zi,
      true_solar: trueSolar,
    });

    setScreen('loading');
    const minDelay = new Promise(r => setTimeout(r, 1200));
    let stageI = 0;
    useAppStore.setState({ loadingStage: 0 });
    const stageTimer = setInterval(() => {
      stageI++;
      if (stageI < LOADING_STAGES.length) useAppStore.setState({ loadingStage: stageI });
      else clearInterval(stageTimer);
    }, 280);

    try {
      const [data] = await Promise.all([
        createChart({ birth_input: payload, label: generateChartLabel(birth) }),
        minDelay,
      ]);
      clearInterval(stageTimer);
      await new Promise(r => setTimeout(r, 250));
      openChartFromResponse(data, { skipConversationHydration: true });
      await ensureConversation(data.chart.id);
      track('chart_create_success', {
        flow: 'app',
        chart_id: data.chart?.id,
        has_time: !hourUnknown,
        gender,
      });
      setSections([]);
      setSectionsError(null);
      setSectionsLoading(false);
    } catch (e) {
      clearInterval(stageTimer);
      console.error(e);
      const friendly = friendlyError(e, 'paipan');
      track('chart_create_failed', {
        flow: 'app',
        error_code: e?.payload?.detail?.code || e?.status || 'UNKNOWN',
      });
      setFormError(friendly.title);
      setScreen('input');
    }
  }

  return (
    <div className="screen active">
      <div className="form-wrap fade-in">
        <button type="button" className="back-link" onClick={() => setScreen('landing')}>← 返回</button>
        <div className="section-num" style={{ marginBottom: 16 }}>Step 01</div>
        <h2 className="serif">生辰</h2>

        <div className="form-row">
          <label className="form-label" htmlFor="birth-date">公历生日</label>
          <input
            id="birth-date"
            type="date"
            min={BIRTH_DATE_MIN}
            max={birthDateMax()}
            value={date}
            onChange={e => setDate(e.target.value)}
          />
        </div>

        <div className="form-row" style={{ display:'grid', gridTemplateColumns:'1fr auto', gap:16, alignItems:'end' }}>
          <div>
            <label className="form-label" htmlFor="birth-time">出生时间</label>
            <input id="birth-time" type="time" value={time} disabled={hourUnknown} onChange={e => setTime(e.target.value)} />
          </div>
          <label className="muted" style={{ fontSize:12, display:'flex', alignItems:'center', gap:6, paddingBottom:8, cursor:'pointer' }}>
            <input type="checkbox" checked={hourUnknown} onChange={e => setHU(e.target.checked)} style={{ width:'auto' }} /> 时辰未知
          </label>
        </div>
        {hourUnknown && (
          <p className="form-field-hint">时柱（第四柱）将留空，命盘仍可排出，但十神力量分布和用神判断会有一定偏差。如果只知道大概时段也可先填入，事后可重新排盘。</p>
        )}

        <div className="form-row">
          <label className="form-label" htmlFor="birth-city">出生地</label>
          <input id="birth-city" type="text" value={city} onChange={e => setCity(e.target.value)}
                 placeholder="北京 / 上海 / 长沙 …（用于真太阳时校正）" list="city-list" />
          <datalist id="city-list">
            {cities.map(c => <option key={c} value={c} />)}
          </datalist>
        </div>

        <div className="form-row">
          <label className="form-label">性别</label>
          <div style={{ display:'flex', gap:24, paddingTop:8 }}>
            <label style={{ fontSize:14, display:'flex', alignItems:'center', gap:6, cursor:'pointer' }}>
              <input type="radio" name="g" value="male" checked={gender==='male'} onChange={() => setGender('male')} style={{ width:'auto' }} /> 男
            </label>
            <label style={{ fontSize:14, display:'flex', alignItems:'center', gap:6, cursor:'pointer' }}>
              <input type="radio" name="g" value="female" checked={gender==='female'} onChange={() => setGender('female')} style={{ width:'auto' }} /> 女
            </label>
          </div>
        </div>

        <details className="form-disclosure" style={{ marginTop:12, fontSize:12, color:'#666' }}>
          <summary>高级选项</summary>
          <div className="form-row" style={{ marginTop:12 }}>
            <label className="form-label">子时派</label>
            <div style={{ display:'flex', gap:24, paddingTop:8 }}>
              <label style={{ fontSize:13, display:'flex', alignItems:'center', gap:6, cursor:'pointer' }}>
                <input type="radio" name="zi" value="early" checked={zi==='early'} onChange={() => setZi('early')} style={{ width:'auto' }} /> 早子时（23:00 归次日）
              </label>
              <label style={{ fontSize:13, display:'flex', alignItems:'center', gap:6, cursor:'pointer' }}>
                <input type="radio" name="zi" value="late" checked={zi==='late'} onChange={() => setZi('late')} style={{ width:'auto' }} /> 晚子时（23:00 归本日）
              </label>
            </div>
            <p className="form-field-hint">子时（23:00–01:00）跨越两日，两派处理方式不同。早子时认为 23:00 起已属次日，是多数命理软件的默认值；晚子时认为 23:00–00:00 仍属当日，00:00 后才换日。仅影响 23:00–00:00 出生者的日柱。</p>
          </div>
          <div className="form-row">
            <label style={{ fontSize:13, display:'flex', alignItems:'center', gap:6, cursor:'pointer' }}>
              <input type="checkbox" checked={trueSolar} onChange={e => setTS(e.target.checked)} style={{ width:'auto' }} /> 修正真太阳时（推荐）
            </label>
            <p className="form-field-hint">各地日出时间因经度不同而有偏差，真太阳时按出生地经度将时钟时间修正为当地实际太阳位置。偏差一般在 ±30 分钟以内，但可能影响时柱或日柱。填写了出生地建议保持勾选。</p>
          </div>
        </details>

        {formError && (
          <div style={{ marginTop:16, padding:'10px 12px', borderLeft:'3px solid #000', background:'#f7f5f2', fontSize:13, color:'#333' }}>{formError}</div>
        )}

        <p className="form-subtle-hint">只填你确定的信息。时辰拿不准，就勾选“时辰未知”。</p>

        <div className="form-privacy-agreement">
          <input
            id="privacy-agreement-checkbox"
            type="checkbox"
            checked={privacyAgreed}
            onChange={e => setPrivacyAgreed(e.target.checked)}
          />
          <div className="form-privacy-agreement-copy">
            <label htmlFor="privacy-agreement-checkbox">我已阅读并同意</label>
            <Link to="/legal/terms">《服务条款》</Link>
            <span>和</span>
            <Link to="/legal/privacy">《隐私政策》</Link>
            <p>出生信息仅用于排盘与解读，命盘档案和对话内容按隐私政策加密处理。</p>
          </div>
        </div>

        <div className="form-actions">
          <button
            className="btn-primary"
            onClick={onSubmit}
            disabled={!privacyAgreed}
            title={!privacyAgreed ? '请先勾选同意服务条款和隐私政策' : undefined}
          >
            生成命盘 →
          </button>
        </div>
      </div>
    </div>
  );
}

export function LoadingScreen({ title = '计算中', label = null, compact = false }) {
  const loadingStage = useAppStore(s => s.loadingStage);
  // 阶段文案用 displayedStage + phase（out → swap → in）实现淡入淡出，
  // 跟 hero mockup 的轮播同款节奏，避免 280ms 一刀切的硬感。
  const [displayedStage, setDisplayedStage] = useState(loadingStage);
  const [phase, setPhase] = useState('in');
  useEffect(() => {
    if (loadingStage === displayedStage) return;
    setPhase('out');
    const t = setTimeout(() => {
      setDisplayedStage(loadingStage);
      setPhase('in');
    }, 280);
    return () => clearTimeout(t);
  }, [loadingStage, displayedStage]);

  return (
    <div className="screen active">
      <div className="center-wrap">
        <div style={{ textAlign:'center' }} className="fade-in">
          <div className="section-num" style={{ marginBottom:24 }}>{title}</div>
          <div
            className="serif loading-stage-label"
            data-phase={phase}
            style={{ fontSize:22, marginBottom: compact ? 28 : 48, height:28 }}
          >
            {label || LOADING_STAGES[displayedStage] || ''}
          </div>
          {!compact ? (
            <div className="loading-stages">
              {LOADING_STAGES.map((_, i) => (
                <span
                  key={i}
                  className={
                    (i < loadingStage ? 'on' : '')
                    + (i === loadingStage ? ' current' : '')
                  }
                />
              ))}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export function LandingScreen() {
  const enterFromLanding = useAppStore(s => s.enterFromLanding);
  return (
    <div className="screen active">
      <div className="center-wrap">
        <div className="landing fade-in">
          <div className="section-num" style={{ marginBottom:24 }}>命 · 盘 · 读</div>
          <h1 className="serif">一个<span className="muted">理性的</span>命理工具</h1>
          <p>不讲玄学。用子平真诠 + 现代结构化方法，把你的八字翻译成一份可以读、可以聊、可以对照的自我说明书。</p>
          <button className="btn-primary" onClick={() => void enterFromLanding()}>开始排盘 →</button>
          <div className="landing-product-peek" aria-label="产品预览">
            <div className="landing-peek-chart">
              <span className="landing-peek-kicker">命盘档案</span>
              <div className="landing-peek-pillars">
                <strong>丁</strong>
                <strong>酉</strong>
                <strong>食神格</strong>
              </div>
              <div className="landing-peek-lines">
                <span />
                <span />
                <span />
              </div>
            </div>
            <div className="landing-peek-chat">
              <span className="landing-peek-kicker">对话</span>
              <p>可以继续问：这盘的核心矛盾是什么？接下来两年重点看什么？</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
