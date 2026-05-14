// frontend/src/components/card/CardActions.jsx
export function CardActions({
  onSave,
  onShare,
  onInvitePair,
  disabled = false,
  saveDisabled = disabled,
  shareDisabled = disabled,
  pairDisabled = disabled,
  pairOpen = false,
}) {
  return (
    <div className="card-actions">
      <button type="button" className="action-save" disabled={saveDisabled} onClick={onSave}>
        <span>01</span>
        导出图片
      </button>
      <button type="button" className="action-share" disabled={shareDisabled} onClick={onShare}>
        <span>02</span>
        复制链接
      </button>
      <button
        type="button"
        className="action-pair"
        disabled={pairDisabled}
        onClick={onInvitePair}
        aria-expanded={pairOpen}
      >
        <span>03</span>
        合盘
      </button>
    </div>
  );
}
