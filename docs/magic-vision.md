# 魔视界 — CSS 滤镜系统

## 概述

魔视界为用户提供 10 种 CSS 标准滤镜函数的可视化调节面板，可实时预览并持久化保存。`ui_prefs.magic_vision` JSONB 字段存储。

## 三种作用域

| 模式 | 实现方式 | 原理 |
|------|---------|------|
| `all` 全部生效 | `html.style.filter` | 直接挂根元素，所有子孙继承 |
| `images` 仅对图片 | `<style>* { none } img { css }</style>` | 全局清零后只激活媒体元素 |
| `ui` 仅对 UI | **`<style>*:not(:has(img)) { css }</style>`** | CSS `:has()` 选择器原生实时生效 |

## 核心技术：`:has()` 选择器

**仅对 UI** 是核心难点。使用 CSS `:has()` 父选择器精准跳过含媒体子树的容器：

```css
/* 只选不含 img/video/canvas/picture 子树的元素 */
*:not(:has(img)):not(:has(video)):not(:has(canvas)):not(:has(picture)) {
  filter: var(--mv-val) !important;
}
```

**为什么不用 JS 遍历（TreeWalker）？**

对比结论：**`:has()` 纯 CSS 方案在 React 生态下明显优于 JS 方案。**

| 维度 | `:has()` CSS | TreeWalker + MutationObserver |
|------|-------------|------------------------------|
| React 兼容性 | **不碰 DOM 结构**，虚拟 DOM 无感知 | `replaceChild` 包文本节点，与 React 重绘可能拉锯 |
| 动态内容 | **浏览器原生实时生效**，新节点自动匹配 | 需 MutationObserver 监听 + 重新遍历 |
| 性能 | CSS 引擎直接处理，零 JS 开销 | 全量遍历 + getComputedStyle + Observer 防抖 |
| 代码量 | ~10 行 CSS | ~80 行 JS + 状态管理 |
| 浏览器要求 | Chrome 105+, Safari 15.4+, Firefox 121+ | 全兼容 |

**什么时候应该用 JS 方案？**

- 需要兼容 Chrome < 105 或 Safari < 15.4
- 需求超越"过滤媒体标签"，如根据运行时数据动态决定
- 需要对文本节点做字符级处理

## CSS 优先级处理

这是实现中最容易踩的坑。清零规则必须压过通配符选择器：

```css
/* 通配符：4 个 :not(:has(...)) → 优先级 (0,4,0) */
*:not(:has(img)):not(:has(video)):not(:has(canvas)):not(:has(picture)) {
  filter: hue-rotate(90deg) !important;
}

/* 清零规则：4 个 :not(.x) + img → 优先级 (0,4,1) > (0,4,0) */
:not(.a):not(.b):not(.c):not(.d) img {
  filter: none !important;
}
```

`!important` 同时存在时，优先级更高的规则获胜。

## 附加清零规则

除了 `<img>` 标签，以下情况也需要不受滤镜影响：

- `[style*="background-image"]` — 内联样式的背景图
- `[class*="avatar"]`, `[class*="Avatar"]` — 常见头像 class 命中的背景图
- 纯 CSS `::before`/`::after` 背景图无法通过选择器检测，但不常见

## 10 种滤镜函数

| ID | 名称 | CSS | 范围 | 默认值 |
|----|------|-----|------|--------|
| blur | 模糊 | `blur(v px)` | 0–20 | 0 |
| brightness | 亮度 | `brightness(v %)` | 0–300 | 100 |
| contrast | 对比度 | `contrast(v %)` | 0–300 | 100 |
| drop-shadow | 投影 | `drop-shadow(v v v*.5 rgba(0,0,0,.5))` | 0–30 | 0 |
| grayscale | 灰度 | `grayscale(v %)` | 0–100 | 0 |
| hue-rotate | 色相旋转 | `hue-rotate(v deg)` | 0–360 | 0 |
| invert | 反色 | `invert(v %)` | 0–100 | 0 |
| opacity | 透明度 | `opacity(v %)` | 0–100 | 100 |
| saturate | 饱和度 | `saturate(v %)` | 0–500 | 100 |
| sepia | 棕褐色 | `sepia(v %)` | 0–100 | 0 |

## 持久化

- **前端**：`localStorage.magic_vision_prefs` — 页面加载时 `Layout` 组件 `useEffect` 恢复
- **云端**：`PUT /user/settings` → `ui_prefs.magic_vision` — "应用"按钮独立保存，不依赖主保存按钮
- **恢复时机**：Layout 组件的 `useEffect([], [])`，确保 React 首屏渲染完成后才执行

## 文件结构

```
frontend/src/
├── utils/cssFilters.ts          ← 核心：类型/构建/注入/存储
├── components/MagicVisionFilter.tsx  ← UI：设置页中的魔视界面板
├── components/Layout.tsx         ← 恢复：首屏后读取 localStorage 应用
└── main.tsx                     ← 不清不染
```
