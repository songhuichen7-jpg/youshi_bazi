export function YoushiMark({ className = '' }) {
  return (
    <svg
      className={className}
      viewBox="0 0 100 100"
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      <circle cx="50" cy="50" r="35" fill="none" stroke="currentColor" strokeWidth="3" />
      <path d="M50 15V85" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
      <path d="M50 50L73 36" stroke="#C9A96B" strokeWidth="3" strokeLinecap="round" />
      <path
        d="M28 73C39 80 61 81 73 69"
        fill="none"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
      />
      <circle cx="50" cy="50" r="3.6" fill="currentColor" />
    </svg>
  );
}

export function BrandLogo({
  className = '',
  showWordmark = true,
  showRoman = false,
  size = 'default',
}) {
  const classes = ['brand-logo', `brand-logo-${size}`, className].filter(Boolean).join(' ');

  return (
    <span className={classes} aria-label="有时">
      <YoushiMark className="brand-logo-mark" />
      {showWordmark ? (
        <span className="brand-logo-text">
          <span className="brand-logo-cn">有时</span>
          {showRoman ? <span className="brand-logo-roman">YOUSHI</span> : null}
        </span>
      ) : null}
    </span>
  );
}
