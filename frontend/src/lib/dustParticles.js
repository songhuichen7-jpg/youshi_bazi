// frontend/src/lib/dustParticles.js
//
// p5.js instance-mode dust particle sketch for card front.
// 40 white semi-transparent particles drift upward with gentle sin oscillation.

import p5 from 'p5';

export function createDustSketch(containerEl, width, height) {
  const sketch = (p) => {
    const particles = [];
    const N = 40;

    p.setup = () => {
      const c = p.createCanvas(width, height);
      c.style('position', 'absolute');
      c.style('inset', '0');
      c.style('z-index', '2');
      c.style('pointer-events', 'none');
      for (let i = 0; i < N; i++) {
        particles.push({
          x: p.random(0, width),
          y: p.random(0, height),
          size: p.random(1, 3),
          alpha: p.random(12, 38),
          speedX: p.random(-0.3, 0.3),
          speedY: p.random(-0.5, -0.1),
          phase: p.random(p.TWO_PI),
        });
      }
    };

    p.draw = () => {
      p.clear();
      for (const pt of particles) {
        pt.x += pt.speedX + p.sin(p.frameCount * 0.01 + pt.phase) * 0.2;
        pt.y += pt.speedY;
        if (pt.y < -5) pt.y = height + 5;
        if (pt.x < -5) pt.x = width + 5;
        if (pt.x > width + 5) pt.x = -5;
        p.noStroke();
        p.fill(255, 255, 255, pt.alpha);
        p.ellipse(pt.x, pt.y, pt.size);
      }
    };
  };

  const instance = new p5(sketch, containerEl);
  return instance;
}
