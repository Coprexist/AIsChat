// ==================== 音频引擎（多层声源 + HRTF 双耳空间化） ====================
//
// 空间化参考专业做法（W3C Web Audio PannerNode / HRTF 双耳渲染）：
// 每个噪声层是独立的单声道声源，经 PannerNode（panningModel:'HRTF'）摆到
// 真实方位（±方位角），浏览器用头相关传递函数渲染成双耳输出——比手工
// 等功率 pan 真实得多；方位可平滑移动（浪花/水滴在声场中漂移）。
//
// 无缝：每层两个不同内容的 10s buffer 交替播放，切换时 300ms 交叉淡化。
// 兼容性：全部用预生成 buffer + 原生节点（PannerNode 无需 secure context、
// 无需外部资源），file:// / http / iframe 都能响。
'use strict';

let audioCtx = null;
let masterGain = null;
let layers = [];          // 当前音色的所有声源层

// 每层独立交叉淡化（错峰 + 随机 jitter）：任何时刻只有一层在过渡，
// 避免"所有层同时切换"造成的周期性落差感
const BUFFER_SECONDS = 20;
const FADE = 0.8;
// 切换间隔必须 < buffer 时长 - FADE（旧声源需留 ≥FADE 余量做淡出），
// 否则旧声源先播完 → 该层完全无声直到切换 → 可闻"陡变断点"
const SWAP_LEAD = 2;      // 额外余量（秒）：切换时旧声源至少还剩 SWAP_LEAD 秒
const SWAP_JITTER = 1;    // 每层 ±1s 随机错峰（秒）

// ── 层配置：每个音色由若干声源层组成，az = 方位角（弧度，0=正前，+右 -左）──
// drift: 声源方位随机漂移（浪花/水滴在声场中缓缓移动）
const LAYER_DEFS = {
    rain: [
        { key: 'rainbed', az: -0.7 },
        { key: 'rainbed', az: 0.7 },
        { key: 'raindrops', drift: true },
    ],
    forest: [
        { key: 'wind', az: -0.8 },
        { key: 'pink', az: 0 },
        { key: 'leaf', az: 0.8 },
    ],
    deep: [
        { key: 'swell', az: 0 },
        { key: 'foam', drift: true },
    ],
};

// 初始化音频上下文
async function initAudio() {
    if (!audioCtx) {
        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    return audioCtx;
}

// ── 层 buffer 生成（单声道） ──────────────────────────────────────────────

function makeLayerBuffer(ctx, key) {
    const rate = ctx.sampleRate;
    const len = Math.floor(rate * BUFFER_SECONDS);
    const buf = ctx.createBuffer(1, len, rate);
    const data = buf.getChannelData(0);

    // 二阶低通系数（-24dB/oct 塑形）
    const lp = (fc) => 1 - Math.exp(-2 * Math.PI * fc / rate);
    const S = (a) => ({ a, s1: 0, s2: 0, lp: function (x) {
        const t = this.s1 + this.a * (x - this.s1);
        this.s2 = this.s2 + this.a * (t - this.s2);
        this.s1 = t;
        return this.s2;
    }});

    // 各层滤波器
    const bedHi = S(lp(3000)), bedLo = S(lp(400));   // 雨幕带通
    const dropHi = S(lp(4000)), dropLo = S(lp(1000)); // 水滴带通
    const windLo = S(lp(800));                        // 风声低通
    const leafLo = S(lp(1500));                       // 叶沙低通
    const swellLo = S(lp(450));                       // 涌动低通
    const foamHi = S(lp(2500)), foamLo = S(lp(1500)); // 浪花带通

    let brown = 0;
    let k0 = 0, k1 = 0, k2 = 0, k3 = 0, k4 = 0, k5 = 0, k6 = 0;
    // 水滴脉冲状态
    let dropNext = 0, dropPhase = 0, dropDur = 0, dropEnv = 0;
    // 幅度包络状态（森林/浪花：随机游走，无固定周期——自然起伏而非规律涨落）
    let env = 0.6, envTarget = 0.6, envNext = 0;
    // 深海涌动 LFO（唯一保留正弦：慢涌 0.07Hz，深海底噪本来就要"潮汐感"）
    const lfoFreq = key === 'swell' ? 0.07 : 0;

    // 随机游走包络：每 1~4s 随机换目标幅度，慢逼近（τ≈1s）→ 无周期、平滑起伏
    const walkEnv = (i) => {
        envNext -= 1 / rate;
        if (envNext <= 0) {
            envTarget = 0.45 + Math.random() * 0.75;
            envNext = 1 + Math.random() * 3;
        }
        env += (envTarget - env) * 0.00002;
        return env;
    };

    for (let i = 0; i < len; i++) {
        const w = Math.random() * 2 - 1;
        brown = brown * 0.995 + w * 0.005;
        k0 = 0.99886 * k0 + w * 0.0555179;
        k1 = 0.99332 * k1 + w * 0.0750759;
        k2 = 0.96900 * k2 + w * 0.1538520;
        k3 = 0.86650 * k3 + w * 0.3104856;
        k4 = 0.55000 * k4 + w * 0.5329522;
        k5 = -0.7616 * k5 - w * 0.0168980;
        const pink = (k0 + k1 + k2 + k3 + k4 + k5 + k6 + w * 0.5362) * 0.11 * 2;
        k6 = w * 0.115926;

        let s = 0;
        if (key === 'rainbed') {
            s = (bedHi.lp(w) - bedLo.lp(w)) * 0.7 + brown * 0.04;
        } else if (key === 'raindrops') {
            dropNext -= 1 / rate;
            if (dropNext <= 0) {
                dropDur = 0.002 + Math.random() * 0.006;
                dropPhase = dropDur;
                dropEnv = 0.12 + Math.random() * 0.18;
                dropNext = 0.02 + Math.random() * 0.06;
            }
            if (dropPhase > 0) {
                s = (dropHi.lp(w) - dropLo.lp(w)) * Math.exp(-(dropDur - dropPhase) * 400) * dropEnv;
                dropPhase -= 1 / rate;
            }
        } else if (key === 'wind') {
            s = windLo.lp(brown) * 1.6 * walkEnv(i);
        } else if (key === 'leaf') {
            s = leafLo.lp(w) * 0.5 * walkEnv(i);
        } else if (key === 'pink') {
            s = pink * 0.3 * walkEnv(i);
        } else if (key === 'swell') {
            const lfo = 0.65 + 0.35 * Math.sin(2 * Math.PI * lfoFreq * i / rate);
            s = swellLo.lp(brown) * 3.6 * lfo;
        } else if (key === 'foam') {
            s = (foamHi.lp(w) - foamLo.lp(w)) * 1.1 * walkEnv(i);
        }
        data[i] = s;
    }
    return buf;
}

// ── 空间化与播放 ─────────────────────────────────────────────────────────

// HRTF 摆位：声源放在 X-Z 平面单位圆上（listener 默认在原点朝 -Z）
function placePanner(panner, az, when) {
    const t = when !== undefined ? when : audioCtx.currentTime;
    panner.positionX.setTargetAtTime(Math.sin(az), t, 0.05);
    panner.positionY.setTargetAtTime(0, t, 0.05);
    panner.positionZ.setTargetAtTime(-Math.cos(az), t, 0.05);
}

function makeSource(buffer, gain, panner) {
    const s = audioCtx.createBufferSource();
    s.buffer = buffer;
    s.connect(gain);
    gain.connect(panner);
    s.start();
    return s;
}

// 漂移层：每 1~2s 微调目标方位（±20°），HRTF 用 τ=2s 连续渐变跟随——
// 声像永远在平滑渐变（如"左40% 5秒内渐到左48%"），不会跳到端点
function scheduleDrift(ly) {
    ly.driftTimer = setTimeout(() => {
        const az = Math.min(1.0, Math.max(-1.0, ly.az + (Math.random() - 0.5) * 0.7));
        ly.az = az;
        const t = audioCtx.currentTime;
        ly.panner.positionX.setTargetAtTime(Math.sin(az), t, 2);
        ly.panner.positionY.setTargetAtTime(0, t, 2);
        ly.panner.positionZ.setTargetAtTime(-Math.cos(az), t, 2);
        scheduleDrift(ly);
    }, 1000 + Math.random() * 1000);
}

function createLayer(def) {
    const ly = { def, panner: null, bufs: [null, null], srcs: [null, null], gains: [null, null], driftTimer: null, swapTimer: null, active: 0, az: def.az ?? 0 };
    if (def.drift && ly.az === 0) ly.az = (Math.random() * 2 - 1) * 0.6;  // 漂移层随机起点
    ly.panner = new PannerNode(audioCtx, {
        panningModel: 'HRTF',
        distanceModel: 'inverse',
        refDistance: 1,
        maxDistance: 100,
        rolloffFactor: 0,   // 无距离衰减：方位只决定方向，音量统一
    });
    ly.panner.connect(masterGain);
    for (let i = 0; i < 2; i++) {
        ly.bufs[i] = makeLayerBuffer(audioCtx, def.key);
        ly.gains[i] = audioCtx.createGain();
        ly.gains[i].gain.value = i === 0 ? 1 : 0;
    }
    ly.srcs[0] = makeSource(ly.bufs[0], ly.gains[0], ly.panner);
    ly.srcs[1] = makeSource(ly.bufs[1], ly.gains[1], ly.panner);
    return ly;
}

// 单层交叉淡化：该层独立切换，间隔带随机 jitter（错峰 → 任何时刻只一层在过渡）。
// 间隔 = buffer - FADE - 余量 + jitter，保证切换发生时旧声源还剩 >FADE 的信号可淡出，
// 新声源淡入前不会出现"无声间隙"。
function scheduleLayerSwap(ly) {
    const delay = (BUFFER_SECONDS - FADE - SWAP_LEAD + Math.random() * SWAP_JITTER) * 1000;
    ly.swapTimer = setTimeout(() => {
        swapLayer(ly);
        scheduleLayerSwap(ly);
    }, delay);
}

function swapLayer(ly) {
    const t = audioCtx.currentTime + 0.02;
    const next = 1 - ly.active;
    ly.gains[ly.active].gain.cancelScheduledValues(t);
    ly.gains[ly.active].gain.setValueAtTime(Math.max(ly.gains[ly.active].gain.value, 0.0001), t);
    ly.gains[ly.active].gain.linearRampToValueAtTime(0, t + FADE);
    try { ly.srcs[next].stop(); } catch (e) {}
    try { ly.srcs[next].disconnect(); } catch (e) {}
    ly.srcs[next] = makeSource(ly.bufs[next], ly.gains[next], ly.panner);
    ly.gains[next].gain.cancelScheduledValues(t);
    ly.gains[next].gain.setValueAtTime(0, t);
    ly.gains[next].gain.linearRampToValueAtTime(1, t + FADE);
    ly.active = next;
}

// 三角分布 [min,max]，峰值在 mode（高潮持续时间：更多落在 ~40s）
function triMode(min, max, mode) {
    const u = Math.random();
    const p = (mode - min) / (max - min);
    return u < p
        ? min + (mode - min) * Math.sqrt(u / p)
        : mode + (max - mode) * (1 - Math.sqrt((1 - u) / (1 - p)));
}

// 深海高潮包络：整体增益 0.55~1.55 起伏（大浪来了又走）
const swell = { phase: 'calm', remain: 0, target: 1 };
let swellTimer = null;
let swellGain = null;

function planSwell() {
    if (Math.random() < 0.55) {
        swell.phase = 'swell';
        swell.remain = triMode(5, 60, 40);
        swell.target = 1.15 + Math.random() * 0.4;
    } else {
        swell.phase = 'calm';
        swell.remain = 8 + Math.random() * 22;
        swell.target = 0.55 + Math.random() * 0.2;
    }
}

function startSwellScheduler() {
    planSwell();
    swellTimer = setInterval(() => {
        if (!swellGain) return;
        swellGain.gain.setTargetAtTime(swell.target, audioCtx.currentTime, 0.6);
        swell.remain -= 0.1;
        if (swell.remain <= 0) planSwell();
    }, 100);
}

// 开始播放指定类型的噪声
async function startNoise(type) {
    await initAudio();

    if (audioCtx.state === 'suspended') {
        try { await audioCtx.resume(); } catch (e) { console.error('音频恢复失败:', e); }
    }
    stopNoise();

    if (type === 'off') {
        state.soundType = 'off';
        updateSoundButtons();
        return;
    }
    if (!LAYER_DEFS[type]) return;

    const stereo = state.settings.stereo !== false;

    // 总音量节点（deep 后接高潮包络）
    masterGain = audioCtx.createGain();
    masterGain.gain.value = state.settings.volume / 100;
    if (type === 'deep') {
        swellGain = audioCtx.createGain();
        swellGain.gain.value = 1;
        masterGain.connect(swellGain);
        swellGain.connect(audioCtx.destination);
        startSwellScheduler();
    } else {
        masterGain.connect(audioCtx.destination);
    }

    // 创建各声源层并摆位，每层独立错峰交叉淡化
    layers = LAYER_DEFS[type].map((def) => {
        const ly = createLayer(def);
        if (!stereo) {
            placePanner(ly.panner, 0);   // 单声道：全部居中
        } else if (def.drift) {
            scheduleDrift(ly);           // 漂移层：HRTF 方位连续渐变游走
        }
        scheduleLayerSwap(ly);           // 每层独立切换（随机错峰）
        return ly;
    });

    state.soundType = type;
    updateSoundButtons();
}

// 停止噪声
function stopNoise() {
    if (swellTimer) { clearInterval(swellTimer); swellTimer = null; }
    for (const ly of layers) {
        if (ly.driftTimer) clearTimeout(ly.driftTimer);
        if (ly.swapTimer) clearTimeout(ly.swapTimer);
        for (let i = 0; i < 2; i++) {
            if (ly.srcs[i]) { try { ly.srcs[i].stop(); } catch (e) {} try { ly.srcs[i].disconnect(); } catch (e) {} ly.srcs[i] = null; }
            if (ly.gains[i]) { try { ly.gains[i].disconnect(); } catch (e) {} ly.gains[i] = null; }
            ly.bufs[i] = null;
        }
        if (ly.panner) { try { ly.panner.disconnect(); } catch (e) {} ly.panner = null; }
    }
    layers = [];
    if (swellGain) { try { swellGain.disconnect(); } catch (e) {} swellGain = null; }
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
