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
// drift: 声源方位随机漂移（浪花/气泡在声场中缓缓移动）
const LAYER_DEFS = {
    rain: [
        { key: 'rainbed', az: -0.7 },
        { key: 'rainbed', az: 0.7 },
        { key: 'raindrops', drift: true },
    ],
    forest: [                    // 森林：以风声为主（左右两层立体风 + 粉噪 + 叶沙点缀）
        { key: 'wind', az: -0.8 },
        { key: 'wind', az: 0.8 },
        { key: 'pink', az: 0 },
        { key: 'leaf', az: 0, drift: true },
    ],
    sea: [                       // 海面：涌动 + 浪花（原"深海"改名）
        { key: 'swell', az: 0 },
        { key: 'foam', drift: true },
    ],
    deep: [                      // 深海（水下）：低频水压底噪 + 气泡咕噜噜
        { key: 'abyss', az: 0 },
        { key: 'bubble', drift: true },                          // 主气泡组：声场中游走
        { key: 'bubble', az: -0.8, quiet: true },                // 小声远层组：固定左远侧，与主组分声道
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

function makeLayerBuffer(ctx, key, def) {
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
    const abyssLo = S(lp(140));                       // 深海低频水压（极低通）

    let brown = 0;
    let k0 = 0, k1 = 0, k2 = 0, k3 = 0, k4 = 0, k5 = 0, k6 = 0;
    // 水滴脉冲状态
    let dropNext = 0, dropPhase = 0, dropDur = 0, dropEnv = 0;
    // 深海气泡：活跃气泡池（可重叠发声，不用等前一个播完）+ 串触发状态
    // 一串 1~8 个（偏大分布）；串内密集触发（0.08~0.28s）→ 同时 2~4 个气泡叠响
    let bubNext = 1.2, bubRemain = 0;
    const bubbles = [];
    // 幅度包络状态（森林/浪花：随机游走，无固定周期——自然起伏而非规律涨落）
    let env = 0.6, envTarget = 0.6, envNext = 0;
    // 深海涌动 LFO（唯一保留正弦：慢涌 0.035Hz ≈28s 一周期，潮汐感更缓更隐）
    const lfoFreq = key === 'swell' ? 0.035 : 0;

    // 随机游走包络：每 10~22s 才换一次目标幅度（收窄到 0.6~1.0），
    // 逼近更慢（τ≈5.7s）→ 音量几乎恒定，只剩极缓的"呼吸感"，不打扰专注
    const walkEnv = (i) => {
        envNext -= 1 / rate;
        if (envNext <= 0) {
            envTarget = 0.6 + Math.random() * 0.4;
            envNext = 10 + Math.random() * 12;
        }
        env += (envTarget - env) * 0.000004;
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
            s = windLo.lp(brown) * 2.4 * walkEnv(i);
        } else if (key === 'leaf') {
            s = leafLo.lp(w) * 0.35 * walkEnv(i);
        } else if (key === 'pink') {
            s = pink * 0.2 * walkEnv(i);
        } else if (key === 'swell') {
            const lfo = 0.75 + 0.25 * Math.sin(2 * Math.PI * lfoFreq * i / rate);
            s = swellLo.lp(brown) * 3.6 * lfo;
        } else if (key === 'foam') {
            s = (foamHi.lp(w) - foamLo.lp(w)) * 1.1 * walkEnv(i);
        } else if (key === 'abyss') {
            // 深海低频水压底噪：棕色噪声 → 140Hz 极低通，恒定、无起伏（水下压力感）
            s = abyssLo.lp(brown) * 8.0;
        } else if (key === 'bubble') {
            // 深海气泡（可重叠的咕噜串）：一串 1~8 个（偏大分布），串内密集触发，
            // 新气泡不等旧气泡播完——多个气泡同时发声叠加，像水下气泡群一起冒；
            // quiet=小音量远层组：音色与主组完全一致（低频咕噜、同样时长），
            // 只是音量更小、串略小略稀——"远处也有一组同样的气泡"
            const BUBBLE_VOLUME = 0.35;   // 气泡整体音量：在缩减 75% 基础上增大 40%（区间 30~45% 中值）
            const quiet = def && def.quiet;
            const ampScale = (quiet ? 0.12 : 0.3) * BUBBLE_VOLUME;
            const maxConc = quiet ? 3 : 4;
            // 串内触发间隔：以 > 气泡时长为主 → 多数气泡一前一后，偶尔重叠
            const inSerGap = quiet ? 0.3 + Math.pow(Math.random(), 2) * 0.4   // 0.3~0.7s
                                   : 0.24 + Math.pow(Math.random(), 2) * 0.32; // 0.24~0.56s
            const serGap = quiet ? 1.4 + Math.pow(Math.random(), 2) * 4.5
                                 : 1.2 + Math.pow(Math.random(), 2) * 4;   // 串间隔
            bubNext -= 1 / rate;
            if (bubNext <= 0) {
                if (bubRemain <= 0) {
                    bubRemain = quiet
                        ? 1 + Math.floor(Math.pow(Math.random(), 0.7) * 5)  // 小声组串略小
                        : 1 + Math.floor(Math.pow(Math.random(), 0.7) * 8); // 主组串大
                    bubNext = serGap;
                } else {
                    bubRemain--;
                    bubNext = inSerGap;
                }
                if (bubbles.length < maxConc) {
                    // 低沉圆润的"咕噜"音：100~220Hz 几乎不扫频（1.05~1.3 倍）、
                    // 时长 180~340ms——频率不猛跳就没有"啵"的清脆感
                    const f0 = 100 + Math.random() * 120;
                    bubbles.push({
                        f0,
                        f1: f0 * (1.05 + Math.random() * 0.25),
                        amp: (0.25 + Math.random() * 0.3) * ampScale,
                        dur: 0.18 + Math.random() * 0.16,
                        t: 0,
                    });
                }
            }
            // 渲染所有活跃气泡（各自独立推进，可同时发声）
            for (let bi = bubbles.length - 1; bi >= 0; bi--) {
                const b = bubbles[bi];
                if (b.t >= b.dur) { bubbles.splice(bi, 1); continue; }
                const p = b.t / b.dur;
                const f = b.f0 + (b.f1 - b.f0) * p;
                const env = Math.sin(Math.PI * Math.min(1, p));
                s += Math.sin(2 * Math.PI * f * b.t) * env * b.amp;
                b.t += 1 / rate;
            }
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

// 漂移层：每 3.5~7s 才微调一次目标方位（±8°），HRTF 用 τ=4s 极缓渐变跟随——
// 声像几乎静止，只在很长的尺度上缓缓呼吸（如"左40% 20秒内渐到左44%"）
function scheduleDrift(ly) {
    ly.driftTimer = setTimeout(() => {
        const az = Math.min(1.0, Math.max(-1.0, ly.az + (Math.random() - 0.5) * 0.28));
        ly.az = az;
        const t = audioCtx.currentTime;
        ly.panner.positionX.setTargetAtTime(Math.sin(az), t, 4);
        ly.panner.positionY.setTargetAtTime(0, t, 4);
        ly.panner.positionZ.setTargetAtTime(-Math.cos(az), t, 4);
        scheduleDrift(ly);
    }, 3500 + Math.random() * 3500);
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
    // 风声层走 windBoost 节点（阵风调度），其他层直连 masterGain
    ly.panner.connect(def.key === 'wind' && windBoost ? windBoost : masterGain);
    for (let i = 0; i < 2; i++) {
        ly.bufs[i] = makeLayerBuffer(audioCtx, def.key, def);
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

// 等功率交叉淡化曲线（sin/cos）：两段不相关噪声线性交叉（各 0.5 时功率 = 0.25+0.25 = 0.5）
// 会在中间塌陷 -3dB——用户听到的"每 20 秒左右音量骤降 0.几秒"就是这个。
// 等功率用 cos(θ) 淡出 + sin(θ) 淡入：cos²+sin²=1，任意时刻总功率恒定，听感无缝。
const FADE_CURVE_LEN = 128;
const EQ_FADE_OUT = new Float32Array(FADE_CURVE_LEN);
const EQ_FADE_IN = new Float32Array(FADE_CURVE_LEN);
for (let i = 0; i < FADE_CURVE_LEN; i++) {
    const th = (i / (FADE_CURVE_LEN - 1)) * (Math.PI / 2);
    EQ_FADE_OUT[i] = Math.cos(th);
    EQ_FADE_IN[i] = Math.sin(th);
}

function swapLayer(ly) {
    const t = audioCtx.currentTime + 0.02;
    const next = 1 - ly.active;
    ly.gains[ly.active].gain.cancelScheduledValues(t);
    ly.gains[ly.active].gain.setValueAtTime(Math.max(ly.gains[ly.active].gain.value, 0.0001), t);
    ly.gains[ly.active].gain.setValueCurveAtTime(EQ_FADE_OUT, t, FADE);
    try { ly.srcs[next].stop(); } catch (e) {}
    try { ly.srcs[next].disconnect(); } catch (e) {}
    ly.srcs[next] = makeSource(ly.bufs[next], ly.gains[next], ly.panner);
    ly.gains[next].gain.cancelScheduledValues(t);
    ly.gains[next].gain.setValueAtTime(0, t);
    ly.gains[next].gain.setValueCurveAtTime(EQ_FADE_IN, t, FADE);
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
    if (Math.random() < 0.4) {
        swell.phase = 'swell';
        swell.remain = triMode(20, 90, 55);
        swell.target = 1.05 + Math.random() * 0.3;
    } else {
        swell.phase = 'calm';
        swell.remain = 25 + Math.random() * 45;
        swell.target = 0.7 + Math.random() * 0.15;
    }
}

function startSwellScheduler() {
    planSwell();
    swellTimer = setInterval(() => {
        if (!swellGain) return;
        swellGain.gain.setTargetAtTime(swell.target, audioCtx.currentTime, 1.5);
        swell.remain -= 0.1;
        if (swell.remain <= 0) planSwell();
    }, 100);
}

// ── 森林阵风调度器：主体保持稳定，偶尔来一阵风（阴风）再平静 ──
// 只作用于风声层（windBoost 节点）；阵风增益 1.25~1.5 倍、平滑渐变（τ=1.5s），
// 既"突然来一下"又不会过头；多数时间平静（18~48s）保持主体稳定
const windGust = { phase: 'steady', remain: 0, target: 1 };
let windTimer = null;
let windBoost = null;

function planWindGust() {
    if (Math.random() < 0.3) {
        windGust.phase = 'gust';
        windGust.remain = 4 + Math.random() * 8;         // 阵风持续 4~12s
        windGust.target = 1.25 + Math.random() * 0.25;   // 抬升 1.25~1.5 倍（不过头）
    } else {
        windGust.phase = 'steady';
        windGust.remain = 18 + Math.random() * 30;       // 平静期 18~48s
        windGust.target = 1;
    }
}

function startWindScheduler() {
    planWindGust();
    windTimer = setInterval(() => {
        if (!windBoost) return;
        windBoost.gain.setTargetAtTime(windGust.target, audioCtx.currentTime, 1.5);
        windGust.remain -= 0.1;
        if (windGust.remain <= 0) planWindGust();
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

    // 总音量节点（海面后接高潮包络——浪涌来了又走；深海恒定水压，不挂包络；
    // 森林后接阵风节点——风声偶发突袭，只作用于风声层）
    masterGain = audioCtx.createGain();
    masterGain.gain.value = state.settings.volume / 100;
    if (type === 'sea') {
        swellGain = audioCtx.createGain();
        swellGain.gain.value = 1;
        masterGain.connect(swellGain);
        swellGain.connect(audioCtx.destination);
        startSwellScheduler();
    } else if (type === 'forest') {
        windBoost = audioCtx.createGain();
        windBoost.gain.value = 1;
        masterGain.connect(windBoost);
        windBoost.connect(audioCtx.destination);
        startWindScheduler();
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
    if (windTimer) { clearInterval(windTimer); windTimer = null; }
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
    if (windBoost) { try { windBoost.disconnect(); } catch (e) {} windBoost = null; }
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
