// ==================== 主逻辑 ====================
'use strict';

// ---------- DOM引用 ----------
const $ = id => document.getElementById(id);
const timeDisplay = $('time-display');
const progressRing = $('progress-ring');
const statusText = $('status-text');
const startBtn = $('start-btn');
const resetBtn = $('reset-btn');
const timerCard = $('timer-card');
const dotsContainer = $('dots');
const cycleCount = $('cycle-count');
const modeTabs = document.querySelectorAll('.mode-tab');
const fullscreenBtn = $('fullscreen-btn');
const settingsBtn = $('settings-btn');
const settingsModal = $('settings-modal');
const todoInput = $('todo-input');
const todoAddBtn = $('todo-add-btn');
const todoList = $('todo-list');
const todoCount = $('todo-count');
const todoClearBtn = $('todo-clear-btn');
const soundButtons = document.querySelectorAll('.sound-btn');
const volumeSlider = $('volume-slider');
const statSessions = $('stat-sessions');
const statMinutes = $('stat-minutes');
const statStreak = $('stat-streak');
const statOnline = $('stat-online');
const statTotal = $('stat-total');
const studyChart = $('study-chart');
const quoteText = $('quote');
const toastContainer = $('toast-container');
const sidebar = $('sidebar');

// 设置相关
const setFocus = $('set-focus');
const setShort = $('set-short');
const setLong = $('set-long');
const setIntervalInput = $('set-interval');
const setAutoStart = $('set-auto-start');
const setStereo = $('set-stereo');
const setProgressMode = $('set-progress-mode');
const setProgressCap = $('set-progress-cap');
const modalCancel = $('modal-cancel');
const modalSave = $('modal-save');

// ---------- 存储 ----------
function loadStorage() {
    try {
        const raw = localStorage.getItem('studyroom_settings');
        if (raw) {
            const s = JSON.parse(raw);
            // 设置版本：旧版存档（elapsed/round 默认、间隔限 2~8）→ 采用新版默认
            if (!s._v || s._v < SETTINGS_VERSION) {
                state.settings = { ...DEFAULT_SETTINGS };
            } else {
                state.settings = { ...DEFAULT_SETTINGS, ...s };
            }
        }
        const t = localStorage.getItem('studyroom_todos');
        if (t) state.todos = JSON.parse(t);
        const st = localStorage.getItem('studyroom_stats');
        if (st) state.stats = JSON.parse(st);
    } catch(e) {}
}
function saveSettings() {
    state.settings._v = SETTINGS_VERSION;
    localStorage.setItem('studyroom_settings', JSON.stringify(state.settings));
    studySyncSettings();   // 设置变更 → 同步服务器
}
function saveTodos() { localStorage.setItem('studyroom_todos', JSON.stringify(state.todos)); }
function saveStats() { localStorage.setItem('studyroom_stats', JSON.stringify(state.stats)); }

function getTodayKey() {
    const d = new Date();
    return `${d.getFullYear()}-${d.getMonth()+1}-${d.getDate()}`;
}
function getTodayStats() {
    const key = getTodayKey();
    return state.stats[key] || { sessions: 0, minutes: 0 };
}
function updateTodayStats(ds, dm) {
    const key = getTodayKey();
    if (!state.stats[key]) state.stats[key] = { sessions: 0, minutes: 0 };
    state.stats[key].sessions += ds;
    state.stats[key].minutes += dm;
    saveStats();
    updateStatsDisplay();
}
function calculateStreak() {
    let streak = 0;
    const d = new Date();
    const todayKey = getTodayKey();
    if (!state.stats[todayKey] || state.stats[todayKey].sessions === 0) d.setDate(d.getDate() - 1);
    for (let i = 0; i < 3650; i++) {
        const key = `${d.getFullYear()}-${d.getMonth()+1}-${d.getDate()}`;
        if (state.stats[key] && state.stats[key].sessions > 0) {
            streak++;
            d.setDate(d.getDate() - 1);
        } else break;
    }
    return streak;
}

// ---------- 计时器 ----------
function getModeSeconds(mode) {
    return (state.settings[mode] || (mode === 'focus' ? 25 : mode === 'short' ? 5 : 15)) * 60;
}
function formatTime(sec) {
    sec = Math.max(0, Math.floor(sec));
    return `${String(Math.floor(sec / 60)).padStart(2, '0')}:${String(sec % 60).padStart(2, '0')}`;
}
function updateTimerDisplay() {
    const sec = state.isRunning ? Math.max(0, (state.endTime - Date.now()) / 1000) : state.remainingSeconds;
    timeDisplay.textContent = formatTime(sec);
    setRingProgress(sec);
    return sec;
}
// 统一进度环渲染（周长=100 标准方案）：
//   progressMode: elapsed = 环随已过时间填充（空→满）；remaining = 环随剩余递减（满→空）
//   capStyle:     round = 圆形端口；butt = 平直精确端口
function setRingProgress(sec) {
    if (!progressRing) return;
    const total = state.totalSeconds || 1;
    const rem = Math.min(1, Math.max(0, sec / total));
    const p = state.settings.progressMode === 'remaining' ? rem : 1 - rem;
    progressRing.style.strokeDashoffset = String(100 * (1 - p));
    progressRing.style.strokeLinecap = state.settings.capStyle === 'butt' ? 'butt' : 'round';
}
function updateUI() {
    timerCard.className = `timer-card mode-${state.mode}`;
    modeTabs.forEach(tab => tab.classList.toggle('active', tab.dataset.mode === state.mode));
    if (state.isRunning) {
        statusText.textContent = MODES[state.mode].status;
        statusText.classList.add('running');
    } else {
        statusText.textContent = state.mode === 'focus' ? '准备开始' : '准备休息';
        statusText.classList.remove('running');
    }
    if (state.isRunning) {
        startBtn.textContent = '暂停';
        startBtn.classList.add('running');
    } else {
        startBtn.textContent = state.mode === 'focus' ? '开始专注' : '开始休息';
        startBtn.classList.remove('running');
    }
    updateTimerDisplay();
    updateDots();
}
function updateDots() {
    const interval = state.settings.interval;
    dotsContainer.innerHTML = '';
    for (let i = 0; i < interval; i++) {
        const dot = document.createElement('div');
        dot.className = 'dot' + (i < state.currentCycle ? ' filled' : '');
        dotsContainer.appendChild(dot);
    }
    cycleCount.textContent = `${state.currentCycle}/${interval}`;
}
function switchMode(mode) {
    if (state.isRunning || state.isPaused) {
        if (!confirm('切换模式将重置计时器，确定吗？')) return;
        stopTimer();
    }
    state.mode = mode;
    state.remainingSeconds = getModeSeconds(mode);
    state.totalSeconds = state.remainingSeconds;
    state.isRunning = false;
    state.isPaused = false;
    state.endTime = null;
    updateUI();
}
function startTimer() {
    if (state.isRunning) return;
    state.isRunning = true;
    state.isPaused = false;
    state.endTime = Date.now() + state.remainingSeconds * 1000;
    state.timerId = setInterval(() => {
        const sec = updateTimerDisplay();
        if (sec <= 0) handleComplete();
    }, 200);
    // 进度环用 rAF 逐帧平滑驱动（60fps，无 transition 滞后）
    state.rafId = requestAnimationFrame(updateRing);
    updateUI();
}
// rAF 驱动的圆形进度：按毫秒剩余时间逐帧更新
function updateRing() {
    if (!state.isRunning) return;
    const sec = Math.max(0, (state.endTime - Date.now()) / 1000);
    setRingProgress(sec);
    state.rafId = requestAnimationFrame(updateRing);
}
function pauseTimer() {
    if (!state.isRunning) return;
    state.remainingSeconds = Math.max(0, (state.endTime - Date.now()) / 1000);
    clearInterval(state.timerId);
    state.timerId = null;
    if (state.rafId) { cancelAnimationFrame(state.rafId); state.rafId = null; }
    state.isRunning = false;
    state.isPaused = true;
    state.endTime = null;
    updateUI();
}
function resumeTimer() {
    if (!state.isPaused) return;
    startTimer();
    state.isPaused = false;
}
function toggleTimer() {
    if (state.isRunning) pauseTimer();
    else if (state.isPaused) resumeTimer();
    else startTimer();
}
function resetTimer() {
    clearInterval(state.timerId);
    state.timerId = null;
    if (state.rafId) { cancelAnimationFrame(state.rafId); state.rafId = null; }
    state.isRunning = false;
    state.isPaused = false;
    state.endTime = null;
    state.remainingSeconds = getModeSeconds(state.mode);
    state.totalSeconds = state.remainingSeconds;
    updateUI();
}
function stopTimer() {
    clearInterval(state.timerId);
    state.timerId = null;
    if (state.rafId) { cancelAnimationFrame(state.rafId); state.rafId = null; }
    state.isRunning = false;
    state.isPaused = false;
    state.endTime = null;
}
function handleComplete() {
    clearInterval(state.timerId);
    state.timerId = null;
    if (state.rafId) { cancelAnimationFrame(state.rafId); state.rafId = null; }
    state.isRunning = false;
    state.isPaused = false;
    playChime();
    if (state.mode === 'focus') {
        state.sessionsCompleted++;
        state.currentCycle++;
        updateTodayStats(1, state.settings.focus);
        studyRecord(state.settings.focus);   // 云端记录学习时长
        showToast('🎉 完成一个专注周期！');
        if (state.currentCycle >= state.settings.interval) {
            state.currentCycle = 0;
            state.mode = 'long';
            showToast('🌿 全部周期完成，来一个长休息吧！');
        } else {
            state.mode = 'short';
            showToast('☕ 休息一下');
        }
    } else {
        state.mode = 'focus';
        showToast('🎯 休息结束，继续加油！');
    }
    state.remainingSeconds = getModeSeconds(state.mode);
    state.totalSeconds = state.remainingSeconds;
    updateUI();
    studySyncCycle();   // 周期进度变化 → 同步服务器（换设备续上）
    if (state.settings.autoStart) setTimeout(startTimer, 1000);
}

// ---------- 待办 ----------
function renderTodos() {
    todoList.innerHTML = '';
    if (state.todos.length === 0) {
        todoList.innerHTML = '<div style="color:var(--text-muted);text-align:center;padding:10px;">暂无任务</div>';
        todoClearBtn.style.display = 'none';
    } else {
        state.todos.forEach((todo, i) => {
            const li = document.createElement('li');
            li.className = 'todo-item';
            li.innerHTML = `<input type="checkbox" class="todo-checkbox" data-idx="${i}" ${todo.done ? 'checked' : ''}>
                <span class="todo-text ${todo.done ? 'done' : ''}">${escapeHtml(todo.text)}</span>
                <button class="todo-delete" data-idx="${i}">×</button>`;
            todoList.appendChild(li);
        });
        const hasCompleted = state.todos.some(t => t.done);
        todoClearBtn.style.display = hasCompleted ? 'block' : 'none';
    }
    todoCount.textContent = state.todos.length;
}
function escapeHtml(s) {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}
function addTodo(text) {
    const t = text.trim();
    if (!t) return;
    state.todos.push({ text: t, done: false });
    saveTodos();
    renderTodos();
}
function toggleTodo(idx) {
    if (idx >= 0 && idx < state.todos.length) {
        state.todos[idx].done = !state.todos[idx].done;
        saveTodos();
        renderTodos();
    }
}
function deleteTodo(idx) {
    state.todos.splice(idx, 1);
    saveTodos();
    renderTodos();
}
function clearCompleted() {
    state.todos = state.todos.filter(t => !t.done);
    saveTodos();
    renderTodos();
}

// ---------- 统计显示 ----------
function updateStatsDisplay() {
    const today = getTodayStats();
    statSessions.textContent = today.sessions;
    statMinutes.textContent = today.minutes;
    statStreak.textContent = calculateStreak();
}

// ---------- Toast ----------
function showToast(msg) {
    const t = document.createElement('div');
    t.className = 'toast';
    t.textContent = msg;
    toastContainer.appendChild(t);
    setTimeout(() => t.remove(), 2800);
}

// ---------- 全屏 ----------
function toggleFullscreen() {
    if (!document.fullscreenElement) {
        document.documentElement.requestFullscreen();
    } else {
        document.exitFullscreen();
    }
}
function updateFullscreenBtn() {
    const fs = !!document.fullscreenElement;
    state.isFullscreen = fs;
    fullscreenBtn.classList.toggle('active', fs);
    fullscreenBtn.title = fs ? '退出全屏 (F)' : '全屏 (F)';
    // 全屏时自动隐藏侧栏
    sidebar.classList.toggle('hidden', fs);
}

// ---------- 设置 ----------
function openSettings() {
    setFocus.value = state.settings.focus;
    setShort.value = state.settings.short;
    setLong.value = state.settings.long;
    setIntervalInput.value = state.settings.interval;
    setAutoStart.classList.toggle('on', state.settings.autoStart);
    setStereo.classList.toggle('on', state.settings.stereo !== false);
    setProgressMode.classList.toggle('on', state.settings.progressMode === 'remaining');
    setProgressCap.classList.toggle('on', state.settings.capStyle !== 'butt');
    settingsModal.classList.add('show');
}
function closeSettings() {
    settingsModal.classList.remove('show');
}
function saveSettingsFromModal() {
    state.settings.focus = Math.max(1, Math.min(120, parseInt(setFocus.value) || 25));
    state.settings.short = Math.max(1, Math.min(60, parseInt(setShort.value) || 5));
    state.settings.long = Math.max(1, Math.min(60, parseInt(setLong.value) || 15));
    state.settings.interval = Math.max(1, Math.min(12, parseInt(setIntervalInput.value) || 4));
    state.settings.autoStart = setAutoStart.classList.contains('on');
    state.settings.stereo = setStereo.classList.contains('on');
    state.settings.progressMode = setProgressMode.classList.contains('on') ? 'remaining' : 'elapsed';
    state.settings.capStyle = setProgressCap.classList.contains('on') ? 'round' : 'butt';
    saveSettings();
    updateNoiseVolume();
    setRingProgress(state.isRunning ? Math.max(0, (state.endTime - Date.now()) / 1000) : state.remainingSeconds);
    // 声道模式变化：正在播放时重新生成噪声 buffer（立即生效）
    if (state.soundType !== 'off') {
        const t = state.soundType;
        stopNoise();
        startNoise(t);
    }
    if (!state.isRunning && !state.isPaused) {
        state.remainingSeconds = getModeSeconds(state.mode);
        state.totalSeconds = state.remainingSeconds;
        updateTimerDisplay();
    }
    updateDots();
    closeSettings();
    showToast('设置已保存');
}

// ---------- 引用轮换 ----------
function nextQuote() {
    state.quoteIdx = (state.quoteIdx + 1) % QUOTES.length;
    quoteText.textContent = `"${QUOTES[state.quoteIdx]}"`;
}

// ---------- 声音按钮状态 ----------
function updateSoundButtons() {
    soundButtons.forEach(btn => btn.classList.toggle('active', btn.dataset.sound === state.soundType));
}

// ---------- 事件绑定 ----------
function bindEvents() {
    modeTabs.forEach(tab => tab.addEventListener('click', () => switchMode(tab.dataset.mode)));
    startBtn.addEventListener('click', toggleTimer);
    resetBtn.addEventListener('click', resetTimer);
    fullscreenBtn.addEventListener('click', toggleFullscreen);
    document.addEventListener('fullscreenchange', updateFullscreenBtn);
    settingsBtn.addEventListener('click', openSettings);
    // 周期解释问号：点击弹 toast（手机触屏也能看；桌面另有悬停提示）
    const cycleHelp = document.querySelector('.cycle-help');
    if (cycleHelp) cycleHelp.addEventListener('click', (e) => {
        e.stopPropagation();
        showToast(`周期：每完成 ${state.settings.interval} 个专注进一次长休息，然后开始新一轮（间隔可在设置中调整）。`);
    });
    modalCancel.addEventListener('click', closeSettings);
    modalSave.addEventListener('click', saveSettingsFromModal);
    settingsModal.addEventListener('click', e => { if (e.target === settingsModal) closeSettings(); });
    setAutoStart.addEventListener('click', () => setAutoStart.classList.toggle('on'));
    setStereo.addEventListener('click', () => setStereo.classList.toggle('on'));
    setProgressMode.addEventListener('click', () => setProgressMode.classList.toggle('on'));
    setProgressCap.addEventListener('click', () => setProgressCap.classList.toggle('on'));

    todoAddBtn.addEventListener('click', () => {
        addTodo(todoInput.value);
        todoInput.value = '';
    });
    todoInput.addEventListener('keydown', e => {
        if (e.key === 'Enter') {
            addTodo(todoInput.value);
            todoInput.value = '';
        }
    });
    todoList.addEventListener('click', e => {
        const cb = e.target.closest('.todo-checkbox');
        const del = e.target.closest('.todo-delete');
        if (cb) toggleTodo(parseInt(cb.dataset.idx));
        else if (del) deleteTodo(parseInt(del.dataset.idx));
    });
    todoClearBtn.addEventListener('click', clearCompleted);

    soundButtons.forEach(btn => btn.addEventListener('click', () => {
        const snd = btn.dataset.sound;
        if (snd === 'off') {
            stopNoise();
            state.soundType = 'off';
            updateSoundButtons();
        } else {
            startNoise(snd);
        }
    }));
    volumeSlider.addEventListener('input', () => {
        state.settings.volume = parseInt(volumeSlider.value);
        updateNoiseVolume();
        saveSettings();
    });

    document.addEventListener('keydown', e => {
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
        if (e.code === 'Space') { e.preventDefault(); toggleTimer(); }
        else if (e.key === 'f' || e.key === 'F') { e.preventDefault(); toggleFullscreen(); }
        else if (e.key === '1') switchMode('focus');
        else if (e.key === '2') switchMode('short');
        else if (e.key === '3') switchMode('long');
        else if (e.key === 'r' || e.key === 'R') resetTimer();
        else if (e.key === 'Escape') closeSettings();
    });

    setInterval(nextQuote, 25000);

    // ── 云端统计：在线同学 / 累计 / 近 15 天 ──
    studyLoadSummary();
    studyHeartbeat();
    setInterval(studyHeartbeat, 30000);

    // ── 周期 & 设置：从服务器拉取（跨设备一致）──
    studyLoadRemote();

    // ── 小屏手风琴（≤768px 生效）：点整张卡片互斥展开/收起 ──
    const accHosts = document.querySelectorAll('.timer-card, .sidebar .card');
    const accOpen = () => window.matchMedia('(max-width: 768px)').matches;
    if (accHosts.length) {
        // 默认展开：小屏时若全部折叠，强制展开计时卡（双保险，不依赖 HTML class）
        if (accOpen()) {
            const anyOpen = document.querySelector('.timer-card.acc-open, .sidebar .card.acc-open');
            if (!anyOpen) {
                const t = document.getElementById('timer-card');
                if (t) t.classList.add('acc-open');
            }
        }
        accHosts.forEach(host => host.addEventListener('click', (e) => {
            if (!accOpen()) return;   // 桌面不启用折叠
            // 点击卡片内部交互元素（按钮/输入框等）不触发折叠
            if (e.target.closest('button, input, a, .todo-checkbox, .todo-delete, .todo-item')) return;
            // 若已展开 → 收起
            if (host.classList.contains('acc-open')) {
                host.classList.remove('acc-open');
                return;
            }
            // 互斥：收起所有，再展开当前
            accHosts.forEach(c => c.classList.remove('acc-open'));
            host.classList.add('acc-open');
        }));
        // 跨断点切换：进入小屏时若全部折叠则默认展开计时卡
        window.addEventListener('resize', () => {
            if (accOpen()) {
                const anyOpen = document.querySelector('.timer-card.acc-open, .sidebar .card.acc-open');
                if (!anyOpen) {
                    const timerCardEl = document.getElementById('timer-card');
                    if (timerCardEl) timerCardEl.classList.add('acc-open');
                }
            }
        });
    }
}

// ---------- 初始化 ----------
function init() {
    loadStorage();
    bindEvents();
    state.remainingSeconds = getModeSeconds(state.mode);
    state.totalSeconds = state.remainingSeconds;
    volumeSlider.value = state.settings.volume;
    updateUI();
    renderTodos();
    updateStatsDisplay();
    updateSoundButtons();
    quoteText.textContent = `"${QUOTES[state.quoteIdx]}"`;
    updateFullscreenBtn();
}

// ══════════════ 云端统计（在线同学 / 累计 / 近 15 天） ══════════════
// 走 AIsChat 后端 /study API（登录态复用 localStorage access_token）；
// 未登录或请求失败时静默降级为占位，不影响自习室本体。
// API 前缀自动探测：默认 /api（主站 Web），失败自动试 /aischat-api（嵌入场景），
// 也兼容显式指定（window.STUDY_API_BASE）
let studyApiBase = window.STUDY_API_BASE || null;
function studyBase() {
    if (studyApiBase) return studyApiBase;
    try { if (new URLSearchParams(location.search).has('embed')) studyApiBase = '/aischat-api'; } catch (e) {}
    return studyApiBase || '/api';
}

function studyToken() { return localStorage.getItem('access_token') || localStorage.getItem('aisc.token') || ''; }

async function studyFetch(path, opts) {
    const token = studyToken();
    const doFetch = (base) => fetch(base + path, Object.assign({}, opts, {
        headers: Object.assign({ 'Content-Type': 'application/json' }, opts && opts.headers, token ? { Authorization: 'Bearer ' + token } : {}),
    })).then(r => r.ok ? r.json() : Promise.reject(new Error('HTTP ' + r.status)));
    try {
        return await doFetch(studyBase());
    } catch (e) {
        // 非 401 且当前是 /api：自动换 /aischat-api 重试一次（覆盖嵌入场景）
        if (!/401/.test(e.message) && studyBase() === '/api') {
            studyApiBase = '/aischat-api';
            return doFetch('/aischat-api');
        }
        throw e;
    }
}

function studyFmtMinutes(min) {
    if (min < 60) return min + ' 分';
    const h = Math.round(min / 60 * 10) / 10;
    return h + ' 小时';
}

function studyRenderChart(days) {
    if (!studyChart || !days || !days.length) return;
    const W = 300, H = 88, PAD = 10;
    const max = Math.max(15, ...days.map(d => d.minutes));
    const step = (W - PAD * 2) / (days.length - 1);
    const y = (m) => H - PAD - (m / max) * (H - PAD * 2);
    const pts = days.map((d, i) => [PAD + i * step, y(d.minutes)]);
    const line = pts.map(p => p[0].toFixed(1) + ',' + p[1].toFixed(1)).join(' ');
    const hasData = days.some(d => d.minutes > 0);
    // 面积填充 + 折线 + 有数据的点；全 0 时只有基线 + 引导文案
    const area = `${PAD},${H - PAD} ${line} ${W - PAD},${H - PAD}`;
    studyChart.innerHTML = `
        <svg viewBox="0 0 ${W} ${H}" class="lc" preserveAspectRatio="none">
            <polygon points="${area}" class="lc-area"></polygon>
            <polyline points="${line}" class="lc-line" fill="none"></polyline>
            ${pts.map((p, i) => days[i].minutes > 0
                ? `<circle cx="${p[0].toFixed(1)}" cy="${p[1].toFixed(1)}" r="2.5" class="lc-dot"></circle>`
                : '').join('')}
        </svg>
        ${hasData ? '' : '<div class="chart-hint">完成一个专注周期后开始记录</div>'}
        <div class="chart-axis">${days[0].date.slice(5).replace('-', '/')} — ${days[days.length - 1].date.slice(5).replace('-', '/')}</div>
    `;
}

function studySetOffline(err) {
    const label = err ? ('加载失败' + (err.status ? ' (' + err.status + ')' : '')) : '未登录';
    if (statOnline) statOnline.textContent = label;
    if (statTotal) statTotal.textContent = '—';
    if (studyChart) studyChart.innerHTML = '<div class="chart-hint">' + label + '，稍后自动重试</div>';
}

async function studyHeartbeat() {
    if (!studyToken()) { studySetOffline(); return; }
    try {
        const d = await studyFetch('/study/heartbeat', { method: 'POST', body: '{}' });
        if (d && d.online_count !== undefined && statOnline) {
            statOnline.textContent = d.online_count > 0 ? d.online_count + ' 人' : '0 人';
        }
    } catch (e) { console.warn('[自习室] 心跳失败:', e.message); }
}

async function studyLoadSummary() {
    if (!studyToken()) { studySetOffline(); return; }
    try {
        const d = await studyFetch('/study/summary');
        if (!d || !d.days) return;
        if (statOnline) statOnline.textContent = (d.online_count || 0) + ' 人';
        if (statTotal) statTotal.textContent = studyFmtMinutes(d.total_minutes || 0);
        studyRenderChart(d.days);
    } catch (e) {
        console.warn('[自习室] 统计加载失败:', e.message);
        studySetOffline(e);
        // 15s 后自动重试一次（覆盖服务未就绪/时序问题）
        setTimeout(studyLoadSummary, 15000);
    }
}

async function studyRecord(minutes) {
    if (!studyToken() || !minutes) return;
    try {
        await studyFetch('/study/record', { method: 'POST', body: JSON.stringify({ minutes }) });
        studyLoadSummary();   // 刷新累计与 15 天图
    } catch (e) { /* 静默 */ }
}

// ── 周期 & 设置同步服务器（今日周期进度 + 时长设置，跨设备一致）──
async function studySyncSettings() {
    if (!studyToken()) return;
    try {
        await studyFetch('/study/settings', {
            method: 'PUT',
            body: JSON.stringify({
                focus: state.settings.focus,
                short: state.settings.short,
                long: state.settings.long,
                interval: state.settings.interval,
            }),
        });
    } catch (e) { /* 静默：离线时下次再同步 */ }
}

async function studySyncCycle() {
    if (!studyToken()) return;
    try {
        await studyFetch('/study/cycle', {
            method: 'PUT',
            body: JSON.stringify({ cycles: state.currentCycle, sessions: state.sessionsCompleted }),
        });
    } catch (e) { /* 静默 */ }
}

async function studyLoadRemote() {
    if (!studyToken()) return;
    try {
        const d = await studyFetch('/study/settings');
        if (!d) return;
        // 服务器设置优先（跨设备一致），本地仅保留音量（不入服务器，纯设备级）
        if (d.focus) state.settings.focus = d.focus;
        if (d.short) state.settings.short = d.short;
        if (d.long) state.settings.long = d.long;
        if (d.interval) state.settings.interval = d.interval;
        // 今日周期进度：服务器若已有今天的记录则采用（换设备续上）
        if (d.cycle_date === getTodayKey()) {
            state.currentCycle = d.cycles || 0;
            state.sessionsCompleted = d.sessions || 0;
        }
        localStorage.setItem('studyroom_settings', JSON.stringify({ ...state.settings, _v: SETTINGS_VERSION }));
        if (!state.isRunning && !state.isPaused) {
            state.remainingSeconds = getModeSeconds(state.mode);
            state.totalSeconds = state.remainingSeconds;
        }
        updateUI();
        updateDots();
    } catch (e) { /* 静默降级：离线直接用本地 */ }
}

init();