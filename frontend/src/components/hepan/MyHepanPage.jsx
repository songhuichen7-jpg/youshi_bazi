import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAppStore } from '../../store/useAppStore.js';

// /hepan/mine 页保留路由做向后兼容（老书签 / 旧 UI 链接）但其内容已收敛到
// CardWorkspace 合盘 tab 里。任何来访 → 重定向到 /app 并切到 card+hepan 视图。
export default function MyHepanPage() {
  const navigate = useNavigate();
  const setView = useAppStore(s => s.setView);
  const setCardModeHint = useAppStore(s => s.setCardModeHint);
  useEffect(() => {
    setView('card');
    setCardModeHint('hepan');
    navigate('/app', { replace: true });
  }, [navigate, setView, setCardModeHint]);
  return null;
}
