class NoiseProcessor extends AudioWorkletProcessor {
    constructor() {
        super();
        this._brown = 0;
        this._pink = { b0:0,b1:0,b2:0,b3:0,b4:0,b5:0,b6:0 };
        this._rainDropNext = 0;
        this._rainDropPhase = 0;
        this._rainDropDuration = 0;
        this._rainDropEnv = 0;
        this._rainDropFilterState = 0; // 简单一阶低通状态
    }

    static get parameterDescriptors() {
        return [
            { name: 'type', defaultValue: 0, minValue: 0, maxValue: 3, automationRate: 'k-rate' },
            { name: 'volume', defaultValue: 0.3, minValue: 0, maxValue: 1, automationRate: 'k-rate' },
        ];
    }

    _white() {
        return Math.random() * 2 - 1;
    }
    _pink() {
        const w = this._white();
        const p = this._pink;
        p.b0 = 0.99886 * p.b0 + w * 0.0555179;
        p.b1 = 0.99332 * p.b1 + w * 0.0750759;
        p.b2 = 0.96900 * p.b2 + w * 0.1538520;
        p.b3 = 0.86650 * p.b3 + w * 0.3104856;
        p.b4 = 0.55000 * p.b4 + w * 0.5329522;
        p.b5 = -0.7616 * p.b5 - w * 0.0168980;
        const pink = (p.b0 + p.b1 + p.b2 + p.b3 + p.b4 + p.b5 + p.b6 + w * 0.5362) * 0.11;
        p.b6 = w * 0.115926;
        return pink * 2;
    }
    _brown() {
        const w = this._white();
        this._brown = this._brown * 0.995 + w * 0.005; // 更稳定
        return this._brown * 3.5;
    }

    process(inputs, outputs, parameters) {
        const output = outputs[0];
        if (!output || output.length === 0) return true;

        const type = parameters.type[0];
        const volume = parameters.volume[0];
        const sampleRate = globalThis.sampleRate || 44100;

        for (let channel = 0; channel < output.length; ++channel) {
            const out = output[channel];
            for (let i = 0; i < out.length; ++i) {
                let sample = 0;

                if (type === 0) {
                    sample = 0;
                } else if (type === 1) { // rain
                    // 背景雨幕（粉红噪声）
                    sample += this._pink() * 0.3;
                    // 低频轰鸣（布朗噪声）
                    sample += this._brown() * 0.04;

                    // 雨滴脉冲（随机触发，更自然）
                    this._rainDropNext -= 1 / sampleRate;
                    if (this._rainDropNext <= 0) {
                        // 随机持续时间 5~25ms
                        this._rainDropDuration = 0.005 + Math.random() * 0.02;
                        this._rainDropPhase = this._rainDropDuration;
                        this._rainDropEnv = 0.08 + Math.random() * 0.15;
                        // 随机间隔：50%小雨滴密集，50%大雨滴稀疏
                        if (Math.random() < 0.5) {
                            this._rainDropNext = 0.008 + Math.random() * 0.012;
                        } else {
                            this._rainDropNext = 0.02 + Math.random() * 0.06;
                        }
                    }
                    if (this._rainDropPhase > 0) {
                        const t = this._rainDropDuration - this._rainDropPhase;
                        // 使用粉红噪声而不是白噪声，柔和一些
                        const envelope = Math.exp(-t * 120) * this._rainDropEnv;
                        sample += this._pink() * envelope;
                        this._rainDropPhase -= 1 / sampleRate;
                    }
                } else if (type === 2) { // forest
                    sample += this._brown() * 0.45 + this._pink() * 0.25;
                } else if (type === 3) { // deep
                    sample += this._brown() * 0.6 + this._pink() * 0.15;
                }

                out[i] = sample * volume;
            }
        }
        return true;
    }
}

registerProcessor('noise-processor', NoiseProcessor);