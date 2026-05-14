"""Plan 7.3 — static lookup tables for 用神 engine.

Three independent classical methods:
- TIAOHOU       — 穷通宝鉴 调候用神, keyed by (rizhu_gan, month_zhi)
- GEJU_RULES    — 子平真诠 格局取用, keyed by 格局 name
- FUYI_CASES    — 滴天髓 扶抑用神, ordered list matched by dayStrength

Data is sourced from `classics/qiongtong-baojian/` and
`classics/ziping-zhenquan/` files, populated in Tasks 2-4.

Plan 7.3 spec: docs/superpowers/specs/2026-04-20-yongshen-engine-design.md
"""
from __future__ import annotations

# Filled in Task 2
TIAOHOU: dict[tuple[str, str], dict] = {
    # 甲木 (12 months)
    ('甲', '寅'): {
        'name': '丙火',
        'supporting': '癸水',
        'note': '初春余寒，得丙癸逢，名寒木向阳',
        'source': '穷通宝鉴·论甲木·正月',
    },
    ('甲', '卯'): {
        'name': '庚金',
        'supporting': '戊土',
        'note': '木旺阳刃，庚金得所，财资杀方贵',
        'source': '穷通宝鉴·论甲木·二月',
    },
    ('甲', '辰'): {
        'name': '庚金',
        'supporting': '壬水',
        'note': '木气相竭，先取庚金，次用壬水',
        'source': '穷通宝鉴·论甲木·三月',
    },
    ('甲', '巳'): {
        'name': '癸水',
        'supporting': '丁火',
        'note': '甲木退气，丙火司权，先癸后丁',
        'source': '穷通宝鉴·论甲木·四月',
    },
    ('甲', '午'): {
        'name': '癸水',
        'supporting': '丁火',
        'note': '木性虚焦，五月先癸后丁，庚金次之',
        'source': '穷通宝鉴·论甲木·五月',
    },
    ('甲', '未'): {
        'name': '丁火',
        'supporting': '庚金',
        'note': '三伏生寒，先丁后庚，无癸亦可',
        'source': '穷通宝鉴·论甲木·六月',
    },
    ('甲', '申'): {
        'name': '丁火',
        'supporting': '庚金',
        'note': '木性枯槁，丁火为尊，庚金不可少',
        'source': '穷通宝鉴·论甲木·七月',
    },
    ('甲', '酉'): {
        'name': '丁火',
        'supporting': '丙火',
        'note': '木囚金旺，丁火为先，次用丙火',
        'source': '穷通宝鉴·论甲木·八月',
    },
    ('甲', '戌'): {
        'name': '丁火 / 癸水',
        'supporting': '庚金',
        'note': '木星凋零，专用丁癸，见戊透则贵',
        'source': '穷通宝鉴·论甲木·九月',
    },
    ('甲', '亥'): {
        'name': '庚金 / 丁火',
        'supporting': '丙火',
        'note': '十月甲木，庚丁为要，丙火次之',
        'source': '穷通宝鉴·论甲木·十月',
    },
    ('甲', '子'): {
        'name': '丁火',
        'supporting': '庚金',
        'note': '木性生寒，丁先庚后，丙火佐之',
        'source': '穷通宝鉴·论甲木·十一月',
    },
    ('甲', '丑'): {
        'name': '庚金',
        'supporting': '丁火',
        'note': '天寒气冻，先用庚劈甲，丁火次之',
        'source': '穷通宝鉴·论甲木·十二月',
    },

    # 乙木 (12 months)
    ('乙', '寅'): {
        'name': '丙火',
        'supporting': '癸水',
        'note': '余寒未解，非丙不暖，癸水滋根为辅',
        'source': '穷通宝鉴·论乙木·正月',
    },
    ('乙', '卯'): {
        'name': '丙火',
        'supporting': '癸水',
        'note': '阳气渐升，以丙为君，癸为臣佐木',
        'source': '穷通宝鉴·论乙木·二月',
    },
    ('乙', '辰'): {
        'name': '癸水',
        'supporting': '丙火',
        'note': '阳气愈炽，先癸后丙，最忌己庚并见',
        'source': '穷通宝鉴·论乙木·三月',
    },
    ('乙', '巳'): {
        'name': '癸水',
        'supporting': '辛金',
        'note': '四月专取癸水为尊，辛透佐癸为清',
        'source': '穷通宝鉴·论乙木·四月',
    },
    ('乙', '午'): {
        'name': '癸水 / 丙火',
        'supporting': None,
        'note': '上半月用癸，下半月丙癸齐用',
        'source': '穷通宝鉴·论乙木·五月',
    },
    ('乙', '未'): {
        'name': '丙火',
        'supporting': '癸水',
        'note': '木性且寒，柱多金水，丙火为尊',
        'source': '穷通宝鉴·论乙木·六月',
    },
    ('乙', '申'): {
        'name': '己土',
        'supporting': '丙火',
        'note': '庚金乘令，喜己土为用，丙火辅之',
        'source': '穷通宝鉴·论乙木·七月',
    },
    ('乙', '酉'): {
        'name': '癸水 / 丙火',
        'supporting': None,
        'note': '白露后癸滋桂萼，秋分后喜丙向阳',
        'source': '穷通宝鉴·论乙木·八月',
    },
    ('乙', '戌'): {
        'name': '癸水',
        'supporting': '辛金',
        'note': '根枯叶落，必赖癸水滋养，辛金发源',
        'source': '穷通宝鉴·论乙木·九月',
    },
    ('乙', '亥'): {
        'name': '丙火',
        'supporting': '戊土',
        'note': '壬水司令，取丙为用，戊土次之',
        'source': '穷通宝鉴·论乙木·十月',
    },
    ('乙', '子'): {
        'name': '丙火',
        'supporting': None,
        'note': '花木寒冻，专用丙火解冻回春',
        'source': '穷通宝鉴·论乙木·十一月',
    },
    ('乙', '丑'): {
        'name': '丙火',
        'supporting': '己土',
        'note': '冬至后木寒，得丙透干，己土透更贵',
        'source': '穷通宝鉴·论乙木·十二月',
    },

    # 丙火 (12 months)
    ('丙', '寅'): {
        'name': '壬水',
        'supporting': '庚金',
        'note': '三阳开泰，取壬为尊，庚金佐之',
        'source': '穷通宝鉴·论丙火·正月',
    },
    ('丙', '卯'): {
        'name': '壬水',
        'supporting': '己土',
        'note': '阳气舒升，专用壬水，无壬姑取己土',
        'source': '穷通宝鉴·论丙火·二月',
    },
    ('丙', '辰'): {
        'name': '壬水',
        'supporting': '甲木',
        'note': '土重晦光，用壬不可离，甲木为辅',
        'source': '穷通宝鉴·论丙火·三月',
    },
    ('丙', '巳'): {
        'name': '壬水',
        'supporting': '庚金',
        'note': '建禄炎炎，宜专用壬，得庚发水源',
        'source': '穷通宝鉴·论丙火·四月',
    },
    ('丙', '午'): {
        'name': '壬水',
        'supporting': '庚金',
        'note': '五月专用壬水，丁多兼看癸，申水亦妙',
        'source': '穷通宝鉴·论丙火·五月',
    },
    ('丙', '未'): {
        'name': '壬水',
        'supporting': '庚金',
        'note': '退气生寒，壬水为用，取庚辅佐',
        'source': '穷通宝鉴·论丙火·六月',
    },
    ('丙', '申'): {
        'name': '壬水',
        'supporting': '戊土',
        'note': '太阳转西，仍用壬水，壬多取戊制',
        'source': '穷通宝鉴·论丙火·七月',
    },
    ('丙', '酉'): {
        'name': '壬水',
        'supporting': '癸水',
        'note': '日近黄昏，仍用壬辅映，无壬癸亦可',
        'source': '穷通宝鉴·论丙火·八月',
    },
    ('丙', '戌'): {
        'name': '甲木',
        'supporting': '壬水',
        'note': '火气愈退，必须先甲后壬，癸亦可佐',
        'source': '穷通宝鉴·论丙火·九月',
    },
    ('丙', '亥'): {
        'name': '甲木 / 戊土 / 庚金',
        'supporting': '壬水',
        'note': '太阳失令，甲戊庚显，火旺再取壬',
        'source': '穷通宝鉴·论丙火·十月',
    },
    ('丙', '子'): {
        'name': '壬水',
        'supporting': '戊土',
        'note': '冬至一阳生，壬水为最，戊土佐之',
        'source': '穷通宝鉴·论丙火·十一月',
    },
    ('丙', '丑'): {
        'name': '壬水',
        'supporting': '甲木',
        'note': '气进二阳，喜壬为用，土多不可少甲',
        'source': '穷通宝鉴·论丙火·十二月',
    },

    # 丁火 (12 months)
    ('丁', '寅'): {
        'name': '庚金',
        'supporting': '壬水',
        'note': '甲木当权，非庚不能劈甲引丁，水亦不可无',
        'source': '穷通宝鉴·论丁火·正月',
    },
    ('丁', '卯'): {
        'name': '庚金',
        'supporting': '甲木',
        'note': '湿乙伤丁，先庚后甲，庚甲两透最清',
        'source': '穷通宝鉴·论丁火·二月',
    },
    ('丁', '辰'): {
        'name': '甲木',
        'supporting': '庚金',
        'note': '戊土司令，先用甲引丁制土，次看庚金',
        'source': '穷通宝鉴·论丁火·三月',
    },
    ('丁', '巳'): {
        'name': '庚金',
        'supporting': '甲木',
        'note': '乘旺取甲引丁，必用庚劈甲成木火通明',
        'source': '穷通宝鉴·论丁火·四月',
    },
    ('丁', '午'): {
        'name': '庚金 / 壬水',
        'supporting': '甲木',
        'note': '建禄火盛，火局取庚壬，无火局再用甲',
        'source': '穷通宝鉴·论丁火·五月',
    },
    ('丁', '未'): {
        'name': '甲木',
        'supporting': '壬水',
        'note': '阴柔退气，专取甲木，壬水次之',
        'source': '穷通宝鉴·论丁火·六月',
    },
    ('丁', '申'): {
        'name': '甲木 / 丙火',
        'supporting': '庚金',
        'note': '七月甲丙并用，申中有庚，仍取庚劈甲',
        'source': '穷通宝鉴·论丁火·七月',
    },
    ('丁', '酉'): {
        'name': '甲木 / 丙火 / 庚金',
        'supporting': None,
        'note': '三秋分论言八月甲丙庚皆用，无甲乙亦可',
        'source': '穷通宝鉴·论丁火·八月',
    },
    ('丁', '戌'): {
        'name': '甲木 / 庚金',
        'supporting': None,
        'note': '三秋分论言九月专用甲庚，甲透文书清贵',
        'source': '穷通宝鉴·论丁火·九月',
    },
    ('丁', '亥'): {
        'name': '甲木 / 庚金',
        'supporting': '癸水 / 戊土',
        'note': '三冬丁火微寒，甲木为尊，庚金佐之',
        'source': '穷通宝鉴·论丁火·十月',
    },
    ('丁', '子'): {
        'name': '甲木',
        'supporting': '庚金',
        'note': '仲冬虽有从杀支格，调候仍甲尊庚佐',
        'source': '穷通宝鉴·论丁火·十一月',
    },
    ('丁', '丑'): {
        'name': '甲木 / 庚金',
        'supporting': '癸水 / 戊土',
        'note': '三冬总论言甲为尊，庚佐之，癸戊权宜',
        'source': '穷通宝鉴·论丁火·十二月',
    },

    # 戊土 (12 months)
    ('戊', '寅'): {
        'name': '丙火',
        'supporting': '甲木',
        'note': '三春正月先丙后甲，癸水又次之',
        'source': '穷通宝鉴·论戊土·正月',
    },
    ('戊', '卯'): {
        'name': '丙火',
        'supporting': '甲木',
        'note': '三春二月先丙后甲，癸水又次之',
        'source': '穷通宝鉴·论戊土·二月',
    },
    ('戊', '辰'): {
        'name': '甲木',
        'supporting': '丙火',
        'note': '三月司权，先甲后丙，癸水又次之',
        'source': '穷通宝鉴·论戊土·三月',
    },
    ('戊', '巳'): {
        'name': '甲木',
        'supporting': '丙火 / 癸水',
        'note': '阳升寒藏，先用甲疏，丙癸为佐',
        'source': '穷通宝鉴·论戊土·四月',
    },
    ('戊', '午'): {
        'name': '壬水',
        'supporting': '甲木',
        'note': '仲夏火炎，先看壬水，次取甲木',
        'source': '穷通宝鉴·论戊土·五月',
    },
    ('戊', '未'): {
        'name': '癸水',
        'supporting': '丙火 / 甲木',
        'note': '夏干枯燥，先看癸水，次用丙甲',
        'source': '穷通宝鉴·论戊土·六月',
    },
    ('戊', '申'): {
        'name': '丙火',
        'supporting': '癸水',
        'note': '阳入寒出，先丙后癸，甲木次之',
        'source': '穷通宝鉴·论戊土·七月',
    },
    ('戊', '酉'): {
        'name': '丙火',
        'supporting': '癸水',
        'note': '金泄身寒，赖丙照暖，喜癸滋润',
        'source': '穷通宝鉴·论戊土·八月',
    },
    ('戊', '戌'): {
        'name': '甲木 / 癸水',
        'supporting': '丙火',
        'note': '土旺先甲次癸，见金则先癸后丙',
        'source': '穷通宝鉴·论戊土·九月',
    },
    ('戊', '亥'): {
        'name': '甲木',
        'supporting': '丙火',
        'note': '时值小阳，先用甲木，次取丙火',
        'source': '穷通宝鉴·论戊土·十月',
    },
    ('戊', '子'): {
        'name': '丙火',
        'supporting': '甲木',
        'note': '严寒冰冻，丙火为专，甲木为佐',
        'source': '穷通宝鉴·论戊土·十一月',
    },
    ('戊', '丑'): {
        'name': '丙火',
        'supporting': '甲木',
        'note': '严寒冰冻，丙火为专，甲木为佐',
        'source': '穷通宝鉴·论戊土·十二月',
    },

    # 己土 (12 months)
    ('己', '寅'): {
        'name': '丙火',
        'supporting': '戊土',
        'note': '田园犹冻，丙火为尊，壬多须戊作堤',
        'source': '穷通宝鉴·论己土·正月',
    },
    ('己', '卯'): {
        'name': '甲木',
        'supporting': '癸水',
        'note': '阳气渐升，先取甲疏，次取癸润',
        'source': '穷通宝鉴·论己土·二月',
    },
    ('己', '辰'): {
        'name': '丙火',
        'supporting': '癸水 / 甲木',
        'note': '栽培禾稼，先丙后癸，随用甲疏',
        'source': '穷通宝鉴·论己土·三月',
    },
    ('己', '巳'): {
        'name': '癸水',
        'supporting': '丙火',
        'note': '三夏总论，取癸为要，次用丙火',
        'source': '穷通宝鉴·论己土·四月',
    },
    ('己', '午'): {
        'name': '癸水',
        'supporting': '丙火',
        'note': '三夏总论，取癸为要，次用丙火',
        'source': '穷通宝鉴·论己土·五月',
    },
    ('己', '未'): {
        'name': '癸水',
        'supporting': '丙火',
        'note': '三夏总论，取癸为要，次用丙火',
        'source': '穷通宝鉴·论己土·六月',
    },
    ('己', '申'): {
        'name': '癸水',
        'supporting': '丙火',
        'note': '三秋总论，癸先丙后，辛金辅癸',
        'source': '穷通宝鉴·论己土·七月',
    },
    ('己', '酉'): {
        'name': '癸水',
        'supporting': '丙火',
        'note': '三秋总论，癸先丙后，辛金辅癸',
        'source': '穷通宝鉴·论己土·八月',
    },
    ('己', '戌'): {
        'name': '甲木',
        'supporting': '癸水',
        'note': '九月土盛，宜甲木疏之，余皆酌用',
        'source': '穷通宝鉴·论己土·九月',
    },
    ('己', '亥'): {
        'name': '丙火',
        'supporting': '戊土 / 甲木',
        'note': '初冬壬旺，丙为尊，壬盛再取戊制',
        'source': '穷通宝鉴·论己土·十月',
    },
    ('己', '子'): {
        'name': '丙火',
        'supporting': '甲木',
        'note': '湿泥寒冻，非丙暖不生，甲木参酌',
        'source': '穷通宝鉴·论己土·十一月',
    },
    ('己', '丑'): {
        'name': '丙火',
        'supporting': '甲木',
        'note': '湿泥寒冻，非丙暖不生，甲木参酌',
        'source': '穷通宝鉴·论己土·十二月',
    },

    # 庚金 (12 months)
    ('庚', '寅'): {
        'name': '丙火',
        'supporting': '甲木',
        'note': '木旺寒未除，先用丙暖，须甲疏泄',
        'source': '穷通宝鉴·论庚金·正月',
    },
    ('庚', '卯'): {
        'name': '丁火',
        'supporting': '甲木',
        'note': '二月专用丁火，借甲引丁，借庚劈甲',
        'source': '穷通宝鉴·论庚金·二月',
    },
    ('庚', '辰'): {
        'name': '甲木',
        'supporting': '丁火',
        'note': '土旺金顽，先甲后丁，二者少一不真',
        'source': '穷通宝鉴·论庚金·三月',
    },
    ('庚', '巳'): {
        'name': '壬水',
        'supporting': '戊土 / 丙火',
        'note': '群金生夏，先壬次戊，丙火佐之',
        'source': '穷通宝鉴·论庚金·四月',
    },
    ('庚', '午'): {
        'name': '壬水',
        'supporting': '癸水',
        'note': '丁火旺烈，专用壬水，癸又次之',
        'source': '穷通宝鉴·论庚金·五月',
    },
    ('庚', '未'): {
        'name': '丁火',
        'supporting': '甲木',
        'note': '三伏生寒，先用丁火，次取甲木',
        'source': '穷通宝鉴·论庚金·六月',
    },
    ('庚', '申'): {
        'name': '丁火',
        'supporting': '甲木',
        'note': '刚锐极矣，专用丁炼，次取甲引丁',
        'source': '穷通宝鉴·论庚金·七月',
    },
    ('庚', '酉'): {
        'name': '丁火 / 甲木',
        'supporting': '丙火',
        'note': '刚锐未退，用丁用甲，丙火不可少',
        'source': '穷通宝鉴·论庚金·八月',
    },
    ('庚', '戌'): {
        'name': '甲木',
        'supporting': '壬水',
        'note': '土厚埋金，宜先用甲疏，后用壬洗',
        'source': '穷通宝鉴·论庚金·九月',
    },
    ('庚', '亥'): {
        'name': '丁火 / 丙火',
        'supporting': '甲木',
        'note': '水冷性寒，非丁莫造，非丙不暖',
        'source': '穷通宝鉴·论庚金·十月',
    },
    ('庚', '子'): {
        'name': '丁火 / 甲木',
        'supporting': '丙火',
        'note': '天气严寒，仍取丁甲，次取丙火照暖',
        'source': '穷通宝鉴·论庚金·十一月',
    },
    ('庚', '丑'): {
        'name': '丙火',
        'supporting': '丁火 / 甲木',
        'note': '寒冻湿泥，先取丙火，次丁甲并参',
        'source': '穷通宝鉴·论庚金·十二月',
    },

    # 辛金 (12 months)
    ('辛', '寅'): {
        'name': '己土',
        'supporting': '壬水',
        'note': '正月先己后壬，庚为佐，丙火参看',
        'source': '穷通宝鉴·论辛金·正月',
    },
    ('辛', '卯'): {
        'name': '壬水',
        'supporting': '甲木',
        'note': '阳和之际，壬水为尊，得甲制土方妙',
        'source': '穷通宝鉴·论辛金·二月',
    },
    ('辛', '辰'): {
        'name': '壬水',
        'supporting': '甲木',
        'note': '母旺子相，先壬后甲，壬甲两透则贵',
        'source': '穷通宝鉴·论辛金·三月',
    },
    ('辛', '巳'): {
        'name': '壬水',
        'supporting': '甲木',
        'note': '首夏喜壬洗淘，得甲制戊更清澈',
        'source': '穷通宝鉴·论辛金·四月',
    },
    ('辛', '午'): {
        'name': '己土 / 壬水',
        'supporting': '癸水',
        'note': '阴柔失令，须己壬兼用，癸水亦可',
        'source': '穷通宝鉴·论辛金·五月',
    },
    ('辛', '未'): {
        'name': '壬水',
        'supporting': '庚金',
        'note': '己土当权，先用壬水，取庚佐之',
        'source': '穷通宝鉴·论辛金·六月',
    },
    ('辛', '申'): {
        'name': '壬水',
        'supporting': '甲木 / 戊土',
        'note': '壬水为尊，甲戊酌用，癸水不可为用',
        'source': '穷通宝鉴·论辛金·七月',
    },
    ('辛', '酉'): {
        'name': '壬水',
        'supporting': '甲木',
        'note': '旺极专用壬水淘洗，见甲制土方妙',
        'source': '穷通宝鉴·论辛金·八月',
    },
    ('辛', '戌'): {
        'name': '壬水',
        'supporting': '甲木',
        'note': '须甲疏土，壬泄旺金，先壬后甲',
        'source': '穷通宝鉴·论辛金·九月',
    },
    ('辛', '亥'): {
        'name': '壬水',
        'supporting': '丙火',
        'note': '时值小阳，先用壬水，次取丙火',
        'source': '穷通宝鉴·论辛金·十月',
    },
    ('辛', '子'): {
        'name': '壬水 / 丙火',
        'supporting': '戊土',
        'note': '寒冬雨露，壬丙两透，不见戊癸为佳',
        'source': '穷通宝鉴·论辛金·十一月',
    },
    ('辛', '丑'): {
        'name': '丙火',
        'supporting': '壬水',
        'note': '寒冻之极，先丙后壬，戊己次之',
        'source': '穷通宝鉴·论辛金·十二月',
    },

    # 壬水 (12 months)
    ('壬', '寅'): {
        'name': '庚金',
        'supporting': '丙火',
        'note': '正月专用庚金，以丙为佐，戊土随酌',
        'source': '穷通宝鉴·论壬水·正月',
    },
    ('壬', '卯'): {
        'name': '戊土',
        'supporting': '辛金',
        'note': '二月先戊后辛，庚金又次之',
        'source': '穷通宝鉴·论壬水·二月',
    },
    ('壬', '辰'): {
        'name': '甲木',
        'supporting': '庚金',
        'note': '季土司权，先用甲疏，次取庚金',
        'source': '穷通宝鉴·论壬水·三月',
    },
    ('壬', '巳'): {
        'name': '壬水',
        'supporting': '辛金',
        'note': '水弱极矣，专取比肩，次取辛金发源',
        'source': '穷通宝鉴·论壬水·四月',
    },
    ('壬', '午'): {
        'name': '癸水',
        'supporting': '庚金',
        'note': '丁旺壬弱，取癸为用，取庚为佐',
        'source': '穷通宝鉴·论壬水·五月',
    },
    ('壬', '未'): {
        'name': '辛金',
        'supporting': '甲木',
        'note': '六月先辛后甲，次取癸水扶身',
        'source': '穷通宝鉴·论壬水·六月',
    },
    ('壬', '申'): {
        'name': '戊土',
        'supporting': '丁火',
        'note': '七月专用戊土，丁火为佐制庚',
        'source': '穷通宝鉴·论壬水·七月',
    },
    ('壬', '酉'): {
        'name': '甲木',
        'supporting': '庚金',
        'note': '八月专用甲木，庚金次之',
        'source': '穷通宝鉴·论壬水·八月',
    },
    ('壬', '戌'): {
        'name': '甲木',
        'supporting': '丙火',
        'note': '九月专用甲木，次用丙火',
        'source': '穷通宝鉴·论壬水·九月',
    },
    ('壬', '亥'): {
        'name': '戊土 / 丙火',
        'supporting': '庚金',
        'note': '十月专用戊丙，庚金次之',
        'source': '穷通宝鉴·论壬水·十月',
    },
    ('壬', '子'): {
        'name': '戊土 / 丙火',
        'supporting': None,
        'note': '阳刃帮身，丙戊并用，先戊后丙',
        'source': '穷通宝鉴·论壬水·十一月',
    },
    ('壬', '丑'): {
        'name': '丙火',
        'supporting': '甲木',
        'note': '上半月下半月皆用丙火，甲木为佐',
        'source': '穷通宝鉴·论壬水·十二月',
    },

    # 癸水 (12 months)
    ('癸', '寅'): {
        'name': '辛金',
        'supporting': '庚金 / 丙火',
        'note': '辛金为主，庚金次之，丙火亦不可少',
        'source': '穷通宝鉴·论癸水·正月',
    },
    ('癸', '卯'): {
        'name': '庚金',
        'supporting': '辛金',
        'note': '乙木司令，专以庚金为用，辛金次之',
        'source': '穷通宝鉴·论癸水·二月',
    },
    ('癸', '辰'): {
        'name': '丙火',
        'supporting': '辛金 / 甲木',
        'note': '清明后专丙，谷雨后丙火仍用辛甲',
        'source': '穷通宝鉴·论癸水·三月',
    },
    ('癸', '巳'): {
        'name': '辛金',
        'supporting': '庚金',
        'note': '四月喜辛金为用，无辛则用庚金',
        'source': '穷通宝鉴·论癸水·四月',
    },
    ('癸', '午'): {
        'name': '庚金 / 辛金',
        'supporting': '壬水',
        'note': '至弱无根，庚辛为本，宜见壬水并用',
        'source': '穷通宝鉴·论癸水·五月',
    },
    ('癸', '未'): {
        'name': '壬水 / 癸水 / 庚金 / 辛金',
        'supporting': None,
        'note': '上半月宜比劫，下半月专用庚辛',
        'source': '穷通宝鉴·论癸水·六月',
    },
    ('癸', '申'): {
        'name': '丁火',
        'supporting': '甲木',
        'note': '母旺子相，必取丁火为用，甲木助燄',
        'source': '穷通宝鉴·论癸水·七月',
    },
    ('癸', '酉'): {
        'name': '辛金',
        'supporting': '丙火',
        'note': '正金白水清，故取辛金为用，丙火佐之',
        'source': '穷通宝鉴·论癸水·八月',
    },
    ('癸', '戌'): {
        'name': '辛金',
        'supporting': '甲木',
        'note': '失令无根，辛金发源，要比肩滋甲制戊',
        'source': '穷通宝鉴·论癸水·九月',
    },
    ('癸', '亥'): {
        'name': '庚金 / 辛金',
        'supporting': None,
        'note': '旺中有弱，因亥摇木，宜用庚辛',
        'source': '穷通宝鉴·论癸水·十月',
    },
    ('癸', '子'): {
        'name': '丙火',
        'supporting': '辛金',
        'note': '值冰冻时，专用丙火解冻，辛金滋扶',
        'source': '穷通宝鉴·论癸水·十一月',
    },
    ('癸', '丑'): {
        'name': '丙火',
        'supporting': '壬水',
        'note': '寒极成冰，宜丙解冻，壬水辅阳光',
        'source': '穷通宝鉴·论癸水·十二月',
    },
}

def _scores(force: dict) -> dict:
    """Support both direct tests ({scores}) and analyzer runtime ({scoresNormalized})."""
    return force.get('scores') or force.get('scoresNormalized') or {}


def _has_any(force: dict, *names: str, floor: float = 3.0) -> bool:
    scores = _scores(force)
    return any(scores.get(name, 0) > floor for name in names)


def _has_all(force: dict, names: tuple[str, ...], floor: float = 3.0) -> bool:
    scores = _scores(force)
    return all(scores.get(name, 0) > floor for name in names)


# Filled in Task 3
GEJU_RULES: dict[str, list[dict]] = {
    '正官格': [
        {
            'condition': lambda f, gh: _has_any(f, '正财', '偏财'),
            'name': '财（生官）',
            'sub_pattern': '财官同辉',
            'note': '官星得财滋扶，清纯而贵',
            'source': '子平真诠·论正官',
        },
        {
            'condition': lambda f, gh: _has_any(f, '正印', '偏印'),
            'name': '印（护官）',
            'sub_pattern': '官印相生',
            'note': '官逢印绶护卫，最怕伤官',
            'source': '子平真诠·论正官',
        },
        {
            'condition': lambda f, gh: True,
            'name': '正官',
            'note': '孤官无辅，须防伤官破格',
            'source': '子平真诠·论正官',
        },
    ],
    '七杀格': [
        {
            'condition': lambda f, gh: _has_any(f, '食神'),
            'name': '食神（制杀）',
            'sub_pattern': '食制',
            'note': '杀旺得食神制服，威权可取',
            'source': '子平真诠·论偏官',
        },
        {
            'condition': lambda f, gh: _has_any(f, '正印', '偏印'),
            'name': '印（化杀）',
            'sub_pattern': '印化',
            'note': '杀重无制之时，赖印绶化权',
            'source': '子平真诠·论偏官',
        },
        {
            'condition': lambda f, gh: True,
            'name': '七杀（无制无化）',
            'sub_pattern': '裸杀',
            'note': '七杀失制失化，偏烈为忧',
            'source': '子平真诠·论偏官',
        },
    ],
    '食神格': [
        {
            'condition': lambda f, gh: _has_any(f, '正财', '偏财'),
            'name': '财（食神生财）',
            'sub_pattern': '食神生财',
            'note': '食神吐秀生财，富局最真',
            'source': '子平真诠·论食神',
        },
        {
            'condition': lambda f, gh: _has_any(f, '七杀'),
            'name': '食神（制杀）',
            'sub_pattern': '食神制杀',
            'note': '食神带杀而清，制伏反成权',
            'source': '子平真诠·论食神',
        },
        {
            'condition': lambda f, gh: True,
            'name': '食神',
            'note': '食神有气，贵在清纯不杂',
            'source': '子平真诠·论食神',
        },
    ],
    '伤官格': [
        {
            'condition': lambda f, gh: _has_any(f, '正印', '偏印'),
            'name': '印（伤官配印）',
            'sub_pattern': '伤官配印',
            'note': '伤官旺而佩印，文章显达',
            'source': '子平真诠·论伤官',
        },
        {
            'condition': lambda f, gh: _has_any(f, '正财', '偏财'),
            'name': '财（伤官生财）',
            'sub_pattern': '伤官生财',
            'note': '伤官吐秀生财，最利求财',
            'source': '子平真诠·论伤官',
        },
        {
            'condition': lambda f, gh: True,
            'name': '伤官',
            'note': '伤官虽俊，终须财印调停',
            'source': '子平真诠·论伤官',
        },
    ],
    '正财格': [
        {
            'condition': lambda f, gh: _has_any(f, '正官', '七杀'),
            'name': '官（财生官）',
            'sub_pattern': '财官相辅',
            'note': '财旺生官，富贵两全',
            'source': '子平真诠·论财',
        },
        {
            'condition': lambda f, gh: _has_any(f, '食神', '伤官'),
            'name': '食伤（生财）',
            'sub_pattern': '食伤生财',
            'note': '财透得食伤转生，富气更真',
            'source': '子平真诠·论财',
        },
        {
            'condition': lambda f, gh: True,
            'name': '正财',
            'note': '财星当令，喜身健能任之',
            'source': '子平真诠·论财',
        },
    ],
    '偏财格': [
        {
            'condition': lambda f, gh: _has_any(f, '正官', '七杀'),
            'name': '官（财生官）',
            'sub_pattern': '财官相辅',
            'note': '偏财生官，慷慨而能得贵',
            'source': '子平真诠·论财',
        },
        {
            'condition': lambda f, gh: _has_any(f, '食神', '伤官'),
            'name': '食伤（生财）',
            'sub_pattern': '食伤生财',
            'note': '偏财得食伤引动，最利经商',
            'source': '子平真诠·论财',
        },
        {
            'condition': lambda f, gh: True,
            'name': '偏财',
            'note': '偏财活络，须身旺方能驾驭',
            'source': '子平真诠·论财',
        },
    ],
    '正印格': [
        {
            'condition': lambda f, gh: _has_any(f, '正官', '七杀'),
            'name': '官（官印相生）',
            'sub_pattern': '官印相生',
            'note': '印绶得官杀相生，清贵可取',
            'source': '子平真诠·论印绶',
        },
        {
            'condition': lambda f, gh: _has_any(f, '食神', '伤官'),
            'name': '食伤（泄秀）',
            'sub_pattern': '印赖食泄',
            'note': '印重身强，宜借食伤吐秀',
            'source': '子平真诠·论印绶',
        },
        {
            'condition': lambda f, gh: True,
            'name': '正印',
            'note': '印绶护身，贵在不过不偏',
            'source': '子平真诠·论印绶',
        },
    ],
    '偏印格': [
        {
            'condition': lambda f, gh: _has_any(f, '正官', '七杀'),
            'name': '官（官印相生）',
            'sub_pattern': '官印相生',
            'note': '偏印得官杀相生，亦主清贵',
            'source': '子平真诠·论印绶',
        },
        {
            'condition': lambda f, gh: _has_any(f, '食神', '伤官'),
            'name': '食伤（泄秀）',
            'sub_pattern': '枭印泄秀',
            'note': '偏印偏重，宜食伤疏泄其气',
            'source': '子平真诠·论印绶',
        },
        {
            'condition': lambda f, gh: True,
            'name': '偏印',
            'note': '偏印成格，最忌夺食太甚',
            'source': '子平真诠·论印绶',
        },
    ],
    '比肩格': [
        {
            'condition': lambda f, gh: _has_any(f, '正官', '七杀'),
            'name': '官杀（制比劫）',
            'sub_pattern': '建禄用官',
            'note': '建禄最喜官杀裁制比劫',
            'source': '子平真诠·论建禄月劫',
        },
        {
            'condition': lambda f, gh: (
                _has_any(f, '正财', '偏财')
                and _has_any(f, '食神', '伤官')
            ),
            'name': '财（食伤生财）',
            'sub_pattern': '建禄用财',
            'note': '用财须带食伤，化劫而生财',
            'source': '子平真诠·论建禄月劫',
        },
        {
            'condition': lambda f, gh: _has_any(f, '食神', '伤官'),
            'name': '食伤（泄秀）',
            'sub_pattern': '建禄食伤',
            'note': '无财官时，食伤泄秀亦可取',
            'source': '子平真诠·论建禄月劫',
        },
        {
            'condition': lambda f, gh: True,
            'name': '比肩（自立）',
            'note': '建禄无辅，专凭自身担当',
            'source': '子平真诠·论建禄月劫',
        },
    ],
    '劫财格': [
        {
            'condition': lambda f, gh: _has_any(f, '正官', '七杀'),
            'name': '官杀（制比劫）',
            'sub_pattern': '月劫用官',
            'note': '月劫尤喜官杀制服争夺',
            'source': '子平真诠·论建禄月劫',
        },
        {
            'condition': lambda f, gh: (
                _has_any(f, '正财', '偏财')
                and _has_any(f, '食神', '伤官')
            ),
            'name': '财（食伤生财）',
            'sub_pattern': '月劫用财',
            'note': '月劫用财，须借食伤化劫',
            'source': '子平真诠·论建禄月劫',
        },
        {
            'condition': lambda f, gh: _has_any(f, '食神', '伤官'),
            'name': '食伤（泄秀）',
            'sub_pattern': '月劫食伤',
            'note': '无财官时，先取食伤泄秀',
            'source': '子平真诠·论建禄月劫',
        },
        {
            'condition': lambda f, gh: True,
            'name': '劫财（自立）',
            'note': '月劫无辅，刚烈而待裁成',
            'source': '子平真诠·论建禄月劫',
        },
    ],
    '杂气月（辰戌丑未）': [
        {
            'condition': lambda f, gh: True,
            'name': '看透出十神',
            'note': '一透一用，兼透兼取，会支同参',
            'source': '子平真诠·论杂气如何取用',
        },
    ],
    '格局不清': [],
}

# Filled in Task 4
FUYI_CASES: list[dict] = [
    {
        'when': lambda f, ds: ds == '极弱',
        'name': '印 + 比劫（同扶）',
        'note': '衰者喜帮喜助，元神极弱先扶其本',
        'source': '滴天髓·衰旺·任注',
    },
    {
        'when': lambda f, ds: ds == '身弱',
        'name': '印 / 比劫',
        'note': '身衰喜帮助，取印比中有根者为先',
        'source': '滴天髓·衰旺',
    },
    {
        'when': lambda f, ds: ds == '中和',
        'name': None,
        'note': '中和为贵，无病无药不再别求扶抑',
        'source': '滴天髓·中和',
    },
    {
        'when': lambda f, ds: ds == '身强',
        'name': '官杀 / 财 / 食伤',
        'note': '旺则宜泄宜伤，择财官食伤调停',
        'source': '滴天髓·衰旺·任注',
    },
    {
        'when': lambda f, ds: ds == '极强',
        'name': '官杀 + 食伤（双泄）',
        'note': '旺极宜引其势，制泄并参以免反激',
        'source': '滴天髓·体用·任注',
    },
]
