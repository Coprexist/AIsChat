# 魔视界 — CSS 滤镜系统

## 概述

魔视界为用户提供 10 种 CSS 标准滤镜函数的可视化调节面板，可实时预览并持久化保存。配置存储在 `ui_prefs.magic_vision` JSONB 字段。

## 三种作用域

| 模式 | 实现方式 | 原理 |
|------|---------|------|
| `all` 全部生效 | `html.style.filter` | 直接挂 `<html>`，整页作为其渲染内容被滤镜处理（`filter` 非继承属性） |
| `images` 仅对图片 | `<style>* { filter: none !important } img, video... { filter: css !important }</style>` | 先通配清零所有元素，再对媒体元素单独激活滤镜 |
| `ui` 仅对 UI | `<style>*:not(:has(img)):not(:has(video)):not(:has(canvas)):not(:has(picture)) { filter: css !important } img, video... { filter: none !important }</style>` | CSS `:has()` 父选择器跳过含媒体子树的容器；高特异性清理规则保护媒体元素不被优先级压过 |

## 核心技术：`:has()` 选择器

仅对 UI 是核心难点。使用 CSS `:has()` 父选择器精准跳过含媒体子树的容器：

```css
*:not(:has(img)):not(:has(video)):not(:has(canvas)):not(:has(picture)) {
  filter: var(--mv-val) !important;
}
```

图片所在的祖先容器不挂滤镜，图片本身也被清零规则拦截。接受 `filter` 的元素浏览器会创建堆叠上下文。

### 为什么不用 JS 遍历（TreeWalker）

对比结论：**`:has()` 纯 CSS 方案在 React 生态下优于任何 JS DOM 操作方案。**

| 维度 | `:has()` CSS | TreeWalker + MutationObserver |
|------|-------------|------------------------------|
| React 兼容性 | 不碰 DOM 结构，虚拟 DOM 无感知 | 改 DOM 可能与 React 重绘产生拉锯 |
| 动态内容 | 浏览器原生实时生效，新节点自动匹配 | 需 MutationObserver 监听 + 重新遍历 |
| 性能 | CSS 引擎直接处理，零 JS 开销 | 全量遍历 + getComputedStyle + 防抖 |
| 代码量 | ~10 行 CSS | ~80 行 JS + 状态管理 |
| 浏览器要求 | Chrome 105+, Safari 15.4+, Firefox 121+ | 全兼容 |

### 什么时候应该用 JS 方案

- 需要兼容 Chrome < 105 或 Safari < 15.4
- 需求超越"过滤媒体标签"，如根据运行时数据动态决定
- 需要对文本节点做字符级处理

## CSS 优先级处理

这是实现中最容易踩的坑。清零规则必须压过通配符选择器：

```css
/* 通配符：4 个 :not(:has(...)) → 每个 :not(:has(img)) 的优先级为 (0,0,1)，合计 (0,0,4) */
*:not(:has(img)):not(:has(video)):not(:has(canvas)):not(:has(picture)) {
  filter: hue-rotate(90deg) !important;
}

/* 清零规则：4 个 :not(.x)（各 (0,1,0)）+ img → 优先级 (0,4,1) > (0,0,4) */
:not(.a):not(.b):not(.c):not(.d) img {
  filter: none !important;
}
```

`!important` 同时存在时优先比较特异性（specificity），`:not(.a):not(.b):not(.c):not(.d) img` 的特异性为 (0,4,1)，高于 `*:not(:has(img)):not(:has(video)):not(:has(canvas)):not(:has(picture))` 的 (0,0,4)，清零规则胜出。

## 背景图清零说明

清零规则中包含 `[style*="background-image"]` 来匹配内联样式设置的背景图，以及 `[class*="avatar"]` / `[class*="Avatar"]` 等常见 class 模式。

**局限性**：`[style*="background-image"]` 仅匹配 HTML `style` 属性中包含该字符串的元素。通过 CSS 类定义的背景图（如 `.card { background-image: url(...) }`）无法用属性选择器检测。若需要完整覆盖此场景，可以考虑：
- 在组件层面对背景图容器约定 `data-mv-clean` 属性标记（如 `<div data-mv-clean className="avatar" />`），再在清零规则中增加 `[data-mv-clean] { filter: none !important; }`，这是 React 项目中最干净的解法
- 在 apply 时结合 JS `getComputedStyle` 遍历检查
- 当前方案已覆盖内联 style 设置的背景图。对于通过 CSS 类定义的背景图，可通过 `data-mv-clean` 标记主动豁免

## 10 种滤镜函数

| ID | 名称 | CSS | 范围 | 默认值 |
|----|------|-----|------|--------|
| blur | 模糊 | `blur(v px)` | 0–20 | 0 |
| brightness | 亮度 | `brightness(v %)` | 0–300 | 100 |
| contrast | 对比度 | `contrast(v %)` | 0–300 | 100 |
| drop-shadow | 投影 | `drop-shadow(v px v px v×0.5 px rgba(0,0,0,.5))` | 0–30 | 0 |

> `drop-shadow()` 参数顺序：`offset-x offset-y blur-radius color`，依次为水平偏移、垂直偏移、模糊半径、颜色。
| grayscale | 灰度 | `grayscale(v %)` | 0–100 | 0 |
| hue-rotate | 色相旋转 | `hue-rotate(v deg)` | 0–360 | 0 |
| invert | 反色 | `invert(v %)` | 0–100 | 0 |
| opacity | 透明度 | `opacity(v %)` | 0–100 | 100 |
| saturate | 饱和度 | `saturate(v %)` | 0–500 | 100 |
| sepia | 棕褐色 | `sepia(v %)` | 0–100 | 0 |

## 持久化

- **前端**：`localStorage.magic_vision_prefs` — 页面加载时由 Layout 组件在首屏渲染完成后恢复
- **云端**：`PUT /user/settings` → `ui_prefs.magic_vision` — "应用"按钮独立保存，与主保存按钮解耦
- **恢复时机**：Layout 组件的 `useEffect([], [])`。空依赖数组意味着仅在挂载时执行一次。如果路由切换导致 Layout 重新挂载（如从保护路由切换到公开路由再切换回来），会重复读取并应用，这是无害的。如需全局防重，可在模块级加 `let _applied = false` 标记。

## 文件结构

```
frontend/src/
├── utils/cssFilters.ts              ← 核心：类型/滤镜定义/CSS构建/DOM注入/存储
├── components/MagicVisionFilter.tsx  ← UI：设置页中的魔视界面板
├── components/Layout.tsx             ← 恢复：首屏后读取 localStorage 应用
├── main.tsx                          ← 不污染
└── public/docs/magic-vision.md       ← 本文档
```

## 后端

用户侧无新增表，直接使用 `ui_prefs` JSONB 字段（User 模型已有）。魔视界配置作为 `ui_prefs.magic_vision` 嵌套对象存储。PUT /user/settings 已支持写入，无需数据库迁移。
