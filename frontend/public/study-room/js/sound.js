// ==================== 音频引擎（AudioWorklet 实时合成） ====================
'use strict';

let audioCtx = null;
let noiseNode = null;
let masterGain = null;
let workletReady = false;
let workletLoadPromise = null;

// 初始化音频上下文并加载 AudioWorklet 模块
async function initAudio() {
    if (!audioCtx) {
        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (!workletReady) {
        if (!workletLoadPromise) {
            workletLoadPromise = audioCtx.audioWorklet.addModule('js/noise-worklet.js')
                .then(() => {
                    workletReady = true;
                })
                .catch(err => {
                    console.error('AudioWorklet 加载失败:', err);
                });
        }
        await workletLoadPromise;
    }
    return audioCtx;
}

// 开始播放指定类型的噪声
async function startNoise(type) {
    await initAudio();

    // 确保音频上下文处于运行状态（需要用户手势）
    if (audioCtx.state === 'suspended') {
        await audioCtx.resume();
    }

    // 停止已有声音
    stopNoise();

    if (type === 'off') {
        state.soundType = 'off';
        updateSoundButtons();
        return;
    }

    // 创建总音量节点
    masterGain = audioCtx.createGain();
    masterGain.gain.value = state.settings.volume / 100;
    masterGain.connect(audioCtx.destination);

    // 创建 AudioWorklet 节点
    noiseNode = new AudioWorkletNode(audioCtx, 'noise-processor', {
        numberOfInputs: 0,
        numberOfOutputs: 1,
        outputChannelCount: [2],
    });

    // 映射声音类型
    const typeMap = { rain: 1, forest: 2, deep: 3, off: 0 };
    noiseNode.parameters.get('type').value = typeMap[type] || 0;
    noiseNode.parameters.get('volume').value = 1; // 音量由 masterGain 控制

    noiseNode.connect(masterGain);

    state.soundType = type;
    updateSoundButtons();
}

// 停止噪声
function stopNoise() {
    if (noiseNode) {
        try { noiseNode.disconnect(); } catch(e) {}
        noiseNode = null;
    }
    if (masterGain) {
        try { masterGain.disconnect(); } catch(e) {}
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