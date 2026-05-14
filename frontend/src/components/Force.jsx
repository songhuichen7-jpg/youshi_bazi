import { useAppStore } from '../store/useAppStore';
import { buildForcePortrait, classifyForceBand } from '../lib/forcePortrait.js';

export default function Force() {
  const force = useAppStore(s => s.force);
  const portrait = buildForcePortrait(force);
  return (
    <div className="force-grid">
      {force.map(f => {
        const val = Number(f.val) || 0;
        const w = Math.max(0, Math.min(10, val)) * 10;
        const band = classifyForceBand(val);
        const isDominant = !!portrait && portrait.topName === f.name;
        return (
          <div
            className={`force-row force-row-${band}${isDominant ? ' is-dominant' : ''}`}
            key={f.name}
            data-ref={`shishen.${f.name}`}
            data-tip={`shishen.${f.name}`}
          >
            <div className="force-name">{f.name}</div>
            <div className="force-bar-wrap">
              <div className={`force-bar force-bar-${band}`} style={{ width: w + '%' }} />
            </div>
            <div className="force-val">{val.toFixed(1)}</div>
            {isDominant ? <div className="force-dominant-badge" aria-hidden="true">主导</div> : null}
          </div>
        );
      })}
    </div>
  );
}

function simplifyGuardNote(note) {
  // Strip LLM-facing instructions like "，分析时不能笼统称..."
  return String(note || '').replace(/[，,]\s*分析时.*/s, '').trim();
}

export function GuardList() {
  const guards = useAppStore(s => s.guards);
  return (
    <ul className="guard-list">
      {guards.map((g, i) => (
        <li key={i}>{simplifyGuardNote(g.note)}</li>
      ))}
    </ul>
  );
}
