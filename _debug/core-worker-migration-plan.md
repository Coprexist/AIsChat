# Core Worker 迁移执行计划

> 基于 `core-worker-migration.md`，并结合当前代码库的真实结构、耦合点与测试分布整理。

---

## 当前状态

> 最后更新：2026-07-02。Phase 1 已完成，Phase 2（同线程 BoardApi）已完成。Creator Family + Modifier Family + Chooser Family + UI overlay summary 入口全部迁移完成。Phase 3 全部完成：P3.1–P3.5 核心基础设施、P3.6-A（Chooser async read-path）、P3.6-B（Creator Worker-first 本地草稿）、P3.6-C（渲染叠帧修复 + force 转发 + 选择对象级失效优化）。

以下为完成 P1 + P2 + P3.6-C 后的当前代码库状态：

### 已完成

#### P0：预解耦

| 模块 | 变更 | 关键文件 |
| ---- | ---- | -------- |
| `board.js` | 已拆为 UI Façade，内部持有 `BoardCore` | `board-core.js`（新增） |
| `BoardCore` | 纯 Core 实现，不依赖 DOM/DevicesDAG/bridge | `src/core/components/orchestration/board-core.js` |
| `ActiveObjectManager` | 渲染副作用已抽为注入式 renderHooks | `aom-render-hooks.js` + `board-render-hooks.js`（新增） |
| 文件桥 | `BoardCore` 不再直接 import bridge，通过 persistenceAdapter 注入 | `persistence-adapter.js`（新增） |
| `createDeviceContext()` | 保留未动 | `tool.js` |

#### P1：共享纯模块验证 ✅

| 模块 | 变更 | 关键文件 |
| ---- | ---- | -------- |
| Import 链审计 | 逐文件审查候选共享模块，确认无隐蔽 DOM/Worker/IPC 依赖 | 记录在本文档 |
| `dirty-rect-strategy.js` 拆分 | 纯函数拆为独立文件，Chunk 依赖保留原文件 | `dirty-rect-strategy-shared.js`（新增） |
| 类型定义 | 新建共享类型定义目录 | `src/core/shared/types.js`, `board-api-types.js`, `message-types.js`（新增） |
| Node smoke test | 验证 10 个共享模块在 Node 环境可 import 无报错 | `shared-module-smoke.test.js`（新增） |
| 测试回归 | range/ + utils/ 测试 + 全量测试全部通过 | 81 suites / 1015 tests / 0 failed |

#### P2：同线程 BoardApi ✅（已完成）

| 方法 | 状态 |
| ---- | ---- |
| `createObject(type, props)` | ✅ 实现（P1 遗留） |
| `modifyObject(objectId, patch)` | ✅ 实现 |
| `modifyObjects(patches)` | ✅ 实现 |
| `appendListItem(objectId, key, items)` | ✅ 实现 |
| `replaceListItem(objectId, key, index, item)` | ✅ 实现 |
| `removeListItem(objectId, key, index)` | ✅ 实现 |
| `deleteObjects(objectIds)` | ✅ 实现 |
| `commitObjects(objectIds)` | ✅ 实现 |
| `addActiveObjects(objectIds)` | ✅ 实现 |
| `discardActiveObjects(objectIds)` | ✅ 实现 |
| `queryObjects(ids)` | ✅ 实现 |
| `queryChunkObjects(chunkIds)` | ✅ 实现 |
| `hitTest(range, mode?)` | ✅ 实现 |
| `createMonitor(options)` | ✅ 实现 |
| `destroyMonitor(monitorId)` | ✅ 实现 |
| `undo()` / `redo()` | ❌ 待 P3+ |

### 待完成

- **P2 已完成** ✅（Creator Family + Modifier + Chooser + UI overlay summary 入口）
- **P3 已完成**：
  - P3.1–P3.5 ✅ 核心基础设施
  - **P3.6-A** ✅ Chooser async read-path + RPC 模式禁用 stale board fallback + async-safe handoff
  - **P3.6-B** ✅ Creator Worker 兼容（local draft 对象，worker-first 设计）
  - **P3.6-C** ✅ 修复 Worker 渲染叠帧、force 转发、选中对象级失效
- **当前 demo 入口**：`src/templates/whiteboard.js` 已默认启用 Worker mode（`new Worker(...)` + `Board.enableWorkerMode()`）
- **P4**：性能优化

## 迁移拆解

本次迁移分为四个阶段：

- **P1：共享纯模块验证** — 确认可共享模块并定义跨线程类型
- **P2：同线程 BoardApi + 工具去对象引用化** — 引入 `BoardApi`（同步实现），工具从对象实例直连迁到 API + 同步兼容层，为 P3 异步化做准备
- **P3：Worker 落地 + Proxy 拆分** — 创建 Worker，落地 `BoardCore` / `MonitorCore` / `MonitorProxy`
- **P4：性能优化** — 批量修改、帧复用、基准测试

## 当前代码库中的关键耦合点

> 以下记录 P0 已处理后的关键边界与剩余关注点。其中 A/B 已在 P3.3 正式落地，其余项继续作为 P4 的实现约束。

### A. `board.js` 已拆为 UI Façade，不再承担 Core 职责

**文件**：`src/core/components/orchestration/board.js`

P0 已将 Core 数据职责下沉到 `BoardCore`，`board.js` 现为 UI Façade：

| 职责 | 是否应进 Worker | 当前归属 |
| ---- | --------------- | -------- |
| `objectLoaded` / `chunkLoaded` / `UndoTree` / `AOM` | 是 | `BoardCore` |
| `DevicesDAG` / `signalsEventBus` | 否，应留 UI | `Board`（façade） |
| `createMonitor()` 创建 DOM 节点/canvas，并在 Worker mode 下返回 `MonitorProxy` | 否，应留 UI | `Board`（façade） |
| `boardFileOperateBridge` 文件 IPC | 否，Worker 不能直用 | 通过 `persistenceAdapter` 注入 `BoardCore` |

---

### B. `monitor.js` 已完成 Worker 路径拆分（P3.3 已落地）

**文件**：`src/core/components/orchestration/monitor.js`

当前代码库已新增：

| 角色 | 文件 | 当前状态 |
| ---- | ---- | -------- |
| Worker 侧 monitor | `monitor-core.js` | ✅ 已实现：chunk buffer、BaseRenderer、LiveRenderer、render-frame 产出 |
| UI 侧 monitor | `monitor-proxy.js` | ✅ 已实现：视口副本、UiRenderer、overlay/workflow、render-frame 合成 |
| 同线程 compat path | `monitor.js` | ✅ 保留：旧 `Monitor` 继续作为同线程实现与兼容入口 |

**结论**：P3.3 已完成结构拆分。后续不再从 `monitor.js` 内部继续做方法级剥离，而是以 `MonitorCore` / `MonitorProxy` 为 Worker 路径主实现，`monitor.js` 仅保留 same-thread / compat 职责。

---

### C. `ActiveObjectManager` 已抽离渲染副作用（P0 已完成）

**文件**：`src/core/components/orchestration/active-object-manager.js`

P0 已将三个渲染方法抽成注入式 hooks：

- `requestLiveRender(...)` → `this.renderHooks.requestLiveRender(...)`
- `requestBaseRenderForObjects(...)` → `this.renderHooks.requestBaseRenderForObjects(...)`
- `_flushViewportForObjects(...)` → `this.renderHooks.flushViewportForObjects(...)`

`choose()` / `add()` / `apply()` / `discard()` / `remove()` 语义不变。

后续 Worker 化时只需替换 hook 实现，无需修改 AOM 本身。

---

### D. 当前工具迁移难点不在 API，而在"对象实例依赖"

重点文件：

- `src/core/tools/tool.js`
- `src/core/tools/creator/object-creator.js`
- `src/core/tools/creator/stroke-creator.js`
- `src/core/tools/creator/circle-creator.js`
- `src/core/tools/creator/polygon-creator.js`
- `src/core/tools/modifier/object-modifier.js`
- `src/core/tools/modifier/common-object-modifier.js`
- `src/core/tools/chooser/object-chooser.js`
- `src/core/tools/chooser/rectangle-object-chooser.js`

当前依赖模式：

| 现状 | 后续目标 |
| ---- | -------- |
| 工具持有 `BasicObject` 实例 | 工具只持有 `objectId` + 本地 shadow/summary |
| creator 直接 `new StrokeObject(...)` / `CircleObject(...)` | `await boardApi.createObject(type, props)` |
| modifier 直接改 `obj.position` | `boardApi.modifyObject(id, patch)` |
| chooser 扫 `AOM.activeObjectIndex` | `boardApi.queryObjects()` / `boardApi.hitTest()` |
| 工具直接调 `monitor.liveRenderer` | 由 Core 自动处理 dirty/render |

**结论**：P2 的核心不只是做个 `BoardApi` 壳子，而是把这些工具从"对象直改"改成"消息式修改"。

---

### E. 文件桥当前是 renderer-only，不能直接在 Worker 用

**文件**：`src/core/bridges/file-operate-bridge-renderer.js`

P0 已通过 persistenceAdapter 接口解耦，`BoardCore` 不再直接 import 该 bridge。Worker 版只需提供新的 adapter 实现，通过 UI host 转发 Tauri IPC。

---

### F. Renderer 基类反而已经比较适合迁移

**文件**：`src/core/components/renderer/renderer.js`

`Renderer.resize()`、`_getContext()` 等方式已比较通用，BaseRenderer / LiveRenderer 迁到 OffscreenCanvas 的风险低于工具层解耦风险。

---

## 总览

| 阶段 | 目标 | 预计耗时 | 依赖 |
| ---- | ---- | -------- | ---- |
| **P0** | 先拆真实耦合点：Board / AOM / Bridge | ✅ 已完成 | 无 |
| **P1** | 抽取共享层，验证纯模块可在 Worker / Node 运行 | ✅ 已完成 | 无 |
| **P2** | 同线程 `BoardApi` 所有 13 个方法实现完成；Creator + Modifier + Chooser + UI overlay summary 全部迁移完成 | ✅ 已完成 | P1 完成 |
| **P3** | 创建 Worker，落地 `BoardCore` / `MonitorCore` / `MonitorProxy`，接通 RPC 与渲染管线 | ✅ 已完成 | P2 完成 |
| **P4** | 性能优化、埋点、基准测试、降级方案收尾 | 2-3 天 | P3 完成 |

---

## 术语统一约定

为避免后续实现时把“当前类名”和“迁移后职责”混在一起，本文统一使用以下术语：

| 术语 | 固定含义 |
| ---- | -------- |
| `Board` | **UI 线程 façade**。保留 `DevicesDAG`、`signalsEventBus`、`monitors`、运行时 mount/umount、DOM monitor 创建等职责。默认指当前 `src/core/components/orchestration/board.js` 演化后的主线程宿主。 |
| `BoardCore` | **Core 侧纯实现**。承载对象注册、区块加载、AOM、UndoTree、持久化协调等职责。最终运行在 Worker；在 P0/P2 阶段可先同线程存在。 |
| `BoardApi` | **UI 调 Core 的统一 API façade**。P2 是同线程实现，P3 切为 RPC 实现；方法签名尽量保持不变。 |
| `Monitor` | 泛指“显示器”这一概念，不单指某个具体类。文中若未特别说明，表示抽象概念。 |
| `MonitorProxy` | **UI 线程 monitor 子集**。持有视口状态、UiRenderer、overlay provider、workflow 挂载能力，并与 Worker 交换 viewport/render-frame 消息。 |
| `MonitorCore` | **Worker 线程 monitor 子集**。持有 chunkLoader、BaseRenderer、LiveRenderer，负责 chunk buffer、脏区与渲染帧产出。 |
| `AOM` | `ActiveObjectManager`。语义上始终属于 Core；P0/P2 阶段可能仍与 UI 同线程运行，但应按 Core 模块设计。 |
| `ObjectSummary` | 跨线程传递的对象摘要，供工具命中、overlay、手势缓存使用；不是 `BasicObject` 实例。 |
| `shadow` / 影子副本 | UI 侧缓存的 `ObjectSummary` 或其派生本地状态，用于 overlay 和手势回退。 |
| `objectId` | 工具长期持有的对象令牌；迁移完成后应替代对象实例引用。 |

### 术语使用规则

1. **看到 `Board.createMonitor()` 时先区分语境**
   - 若是在当前代码库类方法语境中，指 UI 线程 DOM 工厂方法
   - 若是在 `BoardApi` / RPC 契约语境中，指 Worker 侧创建 `MonitorCore`
2. **文中单独写 `Board` 时，默认指 UI façade，而不是 Core 实现**
3. **文中单独写 `BoardCore` 时，默认指未来 Worker 内的纯 Core board 实现**
4. **文中单独写 `Monitor` 时，若涉及 overlay / workflow / DevicesDAG，默认更接近 `MonitorProxy`；若涉及 chunk / base/live renderer，默认更接近 `MonitorCore`**

## Phase 1：共享纯模块验证与类型定义

### 目标

逐一验证每个候选共享模块的实际 import 链，确认无 DOM/Worker/Tauri IPC 依赖。对发现的混合文件做物理拆分或边界标记。创建跨线程类型定义文件。

> **核心原则**：不信任模块清单，逐文件验证。当前表格是静态分析，实际 import 链中可能藏着隐式 DOM/Worker 依赖。

### 1.1 逐文件 import 链审计

从每个候选共享模块出发，递归追踪其 import 链，记录每层依赖。分为三类确认：

#### 第一类：纯数学 / 纯数据结构 — 无需改动

| 模块 | 路径 | import 链终点 | 结论 |
| ---- | ---- | ------------ | ---- |
| `Vector`, `Matrix` | `src/core/utils/math.js` | 0 个内部 import | ✅ 无依赖，纯数学 |
| 纯算法函数 | `src/core/utils/math-algorithm.js` | → `math.js`（纯数学） | ✅ 无外部依赖 |
| 工具链 | `src/core/utils/chain.js` | 0 个内部 import | ✅ 无依赖，纯函数 |
| `Range` 系列 | `src/core/range/` | → `math.js`, 互相引用 | ✅ 纯数学 |
| `render-scheduler.js` | `src/core/components/renderer/render-scheduler.js` | → `range/`（纯数学） | ✅ 无 DOM 依赖 |

#### 第二类：文件内容混合，需拆分或标记边界

`dirty-rect-strategy.js` 是一个文件混了两类函数：

| 函数 | 依赖 | 归属 |
| ---- | ---- | ---- |
| `createLiveDirtyRectThresholdStrategy` | 纯数学 | **共享** |
| `createZoomScaledThresholdStrategy` | 纯数学 | **共享** |
| `createZoomOffsetThresholdStrategy` | 纯数学 | **共享** |
| `createDirtyRectPolicyResolver` | 纯数学 | **共享** |
| `createBaseDirtyRectThresholdStrategy` | 纯数学 | **共享** |
| `createBaseDirtyRectPolicyResolver` | → `createBaseDirtyRectCanonicalRectsResolver`（下一行） | **Core** |
| `createBaseDirtyRectCanonicalRectsResolver` | → `ChunkObjectManager` | **Core** |
| `collectLoadedChunksForWorldRect` | → `ChunkObjectManager` | **Core** |
| `screenRectToWorldRect` | 纯函数 | **共享**（但仅 base 使用，实际共享价值低）|

> **操作**：将共享函数（`createLiveDirtyRectThresholdStrategy` 及其纯依赖链）提取为独立文件 `src/core/components/renderer/dirty-rect-strategy-shared.js`，原文件保留 Core 专属 chunk 依赖。或在本文件中用 JSDoc 显式标记每条函数的归属。

#### 第三类：模块本身可共享，但 import 链带 Core 特有类型

`renderer.js`（Renderer 基类）：

```js
import { BasicObject } from "../../objects/basic-obj.js";    // Core 特有
import { Range } from "../../range/index.js";                // 共享（纯数学）
import { PathRange } from "../../range/path.js";             // 共享（纯数学）
import { RenderScheduler } from "./render-scheduler.js";     // 共享
```

`BasicObject` 的 import 链：
```
basic-obj.js → math.js ✓, range/ ✓   （无任何 DOM/Worker 依赖）
```

所以虽然 `renderer.js` 引用了 Core 侧的对象类型，但**依赖链中不含任何 DOM/Worker API**。`Renderer.resize()` 和 `_getContext()` 操作 `this._canvas`，对 `HTMLCanvasElement` 和 `OffscreenCanvas` 的行为一致。

**结论**：`renderer.js` 可共享，不需要拆分。

### 1.2 创建 `src/core/shared/` 类型定义文件

新增：

```
src/core/shared/
  ├── types.js              # ObjectSummary, RectangleRange 等通用 typedef
  ├── board-api-types.js    # BoardApi 方法签名 typedef
  └── message-types.js      # Worker 消息协议 typedef
```

这些文件**仅含 JSDoc `@typedef`，不含可执行代码**，两侧均可 import 用于 IDE 类型提示。

#### `types.js` 内容大纲

```js
/**
 * @typedef {Object} ObjectSummary
 * @property {number} id
 * @property {string} type - "StrokeObject" | "CircleObject" | "PolygonObject" | ...
 * @property {boolean} isActive - 是否是活动对象
 * @property {import("../../range/rectangle.js").RectangleRange} boundingBox - 外接矩形
 * @property {import("../../range/range.js").Range} range - 主判定范围
 * @property {{x:number, y:number}} position
 * @property {{a:number,b:number,c:number,d:number}|undefined} transform
 * @property {Record<string,any>} property - 属性快照
 * @property {Record<string,any>} data - 类型专属几何数据快照
 */

/**
 * @typedef {Object} Rect
 * @property {number} left
 * @property {number} top
 * @property {number} right
 * @property {number} bottom
 */
```

#### `board-api-types.js` 内容大纲

```js
/**
 * BoardApi 方法签名 typedef。
 * 同时约束同线程实现和 RPC 实现。
 */

/**
 * @typedef {Object} BoardApi
 * @property {(type:string, props:{position:Object, property?:Object, data?:Object}) => Promise<number>} createObject
 * @property {(objectId:number, patch:Object) => Promise<void>} modifyObject
 * @property {(patches:Array<{objectId:number, patch:Object}>) => Promise<void>} modifyObjects
 * @property {(objectId:number, key:string, items:any[]) => Promise<void>} appendListItem
 * @property {(objectId:number, key:string, index:number, item:any) => Promise<void>} replaceListItem
 * @property {(objectId:number, key:string, index:number) => Promise<void>} removeListItem
 * @property {(objectIds:number[]) => Promise<void>} deleteObjects
 * @property {(objectIds:number[]) => Promise<void>} commitObjects
 * @property {(objectIds:number[]) => Promise<ObjectSummary[]>} queryObjects
 * @property {(chunkIds:number[]) => Promise<number[]>} queryChunkObjects
 * @property {(range:Object, mode?:string) => Promise<number[]>} hitTest
 * @property {(objectIds:number[]) => Promise<void>} addActiveObjects
 * @property {(objectIds:number[]) => Promise<void>} discardActiveObjects
 * @property {({monitorId:string, width:number, height:number}) => Promise<void>} createMonitor
 * @property {(monitorId:string) => Promise<void>} destroyMonitor
 */
```

#### `message-types.js` 内容大纲

定义设计文档中列出的消息类型：`WorkerReadyMessage`、`RpcRequest`、`RpcResponse`、`ViewportChangeMessage`、`RequestRenderFlushMessage`、`RenderFrameMessage`、`ObjectChangedMessage`、`MutateListPropertyMessage`。

### 1.3 编写 Node smoke test

新增 `src/core/tests/shared-module-smoke.test.js`：

```js
/**
 * @jest-environment node
 */

describe("Shared module smoke test", () => {
  test("range/* can be imported in Node", () => {
    expect(() => {
      require("../range/index.js");
    }).not.toThrow();
  });

  test("utils/math.js can be imported in Node", () => {
    expect(() => {
      require("../utils/math.js");
    }).not.toThrow();
  });

  test("utils/math-algorithm.js can be imported in Node", () => {
    expect(() => {
      require("../utils/math-algorithm.js");
    }).not.toThrow();
  });

  test("utils/chain.js can be imported in Node", () => {
    expect(() => {
      require("../utils/chain.js");
    }).not.toThrow();
  });

  test("renderer/renderer.js can be imported in Node", () => {
    expect(() => {
      require("../components/renderer/renderer.js");
    }).not.toThrow();
  });
});
```

> **注意**：Jest `node` 环境中 `import` 语句会被转译为 `require`。如果某个模块在 `node` 环境下 import 了 `self`、`window`、`document` 等，会抛出 `ReferenceError`。这个测试就是这个目的——**尽早暴露**隐式 DOM 依赖。

### 1.4 验证现有测试继续通过

P1 不改任何运行时逻辑，但需确认现有测试不受影响：

```bash
npx jest src/core/range/tests/
npx jest src/core/utils/tests/
```

### 1.5 验收标准

- [x] 每个候选共享模块的 import 链已审查完毕，无隐蔽 DOM/Worker/IPC 依赖
- [x] `dirty-rect-strategy.js` 中共享函数与 Core 专属函数边界已标记（或已拆出独立文件）
- [x] `src/core/shared/types.js`、`board-api-types.js`、`message-types.js` 已创建
- [x] Node smoke test 通过：所有共享模块在 `node` 环境可 import 不报错
- [x] 现有 `range/` 和 `utils/` 测试全部通过

### 1.6 交付物清单

| 交付物 | 文件路径 | 说明 |
| ------ | -------- | ---- |
| Import 链审计结果 | 记录在本文档中 | 每个候选共享模块的依赖链已审查 |
| 共享/Core 边界标记 | `dirty-rect-strategy.js` 或拆出的 `-shared.js` | 纯函数标记为共享，Chunk 依赖标记为 Core |
| 类型定义 | `src/core/shared/types.js` | 通用 typedef |
| 类型定义 | `src/core/shared/board-api-types.js` | BoardApi 方法签名 typedef |
| 类型定义 | `src/core/shared/message-types.js` | Worker 消息协议 typedef |
| 测试文件 | `src/core/tests/shared-module-smoke.test.js` | Node 环境 import 验证 |

---

## Phase 2：同线程 `BoardApi` + 工具去对象实例依赖

### 目标

在**不引入 Worker** 的前提下，把工具、AOM、monitor 的交互逐步改成最终 Worker 模式会使用的接口。

> 这一阶段做得越扎实，P3 越轻松。

### 2.1 新增同线程 `BoardApi`

建议新文件：

- `src/core/bridges/board-api.js`

**实现策略**：P2 的同线程 `BoardApi` 直接调用 `BoardCore` 的同步方法实现，不做异步模拟。`createObject()` 返回 `Promise.resolve(id)`（立即完成），`modifyObject()` 等 fire-and-forget 方法直接同步执行。P2 与 P3 之间因 RPC 延迟带来的时序差异问题，留到 P3 落地时一并修复。

> 这个策略的优点是 P2 迁移成本最低（不需要复杂的异步假消息机制），缺点是 P2 测试全绿不代表 P3 后行为完全一致。需在 P3 切入 RPC 版本后对工具层做回归。

### 2.2 `context.acc` 进入兼容双栈阶段

当前：

- `acc.board`
- `acc.monitor`
- `acc.allocateObjectId`
- `acc.resolveOwnerChunkId`

兼容阶段建议变为：

```js
acc.board = board; // 暂保留
acc.boardApi = boardApi; // 新增
acc.monitor = monitor; // 暂保留
```

不要一上来删掉 `board`，否则会同时炸掉：

- `tool.test.js`
- `board-input-flow.test.js`
- `handoff-handler.test.js`
- 大量 creator/modifier/chooser 测试

### 2.3 先迁 creator——先改基类，再逐个迁具体工具

`CircleCreatorTool` 等所有 concrete creator 都继承自 `ObjectCreatorTool`（`object-creator.js`）。基类 `ensureObject()` 集中管理了对象创建生命周期（惰性分配 objectId、`new StrokeObject` / `new CircleObject`、`AOM.add`、渲染同步）。

因此迁移顺序是：**先改基类，再逐个迁具体工具**。

#### 推荐顺序

| 顺序 | 工具                                        | 原因                                                               |
| ---- | ------------------------------------------- | ------------------------------------------------------------------ |
| 1    | `ObjectCreatorTool` / `object-creator.js` 基类 | 必须先改基类的 `ensureObject()`，才能让所有 concrete creator 走 `boardApi` |
| 2    | `CircleCreatorTool`                         | 只有 `position + radius`，基类改完后最容易验证                     |
| 3    | `StrokeCreatorTool`                         | 需要 `appendListItem("points")`，比 circle 稍复杂                  |
| 4    | `PolygonCreatorTool`                        | 需要 `append / replace / remove` 三种 list op                      |

> 这与之前"先迁 CircleCreatorTool"的想法不同。分析实际代码后发现，不先改基类的话，concrete creator 要么覆写 `ensureObject()` 绕过基类（增加后续迁移成本），要么改不动（依赖基类的同步语义）。因此顺序调整为：先改 `ObjectCreatorTool`，再从 `CircleCreatorTool` 开始逐个验证。

### 2.4 creator 改造的真实影响点

#### 当前直接耦合点

**文件**：`src/core/tools/creator/object-creator.js`

当前基类直接做了这些事：

- 惰性 `allocateObjectId`
- `activeObjectManager.add(new Set([this.obj]))`
- `monitor.liveRenderer.captureObjectSnapshot(...)`
- `monitor.liveRenderer.invalidateObjects(...)`
- `monitor.requestViewportUiRender()`

#### 迁移策略

先把 `ObjectCreatorTool` 基类从“操作对象实例 + renderer”改成“调用板级能力”：

- `ensureObject()` → 同步 fire-and-forget 调用 `boardApi.createObject(...)`
- `beforeGeometryMutation()` / `afterGeometryMutation()` → BoardApi 路径跳过 `liveRenderer.*`，由 Core 自动渲染
- `discardCreatedObjects()` → `boardApi.discardActiveObjects([...])`
- `completeCreatedObject()` → `boardApi.commitObjects([...])`

### 2.5 modifier 是 P2 的重头戏

#### 当前问题文件

- `src/core/tools/modifier/object-modifier.js`
- `src/core/tools/modifier/common-object-modifier.js`

当前 modifier 强耦合：

- 直接持有 `BasicObject`
- 直接写 `obj.position`
- 直接调 `monitor.liveRenderer.*`
- `resolveActiveModifiedObjects()` 仍依赖 AOM 活动对象索引
  - **P2 保留为兼容层**：当前实现继续通过活动对象索引过滤上下文对象；P3 若 read-path 全切到 RPC/summary，再评估是否收口或移除。

#### 迁移顺序建议

1. **手势状态机保留不动**
2. **写路径改造**：`boardApi.modifyObject(id, { position })` 替代直接写 `obj.position`
3. **提交/撤销**：`boardApi.commitObjects` / `discardActiveObjects`
4. **读路径**：同步兼容层（`resolveModifiedObjectPosition`、`resolveModifiedObjectWorldRect` 等），不依赖 `queryObjects`
   - `queryObjects(ids)` 异步查询留到 P3.6 做
   - P2 阶段用同步兼容层处理 summary-like 对象

#### 当前状态 ✅

- 写路径 BoardApi-first：✅
- 提交/撤销 BoardApi-first：✅
- 同步兼容层允许 summary-like 对象正常工作：✅
- `async queryObjects()` 异步读取 → **P3**

### 2.6 chooser 要先换查询方式，再换 overlay 方式

#### 当前文件

- `src/core/tools/chooser/object-chooser.js`
- `src/core/tools/chooser/rectangle-object-chooser.js`

当前选择逻辑：

- 直接扫描 `board.activeObjectManager.activeObjectIndex` 迭代所有活动对象
- 再用 `objectIntersectsSelectionRange(...)` 做命中判定（见 `rectangle-object-chooser.js:131`）
- 再用 `objectIntersectsSelectionRange(...)` 做命中

#### 迁移策略

1. 先把“选中集合”来源改成 `boardApi.queryObjects()` / `boardApi.hitTest()`
2. 暂时保留 chooser 自己的手势状态与 overlay provider
3. 等 summary 驱动的 overlay 跑通后，再移除对象实例依赖

### 2.7 Ui overlay 不要硬切，先做 summary 兼容 API

#### 当前文件

- `src/core/components/renderer/ui-renderer.js`

当前所有工具都依赖：

```js
renderer.createCompatSelectionEntriesForObjects(objects, role);
```

结合现有仓库，**更稳的做法**不是马上删掉这个 API，而是先新增一个平行入口：

```js
renderer.createCompatSelectionEntriesForSummaries(summaries, role);
```

或者让 `normalizeOverlayEntry()` 支持：

- `objectId`
- `boundingBox`
- `worldRect`
- `position`
- `transform`

这样可以让：

- 老工具继续走 `...ForObjects(...)`
- 新工具逐步切到 summary 版本

| 测试文件                                             | 原因                                          |
| ---------------------------------------------------- | --------------------------------------------- |
| `src/core/tools/tests/tool.test.js`                  | `createDeviceContext()` / `createProcessor()` |
| `src/core/components/tests/board-input-flow.test.js` | `acc.board` / `acc.monitor` 注入路径          |
| `src/core/prefixs/tests/handoff-handler.test.js`     | handoff 过程中对象上下文与 AOM 语义           |
| `src/core/tools/creator/tests/*.test.js`             | creator 生命周期                              | ✅ 已迁移（42 tests / 0 failed） |
| `src/core/tools/modifier/tests/*.test.js`            | modifier 手势状态机                           | ✅ 已迁移（40 tests / 0 failed） |
| `src/core/tools/chooser/tests/*.test.js`             | chooser / rectangle chooser                | ✅ 已迁移（18 tests / 0 failed） |

### 2.8 验收标准

- [x] `boardApi` 已接入 `context.acc`
- [x] Creator Family 已通过 BoardApi 跑通
- [x] `CommonObjectModifierTool` 已完成 BoardApi 写路径 + 同步兼容层
- [ ] `RectangleObjectChooserTool` 已不再直接扫描 `board.activeObjectManager.activeObjectIndex`（注：当前 Chooser 已迁到 BoardApi 写路径，但读路径(`collectSelectableObjects`)仍通过同步兼容层扫描 AOM 活动对象索引；完全脱离对象实例直连留待 P3）
- [x] Creator + Modifier BoardApi 路径已跳过 `liveRenderer.*`（仅保留 overlay 刷新）

---

## Phase 3：Worker 落地与 Proxy 拆分

### 目标

把 P2 已经接口化的能力真正搬进 Worker。P3 内部拆为 **6 个子步骤**，按依赖顺序执行。

```
P3.1 DAG async 保护  ──►  P3.2 core-worker.js 入口
                              │
                              ▼
                       P3.3 MonitorCore / MonitorProxy 拆分
                              │
                              ▼
                       P3.4 board-api.js 切 RPC 版本
                              │
                              ▼
                       P3.5 渲染器 OffscreenCanvas 验证
                              │
                              ▼
                       P3.6 工具 async 适配（分三波：A ✅ / B ✅ / C ✅）
```

---

### 3.1 DAG dispatch async 保护

#### 背景

P3 切 RPC 后，**只有需要 read-RPC 的工具路径**（如 chooser 的 `hitTest/queryObjects`、modifier 的读取型查询）才可能让 `process()` 或其内部步骤变为 `async`。Creator 仍应保持 sync fire-and-forget。DAG dispatcher 当前是同步调度，不会 `await` 末端工具的返回值。对于末端工具节点这不影响路由正确性——工具不转发信号到下游。但 `process()` 内抛出的 Promise rejection（如 RPC timeout）将无人捕获。

#### 实现步骤

**文件**：`src/core/devices-dag/dag.js`

在 `_walkSegments()` 方法中，当前 handler 调用为：

```js
const result = handler
  ? normalizeHandlerResult(handler(currentPacket, handlerContext))
  : { packets: [new SignalPacket("", currentPacket.signals)] };
```

改为分步处理：

```js
// 1. 调用 handler，捕获同步异常
let rawResult;
try {
  rawResult = handler
    ? handler(currentPacket, handlerContext)
    : undefined;
} catch (syncErr) {
  console.error(
    `[DevicesDAG] Handler error at "${childPath}":`,
    syncErr,
  );
  rawResult = undefined;
}

// 2. 若返回值为 Promise，仅 catch rejection，不 await 结果
//    工具 fire-and-forget 路径的 Promise 由工具自行管理。
if (rawResult instanceof Promise) {
  rawResult.catch((asyncErr) =>
    console.error(
      `[DevicesDAG] Async handler rejection at "${childPath}":`,
      asyncErr,
    ),
  );
  // 当前不支持 async 返回值参与路由决策，视为 handler 无显式输出
  rawResult = undefined;
}

// 3. 规整结果
const result =
  rawResult !== undefined
    ? normalizeHandlerResult(rawResult)
    : { packets: [new SignalPacket("", currentPacket.signals)] };
```

**关键设计决策**：

- **不 await**：对于 sync fire-and-forget 路径（creator），Promise 由工具自行管理，DAG 不阻塞路由。
- **仅 catch**：防止 unhandled rejection 导致全局崩溃。
- **视 async 返回为无输出**：当前不支持 async 返回值参与路由决策（redirect/stop/packets），留待 P3.6 按需扩展。

**验收**：
- [x] DAG 同步路由行为不变
- [x] handler 抛出同步异常时不阻塞 DAG（日志记录继续）
- [x] handler 返回 Promise rejection 时被 `.catch()` 捕获

后续 P3.6 所有 read-RPC 路径的 async 改造都依赖此基础。

---

### 3.2 core-worker.js 入口

#### 背景

Worker 入口文件 `src/core-worker.js` 是整个 Worker 线程的 bootstrap。它只 import 纯 Core 模块，不碰任何 DOM/DevicesDAG/signalsEventBus/boardFileOperateBridge。使用 `{ type: "module" }` 选项创建，与现有 Tauri 无打包架构一致。

#### 实现步骤

**新建文件**：`src/core-worker.js`

##### 3.2.1 模块 Import

当前实现的 `core-worker.js` 直接 import：

```js
import { BoardApi } from "./core/bridges/board-api.js";
import { createDefaultPersistenceAdapter } from "./core/bridges/persistence-adapter.js";
import { createDefaultAomRenderHooks } from "./core/components/orchestration/aom-render-hooks.js";
import { BoardCore } from "./core/components/orchestration/board-core.js";
import { MonitorCore } from "./core/components/orchestration/monitor-core.js";
import { Logger } from "./utils/log/logger.js";
import { logBus } from "./utils/log/log-bus.js";
```

**注意**：当前实现没有额外 new 一个 `workerLogBus`。`core-worker.js` 直接 import `logBus`，但它运行在 Worker 自己的模块图中，因此与 UI 线程的 `logBus` 实例天然隔离。

##### 3.2.2 运行时状态

当前 Worker 入口不是一组模块级函数，而是 `CoreWorkerRuntime` 类：

```js
class CoreWorkerRuntime {
  #host;
  #boardCore;
  #boardApi;
  #monitorCores;
  #messageListener;
  #log;
  #offWorkerLogs;
  #started;
}
```

其中：

- `#boardCore`：当前 Worker 内唯一的 `BoardCore`
- `#boardApi`：包裹 `BoardCore` 的 Worker 内 `BoardApi`
- `#monitorCores`：`monitorId -> MonitorCore` 注册表
- `#offWorkerLogs`：`logBus.onLevels(...)` 的取消函数

##### 3.2.3 ready 握手

Worker runtime `start()` 后立即发送 ready：

```js
this.#postMessage({ type: "ready" });
```

UI 侧 `Board.enableWorkerMode(worker)` 会先 `waitUntilReady()`，再发送 `createBoard` RPC。

##### 3.2.4 消息分发入口

当前实现仍保留三类主消息入口：

```js
switch (message.type) {
  case "rpc":
    this.#handleRpcMessage(message);
    return;
  case "viewport-change":
    this.#handleViewportChange(message);
    return;
  case "request-render-flush":
    this.#handleRenderFlush(message);
    return;
}
```

其中：

- `rpc`：Board API / createBoard / destroyBoard / createMonitor / destroyMonitor
- `viewport-change`：转发给对应 `MonitorCore.onViewportChange(...)`
- `request-render-flush`：驱动 `MonitorCore.flushRenderFrame()` 产出位图帧

##### 3.2.5 RPC 分发

当前实现通过 `#handleRpcMessage()` 统一捕获同步异常与 Promise rejection，并回传 `rpc-response`：

```js
#handleRpcMessage(message) {
  const result = this.#dispatchRpc(method, params);
  if (result instanceof Promise) {
    result.then((value) => this.#postMessage({
      type: "rpc-response",
      msgId,
      result: value,
    })).catch((error) => this.#postMessage({
      type: "rpc-response",
      msgId,
      error: {
        code: error?.code ?? "INTERNAL_ERROR",
        message: error?.message ?? String(error),
      },
    }));
    return;
  }

  this.#postMessage({ type: "rpc-response", msgId, result });
}
```

##### 3.2.6 RPC 方法路由（当前实现）

当前 `#dispatchRpc()` 将方法分成两层：

1. runtime 自己处理的生命周期方法
2. 交给 Worker 内 `BoardApi` 的对象类方法

```js
#dispatchRpc(method, params) {
  switch (method) {
    case "createBoard":
      return this.createBoard(params);
    case "destroyBoard":
      return this.destroyBoard();
    case "createMonitor":
      return this.createMonitor(params.options);
    case "destroyMonitor":
      return this.destroyMonitor(params.monitorId);
    default:
      return this.#dispatchBoardApiMethod(method, params);
  }
}
```

而 `#dispatchBoardApiMethod(...)` 再把 `createObject / modifyObject / appendListItem / queryObjects / hitTest / undo / redo` 等转发到 Worker 内部的 `BoardApi`。

##### 3.2.7 BoardApi 与 renderHooks 的当前实现

当前 Worker 侧**保留了一个 Worker 内 `BoardApi` 实例**，而不是把所有对象 API 手写成一组 `createObjectOnCore()` / `modifyObjectOnCore()` 函数。这么做的好处是：

- 复用同线程 `BoardApi` 已有的对象创建 / 修改 / 查询逻辑
- `core-worker.js` 只负责 runtime 生命周期、消息分发与 MonitorCore 管理
- `BoardApiRpc` / `BoardApi` / `CoreWorkerRuntime` 三层职责更清晰

`createBoard()` 的当前行为：

```js
createBoard(options = {}) {
  this.#boardCore = new BoardCore({
    width: options.width,
    height: options.height,
    rootPath: options.rootPath,
    persistenceAdapter: createDefaultPersistenceAdapter(),
    aomRenderHooks: createDefaultAomRenderHooks(),
  });
  this.#boardApi = new BoardApi(this.#boardCore);

  const renderHooks = this.#createMonitorRenderHooks();
  this.#boardCore.aomRenderHooks = renderHooks;
  this.#boardCore.activeObjectManager.renderHooks = renderHooks;

  return { ok: true };
}
```

**关键差异 vs 同线程 BoardApi**：

| 项目 | 同线程 BoardApi（P2） | Worker 当前实现（P3） |
|------|----------------------|------------------------|
| BoardCore 引用 | `this.#boardCore` | `CoreWorkerRuntime.#boardCore` + Worker 内 `BoardApi` |
| Monitor 生命周期 | 无 | `CoreWorkerRuntime` 直接管理 `MonitorCore` Map |
| renderHooks | UI 侧注入真实 renderHooks | `createBoard()` 后改写为 `#createMonitorRenderHooks()` |
| persistenceAdapter | UI renderer bridge / memory mode | Worker 默认 `createDefaultPersistenceAdapter()`，文件 IO host 待 P4 |
| 返回值 | `Promise.resolve(value)`（伪异步） | 由 runtime 包成 `rpc-response` |

##### 3.2.8 `createBoard` 生命周期

`createBoard` 是 Worker 收到的第一个 RPC。它创建 `BoardCore` 实例并返回 `{ ok: true }`。

初始化时序（按当前实现）：

```
1. UI 线程：new Worker('core-worker.js', { type: "module" })
2. UI 线程：await board.enableWorkerMode(worker)
3. Core 线程：加载模块，runtime.start() → postMessage({ type: "ready" })
4. UI 收到 ready，BoardApiRpc 发送 createBoard RPC
5. Core 创建 BoardCore + Worker 内 BoardApi，并安装 monitor-aware renderHooks
6. UI 调用 board.createMonitor(...)
7. Board.createMonitor 在 Worker mode 下创建 MonitorProxy，并发送 createMonitor RPC
8. Core 创建 MonitorCore，写入 monitorCores Map
9. createMonitor RPC resolve 后，MonitorProxy.startWorkerSync()
10. MonitorProxy 发送首个 viewport-change，并启动持续 request-render-flush 循环
11. Core 首次 flushRenderFrame() → render-frame
12. UI drawImage(base/live) 后白板可见
```

**验收**：
- [x] `core-worker.js` 在浏览器 / 测试环境中可正常实例化 runtime
- [x] Worker 启动后立即发送 `{ type: "ready" }`
- [x] `createBoard` RPC 创建 BoardCore 实例成功
- [x] `createObject` RPC 创建对象成功，返回 objectId
- [x] Worker 中 Logger 使用 Worker 模块图内独立的 `logBus` 实例（不与 UI 线程共享）

---

### 3.3 MonitorCore / MonitorProxy 拆分

#### 背景

这是 P3 中**工程量最大**的子步骤。当前 `monitor.js` 同时包含视口管理（UI）、区块加载（Core）、三层渲染器（UI+Core），需要拆为：

- **MonitorCore**（Worker 侧）：chunkLoader、BaseRenderer（OffscreenCanvas）、LiveRenderer（OffscreenCanvas）、chunk buffer、渲染帧产出
- **MonitorProxy**（UI 侧）：视口状态副本、UiRenderer、overlay provider、workflow 挂载、接收并合成 Core 传来的 ImageBitmap

#### MonitorCore 实现步骤

**新建文件**：`src/core/components/orchestration/monitor-core.js`

##### 3.3.1 类结构

```js
class MonitorCore {
  #boardCore;         // BoardCore 引用
  #monitorId;         // 显示器 id
  #chunkLoader;       // ChunkLoader
  #baseRenderer;      // BaseRenderer（OffscreenCanvas）
  #liveRenderer;      // LiveRenderer（OffscreenCanvas）
  #origin;            // 视口原点
  #zoom;              // 缩放因子
  #width;             // 视口宽度
  #height;            // 视口高度
  #lastBaseBitmap;    // 上一帧 base bitmap（帧复用）
  #lastLiveBitmap;    // 上一帧 live bitmap（帧复用）
  #frameId;           // 帧序号

  constructor({ boardCore, monitorId, width, height }) {
    this.#boardCore = boardCore;
    this.#monitorId = monitorId;
    this.#width = width;
    this.#height = height;
    this.#zoom = 1;
    this.#origin = new Vector(0, 0);
    this.#frameId = 0;

    // 创建 ChunkLoader
    this.#chunkLoader = boardCore.createChunkLoader(`monitor-${monitorId}`);

    // 创建 OffscreenCanvas 渲染器
    const baseCanvas = new OffscreenCanvas(width, height);
    const liveCanvas = new OffscreenCanvas(width, height);

    this.#baseRenderer = new BaseRenderer(this, { canvas: baseCanvas });
    this.#liveRenderer = new LiveRenderer(
      this, boardCore.activeObjectManager, { canvas: liveCanvas });
  }

  // 视口变更处理
  onViewportChange({ origin, zoom }) { ... }

  // 渲染帧产出
  flushRenderFrame() { ... }

  // 同步 chunk buffer
  #syncChunkBuffer() { ... }

  // resize
  resize(width, height) { ... }

  // 销毁
  destroy() { ... }
}
```

##### 3.3.2 `onViewportChange({ origin, zoom })`

```js
onViewportChange({ origin, zoom }) {
  const prevOrigin = this.#origin;
  const prevZoom = this.#zoom;

  this.#origin = origin instanceof Vector
    ? origin
    : new Vector(origin?.x ?? 0, origin?.y ?? 0);
  this.#zoom = typeof zoom === "number" ? zoom : this.#zoom;

  // 仅视口真正变化时才触发
  if (
    this.#origin.x === prevOrigin.x &&
    this.#origin.y === prevOrigin.y &&
    this.#zoom === prevZoom
  ) return;

  // 同步 chunk buffer
  this.#syncChunkBuffer();

  // 全视口脏区
  this.#baseRenderer.invalidateViewport();
  this.#liveRenderer.invalidateViewport();
}
```

##### 3.3.3 `flushRenderFrame()`

```js
flushRenderFrame() {
  // 从 OffscreenCanvas 提取 ImageBitmap
  const baseBitmap = this.#baseRenderer.canvas.transferToImageBitmap();
  const liveBitmap = this.#liveRenderer.canvas.transferToImageBitmap();

  const frameId = ++this.#frameId;

  self.postMessage(
    {
      type: "render-frame",
      monitorId: this.#monitorId,
      frameId,
      baseBitmap,
      liveBitmap,
    },
    [baseBitmap, liveBitmap],  // 转移所有权
  );

  // 保存引用供帧复用（P4）
  this.#lastBaseBitmap?.close();
  this.#lastLiveBitmap?.close();
  // P4 才做帧复用，P3 先每帧都传
}
```

**关键点**：

- `transferToImageBitmap()` 每次调用创建新的 ImageBitmap（GPU 拷贝），传输本身零拷贝（所有权转移）
- `[baseBitmap, liveBitmap]` 作为第二个参数传给 `postMessage` 实现 Transferable 零拷贝
- Worker 中没有 `requestAnimationFrame`，渲染由 UI 侧的 `request-render-flush` 消息驱动

##### 3.3.4 视口坐标系

MonitorCore 需要保留 UI 侧相同的坐标系方法（纯数学，与 DOM 无关）：

```js
screenPointToWorld(screenPoint, origin = this.#origin, zoom = this.#zoom) { ... }
worldRectToScreenRect(worldRect) { ... }
getViewportScreenRect() { ... }
worldToChunk(worldPoint) { ... }
```

这些方法的实现从 `monitor.js` 复制，去掉 DOM 依赖即可。

#### MonitorProxy 实现步骤

**新建文件**：`src/core/components/orchestration/monitor-proxy.js`

##### 3.3.5 类结构

```js
class MonitorProxy {
  #board;          // UI Board façade
  #monitorId;      // 显示器 id
  #worker;         // Worker 引用
  #origin;         // 视口原点本地副本
  #zoom;           // 缩放因子本地副本
  #width;          // 视口宽度
  #height;         // 视口高度
  #baseCanvas;     // DOM canvas（显示 base 层）
  #liveCanvas;     // DOM canvas（显示 live 层）
  #uiRenderer;     // UiRenderer（uiCanvas）
  #baseCtx;        // baseCanvas 2D context
  #liveCtx;        // liveCanvas 2D context
  #pendingRafId;   // rAF 节流 id

  constructor({ baseCanvas, liveCanvas, uiCanvas, worker, board, monitorId, width, height }) {
    this.#board = board;
    this.#monitorId = monitorId;
    this.#worker = worker;
    this.#width = width;
    this.#height = height;
    this.#zoom = 1;
    this.#origin = new Vector(0, 0);

    this.#baseCanvas = baseCanvas;
    this.#liveCanvas = liveCanvas;
    this.#baseCtx = baseCanvas.getContext("2d");
    this.#liveCtx = liveCanvas.getContext("2d");
    this.#uiRenderer = new UiRenderer(this, null, { canvas: uiCanvas });
  }

  // 视口属性 getter
  get zoom() { return this.#zoom; }
  get origin() { return this.#origin; }

  // 坐标变换（委托到本地计算）
  screenPointToWorld(screenPoint) { ... }
  worldRectToScreenRect(worldRect) { ... }

  // 视口变更 → rAF 节流发送
  setViewportState({ origin, zoom }) {
    if (origin != null) this.#origin = origin instanceof Vector ? origin : new Vector(origin.x, origin.y);
    if (zoom != null) this.#zoom = zoom;

    cancelAnimationFrame(this.#pendingRafId);
    this.#pendingRafId = requestAnimationFrame(() => {
      this.#worker.postMessage({
        type: "viewport-change",
        monitorId: this.#monitorId,
        origin: { x: this.#origin.x, y: this.#origin.y },
        zoom: this.#zoom,
      });
    });
  }

  // 接收 render-frame → 合成到 DOM canvas
  onRenderFrame({ baseBitmap, liveBitmap }) {
    if (baseBitmap) {
      this.#baseCtx.drawImage(baseBitmap, 0, 0);
      baseBitmap.close();
    }
    if (liveBitmap) {
      this.#liveCtx.drawImage(liveBitmap, 0, 0);
      liveBitmap.close();
    }
    // UI overlay 由 UiRenderer 自管理
    this.#uiRenderer.invalidateViewport();
  }

  // Overlay provider 注册（委托 UiRenderer）
  registerUiOverlayProvider(provider, options) {
    return this.#uiRenderer.registerOverlayProvider?.(provider) ?? false;
  }
  unregisterUiOverlayProvider(provider, options) {
    return this.#uiRenderer.unregisterOverlayProvider?.(provider) ?? false;
  }

  // Workflow 挂载（委托 Board façade）
  mountWorkflow(path, workflow) {
    return this.#board.devicesDAG.mountWorkflow(path, workflow);
  }
  unmountWorkflow(path, context) {
    return this.#board.devicesDAG.unmountWorkflow(path, context);
  }

  // 生命周期
  destroy() {
    cancelAnimationFrame(this.#pendingRafId);
    this.#baseCtx?.clearRect(0, 0, this.#width, this.#height);
    this.#liveCtx?.clearRect(0, 0, this.#width, this.#height);
  }
}
```

> **当前实现补充**：`MonitorProxy` 另外实现了 `startWorkerSync()`。该方法会在 `createMonitor` RPC resolve 后启动首个 `viewport-change` 同步，并持续发送 `request-render-flush`，以驱动 Worker 侧 `flushRenderFrame()`。

##### 3.3.6 通信通道

| 通道 | 方向 | 触发 |
|------|------|------|
| `viewport-change` | MonitorProxy → Worker | rAF 节流，origin/zoom 变更时 |
| `request-render-flush` | MonitorProxy → Worker | 每帧 `requestAnimationFrame` |
| `render-frame` | Worker → MonitorProxy | `flushRenderFrame()` 完成后 |

##### 3.3.7 与现有 `monitor.js` 的共存策略

P3 期间不删除 `monitor.js`。新增 `MonitorProxy` / `MonitorCore` 后：

- **UI 侧**：`Board.createMonitor()` 根据配置决定创建旧 `Monitor` 还是新 `MonitorProxy`
- **Worker 侧**：`createMonitor` RPC 创建 `MonitorCore`

两套可并行运行，通过 feature flag 切换：

```js
// board.js
createMonitor(rootElement, { width, height }, monitorId) {
  if (this.#useWorker) {
    return new MonitorProxy({ ... });
  }
  return new Monitor({ ... });
}
```

**验收**：
- [x] `MonitorCore` 能在 Worker 中创建（`new OffscreenCanvas` 不报错）
- [x] `MonitorCore.flushRenderFrame()` 返回 ImageBitmap
- [x] `MonitorProxy` 能接收并合成 `render-frame`
- [x] 视口变更时 rAF 节流发送 `viewport-change`
- [x] `MonitorProxy` 保留完整坐标变换接口（`screenPointToWorld` 等）

---

### 3.4 board-api.js 切 RPC 版本

#### 背景

P2 的 `board-api.js` 是同线程同步实现（直接调用 `BoardCore`）。P3 需要增加 RPC 版本，通过 `postMessage` 与 Worker 通信，使所有方法变为真正的异步调用。

#### 实现步骤

##### 3.4.1 新增 RPC BoardApi 类

**文件**：`src/core/bridges/board-api.js`（在现有文件中增加新类）

```js
/**
 * BoardApi RPC 版本（P3）
 * @description 通过 postMessage 与 Worker 中的 BoardCore 通信。
 *   方法签名与同线程 BoardApi 完全一致，但所有调用变为真正的异步。
 */
class BoardApiRpc {
  #worker;
  #pending;
  #timeoutMs;

  constructor(worker, { timeoutMs = 5000 } = {}) {
    this.#worker = worker;
    this.#pending = new Map();
    this.#timeoutMs = timeoutMs;

    // 监听 Worker 的 rpc-response
    this.#worker.addEventListener("message", this.#onWorkerMessage.bind(this));
  }

  #onWorkerMessage(event) {
    const msg = event.data;
    if (msg.type !== "rpc-response") return;
    const pending = this.#pending.get(msg.msgId);
    if (!pending) return;

    clearTimeout(pending.timer);
    this.#pending.delete(msg.msgId);

    if (msg.error) {
      pending.reject(new Error(msg.error.message));
    } else {
      pending.resolve(msg.result);
    }
  }

  async #call(method, params = {}) {
    const msgId = crypto.randomUUID();
    this.#worker.postMessage({ type: "rpc", msgId, method, params });

    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.#pending.delete(msgId);
        reject(new Error(`RPC timeout: ${method}`));
      }, this.#timeoutMs);
      this.#pending.set(msgId, { resolve, reject, timer });
    });
  }

  // --- 所有 BoardApi 方法都通过 #call 转发 ---
  async createObject(type, props) {
    return this.#call("createObject", { type, props });
  }
  async modifyObject(objectId, patch) {
    return this.#call("modifyObject", { objectId, patch });
  }
  async modifyObjects(patches) {
    return this.#call("modifyObjects", { patches });
  }
  async appendListItem(objectId, key, items) {
    return this.#call("appendListItem", { objectId, key, items });
  }
  async replaceListItem(objectId, key, index, item) {
    return this.#call("replaceListItem", { objectId, key, index, item });
  }
  async removeListItem(objectId, key, index) {
    return this.#call("removeListItem", { objectId, key, index });
  }
  async deleteObjects(objectIds) {
    return this.#call("deleteObjects", { objectIds });
  }
  async commitObjects(objectIds) {
    return this.#call("commitObjects", { objectIds });
  }
  async queryObjects(ids) {
    return this.#call("queryObjects", { ids });
  }
  async queryChunkObjects(chunkIds) {
    return this.#call("queryChunkObjects", { chunkIds });
  }
  async hitTest(range, mode) {
    return this.#call("hitTest", { range, mode });
  }
  async addActiveObjects(objectIds) {
    return this.#call("addActiveObjects", { objectIds });
  }
  async discardActiveObjects(objectIds) {
    return this.#call("discardActiveObjects", { objectIds });
  }
  async createMonitor(options) {
    return this.#call("createMonitor", { options });
  }
  async destroyMonitor(monitorId) {
    return this.#call("destroyMonitor", { monitorId });
  }

  // 销毁
  destroy() {
    this.#worker.removeEventListener("message", this.#onWorkerMessage);
    for (const [msgId, pending] of this.#pending) {
      clearTimeout(pending.timer);
      pending.reject(new Error("BoardApi destroyed"));
    }
    this.#pending.clear();
  }
}
```

##### 3.4.2 与现有 BoardApi 共存

```js
// board-api.js 导出两个版本
export { BoardApi };       // P2 同线程版本
export { BoardApiRpc };    // P3 RPC 版本
```

当前选择逻辑不是在 `Board` 构造函数里静态判断，而是通过显式启用 Worker 模式：

```js
// board.js
const board = new Board({ width, height });
const worker = new Worker(new URL("../../core-worker.js", import.meta.url), {
  type: "module",
});

await board.enableWorkerMode(worker, { timeoutMs: 5000 });
const monitor = board.createMonitor(rootElement, { width, height }, "main");
```

也就是说：

- 默认仍是同线程 `BoardApi`
- 只有调用 `enableWorkerMode(worker)` 后，`Board` 才切到 `BoardApiRpc`
- `createMonitor()` 在 Worker mode 下返回 `MonitorProxy`，并在后台触发 `createMonitor` RPC

##### 3.4.3 RPC 版本的关键差异

| 项目 | 同线程 BoardApi | BoardApiRpc |
|------|----------------|-------------|
| 延迟 | < 0.5ms（直接调用） | 1-3ms（postMessage + 序列化 + 事件循环） |
| `createObject` 返回值 | `Promise.resolve(id)` | 真正的异步 Promise |
| `modifyObject` 返回值 | 同步执行，`Promise.resolve()` | 真正的异步 Promise |
| fire-and-forget 路径 | 无需 await | 可以不 await（DAG 已加 rejection 保护） |
| 序列化 | 无（直接引用传递） | 结构化克隆（structured clone） |
| 超时处理 | 无 | 5s 超时 reject |
| `getBoardCore()` | 返回 `BoardCore` 实例 | **不可用**——Core 在 Worker 中 |

**验收**：
- [x] `BoardApiRpc` 所有已落地方法与 Worker RPC 正常通信
- [x] `queryObjects` / `hitTest` 在当前已实现路径上返回正确结果
- [x] RPC 超时正确 reject
- [x] `destroy()` 清理所有 pending 请求

---

### 3.5 渲染器 OffscreenCanvas 验证

#### 背景

P2 已确认 `Renderer` 基类的 `resize()` 和 `_getContext()` 对 `HTMLCanvasElement` 和 `OffscreenCanvas` 行为一致。P3 需要在真实 Worker 环境中验证 BaseRenderer / LiveRenderer 可正常工作。

#### 实现步骤

##### 3.5.1 BaseRenderer OffscreenCanvas 验证

当前 `BaseRenderer` 构造接收 `{ canvas }` 选项：

```js
this.#baseRenderer = new BaseRenderer(this, {
  canvas: new OffscreenCanvas(width, height),
});
```

验证点：
- `canvas.getContext("2d")` 返回 `OffscreenCanvasRenderingContext2D`（而非 `CanvasRenderingContext2D`）
- `canvas.width` / `canvas.height` 赋值行为一致
- RenderScheduler 的 `invalidate` / `flush` 链在 Worker 中正常（scheduler 注入方式不变）

##### 3.5.2 LiveRenderer OffscreenCanvas 验证

`LiveRenderer` 额外依赖 `ActiveObjectManager`：

```js
this.#liveRenderer = new LiveRenderer(
  this,
  boardCore.activeObjectManager,
  { canvas: new OffscreenCanvas(width, height) },
);
```

验证点：
- AOM 的 `requestLiveRender` hook 可正确触发 LiveRenderer 脏区
- LiveRenderer 的绘制循环（遍历 AOM 活动对象，调用 `BasicObject.render(ctx)`）在 OffscreenCanvas 上正常

##### 3.5.3 Dirty rect strategy 在 Worker 中的行为

`dirty-rect-strategy-shared.js` 的纯函数在 Worker 中直接可用。但 `createBaseDirtyRectCanonicalRectsResolver` 依赖 `ChunkObjectManager`（Core 侧），需确认在 Worker 中 import 路径正确（已在 P1 smoke test 中验证）。

##### 3.5.4 渲染帧驱动模式

Worker 中无 `requestAnimationFrame`，渲染帧由 UI 驱动：

```
UI 侧每帧:
  requestAnimationFrame(() => {
    worker.postMessage({ type: "request-render-flush" });
  });

Worker 接收后:
  onRenderFlush() {
    monitorCore.flushRenderFrame();  // 产出 base/live ImageBitmap
  }
```

**验收**：
- [x] `new OffscreenCanvas(w, h)` 在 Worker 中可用
- [x] `OffscreenCanvas.getContext("2d")` 返回有效上下文
- [x] BaseRenderer 在 OffscreenCanvas 上正确绘制静态图对象
- [x] LiveRenderer 在 OffscreenCanvas 上正确绘制 AOM 活动对象
- [x] `transferToImageBitmap()` 返回的 ImageBitmap 可在 UI 侧 `drawImage`

---

### 3.6 工具 async 适配（分两波）

#### 背景

P2 所有工具的写路径已走 fire-and-forget（不 await BoardApi）。P3 切 RPC 后，**读路径**需要适配。

实际代码分析后发现，只需 `RectangleObjectChooserTool` 的手势结束读路径做真正的 async RPC；Modifier 已通过同步兼容层适配 summary-like 对象，不需要 await。更大隐患是 **Worker mode 下误读本地 stale board compat 状态**：`Board` 在 Worker mode 下仍保留本地空的 `BoardCore`，直接回退到 `board.getObjectById()` / `board.activeObjectManager.activeObjectIndex` 会产生静默错误。

因此 3.6 拆为两波：

| 子任务 | 完成状态 | 内容 |
|--------|---------|------|
| **P3.6-A** | ✅ 已完成 | Chooser async read-path + RPC 模式禁用 stale board fallback + async-safe handoff |
| **P3.6-B** | ✅ 已完成 | Creator Worker 兼容（local draft 对象，worker-first 设计） |
| **P3.6-C** | ✅ 已完成 | 修复 Worker 渲染叠帧、force 转发、选中对象级失效（2026-07-02） |

---

#### 3.6-A 完成内容（2026-07-02）

##### 基础设施

**文件**：`src/core/tools/tool.js`

新增 `canUseLegacyBoardCompat(context)`，统一区分同线程 `BoardApi`（有 `getBoardCore`）与 Worker `BoardApiRpc`（无 `getBoardCore`）。

##### Chooser async read-path

**文件**：`src/core/tools/chooser/rectangle-object-chooser.js`

`selectObjectsInWorldRect(context, worldRect)` 在 RPC 路径下改为：

```
boardApi.hitTest(normalizedSelectionRect, "intersect")  →  boardApi.queryObjects(objectIds)
```

同步路径不变。`process()` 仅在 RPC 路径返回 Promise，同步路径保持原状。

**文件**：`src/core/tools/chooser/object-chooser.js`

`resolveSelectedObjectReference()` 在 RPC 模式下不再回退到本地 `board.getObjectById()`，直接返回 summary 原值。

##### Modifier RPC fallback 修正

**文件**：`src/core/tools/modifier/object-modifier.js`

`resolveActiveModifiedObjects()` 在 RPC 模式下不再误读本地空的 `board.activeObjectManager.activeObjectIndex`，直接信任 `boardApi` 侧的筛选。

##### Async-safe handoff

**文件**：`src/core/prefixs/handoff-handler.js`

- `wrapChooserForHandoff()` 改为 async-safe
- lifecycle wrapper 抽为统一 helper `finalizeLifecycleWrappedResult`
- modifier cancel 路径优先走 `boardApi.discardActiveObjects(...)`

##### 测试覆盖

| 测试文件 | 新增内容 |
|----------|----------|
| `chooser/tests/object-chooser.test.js` | RPC boardApi 下不回填 stale board 对象 |
| `chooser/tests/rectangle-object-chooser.test.js` | RPC boardApi 下走 hitTest/queryObjects 异步框选 |
| `modifier/tests/common-object-modifier.test.js` | RPC boardApi 下不误读本地空 AOM |
| `prefixs/tests/handoff-handler.test.js` | async chooser 的 afterConfirm 仍可触发 phase 切换 |

侧记：`queryActiveObjectIds()` 当前未实现——目前唯一的矩形框选工具直接走 `hitTest` 遍历 `boardCore.objectLoaded`，无需先拉 AOM 列表。

**验收**：
- [x] Chooser 通过 `hitTest` RPC 获取命中结果
- [x] Chooser 通过 `queryObjects` RPC 获取选中对象摘要
- [x] RPC 模式下 `resolveSelectedObjectReference` 不回填本地 stale board
- [x] Modifier 的 `resolveActiveModifiedObjects` 在 RPC 模式下不误读空 AOM
- [x] DAG dispatch 不因工具 `process()` 返回 Promise 而崩溃
- [x] Sync fire-and-forget 路径（creator）不因 async 化受干扰

---

#### 3.6-B 已实现（Creator Worker-first 本地草稿）

Creator 当前问题：

- `StrokeCreatorTool.appendPathPoint()` / `CircleCreatorTool.setRadius()` / `PolygonCreatorTool.appendPoint()` 等依赖 `this.obj` 真实 `BasicObject` 实例
- `object-creator.js` 的 `createObjectThroughBoardApi()` 在 `BoardApiRpc` 下 **不 await**，但立刻调用 `resolveCreatedObjectReference()` 检查实例——RPC 模式下拿不到真实实例，抛出异常
- Creator 的 gestrue hooks（`beginCreationGesture`、`updateCreationGesture`）仍直接通过 `boardApi` 写 RPC（fire-and-forget），但没有本地 shadow 导致后续手势位置计算依赖 `this.obj.position`

解决方案方向：

- 引入 **local shadow / draft object** 替代 `this.obj` 的直接 `BasicObject` 引用
- Creator 子类在创建时同步生成兼容 shadow，手势更新时同时写 RPC + shadow
- `resolveCreatedObjectReference` 在 RPC 模式下返回 shadow 而非真实实例

---

### 3.7 文件 IO 在 Worker 中的落地方式（P3 内可选）

#### 背景

`file-operate-bridge-renderer.js` 只能在渲染线程直接用。Worker 中的文件 IO 需通过 UI host 转发。

#### 实现步骤（P3 内可选，P4 可补）

**新增文件**：`src/core/bridges/worker-file-io-host.js`（可选）

##### 3.7.1 消息协议

| Worker → UI | UI → Worker | 说明 |
|-------------|-------------|------|
| `{ type: "file-io", method: "loadChunkMetadata", params: { chunkId } }` | `{ type: "file-io-response", result: {...} }` | 加载区块元数据 |
| `{ type: "file-io", method: "saveChunkMetadata", params: { chunkId, metadata } }` | `{ type: "file-io-response", result: true }` | 保存区块元数据 |
| `{ type: "file-io", method: "loadObjects", params: { objectIds } }` | `{ type: "file-io-response", result: [...] }` | 加载对象数据 |
| `{ type: "file-io", method: "saveObjects", params: { objects } }` | `{ type: "file-io-response", result: true }` | 保存对象数据 |

##### 3.7.2 UI host 实现

```js
class WorkerFileIoHost {
  constructor(worker, rendererBridge) {
    this.#worker = worker;
    this.#bridge = rendererBridge;
    this.#pending = new Map();
    worker.addEventListener("message", this.#onMessage.bind(this));
  }

  #onMessage(event) {
    if (event.data.type !== "file-io") return;
    const { msgId, method, params } = event.data;
    // 转发到 renderer bridge
    this.#bridge[method](...Object.values(params))
      .then(result => worker.postMessage({ type: "file-io-response", msgId, result }))
      .catch(err => worker.postMessage({ type: "file-io-response", msgId, error: err.message }));
  }
}
```

---

### 3.8 日志系统分层

#### 背景

当前实现没有显式 new 一个 `workerLogBus`。`core-worker.js` 直接 import `logBus`，但因为 Worker 拥有独立模块图，所以这里的 `logBus` 与 UI 线程不是同一个实例。随后再把 WARN/ERROR 级别日志通过 `worker-log` 消息回流主线程。

#### 实现步骤

**文件**：`src/core-worker.js`

```js
this.#log = new Logger("CoreWorker", "INFO", logBus);
this.#offWorkerLogs = logBus.onLevels(["WARN", "ERROR"], (entry) => {
  this.#postMessage({
    type: "worker-log",
    level: entry.level,
    logger: entry.logger,
    args: [...(entry.args ?? [])],
    meta: entry.meta ?? {},
    timestamp: entry.timestamp,
  });
});
```

**验收**：
- [x] Worker 中 Logger 使用 Worker 模块图内独立的 `logBus` 实例
- [x] WARN/ERROR 级别日志通过 `worker-log` 消息回流 UI
- [x] 主线程 `logBus` 不与 Worker 内部实例共享状态

---

### 3.9 P3 测试改造范围

| 测试文件 | 迁移关注点 | 当前状态 |
|----------|-----------|---------|
| `src/core/tests/shared-module-smoke.test.js` | 共享模块在 Node 环境下 import 正常 | ✅ 已有（P1） |
| `src/core/bridges/tests/board-api-rpc.test.js` | `BoardApiRpc` 请求-响应、超时、destroy 清理 | ✅ 已新增并通过 |
| `src/core/tests/core-worker-smoke.test.js` | `core-worker.js` ready / createBoard / createObject / createMonitor / render-frame smoke | ✅ 已新增并通过 |
| `src/core/components/orchestration/tests/monitor-core.test.js` | MonitorCore 构造、viewport-change、flushRenderFrame、OffscreenCanvas | ✅ 已新增并通过 |
| `src/core/components/orchestration/tests/monitor-proxy.test.js` | MonitorProxy 视口同步、render-frame 合成、bitmap.close() | ✅ 已新增并通过 |
| `src/core/components/orchestration/tests/board-worker-mode.test.js` | `Board.enableWorkerMode()` 与 `createMonitor()` 的 Worker mode 接线 | ✅ 已新增并通过 |
| `src/templates/demo/tests/whiteboard-demo-worker-mode.test.js` | demo 配置在 Worker mode 下的输入/创建 smoke | ✅ 已新增并通过 |
| `src/core/components/orchestration/tests/aom/*.test.js` | AOM 去 renderer 副作用后语义仍一致 | ✅ 已有 |
| `src/core/components/renderer/tests/*.test.js` | `OffscreenCanvas` / mock canvas 兼容 | ✅ 已有 |
| `src/core/components/tests/monitor-ui-renderer.test.js` | UI overlay provider 在 compat path 下继续工作 | ✅ 已有 |
| `src/core/components/orchestration/tests/monitor.test.js` | same-thread `Monitor` compat path 行为一致 | ✅ 已有 |
| `src/core/components/tests/board-input-flow.test.js` | UI Board façade + DevicesDAG 输入流保持 | ✅ 已有 |

---

### 3.10 验收标准

- [x] `core-worker.js` 能启动并返回 `ready`
- [x] UI 侧 `Board` 仍可通过现有输入流驱动工具
- [x] `MonitorProxy` 能合成 `render-frame`（ImageBitmap → drawImage）
- [x] `BoardCore` 不再依赖 `DevicesDAG` / DOM / renderer bridge
- [ ] 至少一个 creator、一个 modifier、一个 chooser 在 Worker 模式下跑通
- [x] DAG dispatch 已加 Promise rejection 保护
- [x] `BoardApiRpc` 能正确与 Worker RPC 通信
- [x] 所有现有测试（81 suites / 1015 tests）在 P3 改造后仍通过
- [x] Logger 在 Worker 中使用 Worker 线程内独立的 `logBus` 模块实例，并通过 `worker-log` 消息回流 UI

---

## Phase 4：性能优化与监测

### 目标

在架构跑通后再上批量修改、帧复用、埋点和压力测试。

### 4.1 `modifyObjects()` 放到这一阶段实现

结合现有代码，`modifyObjects()` 的价值主要在：

- 多选对象拖拽时减少消息数量
- 合并多对象 patch
- 降低 Worker 消息压力

所以它适合放在 P4，而不是 P2/P3 提前做。

### 4.2 不脏帧复用

在 `MonitorCore.flushRenderFrame()` 中做：

- base 不脏 → 复用 `lastBaseBitmap`
- live 不脏 → 复用 `lastLiveBitmap`

### 4.3 连续修改合并

对同一 `objectId` 的连续 `modifyObject`，在 Worker 中做帧级 patch merge。

### 4.4 基准测试落地文件

建议新增：

```
benchmarks/
  ├── worker-rpc.bench.js
  └── worker-render.bench.js
```

### 4.5 关键指标

| 指标                         | 目标（同线程/P2） | 目标（Worker/P3） |
| ---------------------------- | ----------------- | ----------------- |
| UI 合成帧耗时                | < 4ms             | < 4ms             |
| Worker 单帧渲染耗时          | < 8ms             | < 8ms             |
| RPC p99                      | < 0.5ms           | < 3ms             |
| viewport-change → 首帧返回   | < 8ms             | < 16ms            |
| appendListItem → live 帧更新 | < 8ms             | < 16ms            |

> RPC p99 在真实 Worker 中设为 < 3ms（`postMessage` ~0.2-0.5ms + Worker 事件循环排队 + 序列化开销），同线程版本可做到 < 0.5ms。

### 4.6 验收标准

- [ ] `modifyObjects()` 可用于多选拖拽优化
- [ ] base/live 帧复用工作正常
- [ ] 埋点与 benchmark 文件就位
- [ ] 高频绘制 / 高频平移场景可稳定 60fps

---

## 建议新增/调整的文件清单

### 新增（建议）

| 文件                                                 | 作用                        |
| ---------------------------------------------------- | --------------------------- |
| `src/core/components/orchestration/board-core.js`    | 纯 Core board 实现          |
| `src/core/components/orchestration/monitor-core.js`  | Worker 侧 monitor           |
| `src/core/components/orchestration/monitor-proxy.js` | UI 侧 monitor proxy         |
| `src/core/bridges/board-api.js`                      | 同线程 / RPC 双实现入口     |
| `src/core/shared/types.js`                           | 共享 typedef                |
| `src/core/shared/board-api-types.js`                 | BoardApi typedef            |
| `src/core/shared/message-types.js`                   | Worker 消息 typedef         |
| `src/core/bridges/worker-file-io-host.js`            | UI 线程文件 IO host（可选） |

### 会被重点修改的现有文件

| 文件                                                         | 原因                                  |
| ------------------------------------------------------------ | ------------------------------------- |
| `src/core/components/orchestration/board.js`                 | UI façade 化                          |
| `src/core/components/orchestration/monitor.js`               | façade/兼容层收口                     |
| `src/core/components/orchestration/active-object-manager.js` | 去 renderer 副作用                    |
| `src/core/tools/tool.js`                                     | `boardApi` 注入、保留兼容阶段         |
| `src/core/tools/creator/object-creator.js`                   | 去 `allocateObjectId` / renderer 直连 |
| `src/core/tools/modifier/object-modifier.js`                 | 同步兼容层 + `modifyObject` 写路径    |
| `src/core/tools/modifier/common-object-modifier.js`          | 本地缓存 + summary-like 对象兼容      |
| `src/core/tools/chooser/object-chooser.js`                       | BoardApi 生命周期 + 同步兼容层        |
| `src/core/tools/chooser/rectangle-object-chooser.js`         | BoardApi 生命周期 + 同步兼容层        |
| `src/core/components/renderer/ui-renderer.js`                | 增加 summary 兼容 overlay 入口        |
| `src/core/components/renderer/base-renderer.js`              | Worker canvas 接入验证                |
| `src/core/components/renderer/live-renderer.js`              | Worker canvas 接入验证                |

---

## 测试计划（按真实测试分布）

### 第一批：预解耦必须守住

- `src/core/tools/tests/tool.test.js`
- `src/core/components/tests/board-input-flow.test.js`
- `src/core/prefixs/tests/handoff-handler.test.js`
- `src/core/components/orchestration/tests/aom/*.test.js`

### 第二批：工具迁移逐个回归

- `src/core/tools/creator/tests/stroke-creator.test.js`
- `src/core/tools/creator/tests/circle-creator.test.js`
- `src/core/tools/creator/tests/polygon-creator.test.js`
- `src/core/tools/modifier/tests/object-modifier.test.js`
- `src/core/tools/modifier/tests/common-object-modifier.test.js`
- `src/core/tools/chooser/tests/object-chooser.test.js`
- `src/core/tools/chooser/tests/rectangle-object-chooser.test.js`

### 第三批：渲染/monitor/worker 相关

- `src/core/components/renderer/tests/*.test.js`
- `src/core/components/orchestration/tests/monitor.test.js`
- `src/core/components/tests/monitor-ui-renderer.test.js`
- 新增 worker/RPC/bridge 测试

### 测试注意事项

沿用项目既有坑点：

- `board.width` / `board.height` 必须设置
- 涉及 DAG dispatch 必须带 `{ board, monitor }` 上下文，兼容阶段再加 `boardApi`
- modifier 的 `position` / `displacement` 双通道都要测
- 断言要验证位置/状态真实变化

---

## 文件级迁移 checklist

> 这份 checklist 面向实际执行，按“先改什么文件、改到什么程度算完成”组织。

### P0：预解耦 checklist（已完成）

- [x] `src/core/components/orchestration/board.js`
  - [x] 明确 UI façade 边界：保留 `DevicesDAG`、`signalsEventBus`、`monitors`、`createMonitor()`
  - [x] 把 Core 数据职责逐步下沉给 `BoardCore`
  - [x] 不再直接承担最终 Worker 侧纯 Core 入口的角色
- [x] `src/core/components/orchestration/board-core.js`（新增）
  - [x] 承接 `objectLoaded`、`chunkLoaded`、`objectCounterPool`、`UndoTree`、AOM、chunk/object 持久化协调
  - [x] 不依赖 `DevicesDAG`、DOM、`boardFileOperateBridge`
- [x] `src/core/components/orchestration/monitor.js`
  - [x] 已收口为 façade / 兼容入口（`board.js` 按 feature flag 选择 `Monitor` 或 `MonitorProxy`）
  - [x] 已明确哪些方法将来归 `MonitorProxy`，哪些归 `MonitorCore`
- [x] `src/core/components/orchestration/active-object-manager.js`
  - [x] 抽离 `requestLiveRender(...)` 到 renderHooks
  - [x] 抽离 `requestBaseRenderForObjects(...)` 到 renderHooks
  - [x] 抽离 `_flushViewportForObjects(...)` 到 renderHooks
  - [x] 保留 `choose/add/apply/discard/remove` 语义不变
- [x] `src/core/bridges/file-operate-bridge-renderer.js`
  - [x] 不再被 `BoardCore` 直接 import
  - [x] 仅作为 UI 线程 persistence adapter 的底层桥接
- [x] `src/core/components/chunk/chunk-loader.js`
  - [x] 维持职责不变

### P1：共享层 checklist ✅

#### 模块审计

- [x] **纯数学模块**确认无 DOM/Worker/IPC 依赖
  - [x] `src/core/range/` — 逐文件验证 import 链终点
  - [x] `src/core/utils/math.js` — 0 个内部 import，已确认
  - [x] `src/core/utils/math-algorithm.js` — import 仅到 math.js
  - [x] `src/core/utils/chain.js` — 0 个内部 import，已确认
  - [x] `src/core/components/renderer/render-scheduler.js` — import 仅到 range/
- [x] **混合文件**处理
  - [x] `src/core/components/renderer/dirty-rect-strategy.js` — 拆出 `dirty-rect-strategy-shared.js`
- [x] **可共享但有 Core 类型引用的模块**
  - [x] `src/core/components/renderer/renderer.js` — 确认 `BasicObject` 依赖链无 DOM/Worker（BasicObject → math.js, range/ ← 纯数学）

#### 类型定义

- [x] `src/core/shared/types.js`（新增）
  - [x] 定义 `ObjectSummary`、`Rect`、`RectangleRange` 等共享 typedef
- [x] `src/core/shared/board-api-types.js`（新增）
  - [x] 定义 `BoardApi` 全部方法签名 typedef
- [x] `src/core/shared/message-types.js`（新增）
  - [x] 定义 Worker 消息协议 typedef（`RpcRequest`、`RpcResponse`、`RenderFrameMessage` 等）

#### 测试

- [x] `src/core/tests/shared-module-smoke.test.js`（新增）
  - [x] `jest-environment node` 下 import 所有共享模块无报错
- [x] `yarn test src/core/range/tests/` 全部通过（359 / 359）
- [x] `yarn test src/core/utils/tests/` 全部通过
- [x] 全量 `yarn test` ✅ 81 suites / 1015 tests / 0 failed

### P2：BoardApi 与工具迁移 checklist

- [x] `src/core/bridges/board-api.js`（新增）
  - [x] 提供同线程 `BoardApi`（13 个方法实现完成）
  - [x] 预留后续 RPC 版本相同签名
- [x] `src/core/tools/tool.js`
  - [x] `context.acc` 兼容注入 `boardApi`
  - [x] 透传已有 `board` / `monitor`，helper 改为优先基于 `boardApi` / `monitor` 推导
  - [x] 不要第一天删除 `createDeviceContext()`
- [x] `src/core/tools/creator/object-creator.js`（已从 `obj-creator.js` 改名）
  - [x] `ensureObject()`：BoardApi-first 双路径，`boardApi.createObject(...)` 优先
  - [x] `commitCreatedObject` / `cancelCreatedObject` / `discardCreatedObjects` 全部 BoardApi-first
  - [x] `beforeGeometryMutation` / `afterGeometryMutation` 统一收口到基类
- [x] `src/core/tools/creator/circle-creator.js`
  - [x] `boardApi.modifyObject({ data: { radius } })` 替代直接 `setData`
- [x] `src/core/tools/creator/stroke-creator.js`
  - [x] `boardApi.appendListItem("points")` 替代整条 points 重写
- [x] `src/core/tools/creator/polygon-creator.js`
  - [x] `boardApi.appendListItem / replaceListItem("points")` 替代直接列表操作
- [x] `src/core/tools/modifier/object-modifier.js`
  - [x] `modifyObject(id, { position })` 替代直接写 `obj.position`
  - [x] `withGeometryMutation()` BoardApi 路径跳过 `liveRenderer.*`，仅保留 overlay 刷新
  - [x] `commitObjects` / `discardActiveObjects` 替代手动 apply/discard
  - [x] 新增 resolve/set 系列 helper（`resolveModifiedObjectId`、`resolveModifiedObjectPosition`、`resolveModifiedObjectRange`、`resolveModifiedObjectWorldRect`、`setModifiedObjectPosition`）
- [x] `src/core/tools/modifier/common-object-modifier.js`
  - [x] 建立 `objectId -> position` 本地缓存
  - [x] summary-like 对象兼容：通过同步兼容层读取 position / worldRect，不要求传入真实 `BasicObject`
  - [x] `setModifiedObjectPosition()` 替代直接写 `obj.position`
  - [x] `_computeCombinedWorldRect` 走基类 worldRect helper，不假设 `getRange`
- [x] `src/core/tools/chooser/object-chooser.js`
  - [x] `process()` / `umount()` BoardApi 路径走 `addActiveObjects` / `discardActiveObjects`
  - [x] `resolveObjectSelectionWorldRange` 兼容 `range` / `getRange()` / `boundingBox`
  - [x] `resolveSelectedObjectReference` 回填 summary-like 条目为真实实例
- [x] `src/core/tools/chooser/rectangle-object-chooser.js`
  - [x] `replaceSelection` BoardApi 路径走 `discardActiveObjects` + `addActiveObjects`
  - [x] `collectSelectableObjects` 优先从 `boardApi.getBoardCore()` 读取
  - [x] 读路径保持同步兼容层；`hitTest`/`queryObjects` → **P3**
- [x] `src/core/components/renderer/ui-renderer.js`
  - [x] 新增 `ObjectSummary` / shadow 驱动的 overlay 兼容入口（`createCompatSelectionEntriesForSummaries`）
  - [x] 保留 `createCompatSelectionEntriesForObjects(...)` 作为 compat 路径

### P2 收尾：清理 legacy 死代码 ✅

- [x] `src/core/tools/creator/object-creator.js`
  - [x] 删除 `beforeGeometryMutation` / `afterGeometryMutation` 中的 legacy 分支（`liveRenderer.*` 直调）
  - [x] 删除 `_usesBoardApiObjectLifecycle` 标志及其条件分支
  - [x] 删除 `discardCreatedObjects` / `commitCreatedObject` / `cancelCreatedObject` 中的 legacy fallback
- [x] `src/core/tools/creator/circle-creator.js`
  - [x] 删除 `setRadius` 中的 legacy fallback（`this.obj?.setData(...)`）
- [x] `src/core/tools/creator/stroke-creator.js`
  - [x] 删除 `appendPathPoint` 中的 legacy fallback
- [x] `src/core/tools/creator/polygon-creator.js`
  - [x] 删除 `appendPoint` / `replacePoint` 中的 legacy fallback
- [x] `src/core/tools/tool.js`
  - [x] 删除 `context.acc.board` / `context.acc.monitor` 的显式兼容补齐，helper 改为按 `boardApi` / `monitor` 推导
- [x] 全量测试验证（清理后不应有路径走到 legacy 分支）

> 清理时机：Modifier + Chooser 迁移完成后、P3 开工前。P3 要处理 Worker 拆分、RPC 契约、异步语义，不应再参杂死代码分支的心智负担。✅ 已于 P3.1 开工前完成。

### P3：Worker 落地 checklist

#### P3.1 DAG dispatch async 保护 ✅

- [x] `src/core/devices-dag/dag.js`
  - [x] `_walkSegments` 中 handler 调用拆为三步：try/catch 同步异常 → Promise rejection catch → normalizeHandlerResult
  - [x] sync fire-and-forget 路径路由行为不变
  - [x] 全量测试 1015 tests / 0 failed

#### P3.2 core-worker.js 入口 ✅

- [x] `src/core-worker.js`（新增）
  - [x] import `BoardCore`、`BoardApi`、`createDefaultAomRenderHooks`、`createDefaultPersistenceAdapter`、`Logger`、`logBus`
  - [x] 使用 Worker 线程内独立模块图中的 `logBus`，并通过 `worker-log` 消息回流 WARN/ERROR
  - [x] 启动后立即发送 `{ type: "ready" }`
  - [x] 消息分发入口：`rpc` → `handleRpc`、`viewport-change` → `handleViewportChange`、`request-render-flush` → `handleRenderFlush`
  - [x] RPC 方法路由：`dispatchRpc(method, params)` 分发到 `createBoard` / `destroyBoard` / `createMonitor` / `destroyMonitor` + 15 个 Worker 内 `BoardApi` 方法
  - [x] `createBoard` 创建 `BoardCore` 实例
  - [x] `createObject` / `modifyObject` / `appendListItem` 等方法通过 Worker 内 `BoardApi` 分发到 `BoardCore` / `BasicObject` API
  - [x] Worker 内 ERROR/WARN 日志通过 `worker-log` 消息回流 UI

#### P3.3 MonitorCore / MonitorProxy 拆分 ✅

- [x] `src/core/components/orchestration/monitor-core.js`（新增）
  - [x] 持有 `chunkLoader`、`BaseRenderer`（OffscreenCanvas）、`LiveRenderer`（OffscreenCanvas）
  - [x] `onViewportChange({ origin, zoom })` 同步 chunk buffer + 全视口脏区
  - [x] `flushRenderFrame()` 产生 base/live ImageBitmap 并通过 `postMessage` 发送
  - [x] 保留坐标变换方法（`screenPointToWorld`、`worldRectToScreenRect` 等）
- [x] `src/core/components/orchestration/monitor-proxy.js`（新增）
  - [x] 持有 DOM canvas（base/live/ui）、`MonitorProxy` 引用
  - [x] `setViewportState()` rAF 节流发送 `viewport-change`
  - [x] `onRenderFrame()` drawImage 合成 + bitmap.close()
  - [x] 委托 `registerUiOverlayProvider` / `mountWorkflow` / `unmountWorkflow`
- [x] `src/core/components/orchestration/monitor.js`
  - [x] 保留为兼容入口（feature flag 切换 `Monitor` vs `MonitorProxy`）

#### P3.4 board-api.js 切 RPC 版本 ✅

- [x] `src/core/bridges/board-api.js`
  - [x] 新增 `BoardApiRpc` 类：JSON-RPC 风格请求-响应模式（每条消息带 `msgId`）
  - [x] 5s 超时机制
  - [x] 所有当前已暴露的 19 个 RPC / BoardApi 相关方法通过 `#call(method, params)` 转发
  - [x] `destroy()` 清理所有 pending 请求
  - [x] 导出 `BoardApi`（同线程）和 `BoardApiRpc`（RPC）两个版本

#### P3.5 渲染器 OffscreenCanvas 验证 ✅

- [x] `src/core/components/renderer/base-renderer.js`
  - [x] 验证 `new OffscreenCanvas(w, h)` 注入路径
  - [x] 验证 `canvas.getContext("2d")` 行为一致
  - [x] 验证 RenderScheduler 在 Worker 中正常
- [x] `src/core/components/renderer/live-renderer.js`
  - [x] 验证 `OffscreenCanvas` 注入路径
  - [x] 验证 AOM 活动对象渲染正常
  - [x] 验证 `transferToImageBitmap()` 产出

#### P3.6-A 工具 async 适配（已落地 2026-07-02）

- [x] src/core/tools/tool.js
  - [x] 新增 `canUseLegacyBoardCompat()` 统一区分 RPC/同线程 BoardApi
- [x] src/core/tools/chooser/rectangle-object-chooser.js
  - [x] `selectObjectsInWorldRect()` RPC 路径：`hitTest()` + `queryObjects()`
  - [x] `process()` 仅在 RPC 路径返回 Promise
- [x] src/core/tools/chooser/object-chooser.js
  - [x] `resolveSelectedObjectReference()` RPC 模式不回填本地 stale board
- [x] src/core/tools/modifier/object-modifier.js
  - [x] `resolveActiveModifiedObjects()` RPC 模式不误读本地空 AOM
- [x] src/core/prefixs/handoff-handler.js
  - [x] async-safe lifecycle wrapper（`finalizeLifecycleWrappedResult`）
  - [x] modifier cancel 优先走 `boardApi.discardActiveObjects()`
- [x] 对应测试新增（4 条 RPC 模式测试）

#### P3.6-B Creator Worker 兼容（已落地 2026-07-02）

- [x] src/core/tools/creator/object-creator.js
  - [x] `createObjectThroughBoardApi()` worker-first：直接创建本地草稿后 fire-and-forget，无实例回填
  - [x] `resolveCreatedObjectReference()` 整段移除，不再有任何 `board.getObjectById()` / `getBoardCore()` 路径
  - [x] `initializeCreatedObjectDraft()` 集中处理草稿对象的 property/data 初始化
  - [x] `ensureObject()` 中 objectId 分配 fallback 改走 `board.allocateObjectId()`
- [x] src/core/tools/creator/stroke-creator.js
  - [x] `appendPathPoint()` 本地草稿与 `boardApi.appendListItem()` 同步更新
- [x] src/core/tools/creator/circle-creator.js
  - [x] `setRadius()` 本地草稿与 `boardApi.modifyObject()` 同步更新
- [x] src/core/tools/creator/polygon-creator.js
  - [x] `appendPoint()` / `replacePoint()` 本地草稿与 `boardApi` 同步更新
- [x] 新增 RPC 风格测试 4 条（每个 creator 子类 1 条 + 基类 1 条）
- [x] identity 断言全部改为“不是同一实例，但序列化一致”

#### P3.7 文件 IO host（可选，P4 可补）

- [ ] `src/core/bridges/worker-file-io-host.js`（新增，可选）
  - [ ] 转发 Worker 文件请求到 renderer bridge

### P4：性能与收尾 checklist

- [ ] `src/core/bridges/board-api.js`
  - [ ] 增加 `modifyObjects()` 批量优化
- [ ] `src/core/components/orchestration/monitor-core.js`
  - [ ] base/live bitmap 复用
  - [ ] 连续 patch 合并
- [ ] `benchmarks/worker-rpc.bench.js`（新增）
  - [ ] RPC 往返延迟基准
- [ ] `benchmarks/worker-render.bench.js`（新增）
  - [ ] Worker 渲染帧时间基准

### 测试 checklist

- [x] `src/core/tools/tests/tool.test.js`
- [x] `src/core/components/tests/board-input-flow.test.js`
- [x] `src/core/prefixs/tests/handoff-handler.test.js`
- [x] `src/core/components/orchestration/tests/aom/*.test.js`
- [x] `src/core/tools/creator/tests/*.test.js`
- [x] `src/core/tools/modifier/tests/*.test.js`
- [x] `src/core/tools/chooser/tests/*.test.js`
- [x] `src/core/components/renderer/tests/*.test.js`
- [x] `src/core/components/orchestration/tests/monitor.test.js`
- [x] `src/core/components/tests/monitor-ui-renderer.test.js`
- [x] 新增 Worker / RPC / bridge 测试（`core-worker-smoke.test.js`、`board-api-rpc.test.js`、`monitor-core.test.js`、`monitor-proxy.test.js`、`board-worker-mode.test.js`）

---

## 风险与回退

| 风险 | 说明 | 缓解措施 |
| ---- | ---- | -------- |
| 直接搬 `board.js` 进 Worker | 会同时卷入 DAG / DOM / renderer bridge | ✅ P0 已拆 `board-core.js` |
| 过早删除 `createDeviceContext()` | 会引爆 DAG / tool / handoff / tests | 保留兼容阶段，最后清理 |
| 过早删除 `createCompatSelectionEntriesForObjects()` | chooser/modifier overlay 会大面积失效 | 先加 summary 版本，再逐步替换 |
| AOM 仍保留 renderer 副作用 | Worker 化时无法独立运行 | ✅ P0 已抽 renderHooks |
| Worker 直接使用 renderer bridge | 当前桥接依赖 preload 注入，只在 UI 生效 | 通过 UI host 转发 |
| creator 迁移顺序错误 | 一开始就碰 stroke/polygon 会放大复杂度 | 先迁 `ObjectCreatorTool` 基类，再从 `CircleCreatorTool` 开始验证（✅ 已解决） |

---

## 一句话版实施原则

**先把当前仓库里的“对象实例直连 + renderer 直连 + Board/Monitor/AOM 混合职责”拆开，再上 Worker。**

如果跳过这一步，后面不是“迁移”，而是“同时重写 Board、Monitor、AOM、Tool、测试”。
