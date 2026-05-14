const WIDTHS = ['94%', '82%', '68%', '88%', '76%', '91%', '63%'];

function lineWidth(index) {
  return WIDTHS[index % WIDTHS.length];
}

export function SkeletonLines({ count = 3, offset = 0 }) {
  return (
    <div className="skeleton-lines" aria-hidden="true">
      {Array.from({ length: count }, (_, index) => (
        <div
          key={index}
          className="skeleton-line skeleton-pulse"
          style={{ width: lineWidth(index + offset) }}
        />
      ))}
    </div>
  );
}

export function SkeletonProgress({ label, subLabel, linesCount = 3, offset = 0 }) {
  return (
    <div className="skeleton-progress fade-in" aria-live="polite">
      {label ? <div className="skeleton-progress-label">{label}</div> : null}
      {subLabel ? <div className="skeleton-progress-sublabel">{subLabel}</div> : null}
      <SkeletonLines count={linesCount} offset={offset} />
    </div>
  );
}
