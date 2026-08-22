// ==================== 常量和全局状态 ====================
'use strict';

const QUOTES = [
    '吹灭读书灯，一身都是月。',
    '我心中一直在暗暗设想，天堂应该是图书馆的模样。——博尔赫斯',
    '此中有真意，欲辨已忘言。——陶渊明',
    '心静即声淡，其间无古今。——白居易',
    '知止而后有定，定而后能静，静而后能安。——《大学》',
    '人间有味是清欢。——苏轼',
    '吾生也有涯，而知也无涯。——庄子',
    '认识你自己。——德尔斐神谕',
    '首要原则是：你绝不能欺骗自己。——费曼',
    '要有耐心对待心中无法解决的一切，去爱问题本身。——里尔克',
    '我不匆忙，太阳和月亮也不匆忙。——佩索阿',
    '每一个不曾起舞的日子，都是对生命的辜负。——尼采',
    '在隆冬，我终于知道，我身上有一个不可战胜的夏天。——加缪',
    '宠辱不惊，看庭前花开花落。——洪应明',
    '问君何能尔，心远地自偏。——陶渊明',
    '静水流深，闻喧享静。',
    '大音希声，大象无形。——老子',
    '此心光明，亦复何言。——王阳明',
    '世界上任何书籍都不能带给你好运，但它们能让你悄悄成为你自己。——黑塞',
    '知者不惑，仁者不忧，勇者不惧。——孔子',
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