import { useEffect, useState } from 'react';
import { removeWhiteBg } from './removeWhiteBg.js';

export function useWhiteBgRemovedImage(src) {
  const [state, setState] = useState({ src: null, processedSrc: null });

  useEffect(() => {
    if (!src) return undefined;

    let cancelled = false;
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => {
      if (!cancelled) setState({ src, processedSrc: removeWhiteBg(img) });
    };
    img.onerror = () => {
      if (!cancelled) setState({ src, processedSrc: src });
    };
    img.src = src;

    return () => {
      cancelled = true;
    };
  }, [src]);

  if (!src) return null;
  return state.src === src ? state.processedSrc : null;
}
