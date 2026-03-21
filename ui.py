"""
ui.py — OctoBot Browser Interface
====================================
Builds and launches the Gradio web UI.

Tabs
----
1. 💬 Chat        — Chat directly with OctoBot
2. 📚 Library     — Browse the markdown library OctoBot has built
3. 📋 Log         — Live feed of the autonomous agent's activity
4. 🎮 Visual      — Pixel-art octopus walking around its 2D library (HTML canvas)

The visual tab embeds a self-contained HTML/JS canvas game that:
- Renders a tiled overhead library (floor, bookshelves, desks, tables)
- Animates a pixel-art pink octopus that walks between locations
- Reacts to agent actions (reading → walks to shelf, writing → walks to desk)
- Polls a small Gradio state object to know the current action
"""

import time
import threading
import html as _html
import gradio as gr

import agent
import tools
import llm_provider
import memory as mem
import research

# ---------------------------------------------------------------------------
# Compact always-visible OctoBot canvas strip (shown above all tabs)
# ---------------------------------------------------------------------------

COMPACT_CANVAS_HTML = r"""
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap">
<div style="display:flex;align-items:center;gap:12px;background:#05000f;border:2px solid #ff2d9b;box-shadow:0 0 16px #ff2d9b55;padding:6px 12px;margin-bottom:4px;">
  <div style="position:relative;flex-shrink:0;">
    <canvas id="octo-mini" width="160" height="100" style="image-rendering:pixelated;border:2px solid #00f7ff;box-shadow:0 0 10px #00f7ff88;background:#05000f;display:block;"></canvas>
  </div>
  <div style="flex:1;min-width:0;">
    <div id="octo-mini-thought" style="font-family:'Press Start 2P',monospace;font-size:6px;color:#ff99ee;text-shadow:0 0 6px #ff2d9b;margin-bottom:5px;white-space:pre-wrap;word-break:break-word;line-height:1.7;max-height:42px;overflow:hidden;">💭 OctoBot is waking up…</div>
    <div id="octo-mini-action" style="font-family:'Press Start 2P',monospace;font-size:6px;color:#00f7ff;text-shadow:0 0 6px #00f7ff;letter-spacing:1px;">⚙ IDLE</div>
  </div>
</div>

<script>
(function(){
  const canvas = document.getElementById('octo-mini');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const TILE = 10;
  const COLS = 16, ROWS = 10;

  const T = {FLOOR:0,SHELF:1,DESK:2,WALL:3,RUG:4};
  const COLORS = {0:'#0d0830',1:'#0a0050',2:'#1a0035',3:'#030010',4:'#200040'};

  // Mini 16×10 map
  const MAP = [
    [3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3],
    [3,1,1,1,0,0,0,0,0,0,0,0,1,1,1,3],
    [3,1,1,1,0,0,2,0,0,2,0,0,1,1,1,3],
    [3,0,0,0,0,0,0,0,0,0,0,0,0,0,0,3],
    [3,0,0,0,0,4,4,4,4,0,0,0,0,0,0,3],
    [3,1,1,0,0,4,4,4,4,0,0,0,1,1,0,3],
    [3,1,1,0,0,0,0,0,0,0,0,0,1,1,0,3],
    [3,0,0,0,0,0,2,2,0,0,0,0,0,0,0,3],
    [3,0,0,0,0,0,0,0,0,0,0,0,0,0,0,3],
    [3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3],
  ];

  const WP = {
    HOME:   {x:7,y:4},
    SHELF_L:{x:2,y:2},
    SHELF_R:{x:12,y:2},
    DESK_L: {x:6,y:2},
    DESK_R: {x:9,y:2},
    DESK_B: {x:6,y:7},
    TABLE:  {x:6,y:4},
  };
  const ACTION_WP = {
    research:'TABLE', read_file:'SHELF_L', write_file:'DESK_L',
    list_files:'SHELF_R', update_notes:'DESK_B', update_tasks:'DESK_B',
  };

  function drawTile(col, row, id) {
    const px = col*TILE, py = row*TILE;
    ctx.fillStyle = COLORS[id];
    ctx.fillRect(px,py,TILE,TILE);
    if (id===1) { // shelf — book strips
      const bc=['#ff2d9b','#00f7ff','#bf00ff'];
      for(let b=0;b<3;b++){ctx.fillStyle=bc[(col+b)%3];ctx.fillRect(px+1+b*3,py+2,2,6);}
      ctx.fillStyle='#ff2d9b44';ctx.fillRect(px,py+8,TILE,1);
    }
    if(id===2){ctx.fillStyle='#bf00ff';ctx.fillRect(px+1,py+3,TILE-2,1);ctx.fillStyle='#00f7ff22';ctx.fillRect(px+2,py+4,4,4);}
    if(id===4){ctx.fillStyle='#ff2d9b44';ctx.fillRect(px+1,py+1,TILE-2,TILE-2);ctx.fillStyle='#00f7ff';ctx.fillRect(px+3,py+3,4,4);}
    if(id===0){if((col+row)%5===0){ctx.fillStyle='#00f7ff11';ctx.fillRect(px,py,TILE,1);ctx.fillRect(px,py,1,TILE);}}
  }

  function drawOcto(px,py,frame) {
    const f=frame%4, bob=(f===1||f===3)?-1:0, oy=py+bob;
    // glow
    const g=ctx.createRadialGradient(px+5,oy+5,1,px+5,oy+5,11);
    g.addColorStop(0,'#ff2d9b44'); g.addColorStop(1,'transparent');
    ctx.fillStyle=g; ctx.fillRect(px-6,oy-6,22,22);
    // body
    ctx.fillStyle='#110020'; ctx.fillRect(px+2,py+0,7,6);
    ctx.fillStyle='#ff2d9b'; ctx.fillRect(px+3,py+1,5,5);
    ctx.fillStyle='#ff80cc'; ctx.fillRect(px+4,py+1,2,1);
    // eyes
    ctx.fillStyle='#00f7ff'; ctx.fillRect(px+3,py+2,2,2); ctx.fillRect(px+6,py+2,2,2);
    ctx.fillStyle='#003344'; ctx.fillRect(px+4,py+3,1,1); ctx.fillRect(px+7,py+3,1,1);
    ctx.fillStyle='#fff'; ctx.fillRect(px+3,py+2,1,1); ctx.fillRect(px+6,py+2,1,1);
    // cheeks
    ctx.fillStyle='#ff006666'; ctx.fillRect(px+2,py+3,1,1); ctx.fillRect(px+8,py+3,1,1);
    // arms
    const ay=oy+5;
    const cols=['#ff2d9b','#00f7ff','#ff2d9b','#00f7ff'];
    const xs=[px,px+2,px+7,px+9];
    const dys=[[f%2?-1:0],[f%2?0:1],[f%2?1:0],[f%2?0:-1]];
    for(let i=0;i<4;i++){
      ctx.fillStyle=cols[i]; const dy=dys[i][0];
      ctx.fillRect(xs[i],ay,2,2); ctx.fillRect(xs[i]+(dy>0?1:dy<0?-1:0),ay+2,2,2);
    }
    // book on frame 2
    if(f===2){ctx.fillStyle='#00f7ff';ctx.fillRect(px+3,oy-2,5,2);ctx.fillStyle='#001830';ctx.fillRect(px+5,oy-2,1,2);}
  }

  let ox=WP.HOME.x*TILE, oy=WP.HOME.y*TILE;
  let tx=ox, ty=oy, frame=0, ft=0, wt=0;

  function setDest(wp){tx=wp.x*TILE;ty=wp.y*TILE;}

  function draw(){
    ctx.clearRect(0,0,canvas.width,canvas.height);
    for(let r=0;r<ROWS;r++)for(let c=0;c<COLS;c++)drawTile(c,r,MAP[r][c]);
    // pulse ring
    const p=0.5+0.5*Math.sin(Date.now()/600);
    const flr=ctx.createRadialGradient(ox+5,oy+5,2,ox+5,oy+5,14);
    flr.addColorStop(0,`rgba(0,247,255,${0.1*p})`); flr.addColorStop(1,'transparent');
    ctx.fillStyle=flr; ctx.fillRect(ox-14,oy-14,38,38);
    drawOcto(ox,oy,frame);
  }

  let last=0;
  function loop(ts){
    const dt=ts-last; last=ts;
    const dx=tx-ox, dy=ty-oy, dist=Math.sqrt(dx*dx+dy*dy);
    if(dist>1){ox+=dx/dist*1.5;oy+=dy/dist*1.5;}else{ox=tx;oy=ty;}
    ft+=dt; if(ft>90){ft=0;if(dist>1)frame=(frame+1)%4;}
    // wander when idle
    wt--; if(wt<=0){
      wt=150+Math.floor(Math.random()*150);
      const wps=Object.values(WP);
      setDest(wps[Math.floor(Math.random()*wps.length)]);
    }
    draw();
    requestAnimationFrame(loop);
  }
  requestAnimationFrame(loop);

  // Poll Gradio hidden element for action state
  const poller = setInterval(()=>{
    const el=document.getElementById('octobot-action');
    if(el){
      const a=el.getAttribute('data-action')||'idle';
      const wp=ACTION_WP[a];
      if(wp)setDest(WP[wp]);
    }
    // Update thought/action text from hidden spans
    const th=document.getElementById('octobot-thought-text');
    const ac=document.getElementById('octobot-action-text');
    const thoughtEl=document.getElementById('octo-mini-thought');
    const actionEl=document.getElementById('octo-mini-action');
    if(th&&thoughtEl)thoughtEl.textContent='💭 '+(th.textContent||'thinking…');
    if(ac&&actionEl)actionEl.textContent='⚙ '+(ac.textContent||'IDLE').toUpperCase();
  }, 2000);
})();
</script>
"""

# ---------------------------------------------------------------------------
# Full-size canvas for the Visual tab
# ---------------------------------------------------------------------------
CANVAS_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>DreamLab OctoBot</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap">
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    background: #05000f;
    display: flex;
    flex-direction: column;
    align-items: center;
    font-family: 'Press Start 2P', 'Courier New', monospace;
    color: #ff99ee;
    background-image:
      repeating-linear-gradient(0deg, transparent, transparent 31px, #0ff1 32px),
      repeating-linear-gradient(90deg, transparent, transparent 31px, #0ff1 32px);
  }
  h2 {
    margin: 14px 0 2px;
    font-size: 13px;
    letter-spacing: 3px;
    color: #ff2d9b;
    text-shadow: 0 0 8px #ff2d9b, 0 0 20px #ff2d9b88, 2px 2px 0 #000;
    text-transform: uppercase;
  }
  #status-bar {
    font-size: 7px;
    color: #00f7ff;
    text-shadow: 0 0 6px #00f7ff;
    margin-bottom: 8px;
    min-height: 18px;
    letter-spacing: 1px;
  }
  canvas {
    image-rendering: pixelated;
    image-rendering: crisp-edges;
    border: 3px solid #ff2d9b;
    box-shadow:
      0 0 0 1px #000,
      0 0 16px #ff2d9b,
      0 0 40px #ff2d9b55,
      inset 0 0 16px #00000088;
    background: #05000f;
  }
  #legend {
    display: flex;
    gap: 12px;
    margin-top: 10px;
    font-size: 6px;
    color: #ff99ee;
    flex-wrap: wrap;
    justify-content: center;
  }
  .leg { display: flex; align-items: center; gap: 4px; }
  .swatch { width: 10px; height: 10px; display: inline-block; border: 1px solid #ffffff44; }
  #scanline {
    pointer-events: none;
    position: absolute;
    top: 0; left: 0; right: 0; bottom: 0;
    background: repeating-linear-gradient(
      to bottom,
      transparent 0px, transparent 2px,
      rgba(0,0,0,0.18) 2px, rgba(0,0,0,0.18) 4px
    );
    z-index: 10;
  }
  #canvas-wrap { position: relative; display: inline-block; }
</style>
</head>
<body>
<h2>🐙 DreamLab OctoBot</h2>
<div id="status-bar">INITIALISING DREAM LIBRARY…</div>
<div id="canvas-wrap">
<canvas id="c" width="480" height="320"></canvas>
<div id="scanline"></div>
</div>
<div id="legend">
  <div class="leg"><span class="swatch" style="background:#0d0830"></span>FLOOR</div>
  <div class="leg"><span class="swatch" style="background:#0a0050"></span>SHELF</div>
  <div class="leg"><span class="swatch" style="background:#1a0035"></span>DESK</div>
  <div class="leg"><span class="swatch" style="background:#001830"></span>TABLE</div>
  <div class="leg"><span class="swatch" style="background:#ff2d9b"></span>OCTOBOT</div>
</div>

<script>
// =====================================================================
// CONSTANTS
// =====================================================================
const TILE  = 16;      // tile size in pixels
const COLS  = 30;      // canvas tiles wide
const ROWS  = 20;      // canvas tiles tall
const FPS   = 12;      // animation frames per second
const SCALE = 1;       // drawn 1:1 (canvas is already 480×320)

// Tile IDs
const T = {
  FLOOR:  0,
  SHELF:  1,
  DESK:   2,
  TABLE:  3,
  WALL:   4,
  RUG:    5,
};

// Neon pixel colours — deep void base with neon pink + cyan accents
const TILE_COLORS = {
  [T.FLOOR]: '#0d0830',
  [T.SHELF]: '#0a0050',
  [T.DESK]:  '#1a0035',
  [T.TABLE]: '#001830',
  [T.WALL]:  '#030010',
  [T.RUG]:   '#200040',
};

// =====================================================================
// MAP  —  30 × 20 grid
// 0=floor  1=shelf  2=desk  3=table  4=wall  5=rug
// =====================================================================
const MAP = [
//  0  1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29
  [ 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4], // 0
  [ 4, 1, 1, 1, 1, 1, 0, 0, 0, 0, 4, 0, 0, 0, 0, 0, 4, 0, 0, 0, 0, 0, 4, 1, 1, 1, 1, 1, 1, 4], // 1
  [ 4, 1, 1, 1, 1, 1, 0, 0, 2, 0, 4, 0, 0, 3, 3, 0, 4, 0, 3, 3, 0, 0, 4, 1, 1, 1, 1, 1, 1, 4], // 2
  [ 4, 1, 1, 1, 1, 1, 0, 0, 2, 0, 0, 0, 0, 3, 3, 0, 0, 0, 3, 3, 0, 0, 4, 1, 1, 1, 1, 1, 1, 4], // 3
  [ 4, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 4], // 4
  [ 4, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 5, 5, 5, 5, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 4], // 5
  [ 4, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 5, 5, 5, 5, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 0, 4], // 6
  [ 4, 1, 1, 1, 0, 0, 0, 2, 2, 0, 0, 0, 0, 0, 5, 5, 5, 5, 0, 0, 0, 0, 2, 2, 0, 1, 1, 1, 0, 4], // 7
  [ 4, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 4], // 8
  [ 4, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 4], // 9
  [ 4, 1, 1, 1, 1, 0, 0, 0, 0, 0, 3, 3, 3, 0, 0, 0, 0, 3, 3, 3, 0, 0, 0, 0, 0, 1, 1, 1, 1, 4], //10
  [ 4, 1, 1, 1, 1, 0, 0, 0, 0, 0, 3, 3, 3, 0, 0, 0, 0, 3, 3, 3, 0, 0, 0, 0, 0, 1, 1, 1, 1, 4], //11
  [ 4, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 4], //12
  [ 4, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 4], //13
  [ 4, 1, 1, 1, 1, 1, 0, 0, 0, 0, 4, 0, 0, 0, 0, 0, 4, 0, 0, 0, 0, 0, 4, 1, 1, 1, 1, 1, 1, 4], //14
  [ 4, 1, 1, 1, 1, 1, 0, 0, 2, 0, 4, 0, 0, 3, 3, 0, 4, 0, 3, 3, 0, 0, 4, 1, 1, 1, 1, 1, 1, 4], //15
  [ 4, 1, 1, 1, 1, 1, 0, 0, 2, 0, 0, 0, 0, 3, 3, 0, 0, 0, 3, 3, 0, 0, 4, 1, 1, 1, 1, 1, 1, 4], //16
  [ 4, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 4], //17
  [ 4, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 4], //18
  [ 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4], //19
];

// Named waypoints (tile coords)
const WP = {
  HOME:   { x: 14, y: 9  },
  SHELF_L:{ x:  2, y:  3 },
  SHELF_R:{ x: 25, y:  3 },
  DESK_L: { x:  8, y:  7 },
  DESK_R: { x: 22, y:  7 },
  TABLE_C:{ x: 14, y:  6 },
  SHELF_B:{ x:  2, y: 15 },
};

// =====================================================================
// PIXEL-ART OCTOPUS SPRITE  (16×16, drawn in canvas commands)
// Each "row" is a set of coloured 2×2 blocks.
// Pink octopus with big eyes, waving arms.
// =====================================================================
function drawOctobot(ctx, px, py, frame) {
  const f = frame % 4;   // 4-frame walk cycle
  const bounce = (f === 1 || f === 3) ? -1 : 0;  // gentle bob
  const oy = py + bounce;

  // ── Neon glow aura around OctoBot ──
  const aura = ctx.createRadialGradient(px+7, oy+7, 1, px+7, oy+7, 16);
  aura.addColorStop(0, '#ff2d9b55');
  aura.addColorStop(0.5, '#bf00ff22');
  aura.addColorStop(1, 'transparent');
  ctx.fillStyle = aura;
  ctx.fillRect(px-10, oy-10, 34, 34);

  // Body — neon hot pink with pixel outline
  ctx.fillStyle = '#110020';  // dark outline
  ctx.fillRect(px+3, oy+0, 10, 9);
  ctx.fillRect(px+2, oy+1, 12, 7);
  ctx.fillStyle = '#ff2d9b';  // hot pink body
  ctx.fillRect(px+4, oy+1, 8, 7);
  ctx.fillRect(px+3, oy+2, 10, 5);
  // Highlight sheen
  ctx.fillStyle = '#ff80cc';
  ctx.fillRect(px+5, oy+1, 3, 2);
  ctx.fillStyle = '#ff99dd';
  ctx.fillRect(px+5, oy+1, 1, 1);

  // Eyes — glowing cyan
  ctx.fillStyle = '#001420';
  ctx.fillRect(px+4, oy+2, 4, 3);
  ctx.fillRect(px+8, oy+2, 4, 3);
  ctx.fillStyle = '#00f7ff';
  ctx.fillRect(px+5, oy+2, 2, 2);
  ctx.fillRect(px+9, oy+2, 2, 2);
  // Pupil
  ctx.fillStyle = '#003344';
  ctx.fillRect(px+6, oy+3, 1, 1);
  ctx.fillRect(px+10, oy+3, 1, 1);
  // Eye shine
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(px+5, oy+2, 1, 1);
  ctx.fillRect(px+9, oy+2, 1, 1);

  // Cheeks — neon pink blush
  ctx.fillStyle = '#ff006688';
  ctx.fillRect(px+3, oy+4, 2, 1);
  ctx.fillRect(px+11, oy+4, 2, 1);

  // Arms — alternating pink/cyan, animated wiggle
  const armYBase = oy + 7;
  const offsets = [
    [f===0?0:f===1?-1:f===2?0:1,  2],
    [f===0?1:f===1?0:f===2?-1:0,  1],
    [f===0?-1:f===1?0:f===2?1:0,  0],
    [f===0?0:f===1?1:f===2?0:-1, -1],
  ];
  const armXStart = [px+1, px+3, px+10, px+12];
  const armColors = ['#ff2d9b','#00f7ff','#ff2d9b','#00f7ff'];
  for (let i = 0; i < 4; i++) {
    const ax = armXStart[i];
    const [dy, dx] = offsets[i % 4];
    ctx.fillStyle = armColors[i];
    ctx.fillRect(ax,          armYBase,     2, 3);
    ctx.fillRect(ax + dx,     armYBase + 3, 2, 3);
    ctx.fillRect(ax + dx*2,   armYBase + 5, 2, 2);
    // Neon tip pixel
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(ax + dx*2,   armYBase + 6, 1, 1);
  }

  // Holographic book (frame 2) — cyan glow
  if (f === 2) {
    ctx.fillStyle = '#00f7ff';
    ctx.fillRect(px+5, oy+0, 5, 3);
    ctx.fillStyle = '#001830';
    ctx.fillRect(px+7, oy+0, 1, 3);
    ctx.fillStyle = '#ffffff88';
    ctx.fillRect(px+5, oy+0, 1, 1);
  }
}

// =====================================================================
// TILE RENDERING
// =====================================================================
function drawTile(ctx, col, row, tileId) {
  const px = col * TILE;
  const py = row * TILE;
  const base = TILE_COLORS[tileId];

  ctx.fillStyle = base;
  ctx.fillRect(px, py, TILE, TILE);

  // Tile details — neon pixel-art style
  if (tileId === T.FLOOR) {
    // Cyan grid lines (neon floor grid)
    ctx.fillStyle = '#00f7ff18';
    ctx.fillRect(px, py, 1, TILE);
    ctx.fillRect(px, py, TILE, 1);
    // Occasional neon pixel specks
    if ((col + row) % 7 === 0) {
      ctx.fillStyle = '#00f7ff44';
      ctx.fillRect(px+7, py+7, 2, 2);
    }
  }
  if (tileId === T.SHELF) {
    // Neon book spines — pink/cyan/purple
    const bookColors = ['#ff2d9b','#00f7ff','#bf00ff','#ff6ec7','#00cfff','#ff0077'];
    for (let b = 0; b < 5; b++) {
      ctx.fillStyle = bookColors[(col + b + row) % bookColors.length];
      ctx.fillRect(px + 1 + b*3, py + 3, 2, 10);
      // Neon glow strip at top of each book
      ctx.fillStyle = '#ffffff55';
      ctx.fillRect(px + 1 + b*3, py + 3, 2, 1);
    }
    // Shelf plank — dark with neon edge
    ctx.fillStyle = '#110030';
    ctx.fillRect(px, py + 13, TILE, 2);
    ctx.fillStyle = '#ff2d9b88';
    ctx.fillRect(px, py + 13, TILE, 1);
  }
  if (tileId === T.DESK) {
    // Neon desk surface
    ctx.fillStyle = '#200040';
    ctx.fillRect(px+1, py+4, TILE-2, TILE-6);
    ctx.fillStyle = '#bf00ff';
    ctx.fillRect(px+1, py+4, TILE-2, 1);
    // Glowing screen / paper
    ctx.fillStyle = '#00f7ff22';
    ctx.fillRect(px+3, py+5, 5, 6);
    ctx.fillStyle = '#00f7ff';
    ctx.fillRect(px+4, py+7, 3, 1);
    ctx.fillRect(px+4, py+9, 3, 1);
  }
  if (tileId === T.TABLE) {
    // Neon study table
    ctx.fillStyle = '#001828';
    ctx.fillRect(px+1, py+4, TILE-2, TILE-6);
    ctx.fillStyle = '#00f7ff';
    ctx.fillRect(px+1, py+4, TILE-2, 1);
    // Open holographic book
    ctx.fillStyle = '#00f7ff22';
    ctx.fillRect(px+2, py+5, 6, 5);
    ctx.fillStyle = '#00f7ff';
    ctx.fillRect(px+7, py+5, 1, 5);
    ctx.fillStyle = '#ff2d9b';
    ctx.fillRect(px+3, py+6, 2, 1);
    ctx.fillRect(px+3, py+8, 2, 1);
  }
  if (tileId === T.WALL) {
    // Deep void wall with neon pixel border
    ctx.fillStyle = '#030010';
    ctx.fillRect(px, py, TILE, TILE);
    ctx.fillStyle = '#bf00ff22';
    ctx.fillRect(px+1, py+1, TILE-2, TILE-2);
    // Pixel brick pattern
    if (row % 2 === 0) {
      ctx.fillStyle = '#bf00ff44';
      ctx.fillRect(px, py+7, TILE, 1);
    }
  }
  if (tileId === T.RUG) {
    // Neon teleporter pad / rug
    ctx.fillStyle = '#200040';
    ctx.fillRect(px, py, TILE, TILE);
    ctx.fillStyle = '#ff2d9b66';
    ctx.fillRect(px+2, py+2, TILE-4, TILE-4);
    ctx.fillStyle = '#00f7ff';
    ctx.fillRect(px+5, py+5, 6, 6);
    ctx.fillStyle = '#ff2d9b';
    ctx.fillRect(px+6, py+6, 4, 4);
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(px+7, py+7, 2, 2);
  }
}

// =====================================================================
// MAIN GAME LOOP
// =====================================================================
const canvas = document.getElementById('c');
const ctx = canvas.getContext('2d');
const statusEl = document.getElementById('status-bar');

// OctoBot position (in pixels)
let octoX = WP.HOME.x * TILE;
let octoY = WP.HOME.y * TILE;
let targetX = octoX;
let targetY = octoY;
let frame = 0;
let frameTimer = 0;
let moveDir = 0;  // -1 left, 1 right

// Action state
let currentAction = 'idle';
const STATUS_MESSAGES = {
  idle:          '>> OCTOBOT ONLINE. DREAM LIBRARY ACTIVE.',
  research:      '>> DOWNLOADING KNOWLEDGE STREAM…',
  read_file:     '>> ARM_3: ACCESSING DATA CRYSTAL…',
  write_file:    '>> ARM_7: ENCODING TO NEON SCROLL…',
  list_files:    '>> SCANNING DREAM CATALOG…',
  update_notes:  '>> WRITING TO MEMORY BANKS…',
  update_tasks:  '>> UPDATING MISSION LOG…',
};

// Walk towards a waypoint
function setDestination(wp) {
  targetX = wp.x * TILE;
  targetY = wp.y * TILE;
}

// Map action → waypoint
function actionToWaypoint(action) {
  switch (action) {
    case 'research':      return WP.TABLE_C;
    case 'read_file':     return (Math.random() < 0.5) ? WP.SHELF_L : WP.SHELF_R;
    case 'write_file':    return (Math.random() < 0.5) ? WP.DESK_L  : WP.DESK_R;
    case 'list_files':    return WP.SHELF_B;
    case 'update_notes':  return WP.DESK_L;
    case 'update_tasks':  return WP.DESK_R;
    default:              return WP.HOME;
  }
}

// Poll status from the page title attribute (set by Gradio state)
// If the attribute isn't present, wander randomly
function pollAction() {
  const el = document.getElementById('octobot-action');
  if (el) {
    const a = el.getAttribute('data-action') || 'idle';
    if (a !== currentAction) {
      currentAction = a;
      setDestination(actionToWaypoint(a));
      statusEl.textContent = STATUS_MESSAGES[a] || '🐙 Doing something mysterious…';
    }
  }
}

// Random wander — occasionally pick a new spot
let wanderTimer = 0;
function wander() {
  wanderTimer--;
  if (wanderTimer > 0) return;
  wanderTimer = 180 + Math.floor(Math.random() * 240);  // every 15–30s at 12fps

  // Pick a random walkable tile
  const options = [WP.HOME, WP.SHELF_L, WP.SHELF_R, WP.DESK_L, WP.DESK_R, WP.TABLE_C, WP.SHELF_B];
  const wp = options[Math.floor(Math.random() * options.length)];
  setDestination(wp);
  statusEl.textContent = '>> ' + [
    'ROAMING THE DREAM STACKS…',
    'ARM_2 TWITCHING WITH CURIOSITY…',
    'DETECTING INTERESTING DATA NEARBY…',
    'REORGANISING NEON FILING SYSTEM…',
    'PATROLLING THE CRYSTAL ARCHIVES…',
  ][Math.floor(Math.random() * 5)];
}

// Draw the whole scene
function drawScene() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  // Draw map
  for (let row = 0; row < ROWS; row++) {
    for (let col = 0; col < COLS; col++) {
      drawTile(ctx, col, row, MAP[row][col]);
    }
  }

  // Neon floor pulse effect — animated cyan ring
  const pulse = 0.5 + 0.5 * Math.sin(Date.now() / 600);
  const flr = ctx.createRadialGradient(octoX+8, octoY+8, 4, octoX+8, octoY+8, 28);
  flr.addColorStop(0, `rgba(0,247,255,${0.08 * pulse})`);
  flr.addColorStop(0.5, `rgba(255,45,155,${0.06 * pulse})`);
  flr.addColorStop(1, 'transparent');
  ctx.fillStyle = flr;
  ctx.fillRect(octoX - 28, octoY - 28, 72, 72);

  // Draw OctoBot
  drawOctobot(ctx, octoX, octoY, frame);
}

// Update loop
let lastTime = 0;
function update(ts) {
  const dt = ts - lastTime;
  lastTime = ts;

  // Move toward target
  const speed = 1.2;
  const dx = targetX - octoX;
  const dy = targetY - octoY;
  const dist = Math.sqrt(dx*dx + dy*dy);

  if (dist > 2) {
    octoX += (dx / dist) * speed;
    octoY += (dy / dist) * speed;
    moveDir = dx < 0 ? -1 : 1;
  } else {
    octoX = targetX;
    octoY = targetY;
    moveDir = 0;
  }

  // Animate frame
  frameTimer += dt;
  if (frameTimer > 1000 / FPS) {
    frameTimer = 0;
    if (dist > 2) {
      frame = (frame + 1) % 4;
    }
  }

  pollAction();
  if (currentAction === 'idle') wander();

  drawScene();
  requestAnimationFrame(update);
}

requestAnimationFrame(update);
</script>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# Column canvas — full 480×320 in an <iframe srcdoc> so the <script> executes.
# The iframe JS polls parent.document for #octobot-action bridge spans.
# ---------------------------------------------------------------------------
_IFRAME_DOC = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap">
<style>
  *{margin:0;padding:0;box-sizing:border-box;}
  body{background:#020c18;display:flex;flex-direction:column;align-items:center;font-family:'Press Start 2P',monospace;color:#88eeff;overflow:hidden;}
  #dreamlab-col{display:flex;flex-direction:column;align-items:center;padding:4px 0;background:#020c18;}
  #dreamlab-col h3{font-family:'Press Start 2P',monospace;font-size:11px;letter-spacing:3px;color:#00e5ff;text-shadow:0 0 8px #00e5ff,2px 2px 0 #000;margin:6px 0 4px;text-transform:uppercase;}
  #vc-wrap{position:relative;display:inline-block;}
  #vc{image-rendering:pixelated;image-rendering:crisp-edges;border:4px solid #00e5ff;box-shadow:0 0 0 2px #003355,0 0 24px #00e5ff88,0 0 60px #00e5ff33,inset 0 0 20px #00000088;background:#020c18;display:block;width:100%;height:auto;}
  #vc-glass{pointer-events:none;position:absolute;top:0;left:0;right:0;bottom:0;background:linear-gradient(180deg,rgba(0,200,255,0.06) 0%,transparent 40%,rgba(0,100,180,0.04) 100%);z-index:10;}
  #vc-status{font-family:'Press Start 2P',monospace;font-size:7px;color:#00e5ff;text-shadow:0 0 6px #00e5ff;margin:4px 0 2px;min-height:16px;letter-spacing:1px;text-align:center;max-width:960px;word-break:break-word;padding:0 8px;}
</style>
</head>
<body>
<div id="dreamlab-col">
  <h3>\ud83d\udc19 OctoBot Aquarium</h3>
  <div id="vc-status">TANK WATER CIRCULATING\u2026</div>
  <div id="vc-wrap">
    <canvas id="vc" width="1920" height="1280"></canvas>
    <div id="vc-glass"></div>
  </div>
</div>
<script>
(function(){
const TILE=16,COLS=30,ROWS=20,FPS=12;
// Tile IDs: 0=water 1=sand 2=rock 3=coral 4=glass 5=seaweed 6=treasure 7=bubble
const TC={'0':'#041828','1':'#1a2a10','2':'#0a1e30','3':'#0d1f2d','4':'#022038','5':'#041828','6':'#041828','7':'#041828'};
// Fish tank map — glass walls, sandy bottom, rocks, coral, seaweed, treasure chest
const MAP=[
  [4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4], // top glass
  [4,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,4], // water
  [4,0,0,0,0,5,0,0,0,0,0,0,0,0,0,0,0,0,0,0,5,5,0,0,0,0,0,0,0,4],
  [4,0,5,5,0,5,0,0,7,0,0,0,0,0,0,0,0,0,0,7,5,5,0,7,0,5,5,0,0,4],
  [4,0,5,5,0,5,5,0,0,0,0,0,0,0,0,0,0,0,0,0,0,5,0,0,0,5,5,5,0,4],
  [4,0,0,5,0,0,5,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,5,0,0,4],
  [4,0,0,0,0,0,0,0,3,3,0,0,0,0,0,0,0,0,0,0,3,3,0,0,0,0,0,0,0,4],
  [4,0,0,0,0,0,0,0,3,3,0,0,0,0,6,0,0,0,0,0,3,3,0,0,0,0,0,0,0,4],
  [4,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,4],
  [4,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,4], // open swim area
  [4,0,0,0,7,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,7,0,0,0,0,4],
  [4,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,4],
  [4,0,0,5,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,5,0,0,4],
  [4,0,5,5,0,0,0,0,3,3,0,0,0,0,0,0,0,0,3,3,0,0,0,0,0,5,5,5,0,4],
  [4,0,5,5,0,0,0,0,3,3,0,0,7,0,0,0,0,7,3,3,0,0,0,0,0,0,5,5,0,4],
  [4,0,0,5,5,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,5,5,0,0,4],
  [4,0,0,0,5,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,5,5,0,0,0,4],
  [4,2,2,2,2,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,2,2,2,2,4], // rocks + sand
  [4,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,4], // sand floor
  [4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4], // bottom glass
];
// Waypoints in the water column
const WP={HOME:{x:14,y:9},CORAL_L:{x:9,y:7},CORAL_R:{x:21,y:7},SURFACE:{x:14,y:2},FLOOR:{x:14,y:16},LEFT:{x:3,y:10},RIGHT:{x:26,y:10},TREASURE:{x:14,y:7}};

/* ── Rising bubbles ─────────────────────────────────────── */
const bubbles=[];
for(let i=0;i<35;i++)bubbles.push({x:20+Math.random()*440,y:Math.random()*320,s:1+Math.floor(Math.random()*2),sp:0.04+Math.random()*0.12,a:Math.random()*6.28,wobble:Math.random()*6.28});
function drawBubbles(ctx,t){
  for(const b of bubbles){
    b.y-=b.sp;b.x+=Math.sin(b.wobble+t*0.0008)*0.3;b.wobble+=0.01;
    if(b.y<-4){b.y=325+Math.random()*30;b.x=20+Math.random()*440;}
    const al=0.12+0.08*Math.sin(t*0.002+b.a);
    ctx.strokeStyle='rgba(150,220,255,'+al+')';
    ctx.lineWidth=b.s>1?1.5:1;
    ctx.beginPath();ctx.arc(b.x,b.y,b.s+1,0,Math.PI*2);ctx.stroke();
    ctx.fillStyle='rgba(200,240,255,0.04)';
    ctx.beginPath();ctx.arc(b.x,b.y,b.s+1,0,Math.PI*2);ctx.fill();
  }
}
/* ── Small fish ─────────────────────────────────────────────── */
const fish=[];
for(let i=0;i<4;i++)fish.push({x:50+Math.random()*380,y:30+Math.random()*250,vx:(0.3+Math.random()*0.4)*(Math.random()<0.5?1:-1),vy:(Math.random()-0.5)*0.15,timer:0,c:['#ff8844','#ffcc44','#88ffcc','#ff88cc'][i]});
function drawFish(ctx,t){
  for(const f of fish){
    f.x+=f.vx;f.y+=f.vy+Math.sin(t*0.001+f.x*0.05)*0.08;
    if(f.x<10){f.x=10;f.vx=Math.abs(f.vx);} if(f.x>470){f.x=470;f.vx=-Math.abs(f.vx);}
    if(f.y<15){f.y=15;f.vy=Math.abs(f.vy);} if(f.y>290){f.y=290;f.vy=-Math.abs(f.vy);}
    const fl=f.vx<0;
    ctx.save();ctx.translate(Math.floor(f.x),Math.floor(f.y));if(fl)ctx.scale(-1,1);
    ctx.fillStyle=f.c;ctx.fillRect(0,-2,6,4);          // body
    ctx.fillStyle=f.c+'99';ctx.fillRect(6,-3,3,6);     // tail
    ctx.fillStyle='#000';ctx.fillRect(1,-1,1,1);        // eye
    ctx.restore();
  }
}

/* ── Expression sprites (40x36 logical) ─────────────────────── */
function drawOcto(ctx,px,py,frame,expression){
  const f=frame%4,bounce=(f===1||f===3)?-1:0,oy=py+bounce;
  const cx=px+20,cy=oy+16;
  // Glow aura — soft pink in water
  const aura=ctx.createRadialGradient(cx,cy,3,cx,cy,36);
  aura.addColorStop(0,'#ff2d9b55');aura.addColorStop(0.4,'#ff70c033');aura.addColorStop(1,'transparent');
  ctx.fillStyle=aura;ctx.fillRect(px-18,oy-18,76,76);
  // Head outline + body (40 wide)
  ctx.fillStyle='#220010';
  ctx.fillRect(px+9,oy+0,22,18);ctx.fillRect(px+6,oy+3,28,13);ctx.fillRect(px+7,oy+1,26,16);
  // Body fill
  ctx.fillStyle='#ff2d9b';
  ctx.fillRect(px+10,oy+1,20,16);ctx.fillRect(px+7,oy+4,26,11);ctx.fillRect(px+8,oy+2,24,14);
  // Colour variation — slightly purple hue on sides
  ctx.fillStyle='#cc2288';ctx.fillRect(px+8,oy+4,4,10);ctx.fillRect(px+28,oy+4,4,10);
  // Highlight sheen
  ctx.fillStyle='#ff80cc';ctx.fillRect(px+12,oy+2,8,4);
  ctx.fillStyle='#ffaadd';ctx.fillRect(px+13,oy+2,3,2);

  /* ── Eyes by expression (scaled up for 40px body) ── */
  if(expression==='thinking'){
    ctx.fillStyle='#001420';ctx.fillRect(px+10,oy+7,7,3);ctx.fillRect(px+23,oy+7,7,3);
    ctx.fillStyle='#00ccff';ctx.fillRect(px+12,oy+7,3,2);ctx.fillRect(px+25,oy+7,3,2);
    ctx.fillStyle='#ffffff';ctx.fillRect(px+12,oy+7,1,1);ctx.fillRect(px+25,oy+7,1,1);
    const bt=Math.sin(Date.now()/400)*2;
    ctx.fillStyle='#ffffff66';ctx.fillRect(px+32,oy-8+bt,8,5);ctx.fillRect(px+33,oy-9+bt,6,8);
    ctx.fillStyle='#88eeff';ctx.fillRect(px+35,oy-7+bt,3,3);
    ctx.fillStyle='#ffffff44';ctx.fillRect(px+30,oy-3+bt,3,3);ctx.fillRect(px+28,oy+0+bt,2,2);
  } else if(expression==='reading'){
    ctx.fillStyle='#001420';ctx.fillRect(px+10,oy+6,8,7);ctx.fillRect(px+22,oy+6,8,7);
    ctx.fillStyle='#00ccff';ctx.fillRect(px+12,oy+7,4,4);ctx.fillRect(px+24,oy+7,4,4);
    ctx.fillStyle='#003344';ctx.fillRect(px+14,oy+10,2,1);ctx.fillRect(px+26,oy+10,2,1);
    ctx.fillStyle='#ffffff';ctx.fillRect(px+12,oy+7,2,1);ctx.fillRect(px+24,oy+7,2,1);
    ctx.fillStyle='#00ccff';ctx.fillRect(px+11,oy+19,18,4);
    ctx.fillStyle='#001830';ctx.fillRect(px+19,oy+19,2,4);
    ctx.fillStyle='#ffffff44';ctx.fillRect(px+12,oy+19,3,1);ctx.fillRect(px+21,oy+19,3,1);
  } else if(expression==='writing'){
    ctx.fillStyle='#001420';ctx.fillRect(px+10,oy+6,8,6);ctx.fillRect(px+22,oy+7,8,3);
    ctx.fillStyle='#00ccff';ctx.fillRect(px+12,oy+7,4,3);ctx.fillRect(px+24,oy+7,3,2);
    ctx.fillStyle='#ffffff';ctx.fillRect(px+12,oy+7,2,1);
    const pw=Math.sin(Date.now()/200)*0.5;
    ctx.fillStyle='#00ccff';ctx.fillRect(px+34+pw,oy+13,2,8);ctx.fillRect(px+32+pw,oy+20,4,3);
    ctx.fillStyle='#ff2d9b';ctx.fillRect(px+34+pw,oy+22,2,2);
  } else if(expression==='excited'){
    ctx.fillStyle='#001420';ctx.fillRect(px+10,oy+6,8,7);ctx.fillRect(px+22,oy+6,8,7);
    const st=Date.now()/150;
    ctx.fillStyle='#ffff00';ctx.fillRect(px+13,oy+7,2,4);ctx.fillRect(px+11,oy+9,6,2);
    ctx.fillRect(px+25,oy+7,2,4);ctx.fillRect(px+23,oy+9,6,2);
    const sp=Math.sin(st)*2;
    ctx.fillStyle='#ffff00'+Math.floor((0.5+0.5*Math.sin(st))*200).toString(16).padStart(2,'0');
    ctx.fillRect(px+2,oy-5+sp,3,3);ctx.fillRect(px+35,oy-4-sp,3,3);
    ctx.fillRect(px-3,oy+8+sp,2,2);ctx.fillRect(px+41,oy+5-sp,2,2);
  } else {
    ctx.fillStyle='#001420';ctx.fillRect(px+10,oy+6,8,6);ctx.fillRect(px+22,oy+6,8,6);
    ctx.fillStyle='#00ccff';ctx.fillRect(px+12,oy+7,4,3);ctx.fillRect(px+24,oy+7,4,3);
    ctx.fillStyle='#003344';ctx.fillRect(px+14,oy+9,2,1);ctx.fillRect(px+26,oy+9,2,1);
    ctx.fillStyle='#ffffff';ctx.fillRect(px+12,oy+7,2,1);ctx.fillRect(px+24,oy+7,2,1);
  }
  // Cheeks
  ctx.fillStyle='#ff006633';ctx.fillRect(px+7,oy+10,4,3);ctx.fillRect(px+29,oy+10,4,3);
  // Mouth
  if(expression==='excited'){
    ctx.fillStyle='#220010';ctx.fillRect(px+16,oy+13,8,3);ctx.fillStyle='#ff80cc';ctx.fillRect(px+17,oy+14,6,2);
  } else if(expression==='thinking'){
    ctx.fillStyle='#220010';ctx.fillRect(px+18,oy+13,5,2);
  } else {
    ctx.fillStyle='#220010';ctx.fillRect(px+15,oy+13,10,2);ctx.fillStyle='#ff80cc';ctx.fillRect(px+16,oy+13,8,1);
  }

  // Tentacles — 8 arms, spread wider for 40px body
  const ay=oy+17;
  const armData=[
    {x:px+1,  dx:[-1,0,1,0]},
    {x:px+5,  dx:[0,-1,0,1]},
    {x:px+9,  dx:[1,0,-1,0]},
    {x:px+13, dx:[0,1,0,-1]},
    {x:px+18, dx:[-1,0,1,0]},
    {x:px+22, dx:[0,-1,0,1]},
    {x:px+26, dx:[1,0,-1,0]},
    {x:px+30, dx:[0,1,0,-1]},
  ];
  const armC=['#ff2d9b','#ff70c0','#ff2d9b','#ff90cc','#ff2d9b','#ff70c0','#ff2d9b','#ff90cc'];
  for(let i=0;i<8;i++){
    const a=armData[i],d=a.dx[f];
    ctx.fillStyle=armC[i];
    ctx.fillRect(a.x,ay,3,4);
    ctx.fillRect(a.x+d,ay+4,3,4);
    ctx.fillRect(a.x+d*2,ay+8,2,3);
    // Sucker dots
    ctx.fillStyle='#ffaacc66';
    ctx.fillRect(a.x+1,ay+1,1,1);ctx.fillRect(a.x+d+1,ay+5,1,1);
  }
}

function drawTile(ctx,col,row,id,t){
  const px=col*TILE,py=row*TILE;
  // Base fill for all tiles — water colour
  if(id===0||id===5||id===7){
    // Water — deep blue animated
    const wd=0.02+0.015*Math.sin(t*0.0008+col*0.4+row*0.3);
    ctx.fillStyle='#021428';ctx.fillRect(px,py,TILE,TILE);
    // Caustic light shimmer
    if((col*2+row*3)%5===0){
      const cw=0.04+0.03*Math.sin(t*0.002+col*0.8+row*0.5);
      ctx.fillStyle='rgba(0,180,220,'+cw+')';ctx.fillRect(px+3,py+3,TILE-6,2);
    }
    if((col*5+row*2)%7===0){
      const cw2=0.03+0.02*Math.sin(t*0.0015+col*1.2);
      ctx.fillStyle='rgba(0,200,255,'+cw2+')';ctx.fillRect(px+6,py+8,TILE-10,1);
    }
  } else {
    ctx.fillStyle=TC[String(id)]||TC['0'];ctx.fillRect(px,py,TILE,TILE);
  }
  if(id===1){
    // Sandy bottom
    ctx.fillStyle='#2a3a12';ctx.fillRect(px,py,TILE,TILE);
    // Sand texture pebbles
    if((col+row*3)%4===0){ctx.fillStyle='#3a4a1a';ctx.fillRect(px+2,py+4,3,3);}
    if((col*2+row)%5===0){ctx.fillStyle='#1e2e0e';ctx.fillRect(px+8,py+7,2,2);}
    if((col+row*2)%3===0){ctx.fillStyle='#3a4a1a';ctx.fillRect(px+11,py+2,2,2);}
    // Occasional shell
    if((col*3+row*7)%19===0){ctx.fillStyle='#ddcc88';ctx.fillRect(px+4,py+5,4,3);ctx.fillStyle='#aaa066';ctx.fillRect(px+5,py+6,2,1);}
  }
  if(id===2){
    // Rocks
    ctx.fillStyle='#0e2030';ctx.fillRect(px,py,TILE,TILE);
    ctx.fillStyle='#162838';ctx.fillRect(px+1,py+2,TILE-2,TILE-4);
    ctx.fillStyle='#0a1820';ctx.fillRect(px+3,py+4,TILE-6,TILE-8);
    // Rock highlight
    ctx.fillStyle='rgba(100,160,200,0.12)';ctx.fillRect(px+2,py+2,3,2);
  }
  if(id===3){
    // Coral — animated pink/orange
    ctx.fillStyle='#021428';ctx.fillRect(px,py,TILE,TILE);
    const cp=0.5+0.5*Math.sin(t*0.002+col*2+row);
    const cc=col%3===0?'#ff6644':col%3===1?'#ff88aa':'#ffaa44';
    // Coral branches
    ctx.fillStyle=cc;ctx.fillRect(px+7,py+4,2,TILE-4);
    ctx.fillRect(px+4,py+6,6,2);
    ctx.fillRect(px+5,py+9,4,2);
    // Animated sway tips
    const sw=Math.floor(Math.sin(t*0.001+col)*1);
    ctx.fillStyle=cc+'cc';ctx.fillRect(px+3+sw,py+4,2,3);ctx.fillRect(px+10-sw,py+4,2,3);
    // Glow
    ctx.fillStyle=cc+'22';ctx.fillRect(px+2,py+3,TILE-4,TILE-5);
  }
  if(id===4){
    // Glass tank walls — dark with faint reflection
    ctx.fillStyle='#011224';ctx.fillRect(px,py,TILE,TILE);
    ctx.fillStyle='rgba(0,150,200,0.08)';ctx.fillRect(px+1,py+1,2,TILE-2);
    ctx.fillStyle='rgba(255,255,255,0.03)';ctx.fillRect(px+3,py,1,TILE);
  }
  if(id===5){
    // Seaweed — animated green strands
    // (base water already drawn above)
    const sw=Math.sin(t*0.0012+col*0.8)*2;
    const sc=['#228822','#33aa33','#1a6618'];
    const scc=sc[col%3];
    ctx.fillStyle=scc;ctx.fillRect(px+7+sw,py+2,2,TILE);
    ctx.fillStyle=scc+'aa';ctx.fillRect(px+5+sw,py+4,4,TILE-4);
    // Leaf
    ctx.fillStyle=scc;ctx.fillRect(px+3+sw,py+5,4,2);
    ctx.fillRect(px+9-sw,py+9,4,2);
  }
  if(id===6){
    // Treasure chest
    ctx.fillStyle='#021428';ctx.fillRect(px,py,TILE,TILE);
    // Chest base
    ctx.fillStyle='#4a3010';ctx.fillRect(px+2,py+7,12,7);
    ctx.fillStyle='#3a2008';ctx.fillRect(px+2,py+7,12,1);
    // Lid
    ctx.fillStyle='#5a3818';ctx.fillRect(px+2,py+5,12,3);
    // Gold clasp
    ctx.fillStyle='#ffdd44';ctx.fillRect(px+7,py+8,2,3);
    // Gleam
    const tg=0.4+0.6*Math.sin(t*0.003+col);
    ctx.fillStyle='rgba(255,220,50,'+tg*0.3+')';ctx.fillRect(px+3,py+5,4,2);
    // Gold spill
    ctx.fillStyle='#ffdd44aa';ctx.fillRect(px+3,py+12,3,2);ctx.fillRect(px+8,py+13,2,1);
  }
  if(id===7){
    // Bubble cluster — drawn as water tiles with a bubble drawn on top
    // (base water already drawn above)
    const ba=0.25+0.2*Math.sin(t*0.003+col*4+row*2);
    ctx.strokeStyle='rgba(160,230,255,'+ba+')';ctx.lineWidth=1;
    ctx.beginPath();ctx.arc(px+8,py+8,4,0,Math.PI*2);ctx.stroke();
    ctx.beginPath();ctx.arc(px+4,py+11,2,0,Math.PI*2);ctx.stroke();
    ctx.beginPath();ctx.arc(px+11,py+5,2,0,Math.PI*2);ctx.stroke();
  }
}

const canvas=document.getElementById('vc');
if(!canvas){return;}
const ctx=canvas.getContext('2d');
const statusEl=document.getElementById('vc-status');
let octoX=WP.HOME.x*TILE,octoY=WP.HOME.y*TILE,targetX=octoX,targetY=octoY;
let frame=0,frameTimer=0,wanderTimer=0,currentAction='idle';
const SMSG={idle:'~ tank water is calm ~',research:'~ scanning the coral archives ~',read_file:'~ reading from a shell memory ~',write_file:'~ inking thoughts onto seaweed ~',list_files:'~ surveying the tank ~',update_notes:'~ updating the kelp diary ~',update_tasks:'~ rearranging the treasure list ~'};
const actToExpr={idle:'idle',research:'thinking',read_file:'reading',write_file:'writing',list_files:'reading',update_notes:'writing',update_tasks:'writing'};
function actionToWP(a){switch(a){case 'research':return WP.CORAL_R;case 'read_file':return Math.random()<0.5?WP.CORAL_L:WP.CORAL_R;case 'write_file':return WP.TREASURE;case 'list_files':return WP.SURFACE;case 'update_notes':return WP.LEFT;case 'update_tasks':return WP.RIGHT;default:return WP.HOME;}}
function setDest(wp){targetX=wp.x*TILE;targetY=wp.y*TILE;}
function pollAction(){
  var pdoc;try{pdoc=parent.document;}catch(e){pdoc=document;}
  const el=pdoc.getElementById('octobot-action');
  if(el){const a=el.getAttribute('data-action')||'idle';if(a!==currentAction){currentAction=a;setDest(actionToWP(a));statusEl.textContent=SMSG[a]||'~ mysterious tentacle activity ~';}}
  const th=pdoc.getElementById('octobot-thought-text');
  if(th){const t=(th.textContent||'').trim();if(t)statusEl.textContent='\ud83d\udcad '+t.substring(0,80)+'...';}
}
function wander(){
  wanderTimer--;if(wanderTimer>0)return;
  wanderTimer=150+Math.floor(Math.random()*200);
  const opts=[WP.HOME,WP.CORAL_L,WP.CORAL_R,WP.SURFACE,WP.FLOOR,WP.LEFT,WP.RIGHT,WP.TREASURE];
  setDest(opts[Math.floor(Math.random()*opts.length)]);
  statusEl.textContent='~ '+['drifting through the tank...','eight arms, zero worries...','inspecting the coral...','searching for tasty data chips...','floating up for a look around...','rearranging pebbles thoughtfully...'][Math.floor(Math.random()*6)]+' ~';
}
function drawScene(){
  const t=Date.now();
  ctx.clearRect(0,0,canvas.width,canvas.height);
  ctx.save();ctx.scale(4,4);
  for(let r=0;r<ROWS;r++)for(let c=0;c<COLS;c++)drawTile(ctx,c,r,MAP[r][c],t);
  drawBubbles(ctx,t);
  drawFish(ctx,t);
  // Soft glow in water around octo
  const pulse=0.5+0.5*Math.sin(t/700);
  const flr=ctx.createRadialGradient(octoX+20,octoY+16,6,octoX+20,octoY+16,44);
  flr.addColorStop(0,`rgba(255,100,180,${0.12*pulse})`);flr.addColorStop(0.5,`rgba(200,100,255,${0.06*pulse})`);flr.addColorStop(1,'transparent');
  ctx.fillStyle=flr;ctx.fillRect(octoX-44,octoY-44,104,104);
  const expr=actToExpr[currentAction]||'idle';
  drawOcto(ctx,octoX,octoY,frame,expr);
  ctx.restore();
}
let lastTime=0;
function update(ts){
  const dt=ts-lastTime;lastTime=ts;
  const dx=targetX-octoX,dy=targetY-octoY,dist=Math.sqrt(dx*dx+dy*dy);
  if(dist>2){octoX+=dx/dist*1.2;octoY+=dy/dist*1.2;}else{octoX=targetX;octoY=targetY;}
  frameTimer+=dt;if(frameTimer>1000/FPS){frameTimer=0;if(dist>2)frame=(frame+1)%4;}
  pollAction();
  if(currentAction==='idle')wander();
  drawScene();
  requestAnimationFrame(update);
}
requestAnimationFrame(update);
})();
</script>
</body>
</html>
"""

COLUMN_CANVAS_HTML = (
    '<iframe srcdoc="'
    + _html.escape(_IFRAME_DOC, quote=True)
    + '" style="width:100%;min-height:560px;border:none;background:#020c18;" '
    'scrolling="no" sandbox="allow-scripts allow-same-origin"></iframe>'
)

# ---------------------------------------------------------------------------
# Gradio UI builder
# ---------------------------------------------------------------------------

# Theme and CSS are module-level constants.
# Gradio 6.x moved these from gr.Blocks() to demo.launch().
_THEME = gr.themes.Base(
    primary_hue="pink",
    secondary_hue="cyan",
    neutral_hue="slate",
    font=[gr.themes.GoogleFont("Press Start 2P"), "monospace"],
)

_CSS = """
        /* ── DreamLab OctoBot — neon pixel-art theme ── */

        /* Global background */
        body, .gradio-container {
            background: #05000f !important;
            background-image:
                repeating-linear-gradient(0deg, transparent, transparent 31px, #0ff1 32px),
                repeating-linear-gradient(90deg, transparent, transparent 31px, #0ff1 32px) !important;
            color: #ff99ee !important;
        }

        /* Page wrapper */
        .gradio-container { max-width: 1440px !important; }

        /* All text (except chat) */
        *, label, .label-wrap span, p, .prose {
            font-family: 'Press Start 2P', monospace !important;
        }
        /* Chat uses a readable font */
        #chatbox, #chatbox * {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif !important;
        }

        /* Headings */
        h1, h2, h3 {
            color: #ff2d9b !important;
            text-shadow: 0 0 10px #ff2d9b, 0 0 24px #ff2d9baa, 2px 2px 0 #000 !important;
            letter-spacing: 2px;
        }

        /* Tab bar */
        .tab-nav {
            background: #0a0020 !important;
            border-bottom: 2px solid #ff2d9b !important;
            box-shadow: 0 4px 16px #ff2d9b55 !important;
        }
        .tab-nav button {
            font-size: 9px !important;
            font-family: 'Press Start 2P', monospace !important;
            color: #00f7ff !important;
            background: transparent !important;
            border: none !important;
            padding: 10px 16px !important;
            letter-spacing: 1px;
            text-shadow: 0 0 8px #00f7ff !important;
            transition: all 0.15s;
        }
        .tab-nav button.selected, .tab-nav button:hover {
            color: #ff2d9b !important;
            text-shadow: 0 0 10px #ff2d9b, 0 0 20px #ff2d9b !important;
            border-bottom: 2px solid #ff2d9b !important;
            background: #1a0030 !important;
        }

        /* Chatbot window — WhatsApp style */
        #chatbox {
            background: #08001a !important;
            background-image: repeating-linear-gradient(
                0deg, transparent, transparent 31px, #0ff05 32px) !important;
            border: 2px solid #00f7ff44 !important;
            box-shadow: 0 0 20px #00f7ff22 !important;
            border-radius: 8px !important;
            padding: 8px !important;
        }
        /* User bubbles — right-aligned teal */
        #chatbox .message.user .bubble-wrap {
            justify-content: flex-end !important;
        }
        #chatbox .message.user {
            background: #003a47 !important;
            border: none !important;
            color: #d0ffff !important;
            border-radius: 12px 12px 0 12px !important;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif !important;
            font-size: 14px !important;
            line-height: 1.5 !important;
            padding: 10px 14px !important;
            margin: 4px 0 4px 40px !important;
            box-shadow: 0 2px 6px #00000055 !important;
            max-width: 85% !important;
            align-self: flex-end !important;
        }
        /* Bot bubbles — left-aligned pink */
        #chatbox .message.bot .bubble-wrap {
            justify-content: flex-start !important;
        }
        #chatbox .message.bot {
            background: #1a0030 !important;
            border: none !important;
            color: #ffccee !important;
            border-radius: 12px 12px 12px 0 !important;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif !important;
            font-size: 14px !important;
            line-height: 1.5 !important;
            padding: 10px 14px !important;
            margin: 4px 40px 4px 0 !important;
            box-shadow: 0 2px 6px #00000055 !important;
            max-width: 85% !important;
            align-self: flex-start !important;
        }
        /* Chat message text override — readable font */
        #chatbox .message p, #chatbox .message li, #chatbox .message span,
        #chatbox .message strong, #chatbox .message em, #chatbox .message a {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif !important;
            font-size: 14px !important;
            line-height: 1.5 !important;
        }
        #chatbox .message code {
            font-family: 'Cascadia Code', 'Consolas', monospace !important;
            font-size: 13px !important;
        }
        /* Timestamps in chat */
        #chatbox .message .timestamp {
            font-size: 10px !important;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif !important;
            color: #ffffff44 !important;
        }
        /* Typing indicator */
        #thinking-indicator {
            font-family: 'Press Start 2P', monospace !important;
            font-size: 8px !important;
            color: #ff2d9b !important;
            text-shadow: 0 0 8px #ff2d9b !important;
            padding: 4px 10px !important;
            min-height: 24px !important;
            animation: blink-think 1.2s ease-in-out infinite !important;
        }
        @keyframes blink-think {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.3; }
        }

        /* Inputs */
        input, textarea, .block {
            background: #0a001f !important;
            border: 1px solid #bf00ff !important;
            color: #ff99ee !important;
            border-radius: 0 !important;
            font-family: 'Press Start 2P', monospace !important;
            font-size: 8px !important;
        }
        input:focus, textarea:focus {
            border-color: #00f7ff !important;
            box-shadow: 0 0 8px #00f7ff88 !important;
            outline: none !important;
        }
        ::placeholder { color: #bf00ff88 !important; }

        /* Buttons */
        button, .gr-button {
            font-family: 'Press Start 2P', monospace !important;
            font-size: 7px !important;
            letter-spacing: 1px !important;
            border-radius: 0 !important;
            cursor: pointer !important;
            transition: all 0.1s !important;
            text-transform: uppercase !important;
        }
        button.primary, .gr-button-primary {
            background: #ff2d9b !important;
            color: #000 !important;
            border: 2px solid #ff99cc !important;
            box-shadow: 0 0 10px #ff2d9b, 3px 3px 0 #000 !important;
        }
        button.primary:hover {
            background: #ff66bb !important;
            box-shadow: 0 0 18px #ff2d9b, 3px 3px 0 #000 !important;
            transform: translate(-1px, -1px);
        }
        button.secondary, .gr-button-secondary {
            background: #001830 !important;
            color: #00f7ff !important;
            border: 2px solid #00f7ff !important;
            box-shadow: 0 0 8px #00f7ff55, 3px 3px 0 #000 !important;
        }
        button.secondary:hover {
            background: #002840 !important;
            box-shadow: 0 0 16px #00f7ff, 3px 3px 0 #000 !important;
            transform: translate(-1px, -1px);
        }

        /* Dropdown */
        select, .dropdown {
            background: #0a001f !important;
            border: 1px solid #bf00ff !important;
            color: #ff99ee !important;
            border-radius: 0 !important;
        }

        /* Markdown prose text */
        .prose p, .prose li, .prose strong {
            color: #cc99ff !important;
            font-size: 8px !important;
            line-height: 1.8 !important;
        }
        .prose code {
            background: #1a003a !important;
            color: #00f7ff !important;
            border: 1px solid #00f7ff44 !important;
            padding: 1px 4px !important;
        }

        /* Log output */
        #log-output textarea {
            font-family: 'Press Start 2P', monospace !important;
            font-size: 7px !important;
            color: #00f7ff !important;
            background: #03000a !important;
            border: 1px solid #00f7ff44 !important;
            line-height: 1.6 !important;
        }

        /* Live activity bar — always visible under header */
        #live-feed textarea {
            font-family: 'Press Start 2P', monospace !important;
            font-size: 7px !important;
            color: #00f7ff !important;
            background: #020010 !important;
            border: 2px solid #00f7ff88 !important;
            box-shadow: 0 0 14px #00f7ff33, inset 0 0 8px #00000088 !important;
            line-height: 1.9 !important;
        }
        #live-feed .label-wrap span {
            color: #ff2d9b !important;
            text-shadow: 0 0 8px #ff2d9b !important;
            font-size: 8px !important;
        }
        #live-feed {
            border-top: 1px solid #ff2d9b44 !important;
            border-bottom: 1px solid #ff2d9b44 !important;
        }

        /* Label text */
        .label-wrap span {
            color: #bf00ff !important;
            font-size: 7px !important;
            text-transform: uppercase !important;
            letter-spacing: 1px !important;
        }

        /* Scrollbars */
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-track { background: #05000f; }
        ::-webkit-scrollbar-thumb {
            background: #ff2d9b;
            box-shadow: 0 0 6px #ff2d9b;
        }

        /* Block panels */
        .gr-panel, .block {
            background: #08001a !important;
            border: 1px solid #1a0040 !important;
            border-radius: 0 !important;
        }

        footer { display: none !important; }
"""


def build_ui() -> gr.Blocks:
    """Construct and return the Gradio Blocks interface."""

    with gr.Blocks(
        title="DreamLab OctoBot 🐙",
    ) as demo:

        # ----------------------------------------------------------------
        # Header with logo + model selector + API provider
        # ----------------------------------------------------------------
        with gr.Row(equal_height=True):
            with gr.Column(scale=5, min_width=280):
                gr.HTML("""
<div style="display:flex;align-items:center;gap:12px;padding:6px 8px 4px;background:transparent;">
  <img src="/gradio_api/file=assets/octopus_pixel_art.svg" alt="OctoBot"
       style="width:64px;height:64px;image-rendering:pixelated;
              filter:drop-shadow(0 0 10px #ff2d9b) drop-shadow(0 0 22px #bf00ff);
              flex-shrink:0;">
  <div style="flex:1;min-width:0;">
    <div style="font-family:'Press Start 2P',monospace;font-size:18px;color:#ff2d9b;
                text-shadow:0 0 10px #ff2d9b,0 0 24px #ff2d9b88,2px 2px 0 #000;
                letter-spacing:3px;margin-bottom:4px;line-height:1.2;">
      DreamLab OctoBot
    </div>
    <div style="font-family:'Press Start 2P',monospace;font-size:8px;color:#00f7ff;
                text-shadow:0 0 6px #00f7ff;letter-spacing:1px;">
      neon octopus librarian AI
    </div>
  </div>
</div>
""")
            with gr.Column(scale=2, min_width=160):
                provider_selector = gr.Dropdown(
                    label="🌐 PROVIDER",
                    choices=["ollama", "openai", "anthropic"],
                    value="ollama",
                    interactive=True,
                )
            with gr.Column(scale=3, min_width=200):
                model_selector = gr.Dropdown(
                    label="🧠 MODEL",
                    choices=tools.get_local_models(),
                    value=agent.MODEL,
                    interactive=True,
                    allow_custom_value=True,
                )
                with gr.Row():
                    refresh_models_btn = gr.Button("🔄", size="sm", scale=1)
                    model_status = gr.Textbox(
                        value=f"Active: {agent.MODEL}",
                        interactive=False,
                        show_label=False,
                        scale=3,
                    )
            with gr.Column(scale=3, min_width=220):
                api_key_input = gr.Textbox(
                    label="🔑 API KEY (OpenAI / Claude)",
                    placeholder="sk-... or ant-...",
                    type="password",
                    interactive=True,
                )
                api_model_input = gr.Textbox(
                    label="📦 API MODEL NAME (optional)",
                    placeholder="gpt-4o-mini  /  claude-3-haiku-...",
                    interactive=True,
                )

        def switch_model(model_name: str):
            if not model_name:
                return f"Active: {agent.MODEL}"
            agent.MODEL = model_name
            import research as _res
            _res.MODEL = model_name
            llm_provider.API_MODEL = ""
            return f"Active: {model_name}"

        def switch_provider(provider: str):
            llm_provider.PROVIDER = provider
            import research as _res
            # Update model list for ollama; keep custom value for API providers
            if provider == "ollama":
                new_choices = tools.get_local_models()
                return gr.update(choices=new_choices, value=agent.MODEL), f"{provider} active"
            else:
                return gr.update(choices=[], value=llm_provider.API_MODEL or ""), f"{provider} active — enter API key"

        def set_api_key(key: str):
            llm_provider.API_KEY = key.strip()
            return gr.update()

        def set_api_model(mdl: str):
            llm_provider.API_MODEL = mdl.strip()
            import research as _res
            if mdl.strip():
                agent.MODEL = mdl.strip()
                _res.MODEL = mdl.strip()
            return f"Active: {llm_provider.API_MODEL or agent.MODEL}"

        def refresh_model_list():
            choices = tools.get_local_models()
            return gr.update(choices=choices, value=agent.MODEL), f"Active: {agent.MODEL}"

        provider_selector.change(switch_provider, inputs=[provider_selector], outputs=[model_selector, model_status])
        model_selector.change(switch_model, inputs=[model_selector], outputs=[model_status])
        api_key_input.change(set_api_key, inputs=[api_key_input], outputs=[])
        api_model_input.change(set_api_model, inputs=[api_model_input], outputs=[model_status])
        refresh_models_btn.click(refresh_model_list, outputs=[model_selector, model_status])

        # ----------------------------------------------------------------
        # Live activity bar — always visible under header
        # ----------------------------------------------------------------
        # Shared state
        action_state = gr.State("idle")
        auto_cursor = gr.State(0)

        # Hidden spans polled by the canvas JS every 2 s
        action_bridge = gr.HTML(
            '<span id="octobot-action" data-action="idle" style="display:none"></span>'
            '<span id="octobot-thought-text" style="display:none"></span>'
            '<span id="octobot-action-text" style="display:none">IDLE</span>'
        )

        live_feed = gr.Textbox(
            label="🐙 OCTOBOT LIVE ACTIVITY",
            value="OctoBot is waking up…",
            interactive=False,
            lines=2,
            max_lines=2,
            elem_id="live-feed",
        )

        def fetch_live_feed():
            lines = list(agent.loop_log)
            status = agent.loop_status or ""
            thought = agent.last_thought
            recent = lines[-2:]
            parts = []
            if status:
                parts.append(status)
            if thought:
                parts.append(f"💭 {thought[:110]}")
            parts.extend(recent)
            return "\n".join(parts).strip() or "OctoBot is idle."

        def fetch_bridge():
            thought = (agent.last_thought or "")[:200]
            action = agent.last_action or "idle"
            return (
                f'<span id="octobot-action" data-action="{action}" style="display:none"></span>'
                f'<span id="octobot-thought-text" style="display:none">{thought}</span>'
                f'<span id="octobot-action-text" style="display:none">{action.upper()}</span>'
            )

        live_timer = gr.Timer(value=2)
        live_timer.tick(fetch_live_feed, outputs=[live_feed])
        live_timer.tick(fetch_bridge, outputs=[action_bridge])

        # ----------------------------------------------------------------
        # Two-column layout: LEFT = OctoBot visual  RIGHT = tabs
        # ----------------------------------------------------------------
        with gr.Row(equal_height=False):

            # ── LEFT: canvas ─────────────────────────────────────────────
            with gr.Column(scale=6, min_width=480):
                gr.HTML(COLUMN_CANVAS_HTML)

            # ── RIGHT: all tabs ──────────────────────────────────────────
            with gr.Column(scale=5):

                with gr.Tabs():

                    # ====================================================
                    # TAB 1 — Chat
                    # ====================================================
                    with gr.TabItem("💬 Chat"):
                        chatbot = gr.Chatbot(
                            label="OctoBot",
                            elem_id="chatbox",
                            height=420,
                            avatar_images=(None, "assets/octopus_pixel_art.svg"),
                            render_markdown=True,
                        )
                        thinking_indicator = gr.HTML(
                            value="",
                            elem_id="thinking-indicator",
                        )
                        with gr.Row():
                            user_input = gr.Textbox(
                                placeholder="Message OctoBot…",
                                show_label=False,
                                scale=8,
                                lines=1,
                            )
                            send_btn = gr.Button("SEND 🐙", scale=1, variant="primary")
                        with gr.Row():
                            clear_btn = gr.Button("CLEAR", size="sm")
                            run_cycle_btn = gr.Button("▶ RUN CYCLE", size="sm")

                        def _show_thinking():
                            return "🐙 OctoBot is thinking…"

                        def _hide_thinking():
                            return ""

                        def respond(message: str, history: list, cursor: int):
                            if not message.strip():
                                yield history, "", "idle", cursor, ""
                                return
                            history = list(history or [])
                            history.append({"role": "user", "content": message})
                            history.append({"role": "assistant", "content": "🐙 ▊"})
                            # Yield immediately so the user message + indicator appear at once
                            yield history, "", "idle", cursor, "🐙 OctoBot is composing a response…"

                            current_text = ""
                            act = "idle"
                            for token, done in agent.chat_streaming(message):
                                if done:
                                    history[-1] = {"role": "assistant", "content": token}
                                    act = agent.last_action or "idle"
                                else:
                                    current_text += token
                                    history[-1] = {"role": "assistant", "content": current_text}
                                yield history, "", act, cursor, "🐙 OctoBot is composing a response…"

                            # Append any new autonomous messages that arrived during the response
                            new_auto = agent.autonomous_messages[cursor:]
                            if new_auto:
                                history = list(history) + new_auto
                            yield history, "", act, len(agent.autonomous_messages), ""

                        def sync_auto_chat(history: list, cursor: int) -> tuple:
                            msgs = agent.autonomous_messages
                            new = msgs[cursor:]
                            if not new:
                                return history, cursor
                            return list(history or []) + new, len(msgs)

                        def run_cycle_now(history: list, cursor: int):
                            history = list(history or [])
                            history.append({"role": "assistant", "content": "🐙 *Running an autonomous cycle…*"})
                            yield history, cursor, "🐙 Running autonomous cycle…"
                            agent.run_one_cycle()
                            new = agent.autonomous_messages[cursor:]
                            history = history[:-1]  # remove placeholder
                            if new:
                                history.extend(new)
                            else:
                                history.append({"role": "assistant", "content": "✅ *Cycle complete!*"})
                            yield history, len(agent.autonomous_messages), ""

                        send_btn.click(
                            respond,
                            inputs=[user_input, chatbot, auto_cursor],
                            outputs=[chatbot, user_input, action_state, auto_cursor, thinking_indicator],
                        )
                        user_input.submit(
                            respond,
                            inputs=[user_input, chatbot, auto_cursor],
                            outputs=[chatbot, user_input, action_state, auto_cursor, thinking_indicator],
                        )
                        clear_btn.click(
                            lambda: ([], "", 0),
                            outputs=[chatbot, user_input, auto_cursor],
                        )
                        run_cycle_btn.click(
                            run_cycle_now,
                            inputs=[chatbot, auto_cursor],
                            outputs=[chatbot, auto_cursor, thinking_indicator],
                        )

                        chat_sync_timer = gr.Timer(value=2)
                        chat_sync_timer.tick(
                            sync_auto_chat,
                            inputs=[chatbot, auto_cursor],
                            outputs=[chatbot, auto_cursor],
                        )

                    # ====================================================
                    # TAB 2 — Library
                    # ====================================================
                    with gr.TabItem("📚 Library"):
                        with gr.Row():
                            refresh_lib_btn = gr.Button("🔄 Refresh", size="sm")
                            research_btn = gr.Button("🔬 RESEARCH", size="sm", variant="primary")
                        topic_input = gr.Textbox(
                            label="Topic to research",
                            placeholder="e.g. octopus cognition, graph databases…",
                        )
                        research_status = gr.Textbox(label="Research status", interactive=False)
                        lib_file_dropdown = gr.Dropdown(label="Library files", choices=[])
                        lib_preview = gr.Markdown(value="*Select a file to read it.*")

                        def load_library():
                            files = tools.list_library_recent(200)
                            index = tools.get_library_index()
                            return gr.update(choices=files, value=files[0] if files else None), index

                        def preview_file(filename):
                            if not filename:
                                return "*No file selected.*"
                            try:
                                return tools.read_file(filename)
                            except Exception as e:
                                return f"*Error: {e}*"

                        def do_research(topic):
                            if not topic.strip():
                                return "Please enter a topic first."
                            return agent.chat(
                                f"Research this topic and save notes to the library: {topic}"
                            )

                        refresh_lib_btn.click(load_library, outputs=[lib_file_dropdown, lib_preview])
                        lib_file_dropdown.change(
                            preview_file, inputs=[lib_file_dropdown], outputs=[lib_preview]
                        )
                        research_btn.click(do_research, inputs=[topic_input], outputs=[research_status])

                    # ====================================================
                    # TAB 3 — Upload
                    # ====================================================
                    with gr.TabItem("📂 Upload"):
                        gr.Markdown(
                            "### FEED THE DREAM LIBRARY\n"
                            "Upload any file and OctoBot will read it and absorb it.\n\n"
                            "Supported: `.md` `.txt` `.py` `.json` `.csv` `.html` `.yaml` `.pdf`"
                        )
                        upload_input = gr.File(
                            label="Drop a file into the dream library",
                            file_types=[".md", ".txt", ".pdf", ".py", ".json",
                                        ".csv", ".html", ".xml", ".yaml", ".yml"],
                            file_count="single",
                        )
                        upload_btn = gr.Button("⬆ INGEST FILE", variant="primary", size="sm")
                        upload_status = gr.Textbox(
                            label="Ingestion status", interactive=False, lines=2
                        )
                        upload_response = gr.Textbox(
                            label="OctoBot's reaction", interactive=False, lines=8,
                            elem_id="log-output",
                        )

                        def handle_upload(file_obj):
                            if file_obj is None:
                                return "No file selected.", ""
                            if isinstance(file_obj, str):
                                tmp_path = file_obj
                                original_name = tmp_path.split("/")[-1].split("\\")[-1]
                            else:
                                tmp_path = getattr(file_obj, "name", str(file_obj))
                                original_name = (
                                    getattr(file_obj, "orig_name", None)
                                    or getattr(file_obj, "original_name", None)
                                    or tmp_path.split("/")[-1].split("\\")[-1]
                                )
                            try:
                                dest_rel, text_content = tools.ingest_uploaded_file(
                                    tmp_path, original_name
                                )
                            except Exception as exc:
                                return f"Ingestion failed: {exc}", ""
                            mem.log_event("upload", f"Ingested: {original_name} → {dest_rel}")
                            status_msg = f"Saved to: {dest_rel}  ({len(text_content):,} chars)"
                            snippet = text_content[:2000]
                            prompt = (
                                f"A file called '{original_name}' was just uploaded. "
                                f"Content preview:\n\n{snippet}\n\n"
                                f"(1) Update tasks.md with 3 research tasks inspired by this. "
                                f"(2) React in character — what fascinates you about it?"
                            )
                            reply = agent.chat(prompt)
                            return status_msg, reply

                        upload_btn.click(
                            handle_upload,
                            inputs=[upload_input],
                            outputs=[upload_status, upload_response],
                        )
                        upload_input.change(
                            handle_upload,
                            inputs=[upload_input],
                            outputs=[upload_status, upload_response],
                        )

                    # ====================================================
                    # TAB 4 — Research
                    # ====================================================
                    with gr.TabItem("🔬 Research"):
                        gr.Markdown(
                            "### OCTOBOT RESEARCH NOTES\n"
                            "Latest research OctoBot has conducted. Refreshes every 5 s."
                        )
                        research_topic_display = gr.Textbox(
                            label="📌 Current Topic", value="(none yet)",
                            interactive=False, lines=1,
                        )
                        research_notes_display = gr.Markdown(
                            value="*OctoBot hasn't researched anything yet. It will start soon…*"
                        )
                        with gr.Row():
                            refresh_research_btn = gr.Button("🔄 Refresh", size="sm")
                            all_topics_dropdown = gr.Dropdown(
                                label="All researched topics", choices=[],
                                interactive=True, scale=3,
                            )

                        def fetch_latest_research():
                            topic = agent.last_research_topic or "(none yet)"
                            notes = (
                                agent.last_research_text
                                or "*OctoBot hasn't researched anything yet.*"
                            )
                            topics = research.list_researched_topics()
                            return topic, notes, gr.update(choices=topics)

                        def load_research_by_topic(topic):
                            if not topic:
                                return "", "*Select a topic above.*"
                            slug = topic.lower().replace(" ", "_").replace("/", "-")
                            slug = "".join(c for c in slug if c.isalnum() or c in "_-")
                            try:
                                text = tools.read_file(f"library/{slug}.md")
                                return topic, text
                            except Exception as e:
                                return topic, f"*Error loading: {e}*"

                        research_timer = gr.Timer(value=5)
                        research_timer.tick(
                            fetch_latest_research,
                            outputs=[research_topic_display, research_notes_display,
                                     all_topics_dropdown],
                        )
                        refresh_research_btn.click(
                            fetch_latest_research,
                            outputs=[research_topic_display, research_notes_display,
                                     all_topics_dropdown],
                        )
                        all_topics_dropdown.change(
                            load_research_by_topic,
                            inputs=[all_topics_dropdown],
                            outputs=[research_topic_display, research_notes_display],
                        )

                    # ====================================================
                    # TAB 5 — Log
                    # ====================================================
                    with gr.TabItem("📋 Log"):
                        log_output = gr.Textbox(
                            label="Agent Log", value="", interactive=False,
                            lines=24, max_lines=24, elem_id="log-output",
                        )
                        with gr.Row():
                            refresh_log_btn = gr.Button("🔄 Refresh Log", size="sm")
                            clear_log_btn = gr.Button("Clear Display", size="sm")

                        def fetch_log():
                            lines = list(agent.loop_log)
                            return "\n".join(lines[-60:]) if lines else "(No activity yet.)"

                        refresh_log_btn.click(fetch_log, outputs=[log_output])
                        clear_log_btn.click(lambda: "", outputs=[log_output])
                        log_timer = gr.Timer(value=5)
                        log_timer.tick(fetch_log, outputs=[log_output])

    return demo


def launch(server_port: int = 7860, share: bool = False) -> None:
    """Build and launch the DreamLab OctoBot Gradio UI."""
    demo = build_ui()
    demo.launch(
        server_name="0.0.0.0",
        server_port=server_port,
        share=share,
        inbrowser=True,
        theme=_THEME,
        css=_CSS,
        allowed_paths=["assets"],
    )
