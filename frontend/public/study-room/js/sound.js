// ==================== 音频引擎（预生成噪声 buffer 循环播放） ====================
//
// 不用 AudioWorklet：模块加载在 file:// / http / 受限 iframe 下会失败导致无声。
// 改为在 main thread 用经典算法（Paul Kellet 粉噪 + 布朗积分）预生成噪声
// buffer，AudioBufferSourceNode.loop 循环播放——任何环境都能响。
'use strict';

let audioCtx = null;
let sourceNode = null;
let masterGain = null;

// 初始化音频上下文
async function initAudio() {
    if (!audioCtx) {
        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    return audioCtx;
}

// 预生成指定类型的噪声 buffer（10 秒，端点交叉淡化避免循环咔哒）
function makeNoiseBuffer(ctx, type, seconds) {
    seconds = seconds || 10;
    const rate = ctx.sampleRate;
    const len = Math.floor(rate * seconds);
    const buf = ctx.createBuffer(2, len, rate);

    for (let ch = 0; ch < 2; ch++) {
        const data = buf.getChannelData(ch);
        // 粉噪声状态（Paul Kellet 滤波器）
        let b0 = 0, b1 = 0, b2 = 0, b3 = 0, b4 = 0, b5 = 0, b6 = 0;
        let brown = 0;
        // 雨滴状态（与旧 AudioWorklet 一致的随机脉冲逻辑）
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
                s = pink * 0.3 + brown * 0.04;
                dropNext -= 1 / rate;
                if (dropNext <= 0) {
                    dropDur = 0.005 + Math.random() * 0.02;
                    dropPhase = dropDur;
                    dropEnv = 0.08 + Math.random() * 0.15;
                    dropNext = Math.random() < 0.5
                        ? 0.008 + Math.random() * 0.012
                        : 0.02 + Math.random() * 0.06;
                }
                if (dropPhase > 0) {
                    const tt = dropDur - dropPhase;
                    s += pink * (Math.exp(-tt * 120) * dropEnv);
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

    // 端点交叉淡化（首尾各 20ms 淡入/淡出），消除 loop 接缝处的咔哒声
    const fade = Math.floor(rate * 0.02);
    for (let ch = 0; ch < 2; ch++) {
        const data = buf.getChannelData(ch);
        for (let i = 0; i < fade; i++) {
            const g = i / fade;
            data[i] *= g;
            data[len - 1 - i] *= g;
        }
    }
    return buf;
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

    // 预生成噪声 buffer 循环播放
    sourceNode = audioCtx.createBufferSource();
    sourceNode.buffer = makeNoiseBuffer(audioCtx, type);
    sourceNode.loop = true;
    sourceNode.connect(masterGain);
    sourceNode.start();

    state.soundType = type;
    updateSoundButtons();
}

// 停止噪声
function stopNoise() {
    if (sourceNode) {
        try { sourceNode.stop(); } catch (e) {}
        try { sourceNode.disconnect(); } catch (e) {}
        sourceNode = null;
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
