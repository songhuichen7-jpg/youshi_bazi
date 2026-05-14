import wx from 'weixin-js-sdk';
import { latestCardIllustrationSrc } from './cardArt.js';

export function isWeChatBrowser(ua = (typeof navigator !== 'undefined' ? navigator.userAgent : '')) {
  return /MicroMessenger/i.test(ua);
}

export function buildShareConfig(kind, card, origin) {
  const base = `${origin}/card/${card.share_slug}`;
  const imgUrl = new URL(latestCardIllustrationSrc(card.illustration_url), origin).toString();
  if (kind === 'friend') {
    return {
      title: `我是${card.cosmic_name}·${card.suffix} -- 你是什么？`,
      desc: '有时人格图鉴，3 秒看到你的类型',
      link: `${base}?from=share_friend`,
      imgUrl,
    };
  }
  return {
    title: `我是${card.cosmic_name} -- 点开看你是什么`,
    link: `${base}?from=share_timeline`,
    imgUrl,
  };
}

export async function copyShareLink(url, {
  clipboard = (typeof navigator !== 'undefined' ? navigator.clipboard : null),
  notify = (message) => alert(message),
} = {}) {
  async function fallbackCopy() {
    if (typeof document === 'undefined') return false;
    try {
      const ta = document.createElement('textarea');
      ta.value = url;
      ta.setAttribute?.('readonly', '');
      ta.style.position = 'fixed';
      ta.style.top = '-1000px';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand?.('copy') === true;
      document.body.removeChild(ta);
      return ok;
    } catch {
      return false;
    }
  }

  try {
    if (!clipboard || typeof clipboard.writeText !== 'function') {
      throw new Error('clipboard unavailable');
    }
    await clipboard.writeText(url);
    notify('链接已复制');
    return true;
  } catch {
    const copied = await fallbackCopy();
    notify(copied ? '链接已复制' : '复制失败，请手动复制浏览器地址栏链接');
    return copied;
  }
}

export async function configureWxShare(card, { onShare } = {}) {
  if (!isWeChatBrowser()) return;

  const currentUrl = window.location.href.split('#')[0];
  const resp = await fetch(`/api/wx/jsapi-ticket?url=${encodeURIComponent(currentUrl)}`);
  const sig = await resp.json();

  wx.config({
    debug: false,
    appId: sig.appId,
    timestamp: sig.timestamp,
    nonceStr: sig.nonceStr,
    signature: sig.signature,
    jsApiList: ['updateAppMessageShareData', 'updateTimelineShareData'],
  });

  wx.ready(() => {
    const origin = window.location.origin;
    wx.updateAppMessageShareData({
      ...buildShareConfig('friend', card, origin),
      success: () => onShare && onShare('wx_friend'),
    });
    wx.updateTimelineShareData({
      ...buildShareConfig('timeline', card, origin),
      success: () => onShare && onShare('wx_timeline'),
    });
  });
}
