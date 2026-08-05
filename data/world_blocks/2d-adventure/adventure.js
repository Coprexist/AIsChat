/* ============================================================
 * 2D 冒险游戏 — 引擎（零依赖，纯 Canvas 程序化绘制）
 *
 * 结构：配置 → 地图/实体数据 → 游戏状态 → 工具 → 输入
 *       → 存档 → 渲染 → 交互 → 主循环 → 启动
 *
 * 世界变量（沉浸入口注入）：
 *   window.WORLD_ID / WORLD_NAME — 存档隔离 + HUD 展示
 * 定制入口：改 MAP / NPCS / CHESTS / CONFIG 即可，无需动引擎。
 * ============================================================ */
(function () {
  'use strict';

  /* ── 配置 ── */
  var CONFIG = {
    tileSize: 48,        // 瓦片像素
    cols: 16,
    rows: 12,
    stepDuration: 0.16,  // 走一格耗时（秒）——按一下只移动一格（珑哥 2026-08-05）
    saveKeyPrefix: 'world-adventure-v1-',
  };

  /* ── 瓦片类型 ── */
  var T = {
    GRASS: 0, TREE: 1, WATER: 2, WALL: 3, FLOWER: 4, ROAD: 5, PORTAL: 6,
  };

  /* ── 地图（12 行 × 16 列，0=草地 1=树 2=水 3=墙 4=花 5=路 6=传送门） ── */
  var MAP = [
    [0, 0, 2, 2, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 2, 2, 2, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 2, 2, 0, 0, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 5, 5, 5, 1, 1, 0, 0, 0, 0, 0, 0],
    [0, 4, 0, 0, 0, 5, 3, 3, 5, 0, 0, 0, 4, 0, 0, 0],
    [0, 0, 0, 0, 0, 5, 3, 3, 5, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 5, 5, 5, 5, 0, 0, 0, 0, 4, 0, 0],
    [0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0],
    [0, 1, 1, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0],
    [0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 4, 0, 0, 0, 0, 0, 0, 6, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
  ];

  /* ── 实体数据 ── */
  var NPCS = [
    { x: 7, y: 7, name: '村长', color: '#94a3b8',
      lines: [
        '欢迎来到冒险世界！这地方叫「{WORLD_NAME}」。',
        '传说湖边的宝箱里藏着古老的秘密……',
        '东边的树林里也埋着财宝，小心别迷路。',
      ] },
    { x: 2, y: 1, name: '旅人', color: '#34d399',
      lines: [
        '我走了很远的路，这世界的风很舒服。',
        '听说右下角的传送门通往新大陆，但还没人回来过。',
      ] },
  ];

  var CHESTS = [
    { x: 10, y: 4, reward: 10, opened: false },
    { x: 13, y: 10, reward: 20, opened: false },
    { x: 1, y: 9, reward: 5, opened: false },
  ];

  var PORTAL = { x: 12, y: 10 };

  /* ── 游戏状态 ── */
  var state = {
    player: { x: 7, y: 6, dir: 'down', moving: false, frame: 0, walkTimer: 0 },
    step: null,          // 走格动画 {fromX, fromY, toX, toY, t}
    coins: 0,
    dialog: null,        // { name, lines[], index, text, charIdx, timer }
    banner: null,        // { text, timer }
    hint: null,          // 可交互对象（'npc' | 'chest' | 'portal'）
  };

  var canvas, ctx, lastTime = 0;

  /* ── 世界变量 ── */
  var worldId = window.WORLD_ID || 0;
  var worldName = window.WORLD_NAME || '未知世界';

  /* ════════════════════════════════════════════════════════════
   * 工具
   * ════════════════════════════════════════════════════════════ */

  function tileAt(c, r) {
    if (r < 0 || r >= MAP.length || c < 0 || c >= MAP[r].length) return T.TREE;
    return MAP[r][c];
  }

  function isWalkable(c, r) {
    var t = tileAt(c, r);
    return t !== T.TREE && t !== T.WATER && t !== T.WALL;
  }

  function gridToPx(c, r) { return { x: c * CONFIG.tileSize, y: r * CONFIG.tileSize }; }

  function pxToGrid(x, y) {
    return { c: Math.floor(x / CONFIG.tileSize), r: Math.floor(y / CONFIG.tileSize) };
  }

  /* ════════════════════════════════════════════════════════════
   * 输入
   * ════════════════════════════════════════════════════════════ */

  var DIR_KEYMAP = {
    ArrowUp: 'up', KeyW: 'up',
    ArrowDown: 'down', KeyS: 'down',
    ArrowLeft: 'left', KeyA: 'left',
    ArrowRight: 'right', KeyD: 'right',
  };

  function onKeyDown(e) {
    // 命令输入框聚焦时：不触发游戏按键（E/WASD 留给打字）
    if (e.target && e.target.tagName === 'INPUT') return;
    if (e.repeat) return;
    var d = DIR_KEYMAP[e.code];
    if (d) { e.preventDefault(); startStep(d); return; }
    if (e.code === 'KeyE' || e.code === 'Space') { e.preventDefault(); interact(); }
  }

  function onKeyUp() { /* 按一下走一格：松开无需处理 */ }

  function bindTouchKeys() {
    document.querySelectorAll('.tk').forEach(function (btn) {
      var dir = btn.dataset.dir;
      var act = btn.dataset.act;
      var tap = function (e) { e.preventDefault(); if (dir) startStep(dir); };
      btn.addEventListener('touchstart', tap, { passive: false });
      btn.addEventListener('mousedown', tap);
      if (act) btn.addEventListener('click', interact);
    });
  }

  /* ════════════════════════════════════════════════════════════
   * 存档（localStorage，按 WORLD_ID 隔离）
   * ════════════════════════════════════════════════════════════ */

  function saveKey() { return CONFIG.saveKeyPrefix + worldId; }

  function save() {
    try {
      localStorage.setItem(saveKey(), JSON.stringify({
        x: state.player.x, y: state.player.y,
        coins: state.coins,
        chests: CHESTS.map(function (c) { return { x: c.x, y: c.y, opened: c.opened }; }),
      }));
    } catch (e) { /* 存储不可用则跳过（隐私模式等） */ }
  }

  function load() {
    try {
      var raw = localStorage.getItem(saveKey());
      if (!raw) return;
      var d = JSON.parse(raw);
      if (typeof d.x === 'number') state.player.x = d.x;
      if (typeof d.y === 'number') state.player.y = d.y;
      if (typeof d.coins === 'number') state.coins = d.coins;
      if (Array.isArray(d.chests)) {
        d.chests.forEach(function (s) {
          var c = CHESTS.find(function (c2) { return c2.x === s.x && c2.y === s.y; });
          if (c) c.opened = !!s.opened;
        });
      }
    } catch (e) { /* 存档损坏则忽略 */ }
  }

  /* ════════════════════════════════════════════════════════════
   * 渲染 — 瓦片
   * ════════════════════════════════════════════════════════════ */

  function drawGrass(x, y, variant) {
    ctx.fillStyle = variant ? '#3f6046' : '#3a5a40';
    ctx.fillRect(x, y, CONFIG.tileSize, CONFIG.tileSize);
    // 噪点：少量深色草叶
    ctx.fillStyle = 'rgba(0,0,0,0.12)';
    for (var i = 0; i < 3; i++) {
      var sx = x + ((i * 17 + variant * 7) % 44) + 2;
      var sy = y + ((i * 13 + variant * 11) % 44) + 2;
      ctx.fillRect(sx, sy, 2, 2);
    }
  }

  function drawFlower(x, y) {
    drawGrass(x, y, 1);
    ctx.fillStyle = '#f472b6';
    ctx.fillRect(x + 22, y + 18, 4, 4);
    ctx.fillStyle = '#fbbf24';
    ctx.fillRect(x + 28, y + 30, 3, 3);
  }

  function drawTree(x, y, time) {
    drawGrass(x, y, 1);
    // 树干
    ctx.fillStyle = '#7c5a3a';
    ctx.fillRect(x + 20, y + 28, 8, 16);
    // 树冠（双层圆，微风吹动偏移）
    var sway = Math.sin(time * 1.5 + x) * 1.2;
    ctx.fillStyle = '#2d6a4f';
    ctx.beginPath();
    ctx.arc(x + 24 + sway, y + 18, 15, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = '#40916c';
    ctx.beginPath();
    ctx.arc(x + 20 + sway, y + 22, 9, 0, Math.PI * 2);
    ctx.fill();
  }

  function drawWater(x, y, time) {
    ctx.fillStyle = '#1d4ed8';
    ctx.fillRect(x, y, CONFIG.tileSize, CONFIG.tileSize);
    // 波纹（两帧闪烁）
    var phase = Math.floor(time * 2 + x) % 2;
    ctx.fillStyle = phase ? 'rgba(255,255,255,0.18)' : 'rgba(255,255,255,0.08)';
    ctx.fillRect(x + 10, y + 16, 12, 3);
    ctx.fillRect(x + 26, y + 32, 10, 3);
  }

  function drawWall(x, y) {
    ctx.fillStyle = '#8d99ae';
    ctx.fillRect(x, y, CONFIG.tileSize, CONFIG.tileSize);
    ctx.fillStyle = '#6c757d';
    // 砖缝
    ctx.fillRect(x, y + 16, CONFIG.tileSize, 2);
    ctx.fillRect(x, y + 34, CONFIG.tileSize, 2);
    ctx.fillRect(x + 24, y, 2, 16);
    ctx.fillRect(x + 8, y + 16, 2, 18);
    ctx.fillRect(x + 40, y + 34, 2, 14);
    ctx.fillStyle = 'rgba(255,255,255,0.15)';
    ctx.fillRect(x, y, CONFIG.tileSize, 3);
  }

  function drawRoad(x, y, variant) {
    ctx.fillStyle = variant ? '#b09a6e' : '#a58e63';
    ctx.fillRect(x, y, CONFIG.tileSize, CONFIG.tileSize);
    ctx.fillStyle = 'rgba(0,0,0,0.08)';
    ctx.fillRect(x + ((variant * 19) % 40), y + ((variant * 7) % 40), 5, 3);
  }

  function drawPortal(x, y, time) {
    drawGrass(x, y, 1);
    var cx = x + 24, cy = y + 26;
    var r = 13 + Math.sin(time * 3) * 2;
    var grad = ctx.createRadialGradient(cx, cy, 2, cx, cy, r + 4);
    grad.addColorStop(0, '#f5d0fe');
    grad.addColorStop(0.5, '#a855f7');
    grad.addColorStop(1, 'rgba(88,28,135,0.9)');
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = '#e9d5ff';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(cx, cy, r + 3, time * 2, time * 2 + Math.PI * 1.5);
    ctx.stroke();
  }

  /* ── 渲染 — 角色 ── */

  function drawPerson(x, y, color, hatColor, moving, frame, name) {
    var px = Math.round(x), py = Math.round(y);
    // 脚下阴影
    ctx.fillStyle = 'rgba(0,0,0,0.25)';
    ctx.beginPath();
    ctx.ellipse(px + 12, py + 30, 10, 4, 0, 0, Math.PI * 2);
    ctx.fill();
    // 脚（走路摆动）
    var leg = moving && frame ? 3 : 0;
    ctx.fillStyle = '#1f2937';
    ctx.fillRect(px + 6 + leg, py + 22, 5, 8);
    ctx.fillRect(px + 14 - leg, py + 22, 5, 8);
    // 身体
    ctx.fillStyle = color;
    ctx.fillRect(px + 6, py + 12, 13, 12);
    // 手臂
    ctx.fillRect(px + 3, py + 12, 3, 9);
    ctx.fillRect(px + 19, py + 12, 3, 9);
    // 头
    ctx.fillStyle = '#fcd7b8';
    ctx.fillRect(px + 8, py + 3, 9, 9);
    // 帽子
    ctx.fillStyle = hatColor;
    ctx.fillRect(px + 6, py, 13, 4);
    ctx.fillRect(px + 4, py + 3, 17, 3);
    // 眼睛
    ctx.fillStyle = '#111827';
    ctx.fillRect(px + 10, py + 6, 2, 2);
    ctx.fillRect(px + 14, py + 6, 2, 2);
    // 名字标签
    if (name) {
      ctx.font = 'bold 11px sans-serif';
      ctx.textAlign = 'center';
      ctx.fillStyle = 'rgba(0,0,0,0.55)';
      ctx.fillText(name, px + 12, py - 4);
      ctx.fillStyle = '#e2e8f0';
      ctx.fillText(name, px + 12, py - 5);
    }
  }

  function drawChest(x, y, opened, time) {
    drawGrass(x, y, 1);
    var px = x + 6, py = y + 16;
    ctx.fillStyle = '#92400e';
    ctx.fillRect(px, py + 10, 36, 20);
    // 盖
    if (opened) {
      ctx.fillStyle = '#b45309';
      ctx.fillRect(px, py - 2, 36, 12);
      ctx.fillStyle = '#f59e0b';
      ctx.fillRect(px, py - 10, 36, 9);
      ctx.fillStyle = 'rgba(255,255,255,0.25)';
      ctx.fillRect(px, py - 10, 36, 3);
    } else {
      ctx.fillStyle = '#b45309';
      ctx.fillRect(px, py - 2, 36, 12);
      ctx.fillStyle = '#f59e0b';
      ctx.fillRect(px, py + 2, 36, 3);
      // 锁
      ctx.fillStyle = '#fbbf24';
      ctx.fillRect(px + 15, py + 8, 6, 8);
      ctx.fillStyle = '#92400e';
      ctx.fillRect(px + 16, py + 5, 4, 4);
    }
    ctx.fillStyle = 'rgba(0,0,0,0.2)';
    ctx.fillRect(px, py + 10, 36, 2);
    // 打开后的闪光
    if (opened && Math.floor(time * 3) % 2 === 0) {
      ctx.fillStyle = 'rgba(251,191,36,0.5)';
      ctx.fillRect(px + 4, py - 14, 4, 4);
      ctx.fillRect(px + 28, py - 12, 3, 3);
    }
  }

  /* ════════════════════════════════════════════════════════════
   * 交互
   * ════════════════════════════════════════════════════════════ */

  function nearestInteractable() {
    var p = state.player;
    var pg = { c: Math.round(p.x), r: Math.round(p.y) };
    var result = null;
    NPCS.forEach(function (n) {
      if (Math.abs(n.x - pg.c) <= 1 && Math.abs(n.y - pg.r) <= 1) result = { kind: 'npc', npc: n };
    });
    CHESTS.forEach(function (c) {
      if (!c.opened && c.x === pg.c && c.y === pg.r) result = { kind: 'chest', chest: c };
    });
    if (PORTAL.x === pg.c && PORTAL.y === pg.r) result = { kind: 'portal' };
    return result;
  }

  function interact() {
    if (state.dialog) { advanceDialog(); return; }
    if (state.banner) return;
    var target = nearestInteractable();
    if (!target) return;
    if (target.kind === 'npc') startDialog(target.npc.name, target.npc.color, target.npc.lines);
    else if (target.kind === 'chest') openChest(target.chest);
    else if (target.kind === 'portal') showBanner('✦ 通往新大陆的传送门（下一区域敬请期待）');
  }

  function openChest(chest) {
    chest.opened = true;
    state.coins += chest.reward;
    updateHUD();
    save();
    showBanner('🪙 获得 ' + chest.reward + ' 金币！');
  }

  /* ── 对话框（打字机效果） ── */

  function startDialog(name, color, lines) {
    state.dialog = { name: name, color: color, lines: lines, index: 0, text: '', charIdx: 0 };
    document.getElementById('dialog-name').textContent = name;
    document.getElementById('dialog-name').style.color = color;
    document.getElementById('dialog').classList.remove('hidden');
  }

  function advanceDialog() {
    var d = state.dialog;
    if (!d) return;
    if (d.charIdx < d.text.length) { d.charIdx = d.text.length; return; } // 跳过打字
    d.index += 1;
    if (d.index >= d.lines.length) {
      state.dialog = null;
      document.getElementById('dialog').classList.add('hidden');
      return;
    }
    d.text = '';
    d.charIdx = 0;
  }

  function tickDialog(dt) {
    var d = state.dialog;
    if (!d) return;
    if (d.text === '') {
      d.text = d.lines[d.index].replace('{WORLD_NAME}', worldName);
      d.charIdx = 0;
    }
    d.charIdx = Math.min(d.charIdx + dt * 40, d.text.length);
    document.getElementById('dialog-text').textContent = d.text.slice(0, Math.floor(d.charIdx));
    document.getElementById('dialog-next').style.visibility =
      d.charIdx >= d.text.length ? 'visible' : 'hidden';
  }

  function showBanner(text) {
    state.banner = { text: text, timer: 2.2 };
    var el = document.getElementById('banner');
    el.textContent = text;
    el.classList.remove('hidden');
  }

  function tickBanner(dt) {
    if (!state.banner) return;
    state.banner.timer -= dt;
    if (state.banner.timer <= 0) {
      state.banner = null;
      document.getElementById('banner').classList.add('hidden');
    }
  }

  /* ════════════════════════════════════════════════════════════
   * 世界状态订阅（2.5：世界程序发布 → 实时应用，零轮询）
   * 世界程序经受控 API POST /world/{id}/api/state 发布，页面 EventSource 接收：
   *   {npc_name, npc_say}   → NPC 弹出对话（npc_name 匹配 NPCS 名字）
   *   {npc_name, npc_move}  → NPC 移动到 {x, y}（格子坐标）
   *   {banner}              → 顶部横幅
   * ════════════════════════════════════════════════════════════ */

  function bindWorldEvents() {
    if (!worldId) return;
    var es = new EventSource('/world/' + worldId + '/events');
    es.onmessage = function (e) {
      var state;
      try { state = JSON.parse(e.data); } catch (err) { return; }
      applyWorldState(state);
    };
    // EventSource 断线自动重连，无需处理
  }

  function applyWorldState(state) {
    // NPC 说话
    if (state.npc_say) {
      startDialog(state.npc_name || 'NPC', '#a78bfa', [String(state.npc_say)]);
    }
    // NPC 移动（格子坐标）
    if (state.npc_move && typeof state.npc_move.x === 'number' && typeof state.npc_move.y === 'number') {
      var npc = NPCS.find(function (n) { return n.name === state.npc_name; });
      if (npc) {
        npc.x = state.npc_move.x;
        npc.y = state.npc_move.y;
      }
    }
    // 横幅
    if (state.banner) {
      showBanner(String(state.banner));
    }
  }

  /* ════════════════════════════════════════════════════════════
   * 命令输入框：页面内直接发群消息命令（不用切回群聊）
   * 内容发到绑定群（window.GROUP_ID）→ 群消息钩子 → 世界程序
   * → 响应经 SSE 实时回来（applyWorldState）。零新增后端。
   * ════════════════════════════════════════════════════════════ */

  function bindCommandInput() {
    var input = document.getElementById('cmd-input');
    var send = document.getElementById('cmd-send');
    if (!input || !send) return;
    var doSend = function () {
      var text = input.value.trim();
      if (!text) return;
      sendCommand(text);
      input.value = '';
    };
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); doSend(); }
      if (e.key === 'Escape') { input.blur(); }
    });
    send.addEventListener('click', doSend);
  }

  function sendCommand(text) {
    var gid = window.GROUP_ID;
    var token = localStorage.getItem('access_token');
    if (!gid) { showBanner('本世界未绑定群聊，无法发送命令'); return; }
    if (!token) { showBanner('未登录：请从主界面进入世界（5227 端口）'); return; }
    var headers = { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token };
    var body = JSON.stringify({ content: text });
    // 前端（5227，vite /api 代理）用 /api 前缀；直接访问 backend（5228）时回退原生路由
    fetch('/api/groups/' + gid + '/messages', { method: 'POST', headers: headers, body: body })
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r; })
      .catch(function () {
        return fetch('/groups/' + gid + '/messages', { method: 'POST', headers: headers, body: body });
      })
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); })
      .then(function () { showBanner('已发送：' + text); })
      .catch(function (err) { showBanner('发送失败：' + err.message); });
  }

  /* ════════════════════════════════════════════════════════════
   * 更新（移动 + 碰撞）
   * ════════════════════════════════════════════════════════════ */

  function playerGrid() {
    return { c: Math.round(state.player.x + 0.5), r: Math.round(state.player.y + 0.5) };
  }

  /* ── 走格移动（按一下走一格，平滑滑步） ── */

  var DIR_OFFSET = {
    up: { dx: 0, dy: -1 }, down: { dx: 0, dy: 1 },
    left: { dx: -1, dy: 0 }, right: { dx: 1, dy: 0 },
  };

  function startStep(dir) {
    var p = state.player;
    if (state.step || state.dialog || state.banner) return;
    var g = playerGrid();
    var off = DIR_OFFSET[dir];
    var toC = g.c + off.dx, toR = g.r + off.dy;
    if (!isWalkable(toC, toR)) { p.dir = dir; return; }  // 撞墙：转个方向但不走
    p.dir = dir;
    state.step = { fromX: p.x, fromY: p.y, toX: toC, toY: toR, t: 0 };
  }

  function update(dt) {
    var p = state.player;

    // 走格动画推进
    if (state.step) {
      var s = state.step;
      s.t = Math.min(s.t + dt / CONFIG.stepDuration, 1);
      p.x = s.fromX + (s.toX - s.fromX) * s.t;
      p.y = s.fromY + (s.toY - s.fromY) * s.t;
      p.moving = true;
      p.walkTimer += dt;
      if (p.walkTimer > 1 / 6) { p.walkTimer = 0; p.frame = 1 - p.frame; }
      if (s.t >= 1) {
        p.x = s.toX; p.y = s.toY;
        state.step = null;
        p.moving = false;
        save();  // 落格后存档
        // 传送门触发：角色中心踩到传送门格
        var g = playerGrid();
        if (g.c === PORTAL.x && g.r === PORTAL.y && !state.banner && !state.dialog) {
          interact();
        }
      }
    } else {
      p.moving = false;
    }

    // 交互提示
    var target = state.dialog || state.banner ? null : nearestInteractable();
    var hintEl = document.getElementById('interact-hint');
    if (target) {
      var label = target.kind === 'npc' ? '对话' : target.kind === 'chest' ? '打开宝箱' : '传送门';
      hintEl.innerHTML = '按 <b>E</b> ' + label;
      hintEl.classList.remove('hidden');
    } else {
      hintEl.classList.add('hidden');
    }

    tickDialog(dt);
    tickBanner(dt);
  }

  /* ── 渲染主流程 ── */

  function render(time) {
    // 瓦片
    for (var r = 0; r < CONFIG.rows; r++) {
      for (var c = 0; c < CONFIG.cols; c++) {
        var x = c * CONFIG.tileSize, y = r * CONFIG.tileSize;
        var t = MAP[r][c];
        if (t === T.GRASS) drawGrass(x, y, (c + r) % 3);
        else if (t === T.FLOWER) drawFlower(x, y);
        else if (t === T.TREE) drawTree(x, y, time);
        else if (t === T.WATER) drawWater(x, y, time);
        else if (t === T.WALL) drawWall(x, y);
        else if (t === T.ROAD) drawRoad(x, y, (c + r) % 2);
        else if (t === T.PORTAL) drawPortal(x, y, time);
      }
    }
    // 宝箱
    CHESTS.forEach(function (c) {
      var g = gridToPx(c.x, c.y);
      drawChest(g.x, g.y, c.opened, time);
    });
    // NPC
    NPCS.forEach(function (n) {
      var g = gridToPx(n.x, n.y);
      drawPerson(g.x + 12, g.y + 18, n.color, '#1f2937', false, 0, n.name);
    });
    // 玩家（最后画，保证在最上层）
    var p = state.player;
    drawPerson(p.x * CONFIG.tileSize, p.y * CONFIG.tileSize, '#6366f1', '#312e81', p.moving, p.frame);
  }

  /* ════════════════════════════════════════════════════════════
   * 主循环 + 启动
   * ════════════════════════════════════════════════════════════ */

  function loop(t) {
    var dt = Math.min((t - lastTime) / 1000, 0.05); // 防切后台后大步长
    lastTime = t;
    update(dt);
    render(t / 1000);
    requestAnimationFrame(loop);
  }

  function updateHUD() {
    document.getElementById('hud-coin-count').textContent = state.coins;
  }

  function init() {
    canvas = document.getElementById('game');
    ctx = canvas.getContext('2d');
    document.getElementById('hud-world-name').textContent = worldName;
    document.getElementById('hud-world-id').textContent = '世界 #' + worldId;
    load();
    updateHUD();
    bindWorldEvents();
    bindCommandInput();
    document.addEventListener('keydown', onKeyDown);
    document.addEventListener('keyup', onKeyUp);
    bindTouchKeys();
    requestAnimationFrame(loop);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
