// frontend/src/components/card/TimeSegmentPicker.jsx
import { TIME_SEGMENTS } from './timeSegments.js';

export { TIME_SEGMENTS };  // re-export for anyone already importing from the .jsx

export function TimeSegmentPicker({ selected, onSelect }) {
  return (
    <div className="time-segment-picker" role="radiogroup">
      {TIME_SEGMENTS.map(seg => (
        <button
          key={seg.label}
          type="button"
          role="radio"
          aria-checked={selected === seg.label}
          className={selected === seg.label ? 'is-selected' : ''}
          onClick={() => onSelect(seg.label)}
        >
          <span className="label">{seg.label}</span>
          <span className="range">{seg.range}</span>
        </button>
      ))}
    </div>
  );
}
