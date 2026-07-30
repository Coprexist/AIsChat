# 魔视界 — CSS 滤镜系统

## 概述

魔视界为用户提供 10 种 CSS 标准滤镜函数的可视化调节面板，可实时预览并持久化保存。配置存储在 `ui_prefs.magic_vision` JSONB 字段。

## 三种作用域

| 模式 | 实现方式 | 原理 |
|------|---------|------|
| `all` 全部生效 | `html.style.filter` | 直接挂 `<html>`，整页作为其渲染内容被滤镜处理（`filter` 非继承属性） |
| `images` 仅对图片 | `<style>* { none !important } img { css !important }</style>` | 先通配清零，再对媒体元素单独激活 |
| `ui` 仅对 UI | `<style>*:not(:has(img)) { css }</style>` + 隐藏 `#mv` 锚点 | `:has()` 跳过含媒体子树的容器 + `#mv img` 高特异性清零 |

## 核心技术：`:has()` 选择器

仅对 UI 使用 CSS `:has()` 父选择器精准跳过含媒体子树的容器：

```css
*:not(:has(img)):not(:has(video)):not(:has(canvas)):not(:has(picture)) {
  filter: var(--mv-val) !important;
}
```

图片所在的祖先容器不挂滤镜，图片本身也被清零规则拦截。接受 `filter` 的元素浏览器会创建堆叠上下文。

### ⚠️ 兼容性

`:has()` 需要 **Chrome 105+ / Safari 15.4+ / Firefox 121+**。不支持 `:has()` 的浏览器下此规则被整体丢弃，"仅对 UI" 模式降级为无效果（不影响其他功能）。

### 性能说明

`*:not(:has(img))` 会让浏览器为每个元素检查子树中是否含有媒体元素。在典型聊天页面（数百 DOM 节点）中实测无感；若在数千节点的重型页面中使用需评估。相比 JS TreeWalker + MutationObserver 方案，`:has()` 仍为更优选择。

## CSS 优先级处理

清零规则必须压过通配符选择器。使用**隐藏锚点元素** `#mv` 提供确定性的高特异性：

```css
/* :has() 规则：4 个 not(:has(...)) → 优先级 (0,0,4) */
*:not(:has(img)):not(:has(video)):not(:has(canvas)):not(:has(picture)) {
  filter: hue-rotate(90deg) !important;
}

/* 清零规则：#mv img → 优先级 (1,0,1) > (0,0,4) */
#mv img, #mv video, #mv canvas, #mv picture,
#mv [style*="background-image"], #mv [class*="avatar"], #mv [class*="Avatar"], #mv [data-mv-clean] {
  filter: none !important;
}
```

`#mv` 是一个 `display:none` 的 `<div>`，不影响页面布局。`#mv img` 的选择器特异性为 (1,0,1)，确定性地压过 `:has()` 的 (0,0,4)。

### 为什么不用 JS 遍历（TreeWalker）

| 维度 | `:has()` CSS | TreeWalker + MutationObserver |
|------|-------------|------------------------------|
| React 兼容性 | 不碰 DOM 结构，虚拟 DOM 无感知 | 改 DOM 可能与 React 重绘产生拉锯 |
| 动态内容 | 浏览器原生实时生效 | 需 MutationObserver + 重新遍历 |
| 性能 | CSS 引擎处理，零 JS 开销 | 全量遍历 + getComputedStyle + 防抖 |
| 代码量 | ~10 行 CSS | ~80 行 JS + 状态管理 |
| 浏览器要求 | Chrome 105+, Safari 15.4+, Firefox 121+ | 全兼容 |

## 背景图清零说明

清零规则包含 `[style*="background-image"]`（内联样式）、`[class*="avatar"]` / `[class*="Avatar"]`（常见 class 模式）以及 `[data-mv-clean]`（手动标记）。

**局限性**：`[style*="background-image"]` 仅匹配 HTML `style` 属性中的字符串。通过 CSS 类定义的背景图（如 `.card { background-image: url(...) }`）无法命中。如需完整覆盖，可在组件层面对背景图容器添加 `data-mv-clean` 属性。

## 已知限制

与所有 CSS `filter` 应用一样，魔视界具有以下浏览器固有行为：
- `filter` 会改变元素的包含块（containing block），可能影响内部 `position: fixed` 元素的定位
- 每个接受 `filter` 的元素创建堆叠上下文，大量元素时可能增加 GPU 合成层内存
- 浏览器打印模式下通常禁用 CSS 滤镜

## 10 种滤镜函数

| ID | 名称 | CSS | 范围 | 默认值 |
|----|------|-----|------|--------|
| blur | 模糊 | `blur(v px)` | 0–20 | 0 |
| brightness | 亮度 | `brightness(v %)` | 0–300 | 100 |
| contrast | 对比度 | `contrast(v %)` | 0–300 | 100 |
| drop-shadow | 投影 | `drop-shadow(v px v px v×0.5 px rgba(0,0,0,.5))` | 0–30 | 0 |
| grayscale | 灰度 | `grayscale(v %)` | 0–100 | 0 |
| hue-rotate | 色相旋转 | `hue-rotate(v deg)` | 0–360 | 0 |
| invert | 反色 | `invert(v %)` | 0–100 | 0 |
| opacity | 透明度 | `opacity(v %)` | 0–100 | 100 |
| saturate | 饱和度 | `saturate(v %)` | 0–500 | 100 |
| sepia | 棕褐色 | `sepia(v %)` | 0–100 | 0 |

> `drop-shadow()` 参数顺序：`offset-x offset-y blur-radius color`，依次为水平偏移、垂直偏移、模糊半径、颜色。

## 持久化

- **前端**：`localStorage.magic_vision_prefs` — 页面加载时由 Layout 组件在首屏渲染完成后恢复
- **云端**：`PUT /user/settings` → `ui_prefs.magic_vision` — "应用"按钮独立保存，与主保存按钮解耦
- **主保存保护**：主"保存设置"按钮同步写 localStorage + 重新 `apply()`，防止 `refreshUser()` 覆盖
- **恢复时机**：Layout 组件的 `useEffect([], [])`。空依赖数组意味着仅在挂载时执行一次。

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

用户侧无新增表，直接使用 `ui_prefs` JSONB 字段（User 模型已有）。魔视界配置作为 `ui_prefs.magic_vision` 嵌套对象存储。后端 `update_user_settings` 对 `ui_prefs` 做浅合并而非整字段覆盖，避免丢失 `magic_vision`。
