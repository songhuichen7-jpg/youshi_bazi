import { RichText } from './RefChip';

export default function GuaCard({ data }) {
  if (!data) return null;
  const { symbol, name, upper, lower, drawnAt, guaci, daxiang, question, body, streaming } = data;

  return (
    <div className="gua-card">
      {question && (
        <div className="gua-card-question">
          「{question}」的卦象
        </div>
      )}
      <div className="gua-card-header">
        <span className="gua-card-symbol">{symbol}</span>
        <div>
          <div className="serif" style={{ fontSize: 18 }}>{name}</div>
          <div className="muted" style={{ fontSize: 11 }}>上{upper} · 下{lower}</div>
          {drawnAt && <div className="muted" style={{ fontSize: 10, marginTop: 2 }}>{drawnAt}</div>}
        </div>
      </div>
      <div className="gua-card-texts">
        <div><b>卦辞：</b>{guaci}</div>
        <div style={{ marginTop: 4 }}><b>大象：</b>{daxiang}</div>
      </div>
      <div className="gua-card-body">
        {body
          ? <RichText text={body} />
          : <span className="muted">{streaming ? '生成中…' : ''}</span>
        }
      </div>
    </div>
  );
}
