// frontend/src/components/card/UpgradeCTA.jsx
import { Link } from 'react-router-dom';

export function UpgradeCTA({ typeId }) {
  return (
    <aside className="upgrade-cta">
      <p className="hook">继续深读</p>
      <p className="detail">4 份深度报告 + AI 命盘对话</p>
      <Link to={`/?type_id=${typeId}`} className="cta-link">
        打开工作台
      </Link>
    </aside>
  );
}
