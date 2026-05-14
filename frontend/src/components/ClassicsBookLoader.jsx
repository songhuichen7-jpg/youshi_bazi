import { useEffect, useRef, useState } from 'react';
import { PageFlip } from 'page-flip';
import 'page-flip/src/Style/stPageFlip.css';

const PAGE_WIDTH = 280;
const PAGE_HEIGHT = 340;
const FLIP_INTERVAL_MS = 1750;
const BOOK_SWAP_MS = 1000;

const BOOKS = [
  {
    title: '滴天髓',
    tone: '#2f4f46',
    seal: '命',
    pages: [
      ['欲识三元', '先观帝载', '五气偏全', '阴阳顺逆', '格局成败'],
      ['调候为先', '旺衰有别', '喜忌须辨', '看其气势', '取其清浊'],
      ['天道', '地道', '人道', '体用', '精神'],
      ['生方怕动', '旺处宜静', '寒暖燥湿', '进退存亡', '皆有机缄'],
    ],
  },
  {
    title: '三命通会',
    tone: '#6b4327',
    seal: '卷',
    pages: [
      ['原造化始', '论五行成', '十二支藏', '十干配合', '用神得失'],
      ['论干支', '察月令', '分格局', '审轻重', '定去留'],
      ['年为根', '月为苗', '日为花', '时为实', '通看气势'],
      ['财官印食', '伤杀枭刃', '得位成格', '失时为病', '须看制化'],
    ],
  },
  {
    title: '子平真诠',
    tone: '#3b4e5e',
    seal: '真',
    pages: [
      ['专求月令', '以日配支', '生克不同', '格局分焉', '运喜扶助'],
      ['论用神', '论相神', '论成败', '论喜忌', '论行运'],
      ['官杀有别', '印绶有情', '财须有根', '食伤吐秀', '清浊自分'],
      ['成格者贵', '破格者病', '相神得力', '忌神有制', '方可取用'],
    ],
  },
];

function usePrefersReducedMotion() {
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(() => (
    typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  ));

  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return undefined;
    const query = window.matchMedia('(prefers-reduced-motion: reduce)');

    const onChange = (event) => setPrefersReducedMotion(event.matches);
    if (query.addEventListener) {
      query.addEventListener('change', onChange);
      return () => query.removeEventListener('change', onChange);
    }

    query.addListener(onChange);
    return () => query.removeListener(onChange);
  }, []);

  return prefersReducedMotion;
}

function VerticalCopy({ lines }) {
  return (
    <div className="classics-pageflip-content">
      <div className="classics-pageflip-copy">
        {lines.map((line) => <span key={line}>{line}</span>)}
      </div>
    </div>
  );
}

function BookPages({ book }) {
  return (
    <>
      <div className="classics-pageflip-page classics-pageflip-hard" data-density="hard">
        <div className="classics-pageflip-title-slip">{book.title}</div>
        <div className="classics-pageflip-seal">{book.seal}</div>
      </div>
      {book.pages.map((page, pageIndex) => (
        <div
          className={`classics-pageflip-page ${pageIndex % 2 === 0 ? '--right' : '--left'}`}
          key={`${book.title}-${pageIndex}`}
        >
          <VerticalCopy lines={page} />
        </div>
      ))}
      <EndleafPage />
    </>
  );
}

function EndleafPage() {
  return <div className="classics-pageflip-page classics-pageflip-endleaf" aria-hidden="true" />;
}

function appendTextNode(parent, className, text) {
  const node = document.createElement('div');
  node.className = className;
  node.textContent = text;
  parent.appendChild(node);
  return node;
}

function buildCoverNode(book, withSeal = false) {
  const cover = document.createElement('div');
  cover.className = 'classics-pageflip-page classics-pageflip-hard';
  cover.dataset.density = 'hard';
  appendTextNode(cover, 'classics-pageflip-title-slip', book.title);
  if (withSeal) appendTextNode(cover, 'classics-pageflip-seal', book.seal);
  return cover;
}

function buildTextPageNode(lines, pageIndex) {
  const page = document.createElement('div');
  page.className = `classics-pageflip-page ${pageIndex % 2 === 0 ? '--right' : '--left'}`;

  const content = document.createElement('div');
  content.className = 'classics-pageflip-content';

  const copy = document.createElement('div');
  copy.className = 'classics-pageflip-copy';
  lines.forEach((line) => {
    const span = document.createElement('span');
    span.textContent = line;
    copy.appendChild(span);
  });

  content.appendChild(copy);
  page.appendChild(content);
  return page;
}

function buildEndleafNode() {
  const page = document.createElement('div');
  page.className = 'classics-pageflip-page classics-pageflip-endleaf';
  page.setAttribute('aria-hidden', 'true');
  return page;
}

function buildPageFlipNodes(book) {
  return [
    buildCoverNode(book, true),
    ...book.pages.map((page, pageIndex) => buildTextPageNode(page, pageIndex)),
    buildEndleafNode(),
  ];
}

function BookVolume({ book, index, activeIndex, exitingIndex, registerMount, reducedMotion }) {
  const isActive = index === activeIndex;
  const isExiting = index === exitingIndex;
  const showStatic = reducedMotion && index === 0;
  const classes = [
    'classics-pageflip-book',
    isActive ? 'is-active' : '',
    isExiting ? 'is-exiting' : '',
    showStatic ? 'is-static' : '',
  ].filter(Boolean).join(' ');

  return (
    <article className={classes} data-book={book.title} style={{ '--book-color': book.tone }}>
      <div className="classics-pageflip-frame" />
      <div className="classics-pageflip-mount" ref={(node) => registerMount(index, node)}>
        {reducedMotion ? (
          <div className="classics-pageflip-host">
            <BookPages book={book} />
          </div>
        ) : null}
      </div>
      <div className="classics-pageflip-label">{book.title}</div>
    </article>
  );
}

export default function ClassicsBookLoader({ isSlow = false }) {
  const reducedMotion = usePrefersReducedMotion();
  const mountRefs = useRef([]);
  const flipRefs = useRef([]);
  const activeIndexRef = useRef(0);
  const intervalRef = useRef(null);
  const resetTimeoutRef = useRef(null);
  const [activeIndex, setActiveIndex] = useState(0);
  const [exitingIndex, setExitingIndex] = useState(null);

  const registerMount = (index, node) => {
    mountRefs.current[index] = node;
  };

  useEffect(() => {
    if (reducedMotion) return undefined;

    flipRefs.current = mountRefs.current.map((mount, index) => {
      if (!mount) return null;
      const host = document.createElement('div');
      host.className = 'classics-pageflip-host';
      host.replaceChildren(...buildPageFlipNodes(BOOKS[index]));
      mount.replaceChildren(host);
      const pageFlip = new PageFlip(host, {
        width: PAGE_WIDTH,
        height: PAGE_HEIGHT,
        size: 'fixed',
        minWidth: 240,
        maxWidth: PAGE_WIDTH,
        minHeight: 292,
        maxHeight: PAGE_HEIGHT,
        drawShadow: true,
        flippingTime: 1180,
        usePortrait: false,
        startPage: 1,
        startZIndex: 10,
        autoSize: false,
        maxShadowOpacity: 0.36,
        showCover: false,
        mobileScrollSupport: false,
        useMouseEvents: false,
      });
      pageFlip.loadFromHTML(host.querySelectorAll('.classics-pageflip-page'));
      return pageFlip;
    });

    intervalRef.current = setInterval(() => {
      const currentIndex = activeIndexRef.current;
      const currentBook = flipRefs.current[currentIndex];
      if (!currentBook || currentBook.getState() !== 'read') return;

      const currentPage = currentBook.getCurrentPageIndex();
      const lastFlipStart = currentBook.getPageCount() - 3;
      if (currentPage < lastFlipStart) {
        currentBook.flipNext('bottom');
        return;
      }

      const nextIndex = (currentIndex + 1) % BOOKS.length;
      activeIndexRef.current = nextIndex;
      setExitingIndex(currentIndex);
      setActiveIndex(nextIndex);

      resetTimeoutRef.current = setTimeout(() => {
        try {
          currentBook.turnToPage(1);
        } catch {
          // PageFlip can be mid-cleanup if the component unmounts during a swap.
        }
        setExitingIndex(null);
      }, BOOK_SWAP_MS);
    }, FLIP_INTERVAL_MS);

    return () => {
      clearInterval(intervalRef.current);
      clearTimeout(resetTimeoutRef.current);
      flipRefs.current.forEach((pageFlip) => {
        try {
          pageFlip?.destroy();
        } catch {
          // The library mutates DOM during teardown; unmount cleanup should stay quiet.
        }
      });
      flipRefs.current = [];
    };
  }, [reducedMotion]);

  return (
    <div className="classics-loader" role="status" aria-label="正在翻检古籍">
      <div
        className={`classics-pageflip-stage${reducedMotion ? ' is-reduced-motion' : ''}`}
        aria-hidden="true"
      >
        <div className="classics-pageflip-desk" />
        <div className="classics-pageflip-rail">
          {BOOKS.map((book, index) => (
            <BookVolume
              key={book.title}
              book={book}
              index={index}
              activeIndex={activeIndex}
              exitingIndex={exitingIndex}
              registerMount={registerMount}
              reducedMotion={reducedMotion}
            />
          ))}
        </div>
      </div>
      <div className="classics-loader-text">
        {isSlow ? '古籍较厚，再翻一会儿' : '正在翻阅古籍'}
      </div>
    </div>
  );
}
