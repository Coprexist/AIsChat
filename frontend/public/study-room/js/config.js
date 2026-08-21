// ==================== 常量和全局状态 ====================
'use strict';

const QUOTES = [
    '学如逆水行舟，不进则退。', '千里之行，始于足下。', '不积跬步，无以至千里。',
    '知之者不如好之者，好之者不如乐之者。', '学而不思则罔，思而不学则殆。',
    '书山有路勤为径，学海无涯苦作舟。', '业精于勤，荒于嬉。', '黑发不知勤学早，白首方悔读书迟。',
    '一寸光阴一寸金，寸金难买寸光阴。', '博学之，审问之，慎思之，明辨之，笃行之。',
    '三人行，必有我师焉。', '温故而知新，可以为师矣。', '敏而好学，不耻下问。',
    '知之为知之，不知为不知，是知也。', '路漫漫其修远兮，吾将上下而求索。',
    '少壮不努力，老大徒伤悲。', '读书破万卷，下笔如有神。', '纸上得来终觉浅，绝知此事要躬行。',
    '问渠那得清如许，为有源头活水来。', '宝剑锋从磨砺出，梅花香自苦寒来。'
];

const DEFAULT_SETTINGS = {
    focus: 25,
    short: 5,
    long: 15,
    interval: 4,
    volume: 30,
    autoStart: false,
    stereo: true
};

const MODES = {
    focus: { label: '专注', status: '专注中...' },
    short: { label: '短休', status: '休息中...' },
    long: { label: '长休', status: '深度休息...' }
};

// 全局状态对象
const state = {
    mode: 'focus',
    isRunning: false,
    isPaused: false,
    remainingSeconds: DEFAULT_SETTINGS.focus * 60,
    totalSeconds: DEFAULT_SETTINGS.focus * 60,
    endTime: null,
    timerId: null,
    sessionsCompleted: 0,
    currentCycle: 0,
    settings: { ...DEFAULT_SETTINGS },
    soundType: 'off',
    todos: [],
    stats: {},
    quoteIdx: Math.floor(Math.random() * QUOTES.length),
    isFullscreen: false,
};