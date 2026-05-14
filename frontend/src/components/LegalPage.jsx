import { Link, useNavigate, useParams } from 'react-router-dom';

import { BrandLogo } from './brand/BrandLogo.jsx';

// 整站名字"有时"来自《传道书》3:1–8 — 这个 about 页就把它当锚点，
// 让用户一进来先读完再讲产品。terms / privacy 是功能性文档，不掺哲学。
const ABOUT_VERSE = `凡事都有定期，
天下万务都有定时。

生有时，死有时。栽种有时，拔出所栽种的，也有时。
杀戮有时，医治有时。拆毁有时，建造有时。
哭有时，笑有时。哀恸有时，跳舞有时。
抛掷石头有时，堆聚石头有时。怀抱有时，不怀抱有时。
寻找有时，失落有时。保守有时，舍弃有时。
撕裂有时，缝补有时。静默有时，言语有时。
喜爱有时，恨恶有时。争战有时，和好有时。`;

const PAGES = {
  about: {
    title: '关于「有时」',
    eyebrow: '凡 事 都 有 定 期 · 命 有 其 时',
    verse: ABOUT_VERSE,
    verseSource: '——《传道书》3:1–8',
    verseCaption: '「有时」这个名字，就出自这里。',
    sections: [
      ['我们相信什么',
        '命理不是预言，而是节律。\n' +
        '人有自己的春夏秋冬。\n' +
        '这个工具的角色，是帮你看清当下站在哪一段时序里 —\n' +
        '该播种的时候不迟疑，该静默的时候不焦虑。'],
      ['它能做什么',
        '· 排盘：完整的八字 + 大运 + 流年 + 神煞\n' +
        '· 解读：性格 / 事业 / 财运 / 婚姻 / 健康，都是按你的盘说\n' +
        '· 对话：你问，它答。问到模糊处会主动起一卦\n' +
        '· 古籍：自动检索古籍原文，给参考依据'],
      ['它不能做什么',
        '· 不预言时间 — 时序是粗粒度的，不是日历\n' +
        '· 不替你做选择 — 命理只描述势能，决定权在你\n' +
        '· 不代替专业咨询 — 健康 / 法律 / 重大决策请先找专业人士'],
      ['作者',
        '一个相信"命由心造"的写代码的人。\n' +
        '做这个工具，是因为命理学被神秘化太久 —\n' +
        '它本来该像散文一样被读。'],
    ],
  },
  terms: {
    title: '服务条款',
    sections: [
      ['一、服务说明',
        '「有时」由作者本人提供，目前处于内测阶段。\n' +
        '我们不保证服务持续可用，也不保证模型回答的准确性。'],
      ['二、用户行为',
        '使用本服务即表示你同意：\n' +
        '· 不在排盘 / 对话中输入他人的真实身份信息\n' +
        '· 不利用本服务进行算命收费、风水迷信传播等\n' +
        '· 不对服务做反向工程 / 自动化大量调用\n' +
        '· 不上传违法违规内容'],
      ['三、生成内容',
        'AI 输出的所有内容（排盘解读 / 流年判语 / 卦象 / 古籍引述）\n' +
        '仅供个人参考，不构成任何形式的预测、建议或承诺。\n' +
        '凡基于此做出的人生决策，作者不承担责任。'],
      ['四、账号',
        '你创建的账号属于你。\n' +
        '若长期不登录或违反本条款，作者保留停用账号的权利。\n' +
        '你随时可以在用户中心选择"注销账号"。'],
      ['五、变更',
        '我们可能不时调整这些条款；重大变更会在登录后提示。'],
    ],
  },
  privacy: {
    title: '隐私政策',
    sections: [
      ['我们收集什么',
        '· 手机号（登录用，加密存储）\n' +
        '· 你输入的出生信息（用于排盘）\n' +
        '· 你的对话内容（用于上下文，不用于训练）\n' +
        '· 头像图片（上传后只服务于你的展示）'],
      ['我们不收集什么',
        '· 不要求 / 不存储任何身份证、银行卡等敏感信息\n' +
        '· 不收集精确定位\n' +
        '· 不接入第三方广告 SDK'],
      ['加密',
        '· 你的命盘数据用 per-user 加密密钥（DEK）封装；\n' +
        '  服务器密钥不解密，作者也不能直接读\n' +
        '· 注销账号时执行 crypto-shred — 物理上让数据再也读不回'],
      ['留存',
        '· 你主动删除的命盘 / 对话立即软删除，30 天后清理\n' +
        '· 你注销账号时，所有数据立即不可恢复'],
      ['第三方',
        '· LLM 调用经火山引擎 / DeepSeek 等模型服务商 — 仅传必要 prompt\n' +
        '· 短信经云片 / 阿里云等服务商发送'],
      ['联系',
        '隐私问题请发邮件至：songhuichen7@gmail.com'],
    ],
  },
};

// react-router v6 会在 history.state 上挂 `idx`：>0 表示还有历史可退；
// 等于 0（或 undefined）表示这是会话第一页，navigate(-1) 是哑火，
// 兜底跳首页 — 这样用户直接 deep-link 进 /legal/* 也有出口。
function goBackOrHome(navigate) {
  const idx = typeof window !== 'undefined'
    ? window.history.state?.idx
    : undefined;
  if (typeof idx === 'number' && idx > 0) navigate(-1);
  else navigate('/', { replace: true });
}

export default function LegalPage() {
  const { slug } = useParams();
  const navigate = useNavigate();
  const page = PAGES[slug];

  if (!page) {
    return (
      <div className="screen active legal-screen">
        <div className="legal-wrap">
          <button className="legal-back" type="button" onClick={() => goBackOrHome(navigate)}>← 返回</button>
          <Link to="/" className="legal-brand-link" aria-label="回到「有时」首页">
            <BrandLogo size="small" className="legal-brand" />
          </Link>
          <h1 className="serif legal-title">页面不存在</h1>
          <p className="legal-section-body">你访问的法律页面不在「有时」的资料里。</p>
        </div>
      </div>
    );
  }

  return (
    <div className="screen active legal-screen">
      <div className="legal-wrap">
        <button className="legal-back" type="button" onClick={() => goBackOrHome(navigate)}>← 返回</button>
        {/* 进 /legal/* 的人有时是直接 deep-link 来的；这个 logo 同时是品牌
            标识 + 兜底"回首页"入口，与 user-center 弹层底部的纯文本链接区分开。 */}
        <Link to="/" className="legal-brand-link" aria-label="回到「有时」首页">
          <BrandLogo size="small" className="legal-brand" />
        </Link>
        {page.eyebrow ? <div className="legal-eyebrow">{page.eyebrow}</div> : null}
        <h1 className="serif legal-title">{page.title}</h1>
        <div className="legal-meta">最近更新：2026.05</div>

        {page.verse ? (
          <blockquote className="legal-verse serif">
            <p className="legal-verse-body">{page.verse}</p>
            {page.verseSource ? (
              <footer className="legal-verse-source">{page.verseSource}</footer>
            ) : null}
            {page.verseCaption ? (
              <div className="legal-verse-caption">{page.verseCaption}</div>
            ) : null}
          </blockquote>
        ) : null}

        <div className="legal-body">
          {page.sections.map(([heading, body]) => (
            <section key={heading} className="legal-section">
              <h2 className="legal-section-heading">{heading}</h2>
              <p className="legal-section-body">{body}</p>
            </section>
          ))}
        </div>
      </div>
    </div>
  );
}
