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

// 预生成指定类型的噪声 buffer
// 合成手法（业界共识，参考 Audiokinetic 雨声合成 / procedural audio 滤波塑形）：
// 白噪/棕噪为源 → 二阶 IIR 滤波塑形（带通雨幕、低通风声、低通涌动）→
// 慢速 LFO 幅度起伏（风/涌动）→ Kellet 粉噪作森林中频层。
//   rain  雨幕 = 白噪二阶带通(400~3000Hz) + 白噪二阶带通(1k~4k)水滴短脉冲 + 棕噪湿润
//   forest 风声 = 棕噪二阶低通(800Hz) + Kellet 粉噪中频 + 白噪二阶低通(1500Hz)叶沙 + 0.11Hz LFO
//   deep   涌动 = 棕噪二阶低通(450Hz) + 白噪二阶带通(1.5k~2.5k)水泡 + 0.07Hz LFO
function makeNoiseBuffer(ctx, type) {
    const seconds = BUFFER_SECONDS;
    const rate = ctx.sampleRate;
    const len = Math.floor(rate * seconds);
    const buf = ctx.createBuffer(2, len, rate);

    // 二阶低通系数（级联两个一阶，-24dB/oct 才够塑形）：a = 1 - exp(-2π·fc/fs)
    const lp = (fc) => 1 - Math.exp(-2 * Math.PI * fc / rate);

    for (let ch = 0; ch < 2; ch++) {
        const data = buf.getChannelData(ch);
        // 各二阶低通状态（每声道独立 → 立体声宽度）；状态按 [s1, s2] 级联
        const S = (a) => ({ a, s1: 0, s2: 0, lp: function (x) {
            const t = this.s1 + this.a * (x - this.s1);
            this.s2 = this.s2 + this.a * (t - this.s2);
            this.s1 = t;
            return this.s2;
        }});
        const rainBedHi = S(lp(3000)), rainBedLo = S(lp(400));   // 雨幕带通上下界
        const dropHi = S(lp(4000)), dropLo = S(lp(1000));        // 水滴带通（更像水珠，不刺耳）
        const windLo = S(lp(800));                                // 森林风声
        const leafLo = S(lp(1500));                               // 森林叶沙
        const deepLo = S(lp(450));                                // 深海涌动
        const bubbleHi = S(lp(2500)), bubbleLo = S(lp(1500));     // 深海气泡带通
        let brown = 0;   // 棕噪积分器
        // 经典 Paul Kellet 粉噪状态（森林中频层）
        let k0 = 0, k1 = 0, k2 = 0, k3 = 0, k4 = 0, k5 = 0, k6 = 0;
        // 雨滴状态：高通白噪短脉冲（2~8ms），间隔 30~120ms
        let dropNext = 0, dropPhase = 0, dropDur = 0, dropEnv = 0;
        // LFO 起伏（风声/涌动）：每声道相位错开
        const lfoFreq = type === 'deep' ? 0.07 : 0.11;
        const lfoPhase = ch * Math.PI; // 左右错相，立体声更宽

        for (let i = 0; i < len; i++) {
            const w = Math.random() * 2 - 1;  // 白噪源
            brown = brown * 0.995 + w * 0.005;
            // 经典 Paul Kellet 粉噪（森林中频层更自然）
            k0 = 0.99886 * k0 + w * 0.0555179;
            k1 = 0.99332 * k1 + w * 0.0750759;
            k2 = 0.96900 * k2 + w * 0.1538520;
            k3 = 0.86650 * k3 + w * 0.3104856;
            k4 = 0.55000 * k4 + w * 0.5329522;
            k5 = -0.7616 * k5 - w * 0.0168980;
            const pink = (k0 + k1 + k2 + k3 + k4 + k5 + k6 + w * 0.5362) * 0.11 * 2;
            k6 = w * 0.115926;

            let s = 0;
            if (type === 'rain') {
                // 雨幕：白噪 → 二阶带通 400~3000Hz（雨落的"嘶"，主体）
                const bed = rainBedHi.lp(w) - rainBedLo.lp(w);
                // 水滴：白噪 → 二阶带通 1000~4000Hz 的短脉冲（点缀，幅度小）
                const dropNoise = dropHi.lp(w) - dropLo.lp(w);
                dropNext -= 1 / rate;
                if (dropNext <= 0) {
                    dropDur = 0.002 + Math.random() * 0.006;
                    dropPhase = dropDur;
                    dropEnv = 0.06 + Math.random() * 0.1;
                    dropNext = 0.03 + Math.random() * 0.09;
                }
                let drop = 0;
                if (dropPhase > 0) {
                    const tt = dropDur - dropPhase;
                    drop = dropNoise * (Math.exp(-tt * 400) * dropEnv);
                    dropPhase -= 1 / rate;
                }
                s = bed * 1.4 + drop + brown * 0.06;
            } else if (type === 'forest') {
                // 风声：棕噪 → 二阶低通800；叶沙：白噪 → 二阶低通1500；中频：Kellet 粉噪
                const wind = windLo.lp(brown);
                const leaf = leafLo.lp(w);
                // 0.11Hz LFO 风起伏（±40%）
                const lfo = 0.6 + 0.4 * Math.sin(2 * Math.PI * lfoFreq * i / rate + lfoPhase);
                s = (wind * 0.42 + pink * 0.3 + leaf * 0.14) * lfo;
            } else if (type === 'deep') {
                // 涌动：棕噪 → 二阶低通450；水泡：白噪 → 二阶带通(1500~2500)
                const swell = deepLo.lp(brown);
                const bubbles = bubbleHi.lp(w) - bubbleLo.lp(w);
                // 0.07Hz LFO 涌动（±35%）
                const lfo = 0.65 + 0.35 * Math.sin(2 * Math.PI * lfoFreq * i / rate + lfoPhase);
                s = (swell * 2.2 + bubbles * 0.15) * lfo;
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
