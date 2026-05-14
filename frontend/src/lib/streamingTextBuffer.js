function defaultSchedule(callback) {
  if (typeof window !== 'undefined' && typeof window.requestAnimationFrame === 'function') {
    return window.requestAnimationFrame(callback);
  }
  return setTimeout(callback, 16);
}

function defaultCancel(frameId) {
  if (typeof window !== 'undefined' && typeof window.cancelAnimationFrame === 'function') {
    window.cancelAnimationFrame(frameId);
    return;
  }
  clearTimeout(frameId);
}

export function createStreamingTextBuffer(options = {}) {
  const schedule = options.schedule || defaultSchedule;
  const cancel = options.cancel || defaultCancel;
  let onFlush = typeof options.onFlush === 'function' ? options.onFlush : () => {};
  let pendingText = null;
  let frameId = null;

  const clearFrame = () => {
    if (frameId == null) return;
    cancel(frameId);
    frameId = null;
  };

  const emit = () => {
    frameId = null;
    if (pendingText == null) return;
    const text = pendingText;
    pendingText = null;
    onFlush(text);
  };

  return {
    push(text) {
      pendingText = String(text || '');
      if (frameId != null) return;
      frameId = schedule(emit);
    },
    flush() {
      if (pendingText == null) return;
      clearFrame();
      emit();
    },
    cancel() {
      clearFrame();
      pendingText = null;
    },
    setOnFlush(nextOnFlush) {
      if (typeof nextOnFlush === 'function') onFlush = nextOnFlush;
    },
  };
}
