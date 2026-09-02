window.Chrome = window.Chrome || {};

// Part A — BootSequence

window.Chrome.createBootOverlay = function () {
  var E = window.Theme.EXTRA || {};
  var overlay = document.createElement('div');
  overlay.style.cssText = 'position:fixed;inset:0;background:' + (E.bgRoot||'#0a0b0f') + ';z-index:99999;display:flex;flex-direction:column;justify-content:center;align-items:center;overflow:hidden;';
  var box = document.createElement('div');
  box.style.cssText = 'width:min(640px,90vw);height:min(420px,70vh);overflow:hidden;border:1px solid ' + (E.glassBorder||'#22242c') + ';border-radius:8px;background:rgba(0,0,0,0.4);padding:20px 24px;font-family:' + (E.fontMono||'monospace') + ';font-size:13px;line-height:1.7;color:' + (E.lime||'#bef264') + ';';
  box.id = 'boot-log';
  overlay.appendChild(box);
  var lines = [
    '> DELTA COMMAND CENTER v2.4.1',
    '> initializing kernel ...... OK',
    '> mounting bridge [127.0.0.1:8088] ...... OK',
    '> loading market feed ...... OK',
    '> loading strategies [12] ...... OK',
    '> arming execution engine ...... OK',
    '> handshake secure handshake complete',
    '> systems nominal. awaiting input_'
  ];
  lines.forEach(function (t) { var d = document.createElement('div'); d.textContent = ''; d.dataset.full = t; box.appendChild(d); });
  return overlay;
};

window.Chrome.runBoot = function (onDone) {
  var overlay = window.Chrome.createBootOverlay();
  document.body.appendChild(overlay);
  var log = overlay.querySelector('#boot-log');
  var children = log.children;
  var li = 0, ci = 0;
  function typeLine(i, cb) {
    var node = children[i]; var full = node.dataset.full;
    function step() { ci++; node.textContent = full.slice(0, ci); if (ci < full.length) { setTimeout(step, 8); } else { node.textContent = full + '_'; cb(); } }
    setTimeout(step, 180);
  }
  function next() {
    if (li >= children.length) {
      setTimeout(function () { overlay.style.transition = 'opacity 500ms'; overlay.style.opacity = '0'; setTimeout(function () { if (overlay.parentNode) overlay.parentNode.removeChild(overlay); if (onDone) onDone(); }, 520); }, 400);
      return;
    }
    ci = 0; typeLine(li, function () { li++; next(); });
  }
  next();
};

// Part B — Overlay primitives

window.Chrome.createScanline = function () {
  var E = window.Theme.EXTRA || {};
  var el = document.createElement('div');
  el.style.cssText = 'position:fixed;inset:0;pointer-events:none;z-index:1;opacity:' + (E.scanlineOpacity!=null?E.scanlineOpacity:0.03) + ';background:repeating-linear-gradient(0deg,transparent 0px,transparent 3px,rgba(190,242,100,0.7) 3px,rgba(190,242,100,0.7) 4px);';
  return el;
};

window.Chrome.createGrid = function () {
  var E = window.Theme.EXTRA || {};
  var el = document.createElement('div');
  el.style.cssText = 'position:fixed;inset:0;pointer-events:none;z-index:1;opacity:' + (E.gridOpacity!=null?E.gridOpacity:0.06) + ';background-image:linear-gradient(rgba(190,242,100,0.5) 1px,transparent 1px),linear-gradient(90deg,rgba(190,242,100,0.5) 1px,transparent 1px);background-size:44px 44px;';
  return el;
};

window.Chrome.createNoise = function () {
  var E = window.Theme.EXTRA || {};
  var canvas = document.createElement('canvas');
  canvas.width = 200; canvas.height = 200;
  canvas.style.cssText = 'position:fixed;inset:0;pointer-events:none;z-index:1;opacity:' + (E.noiseOpacity!=null?E.noiseOpacity:0.035) + ';';
  var ctx = canvas.getContext('2d');
  var img = ctx.createImageData(canvas.width, canvas.height);
  for (var i = 0; i < img.data.length; i += 4) { var v = Math.floor(Math.random()*255); img.data[i]=v; img.data[i+1]=v; img.data[i+2]=v; img.data[i+3]=40; }
  ctx.putImageData(img, 0, 0);
  canvas.style.backgroundImage = 'url(' + canvas.toDataURL() + ')';
  return canvas;
};

// Part C — ParticleField

(function () {
  var _canvas = null, _raf = null, _resize = null;
  var _particles = [], _ctx = null;
  function mkCanvas() {
    var E = window.Theme.EXTRA || {};
    var c = document.createElement('canvas');
    c.style.cssText = 'position:fixed;inset:0;pointer-events:none;z-index:0;';
    _ctx = c.getContext('2d');
    function size() { c.width = window.innerWidth; c.height = window.innerHeight; }
    size(); _resize = size; window.addEventListener('resize', _resize);
    var n = E.particleCount || 40;
    _particles = [];
    for (var i=0;i<n;i++) _particles.push({ x: Math.random()*(c.width||800), y: Math.random()*(c.height||600), vx:(Math.random()-0.5)*0.5, vy:(Math.random()-0.5)*0.5, r:E.particleRadius||1.5 });
    return c;
  }
  function frame() {
    var c = _canvas, ctx = _ctx, E = window.Theme.EXTRA || {};
    if (!c || !ctx) return;
    ctx.clearRect(0,0,c.width,c.height);
    var maxD = E.particleMaxDist || 150;
    for (var L=0;L<_particles.length;L++){ var p=_particles[L]; p.x+=p.vx; p.y+=p.vy; if(p.x<0)p.x=c.width; if(p.x>c.width)p.x=0; if(p.y<0)p.y=c.height; if(p.y>c.height)p.y=0; }
    for (var i=0;i<_particles.length;i++){ var a=_particles[i]; ctx.beginPath(); ctx.arc(a.x,a.y,a.r,0,Math.PI*2); ctx.fillStyle='rgba(190,242,100,0.6)'; ctx.fill(); for(var j=i+1;j<_particles.length;j++){ var b=_particles[j]; var dx=a.x-b.x, dy=a.y-b.y; var d=Math.sqrt(dx*dx+dy*dy); if(d<maxD){ ctx.beginPath(); ctx.moveTo(a.x,a.y); ctx.lineTo(b.x,b.y); ctx.strokeStyle='rgba(190,242,100,'+(0.15*(1-d/maxD)).toFixed(3)+')'; ctx.stroke(); } } }
    _raf = requestAnimationFrame(frame);
  }
  window.Chrome.createParticleField = function () { if (!_canvas) { _canvas = mkCanvas(); frame(); } return _canvas; };
  window.Chrome.stopParticles = function () { if (_raf) cancelAnimationFrame(_raf); _raf = null; };
  window.Chrome.startParticles = function () { if (_canvas && !_raf) frame(); };
})();

// Part D — DataStream

window.Chrome.createDataStream = function () {
  var E = window.Theme.EXTRA || {};
  var svgNS = 'http://www.w3.org/2000/svg';
  var svg = document.createElementNS(svgNS, 'svg');
  svg.setAttribute('width', '100%'); svg.setAttribute('height', '3');
  svg.style.cssText = 'position:fixed;left:0;right:0;top:0;pointer-events:none;z-index:3;opacity:0.5;';
  var defs = document.createElementNS(svgNS, 'defs');
  var lf = document.createElementNS(svgNS, 'linearGradient');
  lf.setAttribute('id', 'ds-grad'); lf.setAttribute('x1','0'); lf.setAttribute('y1','0'); lf.setAttribute('x2','1'); lf.setAttribute('y2','0');
  var s1 = document.createElementNS(svgNS, 'stop'); s1.setAttribute('offset','0'); s1.setAttribute('stop-color','transparent');
  var s2 = document.createElementNS(svgNS, 'stop'); s2.setAttribute('offset','0.5'); s2.setAttribute('stop-color', E.lime||'#bef264');
  var s3 = document.createElementNS(svgNS, 'stop'); s3.setAttribute('offset','1'); s3.setAttribute('stop-color','transparent');
  lf.appendChild(s1); lf.appendChild(s2); lf.appendChild(s3); defs.appendChild(lf); svg.appendChild(defs);
  var line = document.createElementNS(svgNS, 'line');
  line.setAttribute('x1','0'); line.setAttribute('y1','1.5'); line.setAttribute('x2','100%'); line.setAttribute('y2','1.5');
  line.setAttribute('stroke','url(#ds-grad)'); line.setAttribute('stroke-width','1');
  line.setAttribute('stroke-dasharray','8 12'); line.style.animation = 'dashmove ' + (E.streamDuration||24) + 's linear infinite';
  svg.appendChild(line);
  if (!document.querySelector('style[data-ds]')) {
    var st = document.createElement('style'); st.setAttribute('data-ds','');
    st.textContent = '@keyframes dashmove { to { stroke-dashoffset: -2000; } }';
    document.head.appendChild(st);
  }
  return svg;
};

// Part E — CursorFX + TiltCard

window.Chrome.initCursor = function () {
  if (window.Chrome._cursorInit) return; window.Chrome._cursorInit = true;
  var E = window.Theme.EXTRA || {};
  var dot = document.createElement('div');
  dot.style.cssText = 'position:fixed;left:0;top:0;width:6px;height:6px;border-radius:50%;background:'+(E.lime||'#bef264')+';pointer-events:none;z-index:9999;transform:translate(-50%,-50%);box-shadow:0 0 6px '+(E.limeDim||'#bef26444')+';';
  var ring = document.createElement('div');
  ring.style.cssText = 'position:fixed;left:0;top:0;width:26px;height:26px;border-radius:50%;border:1px solid '+(E.lime||'#bef264')+';pointer-events:none;z-index:9998;transform:translate(-50%,-50%);opacity:0.5;transition:width 0.1s,height 0.1s;';
  document.body.appendChild(dot); document.body.appendChild(ring);
  document.documentElement.classList.add('cc-cursor');
  var mx=0,my=0,rx=0,ry=0,down=false, ticking=false;
  document.addEventListener('mousemove', function(e){ mx=e.clientX; my=e.clientY; if(!ticking){ ticking=true; requestAnimationFrame(loop); } });
  document.addEventListener('mousedown', function(){ down=true; ring.style.width='18px'; ring.style.height='18px'; });
  document.addEventListener('mouseup', function(){ down=false; ring.style.width='26px'; ring.style.height='26px'; });
  document.addEventListener('mouseleave', function(){ dot.style.opacity='0'; ring.style.opacity='0'; });
  document.addEventListener('mouseenter', function(){ dot.style.opacity='1'; ring.style.opacity='0.5'; });
  function loop(){ rx += (mx-rx)*0.18; ry += (my-ry)*0.18; dot.style.left=mx+'px'; dot.style.top=my+'px'; ring.style.left=rx+'px'; ring.style.top=ry+'px'; ticking=false; }
};

window.Chrome.initTilt = function () {
  if (window.Chrome._tiltInit) return; window.Chrome._tiltInit = true;
  var E = window.Theme.EXTRA || {};
  var maxT = E.tiltMaxDeg || 8;
  document.addEventListener('mousemove', function (ev) {
    var el = ev.target && ev.target.closest ? ev.target.closest('.tilt-card') : null;
    if (el) {
      var r = el.getBoundingClientRect();
      var px = (ev.clientX - r.left) / r.width - 0.5;
      var py = (ev.clientY - r.top) / r.height - 0.5;
      el.style.transform = 'perspective(700px) rotateY(' + (px*maxT).toFixed(2) + 'deg) rotateX(' + (-py*maxT).toFixed(2) + 'deg)';
    } else {
      document.querySelectorAll('.tilt-card').forEach(function (c) { if (c.style.transform) c.style.transform = ''; });
    }
  });
};

// Part F — AudioEngine

(function () {
  var ctx = null, master = null, muted = false;
  try { muted = localStorage.getItem('cc_audio_muted') === '1'; } catch (e) {}
  function ensure() {
    if (!ctx) {
      var AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return null;
      ctx = new AC(); master = ctx.createGain(); master.gain.value = muted ? 0 : 0.15; master.connect(ctx.destination);
    }
    if (ctx.state === 'suspended') ctx.resume();
    return ctx;
  }
  function osc(type, f0, f1, dur, when, vol) {
    var c = ensure(); if (!c || muted) return;
    var t = c.currentTime + (when || 0);
    var o = c.createOscillator(); o.type = type || 'sine';
    o.frequency.setValueAtTime(f0, t); if (f1) o.frequency.exponentialRampToValueAtTime(f1, t+dur);
    var g = c.createGain(); g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(vol||0.12, t+0.01); g.gain.exponentialRampToValueAtTime(0.0001, t+dur);
    o.connect(g); g.connect(master); o.start(t); o.stop(t+dur+0.02);
  }
  window.Chrome = window.Chrome || {};
  window.Chrome.audio = {
    arm: function () { ensure(); return !!ctx; },
    blip: function (freq) { osc('square', freq || 880, null, 0.08, 0, 0.05); },
    ping: function () { osc('sine', 660, 990, 0.09, 0, 0.08); osc('sine', 990, 1320, 0.12, 0.09, 0.07); },
    mute: function () { muted = true; try { localStorage.setItem('cc_audio_muted','1'); } catch(e){} if (master) master.gain.value = 0; },
    unmute: function () { muted = false; try { localStorage.setItem('cc_audio_muted','0'); } catch(e){} if (master) master.gain.value = 0.15; },
    toggle: function () { if (muted) this.unmute(); else this.mute(); return muted; },
    isMuted: function () { return muted; },
    get muted() { return muted; },
  };
})();
