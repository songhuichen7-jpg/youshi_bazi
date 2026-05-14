// frontend/src/lib/cardBinomials.js
//
// Specimen-card supporting data: per-type stylized "Latin binomials" + Roman
// numeral plate labels. Used by Card.jsx and HepanCard.jsx to give each
// specimen plate its scholarly index entry (e.g. "Canis samoyedus", "PLATE Ⅲ")
// underneath the cute mascot illustration. The dissonance — child-book
// illustration × scholarly typography — is the design's intentional identity.
//
// Some binomials are real biological names (萨摩耶 → Canis samoyedus); others
// are playful pseudo-Latin coined to keep the editorial rhythm. Authenticity
// is secondary to typographic feel.

const BINOMIALS = {
  '01': 'Phyllostachys germen', // 春笋 — bamboo shoot
  '02': 'Quercus glans',        // 橡子 — acorn
  '03': 'Canis samoyedus',      // 萨摩耶 — Samoyed dog
  '04': 'Herba frigida',        // 寒秀草 — winter elegance grass
  '05': 'Phoenicopterus roseus',// 火烈鸟 — flamingo
  '06': 'Tussis ardens',        // 热咳咳 — burning cough (pseudo-Latin)
  '07': 'Lampyris noctiluca',   // 萤火虫 — firefly
  '08': 'Lampas vespera',       // 小夜灯 — evening lamp (pseudo-Latin)
  '09': 'Elephas maximus',      // 大象 — Asian elephant
  '10': 'Sciurus vulgaris',     // 松鼠 — squirrel
  '11': 'Succulenta carnosa',   // 多肉 — succulent (pseudo-Latin)
  '12': 'Bradypus tridactylus', // 树懒 — three-toed sloth
  '13': 'Erinaceus europaeus',  // 刺猬 — hedgehog
  '14': 'Takifugu rubripes',    // 河豚 — pufferfish
  '15': 'Vitrum glaciale',      // 琉璃 — colored glass
  '16': 'Felis catus',          // 猫 — domestic cat
  '17': 'Lutra lutra',          // 水獭 — Eurasian otter
  '18': 'Octopus vulgaris',     // 章鱼 — common octopus
  '19': 'Aurelia aurita',       // 水母 — moon jellyfish
  '20': 'Taraxacum officinale', // 蒲公英 — dandelion
};

const ROMAN_NUMERALS = [
  '', 'Ⅰ', 'Ⅱ', 'Ⅲ', 'Ⅳ', 'Ⅴ', 'Ⅵ', 'Ⅶ', 'Ⅷ', 'Ⅸ',
  'Ⅹ', 'Ⅺ', 'Ⅻ', 'XIII', 'XIV', 'XV', 'XVI', 'XVII', 'XVIII', 'XIX', 'XX',
];

/** Return the stylized Latin binomial for a type ID like "03". */
export function binomialFor(typeId) {
  if (!typeId) return '';
  const padded = String(typeId).padStart(2, '0');
  return BINOMIALS[padded] || 'Species nondescripta';
}

/** Return the Roman numeral form of a type ID. "03" → "Ⅲ". */
export function plateNumeral(typeId) {
  if (!typeId) return '';
  const n = parseInt(typeId, 10);
  if (!Number.isFinite(n) || n < 1 || n > 20) return '';
  return ROMAN_NUMERALS[n] || '';
}

/** Strip the trailing 格 from a 格局 string. "食神格" → "食神". */
export function gejuStem(geJu) {
  if (!geJu || typeof geJu !== 'string') return '';
  return geJu.replace(/格$/, '');
}

/**
 * Pair-relation seal character. Each of the six 04a relation categories gets
 * one character stamped at the seam between the two halves of a pair card.
 * "合" is the visual / semantic default — the pair has come together.
 */
const PAIR_SEAL = {
  '天作搭子': '合',
  '镜像搭子': '鏡',
  '同频搭子': '同',
  '滋养搭子': '滋',
  '火花搭子': '火',
  '互补搭子': '補',
};

export function pairSeal(category) {
  return PAIR_SEAL[category] || '合';
}
