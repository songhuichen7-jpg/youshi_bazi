// frontend/src/lib/hepanParticles.js
//
// p5.js instance-mode sketch for hepan card-aura particle field.
// Particles spawn from card edges: 50% stay as aura, 50% venture
// to center with behavior determined by relationship type.

import p5 from 'p5';

const CATEGORY_INDEX = {
  '天作搭子': 0,
  '镜像搭子': 1,
  '同频搭子': 2,
  '滋养搭子': 3,
  '火花搭子': 4,
  '互补搭子': 2,
};

function hex2rgb(h) {
  return {
    r: parseInt(h.slice(1, 3), 16),
    g: parseInt(h.slice(3, 5), 16),
    b: parseInt(h.slice(5, 7), 16),
  };
}

export function createHepanSketch(containerEl, width, height, leftGlow, rightGlow, category) {
  const relType = CATEGORY_INDEX[category] ?? 2;

  const sketch = (p) => {
    const W = width;
    const H = height;
    const LC = { x: 0, y: 0, w: Math.round(W * 0.23), h: H };
    const RC = { x: W - Math.round(W * 0.23), y: 0, w: Math.round(W * 0.23), h: H };
    const MID = W / 2;
    const N = 100;
    let particles = [];

    function spawn(side) {
      const card = side === 'left' ? LC : RC;
      const edgeX = side === 'left' ? card.x + card.w : card.x;
      const edgeY = p.random(card.y + 10, card.y + card.h - 10);
      const reach = p.random(0, 1);
      return {
        x: edgeX + (side === 'left' ? p.random(5, 30) : p.random(-30, -5)),
        y: edgeY,
        originX: edgeX,
        originY: edgeY,
        side,
        far: reach > 0.5,
        reach,
        size: p.random(1.5, 4),
        alpha: p.random(100, 220),
        phase: p.random(p.TWO_PI),
        speed: p.random(0.004, 0.01),
        vx: 0,
        vy: 0,
      };
    }

    function initParticles() {
      particles = [];
      for (let i = 0; i < N; i++) {
        particles.push(spawn(i < N / 2 ? 'left' : 'right'));
      }
    }

    p.setup = () => {
      const c = p.createCanvas(W, H);
      c.style('position', 'absolute');
      c.style('inset', '0');
      c.style('z-index', '15');
      c.style('pointer-events', 'none');
      initParticles();
    };

    function moveDestined(pt, t) {
      const orbitR = 40 + pt.reach * 60;
      const tx = MID + p.cos(t * 1.5 + pt.phase) * orbitR * 0.5;
      const ty = H / 2 + p.sin(t * 1.2 + pt.phase) * orbitR * 0.6 + (pt.phase - p.PI) * 20;
      pt.vx += (tx - pt.x) * 0.006;
      pt.vy += (ty - pt.y) * 0.006;
    }

    function moveMirror(pt, t) {
      const dir = pt.side === 'left' ? -1 : 1;
      const dist = 40 + p.sin(t * 1.5 + pt.phase) * 30;
      const tx = MID + dir * dist;
      const ty = H / 2 + p.sin(t * 1.2 + pt.phase * 0.8) * 60 + (pt.phase - p.PI) * 20;
      pt.vx += (tx - pt.x) * 0.008;
      pt.vy += (ty - pt.y) * 0.008;
    }

    function moveSameFreq(pt, t) {
      const dir = pt.side === 'left' ? -1 : 1;
      const sharedWave = p.sin(t * 2) * 40;
      const tx = MID + dir * (50 + pt.reach * 30) + p.sin(t + pt.phase * 0.2) * 15;
      const ty = H / 2 + sharedWave + p.cos(t * 0.5 + pt.phase) * 15 + (pt.phase - p.PI) * 20;
      pt.vx += (tx - pt.x) * 0.007;
      pt.vy += (ty - pt.y) * 0.007;
    }

    function moveNurture(pt, t) {
      if (pt.side === 'left') {
        const progress = (p.sin(t * 0.6 + pt.phase) + 1) / 2;
        const tx = p.lerp(LC.x + LC.w + 30, RC.x - 10, progress);
        const ty = H / 2 + p.sin(t + pt.phase) * 40 + (pt.phase - p.PI) * 20;
        pt.vx += (tx - pt.x) * 0.005;
        pt.vy += (ty - pt.y) * 0.005;
        pt.vx += 0.06;
      } else {
        const tx = RC.x - 15 + p.sin(t + pt.phase) * 20;
        const ty = pt.originY + p.cos(t * 0.8 + pt.phase) * 15;
        pt.vx += (tx - pt.x) * 0.015;
        pt.vy += (ty - pt.y) * 0.015;
      }
    }

    function moveSpark(pt, t) {
      const lc = hex2rgb(leftGlow);
      const rc = hex2rgb(rightGlow);
      const cycle = (p.sin(t * 1.2 + pt.phase) + 1) / 2;
      if (cycle < 0.45) {
        const tx = MID + p.random(-5, 5);
        const ty = H / 2 + (pt.phase - p.PI) * 25;
        pt.vx += (tx - pt.x) * 0.012;
        pt.vy += (ty - pt.y) * 0.008;
      } else {
        const card = pt.side === 'left' ? LC : RC;
        const edgeX = pt.side === 'left' ? card.x + card.w + 20 : card.x - 20;
        pt.vx += (edgeX - pt.x) * 0.006;
        pt.vy += (pt.originY - pt.y) * 0.004;
      }
      if (p.abs(pt.x - MID) < 30) {
        pt.vx += p.random(-0.8, 0.8);
        pt.vy += p.random(-0.6, 0.6);
        const mc = { r: (lc.r + rc.r) / 2, g: (lc.g + rc.g) / 2, b: (lc.b + rc.b) / 2 };
        p.noStroke();
        p.fill(p.min(255, mc.r + 120), p.min(255, mc.g + 120), p.min(255, mc.b + 120), p.random(80, 180));
        p.ellipse(pt.x + p.random(-6, 6), pt.y + p.random(-6, 6), p.random(1, 2.5));
      }
    }

    const moveFns = [moveDestined, moveMirror, moveSameFreq, moveNurture, moveSpark];

    function drawCardGlow(card, c) {
      const isLeft = card === LC;
      const edgeX = isLeft ? card.x + card.w : card.x;
      for (let i = 0; i < 3; i++) {
        const spread = (i + 1) * 15;
        p.noStroke();
        p.fill(c.r, c.g, c.b, 8 - i * 2);
        p.rect(
          isLeft ? edgeX : edgeX - spread,
          card.y + 10,
          spread,
          card.h - 20,
          8,
        );
      }
    }

    function drawLinks(lc, rc) {
      const mr = (lc.r + rc.r) / 2;
      const mg = (lc.g + rc.g) / 2;
      const mb = (lc.b + rc.b) / 2;
      for (let i = 0; i < particles.length; i++) {
        if (!particles[i].far) continue;
        for (let j = i + 1; j < particles.length; j++) {
          if (!particles[j].far || particles[i].side === particles[j].side) continue;
          const dx = particles[i].x - particles[j].x;
          const dy = particles[i].y - particles[j].y;
          const d = p.sqrt(dx * dx + dy * dy);
          if (d < 50) {
            p.stroke(mr, mg, mb, p.map(d, 0, 50, 35, 0));
            p.strokeWeight(0.4);
            p.line(particles[i].x, particles[i].y, particles[j].x, particles[j].y);
          }
        }
      }
    }

    p.draw = () => {
      p.clear();
      const lc = hex2rgb(leftGlow);
      const rc = hex2rgb(rightGlow);
      if (particles.length === 0) initParticles();

      drawCardGlow(LC, lc);
      drawCardGlow(RC, rc);

      for (const pt of particles) {
        const t = p.frameCount * pt.speed;
        if (!pt.far) {
          const card = pt.side === 'left' ? LC : RC;
          const edgeX = pt.side === 'left' ? card.x + card.w : card.x;
          const hoverDist = 8 + pt.reach * 40;
          const dir = pt.side === 'left' ? 1 : -1;
          const tx = edgeX + dir * hoverDist + p.sin(t + pt.phase) * 12;
          const ty = pt.originY + p.cos(t * 0.7 + pt.phase) * 20;
          pt.vx += (tx - pt.x) * 0.02;
          pt.vy += (ty - pt.y) * 0.02;
        } else {
          moveFns[relType](pt, t);
        }
        pt.vx *= 0.94;
        pt.vy *= 0.94;
        pt.x += pt.vx;
        pt.y += pt.vy;
        pt.y = p.constrain(pt.y, 20, H - 20);

        let c = pt.side === 'left' ? lc : rc;
        const maxDist = MID - (pt.side === 'left' ? LC.x + LC.w : RC.x - MID);
        let crossover = 0;
        if (pt.side === 'left' && pt.x > MID) crossover = p.map(pt.x, MID, RC.x, 0, 0.6);
        if (pt.side === 'right' && pt.x < MID) crossover = p.map(pt.x, MID, LC.x + LC.w, 0, 0.6);
        crossover = p.constrain(crossover, 0, 0.6);
        const other = pt.side === 'left' ? rc : lc;
        const dr = p.lerp(c.r, other.r, crossover);
        const dg = p.lerp(c.g, other.g, crossover);
        const db = p.lerp(c.b, other.b, crossover);
        const distFromHome = p.abs(pt.x - pt.originX);
        const distFade = p.map(distFromHome, 0, maxDist, 1, 0.4);
        const a = pt.alpha * distFade;

        p.noStroke();
        p.fill(dr, dg, db, a * 0.12);
        p.ellipse(pt.x, pt.y, pt.size * 5);
        p.fill(dr, dg, db, a);
        p.ellipse(pt.x, pt.y, pt.size);
      }

      if (relType === 0 || relType === 2) {
        drawLinks(lc, rc);
      }
    };
  };

  const instance = new p5(sketch, containerEl);
  return instance;
}
