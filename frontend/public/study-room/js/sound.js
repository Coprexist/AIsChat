// ==================== 音频引擎（双 buffer 交叉淡化无缝播放） ====================
//
// 不用 AudioWorklet（模块加载在 file:// / http / 受限 iframe 下会失败导致无声），
// 也不用单 buffer loop（噪声首尾不连续，每循环一次接缝处有可闻的"断一下"）。
//
// 方案：预生成两个不同内容的噪声 buffer（10s），交替播放，切换时 300ms
// 交叉淡化（一个淡出的同时另一个从开头淡入）——任意环境都能响，且听感无缝。
'use strict';

let audioCtx = null;
let masterGain = null;
let swapTimer = null;

// 双 buffer 播放状态：active 是当前出声的 buffer 下标，另一个待切换。
let bufs = [null, null];
let srcs = [null, null];
let gains = [null, null];
let active = 0;

const BUFFER_SECONDS = 10;   // 每个 buffer 时长
const FADE = 0.3;            // 交叉淡化时长（秒）
const SWAP_INTERVAL = BUFFER_SECONDS - FADE; // 每 9.7s 切换一次

// 初始化音频上下文
async function initAudio() {
    if (!audioCtx) {
        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    return audioCtx;
}

// 预生成指定类型的噪声 buffer（纯 main thread 算法，任何环境可用）
function makeNoiseBuffer(ctx, type) {
    const seconds = BUFFER_SECONDS;
    const rate = ctx.sampleRate;
    const len = Math.floor(rate * seconds);
    const buf = ctx.createBuffer(2, len, rate);

    for (let ch = 0; ch < 2; ch++) {
        const data = buf.getChannelData(ch);
        // 粉噪声状态（Paul Kellet 滤波器）
        let b0 = 0, b1 = 0, b2 = 0, b3 = 0, b4 = 0, b5 = 0, b6 = 0;
        let brown = 0;
        // 雨滴状态：间隔更稀疏、幅度更柔和、衰减更圆润（避免"放鞭炮"感）
        let dropNext = 0, dropPhase = 0, dropDur = 0, dropEnv = 0;

        for (let i = 0; i < len; i++) {
            const w = Math.random() * 2 - 1;
            b0 = 0.99886 * b0 + w * 0.0555179;
            b1 = 0.99332 * b1 + w * 0.0750759;
            b2 = 0.96900 * b2 + w * 0.1538520;
            b3 = 0.86650 * b3 + w * 0.3104856;
            b4 = 0.55000 * b4 + w * 0.5329522;
            b5 = -0.7616 * b5 - w * 0.0168980;
            const pink = (b0 + b1 + b2 + b3 + b4 + b5 + b6 + w * 0.5362) * 0.11 * 2;
            b6 = w * 0.115926;
            brown = brown * 0.995 + w * 0.005;

            let s = 0;
            if (type === 'rain') {
                // 绵密雨幕打底 + 稀疏柔和的滴答点缀
                s = pink * 0.35 + brown * 0.05;
                dropNext -= 1 / rate;
                if (dropNext <= 0) {
                    dropDur = 0.006 + Math.random() * 0.02;
                    dropPhase = dropDur;
                    dropEnv = 0.04 + Math.random() * 0.08; // 0.04~0.12，原来 0.08~0.23
                    // 间隔：60% 密集 20~50ms，40% 稀疏 60~210ms（平均≈65ms，密度约为原来一半）
                    dropNext = Math.random() < 0.6
                        ? 0.02 + Math.random() * 0.03
                        : 0.06 + Math.random() * 0.15;
                }
                if (dropPhase > 0) {
                    const tt = dropDur - dropPhase;
                    s += pink * (Math.exp(-tt * 60) * dropEnv); // 衰减系数 120→60，更圆润
                    dropPhase -= 1 / rate;
                }
            } else if (type === 'forest') {
                s = brown * 0.45 + pink * 0.25;
            } else if (type === 'deep') {
                s = brown * 0.6 + pink * 0.15;
            }
            data[i] = s;
        }
    }
    return buf;
}

// 创建连接到指定 gain 的 source（从 0 开始播放）
function makeSource(buffer, gain) {
    const s = audioCtx.createBufferSource();
    s.buffer = buffer;
    s.connect(gain);
    s.start();
    return s;
}

// 交叉淡化切换：淡出当前、淡入另一个（新 source 从开头播，旧的有 FADE 余量自然结束）
function swapBuffers() {
    if (!audioCtx || !srcs[0] || !srcs[1]) return;
    const t = audioCtx.currentTime + 0.02;
    const next = 1 - active;

    // 淡出当前
    gains[active].gain.cancelScheduledValues(t);
    gains[active].gain.setValueAtTime(Math.max(gains[active].gain.value, 0.0001), t);
    gains[active].gain.linearRampToValueAtTime(0, t + FADE);

    // 旧 source 播完剩余自然结束；新 source 重新从开头播并淡入
    try { srcs[next].stop(); } catch (e) {}
    try { srcs[next].disconnect(); } catch (e) {}
    srcs[next] = makeSource(bufs[next], gains[next]);
    gains[next].gain.cancelScheduledValues(t);
    gains[next].gain.setValueAtTime(0, t);
    gains[next].gain.linearRampToValueAtTime(1, t + FADE);

    active = next;
}

// 开始播放指定类型的噪声
async function startNoise(type) {
    await initAudio();

    // 确保音频上下文处于运行状态（需要用户手势）
    if (audioCtx.state === 'suspended') {
        try { await audioCtx.resume(); } catch (e) { console.error('音频恢复失败:', e); }
    }

    // 停止已有声音
    stopNoise();

    if (type === 'off') {
        state.soundType = 'off';
        updateSoundButtons();
        return;
    }
    if (type !== 'rain' && type !== 'forest' && type !== 'deep') return;

    // 总音量节点
    masterGain = audioCtx.createGain();
    masterGain.gain.value = state.settings.volume / 100;
    masterGain.connect(audioCtx.destination);

    // 两个不同内容的噪声 buffer + 各自的 gain/source
    for (let i = 0; i < 2; i++) {
        bufs[i] = makeNoiseBuffer(audioCtx, type);
        gains[i] = audioCtx.createGain();
        gains[i].gain.value = i === 0 ? 1 : 0;
        gains[i].connect(masterGain);
    }
    srcs[0] = makeSource(bufs[0], gains[0]); // 先出声
    srcs[1] = makeSource(bufs[1], gains[1]); // 静音待命
    active = 0;

    // 每 SWAP_INTERVAL 秒交叉淡化切换一次（无缝衔接）
    swapTimer = setInterval(swapBuffers, SWAP_INTERVAL * 1000);

    state.soundType = type;
    updateSoundButtons();
}

// 停止噪声
function stopNoise() {
    if (swapTimer) { clearInterval(swapTimer); swapTimer = null; }
    for (let i = 0; i < 2; i++) {
        if (srcs[i]) { try { srcs[i].stop(); } catch (e) {} try { srcs[i].disconnect(); } catch (e) {} srcs[i] = null; }
        if (gains[i]) { try { gains[i].disconnect(); } catch (e) {} gains[i] = null; }
        bufs[i] = null;
    }
    if (masterGain) {
        try { masterGain.disconnect(); } catch (e) {}
        masterGain = null;
    }
}

// 更新音量（供音量滑块调用）
function updateNoiseVolume() {
    if (masterGain && audioCtx) {
        masterGain.gain.setTargetAtTime(state.settings.volume / 100, audioCtx.currentTime, 0.08);
    }
}

// 播放完成提示音（和弦铃声）
function playChime() {
    if (!audioCtx) return;
    if (audioCtx.state === 'suspended') {
        audioCtx.resume();
    }
    [523.25, 659.25, 783.99].forEach((freq, i) => {
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.type = 'sine';
        osc.frequency.value = freq;
        const t = audioCtx.currentTime + i * 0.15;
        gain.gain.setValueAtTime(0, t);
        gain.gain.linearRampToValueAtTime(0.2, t + 0.03);
        gain.gain.exponentialRampToValueAtTime(0.001, t + 0.4);
        osc.connect(gain);
        gain.connect(audioCtx.destination);
        osc.start(t);
        osc.stop(t + 0.45);
    });
}
