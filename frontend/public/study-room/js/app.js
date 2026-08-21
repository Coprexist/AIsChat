// ==================== 主逻辑 ====================
'use strict';

// ---------- DOM引用 ----------
const $ = id => document.getElementById(id);
const timeDisplay = $('time-display');
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
const quoteText = $('quote');
const toastContainer = $('toast-container');
const sidebar = $('sidebar');

// 设置相关
const setFocus = $('set-focus');
const setShort = $('set-short');
const setLong = $('set-long');
const setIntervalInput = $('set-interval');
const setAutoStart = $('set-auto-start');
const modalCancel = $('modal-cancel');
const modalSave = $('modal-save');

// ---------- 存储 ----------
function loadStorage() {
    try {
        const s = localStorage.getItem('studyroom_settings');
        if (s) state.settings = { ...DEFAULT_SETTINGS, ...JSON.parse(s) };
        const t = localStorage.getItem('studyroom_todos');
        if (t) state.todos = JSON.parse(t);
        const st = localStorage.getItem('studyroom_stats');
        if (st) state.stats = JSON.parse(st);
    } catch(e) {}
}
function saveSettings() { localStorage.setItem('studyroom_settings', JSON.stringify(state.settings)); }
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
    return sec;
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
    updateUI();
}
function pauseTimer() {
    if (!state.isRunning) return;
    state.remainingSeconds = Math.max(0, (state.endTime - Date.now()) / 1000);
    clearInterval(state.timerId);
    state.timerId = null;
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
    state.isRunning = false;
    state.isPaused = false;
    state.endTime = null;
}
function handleComplete() {
    clearInterval(state.timerId);
    state.timerId = null;
    state.isRunning = false;
    state.isPaused = false;
    playChime();
    if (state.mode === 'focus') {
        state.sessionsCompleted++;
        state.currentCycle++;
        updateTodayStats(1, state.settings.focus);
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
    settingsModal.classList.add('show');
}
function closeSettings() {
    settingsModal.classList.remove('show');
}
function saveSettingsFromModal() {
    state.settings.focus = Math.max(1, Math.min(120, parseInt(setFocus.value) || 25));
    state.settings.short = Math.max(1, Math.min(60, parseInt(setShort.value) || 5));
    state.settings.long = Math.max(1, Math.min(60, parseInt(setLong.value) || 15));
    state.settings.interval = Math.max(2, Math.min(8, parseInt(setIntervalInput.value) || 4));
    state.settings.autoStart = setAutoStart.classList.contains('on');
    saveSettings();
    updateNoiseVolume();
    if (!state.isRunning && !state.isPaused) {
        state.remainingSeconds = getModeSeconds(state.mode);
        state.totalSeconds = state.remainingSeconds;
        updateTimerDisplay();
    }
    updateDots();
    closeSettings();
    showToast('✅ 设置已保存');
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
    modalCancel.addEventListener('click', closeSettings);
    modalSave.addEventListener('click', saveSettingsFromModal);
    settingsModal.addEventListener('click', e => { if (e.target === settingsModal) closeSettings(); });
    setAutoStart.addEventListener('click', () => setAutoStart.classList.toggle('on'));

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

init();