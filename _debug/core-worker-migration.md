# Core Worker 迁移设计

## 概述

将白板前端拆分为 UI 线程和 Core Worker 线程，共同运行在浏览器渲染进程中。Core 侧的区块管理、对象生命周期、渲染管线和时间回溯树迁移到 Worker 中运行，UI 侧保留设备图、工具调度和帧域管控。

## 当前进展

> 最后更新：2026-07-02。Phase 1（共享纯模块验证）已完成。Phase 2（同线程 BoardApi）已完成——全部 13 个方法实现完成，Creator Family + Modifier Family + Chooser Family + UI overlay summary 入口全部迁移完成；P2 收尾中的 Creator legacy 死代码清理也已完成。Phase 3 现已全部完成（P3.1–P3.6），全部工具数据路径已不依赖 legacy board compat。

已完成的工作：

### P0：预解耦

| 模块 | 变更 | 完成时间 |
| ---- | ---- | -------- |
| `board.js` / `board-core.js` | `Board` 拆为 UI Façade，新增 `BoardCore` 承载 Core 数据职责 | P0 |
| `active-object-manager.js` | 4 个渲染方法抽为注入式 renderHooks，不再直接访问 `board.monitors` | P0 |
| `aom-render-hooks.js` | 新增：AOM 渲染钩子接口 + 默认空实现 | P0 |
| `board-render-hooks.js` | 新增：UI 侧钩子工厂，将 AOM 请求分派到 monitors 中各 renderer | P0 |
| `persistence-adapter.js` | 新增：持久化适配器接口 + UI bridge 适配器工厂 | P0 |

### P1：共享纯模块验证 ✅

| 模块 | 变更 | 完成时间 |
| ---- | ---- | -------- |
| Import 链审计 | 逐文件审查候选共享模块，确认无隐蔽 DOM/Worker/IPC 依赖 | P1 |
| `dirty-rect-strategy.js` 拆分 | 纯函数拆为 `dirty-rect-strategy-shared.js`，Chunk 依赖保留原文件 | P1 |
| `src/core/shared/` 类型定义 | 新建 `types.js`、`board-api-types.js`、`message-types.js` — 仅含 JSDoc `@typedef`，无执行代码 | P1 |
| Node smoke test | `shared-module-smoke.test.js` — 验证 10 个共享模块在 Node 环境可 import 无报错 | P1 |
| 全量测试回归 | 81 suites / 1015 tests / 0 failed | P1 |

### P2：同线程 BoardApi ✅（已完成）

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

### 已完成

| 阶段 | 内容 | 状态 |
|------|------|------|
| **P1** | 共享纯模块验证 | ✅ |
| **P2** | 同线程 BoardApi + 工具去对象引用化 | ✅ |
| **P3.1** | DAG dispatch async 保护 | ✅ |
| **P3.2** | `core-worker.js` 入口 + RPC 方法路由 | ✅ |
| **P3.3** | `MonitorCore` / `MonitorProxy` 拆分（OffscreenCanvas 渲染器验证） | ✅ |
| **P3.4** | `BoardApiRpc`（RPC 通信层） | ✅ |
| **P3.5** | OffscreenCanvas 渲染器落地验证 | ✅ |
| **P3.6-A** | Chooser async read-path + RPC 模式禁用 stale board fallback + async-safe handoff | ✅ |
| **P3.6-B** | Creator Worker-first 本地草稿模式 | ✅ |
| **P3.6-C** | 修复 Worker 渲染叠帧、force 转发、选中对象级失效（2026-07-02） | ✅ |
| **demo 入口** | `whiteboard.js` 默认启用 Worker mode，`MonitorProxy` 路径 | ✅ |

### P4：待进行

- [ ] 位图 / 帧复用（`monitor-core.js` transferToImageBitmap 恢复现为每帧 copy）
- [ ] RPC / patch 合并
- [ ] 基准测试
## 与当前代码库的对齐说明

结合当前仓库实现，这里的"迁移"不是把现有 `src/core/components/orchestration/board.js` 整个搬进 Worker，而是要先把其中混杂的 UI/Core 职责拆开。

P0 已完成以下解耦：

1. **`board.js` 已拆为 UI Façade**：新增 `BoardCore` 承载 `objectLoaded`、`chunkLoaded`、`ActiveObjectManager`、`UndoTree`、文件持久化协调等 Core 职责；`Board` 保留 `DevicesDAG`、`signalsEventBus`、`monitors`、`createMonitor()` DOM 工厂。
2. **`monitor.js` 已通过 MonitorCore/MonitorProxy 完成拆分**：P0 时 `monitor.js` 仍是混合体；P3.3 已新增 `monitor-core.js` 和 `monitor-proxy.js`，`monitor.js` 退化为同线程兼容入口。
3. **`ActiveObjectManager` 渲染副作用已抽离**：通过注入式 `renderHooks` 替代直接访问 `board.monitors`。
4. **工具层**：Creator 已完成 BoardApi 迁移。Modifier 已完成 BoardApi 写路径 + 同步兼容层。Chooser 已完成 BoardApi 生命周期 + 同步兼容层。
5. **`Board.createMonitor()`** 仍是 UI 线程入口，但在 Worker mode 下会创建 `MonitorProxy` 并在后台触发 `createMonitor` RPC；它本身不是 Worker 内的 `MonitorCore` 构造函数。

因此，本文中提到的 Core 侧 `Board` 在实际落地时应理解为一个新增的 **`BoardCore`**（P0 已完成），而 `board.js` 已转换为 **UI façade / runtime host**。

## 术语统一约定

为避免本文中的“现有类名”和“迁移后职责”互相混淆，统一采用以下术语：

| 术语 | 含义 |
| ---- | ---- |
| `Board` | 默认指 **UI 线程 façade**，即当前 `src/core/components/orchestration/board.js` 演化后的主线程宿主；保留 `DevicesDAG`、`signalsEventBus`、`monitors`、DOM monitor 创建等能力。 |
| `BoardCore` | 指 **Core 侧纯实现**，承载对象注册、区块加载、AOM、UndoTree、持久化协调等职责。P0/P2 阶段可先同线程存在，P3 后进入 Worker。 |
| `BoardApi` | UI 调 Core 的统一 API façade。P2 是同线程实现，P3 切为 RPC 实现。 |
| `Monitor` | 泛指“显示器”这一概念，不强绑定某个具体类。 |
| `MonitorProxy` | UI 线程 monitor 子集：视口状态、UiRenderer、overlay provider、workflow 挂载、与 Worker 通信。 |
| `MonitorCore` | Worker 线程 monitor 子集：chunkLoader、BaseRenderer、LiveRenderer、chunk buffer、渲染帧产出。 |
| `AOM` | `ActiveObjectManager`。语义上始终属于 Core；在真正迁入 Worker 前，也应按 Core 模块来拆副作用。 |
| `ObjectSummary` | 跨线程对象摘要，不是 `BasicObject` 实例。 |
| `shadow` / 影子副本 | UI 侧缓存的 `ObjectSummary` 或其派生状态，用于 overlay、命中、回退与恢复。 |
| `objectId` | 工具长期持有的对象令牌；迁移完成后应替代对象实例引用。 |

### 术语规则

1. 文中单独出现 `Board` 时，默认指 UI façade；若指 Worker 内核心实现，会显式写成 `BoardCore`
2. 文中单独出现 `Monitor` 时，若涉及 overlay / workflow / DevicesDAG，默认更接近 `MonitorProxy`；若涉及 chunk / base/live renderer，默认更接近 `MonitorCore`
3. `Board.createMonitor()` 若出现在类方法语境，指当前 UI 线程 DOM 工厂；若出现在 Board API / RPC 契约语境，指创建 `MonitorCore`
4. `ObjectSummary`、`shadow`、`objectId` 属于工具跨线程适配层术语，不等同于 `BasicObject`

## 模块拆分（实施状态）

Core 当前模块按职责划分归属，标注每个模块的迁移状态：

### UI 线程（渲染进程主线程）

| 模块 | 说明 | 状态 |
| ---- | ---- | ---- |
| `devices-dag` | 设备图核心 | 无需迁移 |
| `devices` | 物理设备节点（mouse / keyboard / touchscreen） | 无需迁移 |
| `prefixs` | 设备图修饰节点 | 无需迁移 |
| `frame` | 取景框与导引链系统 | 无需迁移 |
| `tool` | 设备图工具（白板交互工具） | ✅ P2 已完成：Creator + Modifier + Chooser 全部迁到 BoardApi 双路径 |
| `bridges` | 与 Tauri 主进程的 IO 桥接（文件持久化） | 已通过 persistenceAdapter 解耦 |

### Core 线程（Worker）

| 模块 | 说明 | 状态 |
| ---- | ---- | ---- |
| `components/chunk` | 区块加载及内容管理 | ✅ 已接入 Worker 路径（由 `BoardCore` / `MonitorCore` 在 Worker 中使用） |
| `components/orchestration/board-core` | 白板编排核心（由 `board.js` 拆出） | ✅ 已在 Worker mode 下运行 |
| `components/orchestration/active-object-manager` | 活动对象管理器 | ✅ 已由 Worker 侧 `BoardCore` 持有并通过 renderHooks 驱动渲染 |
| `objects` | 白板对象模型 | ✅ 已接入 Worker 路径（实例在 Worker 内创建/修改/查询） |
| `hit` | 时间回溯树（UndoTree） | ✅ 已随 `BoardCore` 进入 Worker；undo/redo API 仍待接通 |

### 两线程共享

| 模块 | 说明 | 状态 |
| ---- | ---- | ---- |
| `range` | 范围类（纯数学类型，无线程依赖，两侧共享） | ✅ 可共享，已通过 smoke test |
| `utils/math.js` | 向量/矩阵等基础数学 | ✅ 可共享，已通过 smoke test |
| `utils/math-algorithm.js` | 纯算法函数 | ✅ 可共享，已通过 smoke test |
| `utils/chain.js` | 纯工具链 | ✅ 可共享，已通过 smoke test |
| `components/renderer/render-scheduler.js` | 渲染调度器（仅依赖 range/ 纯数学） | ✅ 可共享，已通过 smoke test |
| `components/renderer/renderer.js` | Renderer 基类（`BasicObject` import 链无 DOM/Worker 依赖） | ✅ 可共享，已通过 smoke test |
| `components/renderer/dirty-rect-strategy-shared.js` | 纯函数脏区策略（P1 从 `dirty-rect-strategy.js` 拆出） | ✅ 可共享，已通过 smoke test |
| `shared/types.js` | 共享 `ObjectSummary`、`Rect` 等 typedef | ✅ 已创建 |
| `shared/board-api-types.js` | BoardApi 方法签名 typedef | ✅ 已创建 |
| `shared/message-types.js` | Worker 消息协议 typedef | ✅ 已创建 |

### 跨线程拆分

| 模块 | 拆分方案 | 状态 |
| ---- | -------- | ---- |
| `components/renderer` | `Renderer`（基类）、`BaseRenderer`、`LiveRenderer` 归 Core；`UiRenderer` 归 UI（`render-scheduler` 已确认可共享） | ✅ 已在 Worker mode 下按职责分层使用（文件目录仍共存） |
| `components/orchestration/monitor` | `MonitorCore` 归 Core，`MonitorProxy` 归 UI | ✅ 已完成（新增 `monitor-core.js` / `monitor-proxy.js`） |

### utils 模块拆分

当前 `core/utils/` 下共 12 个模块，迁移后按使用方划分归属：

| 模块                | 主要使用方                           | 归属 | 说明                                          |
| ------------------- | ------------------------------------ | ---- | --------------------------------------------- |
| `directed-graph.js` | AOM、BaseRenderer                    | Core | 图数据结构，AOM 和渲染器依赖                  |
| `event-bus.js`      | Board、ChunkLoader、Worker 日志/桥接 | 共享 | 纯事件总线工具；当前 UI 与 Core 两侧都可使用  |
| `counter-pool.js`   | Board（`allocateObjectId`）          | Core | ID 分配移至 Core，`CounterPool` 随 Board 迁移 |
| `random.js`         | AOM（`RandomNumberPool`）            | Core | 随机数池仅 AOM 使用                           |
| `queue.js`          | AOM                                  | Core | 队列仅 AOM 使用                               |
| `deque.js`          | AOM                                  | Core | 双端队列仅 AOM 使用                           |
| `math.js`           | objects、range、devices-dag、tools   | 共享 | `Vector` 等基础数学类型，两侧都需要           |
| `math3d.js`         | objects（3D 图元）                   | Core | 仅 Core 侧 objects 模块使用                   |
| `math-algorithm.js` | 通用算法                             | 共享 | 纯函数，无线程依赖                            |
| `path.js`           | DAG、prefixs                         | UI   | DAG 路径操作，UI 侧专用                       |
| `chain.js`          | 通用工具链                           | 共享 | 纯工具函数，无线程依赖                        |
| `docs/`             | —                                    | —    | 文档跟随对应模块                              |

> **原则**：共享模块必须保持纯函数/纯数学，不引用 DOM、Worker API、Tauri IPC 或任何线程绑定对象。**绝对不得**在共享模块中导入 `HTMLElement`、`OffscreenCanvas`、`self`、`window`。

## Board API

Board 提供一套通过 `postMessage` 调用的通用 API。工具不再直接操作对象实例，全部通过此 API 以 `objectId` 令牌交互。

> **对齐当前实现**：这里的 `board.createMonitor()` / `board.destroyMonitor()` 指的是 **Board API / Worker RPC** 契约；当前仓库里 `src/core/components/orchestration/board.js` 上的 `createMonitor(rootElement, { width, height }, monitorId)` 仍是 UI 线程里的 DOM 工厂方法，迁移落地时应保留在 UI façade 上，而不是直接搬进 Worker。

### API 契约

所有 API 返回 `Promise`，采用 JSON-RPC 风格的请求-响应模式（每条消息带 `msgId`）。

| 分类         | API                                                 | 说明                                                                                                                                                                                                      |
| ------------ | --------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 对象创建     | `board.createObject(type, props)`                   | 在 Core 侧创建对象实例，注册到 AOM 动态图，返回 `objectId`。`props` 含 `position`（坐标）、`property`（样式属性）、`data`（类型专属几何数据）                                                              |
| 对象修改     | `board.modifyObject(objectId, patch)`               | 修改对象的几何/样式属性。`patch` 支持：`position`（`{x,y}`）、`transform`（`{a,b,c,d}`）、对象级几何标量（如 `radius`、`points`）、`property`（样式属性合并）。修改操作自动触发 Core 侧脏区计算与渲染调度 |
| 对象批量修改 | `board.modifyObjects(patches)`                      | 批量修改多个对象，每个 patch 格式同 `modifyObject`，fire-and-forget（Phase 4 性能优化项）                                                                                                                 |
| 列表属性追加 | `board.appendListItem(objectId, key, items)`        | 向对象的列表属性追加元素，fire-and-forget                                                                                                                                                                 |
| 列表属性替换 | `board.replaceListItem(objectId, key, index, item)` | 替换指定索引的元素，fire-and-forget                                                                                                                                                                       |
| 列表属性删除 | `board.removeListItem(objectId, key, index)`        | 删除指定索引的元素，fire-and-forget                                                                                                                                                                       |
| 对象删除     | `board.deleteObjects(objectIds)`                    | 永久删除对象：若对象在 AOM 中则先移出 AOM，再从静态图移除                                                                                                                                                 |
| 对象提交     | `board.commitObjects(objectIds)`                    | 将 AOM 动态图中的对象写回静态图：新对象写入静态图，旧对象写回修改结果（触发 undo 记录）                                                                                                                   |
| 活动对象添加 | `board.addActiveObjects(objectIds)`                 | 将对象加入 AOM 动态图。用于 chooser 将静态图中已有对象拉入动态图（Core 内部走 `choose` 语义）；新建对象已由 `createObject` 自动注册到 AOM，无需再次调用本方法                                             |
| 活动对象移除 | `board.discardActiveObjects(objectIds)`             | 将对象从 AOM 动态图移除。对静态图中已有对象恢复为静态态；对未提交新对象直接丢弃其动态图副本                                                                                                               |
| 对象查询     | `board.queryObjects(ids)`                            | 按 id 列表查询对象，返回**合并视图**摘要（AOM 动态对象遮蔽同 id 的静态对象）                                                                                                                           |
| 区块对象查询 | `board.queryChunkObjects(chunkIds)`                  | 按区块查询对象，遍历指定区块的静态图收集所有 `objectId[]`                                                                                                                                               |
| 命中测试     | `board.hitTest(range, mode?)`                        | 在**合并视图**上做空间索引查询，返回命中的 `objectId[]`（去重后，AOM 对象优先）                                                                                                                           |
| 创建显示器   | `board.createMonitor({ monitorId, width, height })` | 在 Core 侧创建 MonitorCore 实例（含 OffscreenCanvas 和渲染器）                                                                                                                                            |
| 销毁显示器   | `board.destroyMonitor(monitorId)`                   | 销毁 Core 侧的 MonitorCore 实例                                                                                                                                                                           |
| 撤销/重做    | `board.undo()` / `board.redo()`                     | 委托给 Core 侧的 UndoTree，暂不考虑                                                                                                                                                                       |

### 返回值策略

工具只需要对象的 id、类型和边界框来做选择/手势判定。Board API 的返回值是轻量摘要对象，非完整序列化。

```typescript
interface ObjectSummary {
  id: number;
  type: string; // "StrokeObject" | "CircleObject" | "PolygonObject" | ...
  isActive: boolean; // 是否是活动对象
  boundingBox: RectangleRange; // 外接矩形，用于碰撞过滤
  range: Range; // 主判定范围（getRange()），用于精确命中
  position: { x: number; y: number };
  transform?: { a: number; b: number; c: number; d: number };
  property: Record<string, any>;
  data: Record<string, any>;
}
```

`boundingBox` 是对象的外接矩形，`range` 是对象的主判定范围（`getRange()` 返回值）。两者不同：圆形对象的主判定范围是 `CircleRange`，`boundingBox` 是它的外接矩形。命中查询使用 `range`。

`Range` 系列（`RectangleRange`、`PathRange`、`PolygonRange`、`CircleRange` 等）是纯数学类，无线程依赖，两线程共享同一份实现。

### objectId 令牌

工具不持有 `BasicObject` 实例引用，只持有 `objectId` 数值。

```js
// ❌ 禁止
context.acc.board.activeObjectManager.add(new Set([this.obj]));
this.obj.setProperty({ strokeColor: "red" });

// ✅ 通过 Board API
context.acc.boardApi.addActiveObjects([this.objectId]);
context.acc.boardApi.modifyObject(this.objectId, { strokeColor: "red" });
```

工具可以保留 `objectId` 和 `objectType` 字段，但不保留对象实例。

### AOM 进入/退出语义

当前工具层并**不区分**“选中态”和“编辑态”两种不同的可见运行态。Chooser 调用 `AOM.choose()`，creator / modifier 调用 `AOM.add()`，但从工具与渲染视角看，它们都只是把对象放入 AOM 动态图，由 LiveRenderer 统一渲染。

因此 Board API 不单独暴露 `selectObjects()` / `deselectObjects()`。统一使用：

- `addActiveObjects(objectIds)`：把对象放入 AOM 动态图
- `discardActiveObjects(objectIds)`：把对象从 AOM 动态图移出

Core 内部再根据对象来源决定走 `choose` 还是 `add`：

| 对象来源                            | `addActiveObjects` 内部行为                                    |
| ----------------------------------- | -------------------------------------------------------------- |
| 静态图中已有对象（如 chooser 选中） | 走 `AOM.choose()`，沿对象依赖图做分层接管                      |
| 新建未提交对象                      | 不需要调用 `addActiveObjects`——`createObject` 已自动注册到 AOM |

### 查询视图语义

`queryObjects()`（按 id）、`queryChunkObjects()`（按区块）与 `hitTest()`（按空间范围）读取的都是**静态图 + AOM 的合并视图**：

1. 若某个 `objectId` 同时存在于静态图和 AOM，则以 AOM 中的动态版本为准
2. 返回结果按 `objectId` 去重，不重复暴露静态/动态图两个版本
3. `isActive === true` 仅表示对象当前在 AOM 动态图中，不再细分 chooser / modifier / creator 来源

这保证 chooser、modifier、creator 在工具侧都看到同一份“当前真相”。

### Core 侧渲染副作用

所有修改类 Board API 在 Core 侧**自动触发**渲染同步，工具不再需要手动管理 snapshot 捕获或脏区标记。原有工具中的以下操作变为 Core 内部自动行为：

| 原工具操作                                          | 迁移后                                                                                                  |
| --------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| `monitor.liveRenderer.captureObjectSnapshot([obj])` | `modifyObject` / `appendListItem` / `replaceListItem` / `removeListItem` 调用时 Core 自动捕获变更前快照 |
| `monitor.liveRenderer.invalidateObjects([obj])`     | 同上调用完成后 Core 自动计算受影响屏幕区域并标记 LiveRenderer 脏区                                      |
| `monitor.requestViewportUiRender()`                 | 保留在 UI 侧，工具通过 `requestUiOverlayRefresh()` 触发本地 UiRenderer 重绘                             |

Core 侧处理流程：

```
modifyObject / appendListItem / replaceListItem / removeListItem
  │
  ├── ① 捕获变更前快照（LiveRenderer.captureObjectSnapshot）
  ├── ② 应用变更（setProperty / push / splice / 赋值）
  ├── ③ 计算新 screenRect（worldToScreen）
  ├── ④ 合并新旧 screenRect → 标记脏区（LiveRenderer.invalidate）
  └── ⑤ 调度渲染（renderScheduler.invalidate → 标记脏区，等待 UI 的 `request-render-flush` 消息触发 flush）

>
> **注意**：Worker 中没有 `requestAnimationFrame`。Core 侧的渲染是**被动驱动**——修改类 API 只负责标记脏区，实际的 `transferToImageBitmap` 和 `postMessage("render-frame")` 由 UI 侧每帧发送的 `request-render-flush` 消息触发。Worker 内部 RenderScheduler 的 `invalidate()` 仅收集脏区，不含自驱 flush 能力。
> 详见「渲染帧触发路径与 flush 周期整合」章节。
```

### createObject 属性初始化

`createObject(type, props)` 的 `props` 支持一次性设置所有对象状态，包括列表属性初始值，避免创建后立即追加的开销：

```js
// Stroke：初始路径点随创建一起提交
const id = await boardApi.createObject("StrokeObject", {
  position: { x: 100, y: 200 },
  property: {
    strokeColor: "#000",
    strokeWidth: 3,
  },
  data: { points: [{ x: 0, y: 0 }] }, // 初始路径点
});

// Circle：初始半径
const id = await boardApi.createObject("CircleObject", {
  position: { x: 100, y: 200 },
  property: { strokeColor: "#f00", strokeWidth: 2 },
  data: { radius: 0 }, // 对象级几何标量
});

// Polygon：初始顶点
const id = await boardApi.createObject("PolygonObject", {
  position: { x: 100, y: 200 },
  property: { fillColor: "#00f" },
  data: { points: [{ x: 0, y: 0 }] }, // 初始顶点列表
});
```

> **约定**：`props` 包含三个顶层字段——`position`（坐标）、`property`（样式属性）、`data`（类型专属几何数据）。`data` 中的具体键由对象类型决定，如 `CircleObject` 使用 `{ radius }`，`StrokeObject`/`PolygonObject` 使用 `{ points }`。

> **chooser 的选中**：当前 Chooser 调用 `AOM.choose()` 将选中对象加入动态图。迁移后通过 `addActiveObjects` 实现——从 Board API 视角，chooser 的「选中」和 modifier 的「激活编辑」都是把对象放入 AOM 动态图，LiveRenderer 对其渲染表现相同。AOM 内部 `choose` 的图拓扑分层逻辑是 Core 侧实现细节，不暴露为独立 API。

## Monitor Proxy

Monitor 同时连接视口（UI）、区块加载（Core）和渲染管线（两边），是拆分复杂度最高的模块。渲染调度链（scheduler、dirty rect 策略、canvas 管理）已完全内聚到各 Renderer 内部，Monitor 仅保留视口状态（`_origin`/`_zoom`）、ChunkLoader、三个 Renderer 引用及 DAG 相关方法。

### 拆分方案

拆为 `MonitorProxy`（UI 线程）和 `MonitorCore`（Core 线程）。

**MonitorProxy（UI 线程）**：持有 UiRenderer 引用（内含 uiCanvas）、base/live 显示用 DOM canvas、视口状态本地副本；接收 Core 的渲染帧后将 ImageBitmap 合成到 DOM canvas 上。

```js
class MonitorProxy {
  #baseCanvas; // DOM canvas，用于显示 Core 传来的 base ImageBitmap
  #liveCanvas; // DOM canvas，用于显示 Core 传来的 live ImageBitmap
  #uiRenderer; // UiRenderer（含 uiCanvas + scheduler）
  #baseCtx; // baseCanvas 2D context
  #liveCtx; // liveCanvas 2D context
  #origin;
  #zoom;
  #worker;
  #pendingRenderId;

  constructor({ baseCanvas, liveCanvas, uiCanvas, worker }) {
    this.#baseCanvas = baseCanvas;
    this.#liveCanvas = liveCanvas;
    this.#baseCtx = baseCanvas.getContext("2d");
    this.#liveCtx = liveCanvas.getContext("2d");
    this.#uiRenderer = new UiRenderer(this, undefined, { canvas: uiCanvas });
    this.#worker = worker;
  }

  onViewportChanged() {
    cancelAnimationFrame(this.#pendingRenderId);
    this.#pendingRenderId = requestAnimationFrame(() => {
      this.#worker.postMessage({
        type: "viewport-change",
        origin: this.#origin,
        zoom: this.#zoom,
      });
    });
  }

  onRenderFrame(frameData) {
    const { baseBitmap, liveBitmap } = frameData;
    this.#baseCtx.drawImage(baseBitmap, 0, 0);
    this.#liveCtx.drawImage(liveBitmap, 0, 0);
    // UI overlay 由 UiRenderer 自管理绘制
    this.#uiRenderer.invalidateViewport();
  }

  // 委托给 UiRenderer
  registerUiOverlayProvider(provider, options) {
    return this.#uiRenderer.registerOverlayProvider?.(provider) ?? false;
  }

  unregisterUiOverlayProvider(provider, options) {
    return this.#uiRenderer.unregisterOverlayProvider?.(provider) ?? false;
  }
}
```

**MonitorCore（Core 线程）**：持有 BaseRenderer（内含 base OffscreenCanvas + scheduler）、LiveRenderer（内含 live OffscreenCanvas + scheduler）、ChunkLoader；渲染完成后通过 `transferToImageBitmap` 将帧数据传回 UI。

```js
class MonitorCore {
  #chunkLoader;
  #baseRenderer; // 内含 base OffscreenCanvas + scheduler
  #liveRenderer; // 内含 live OffscreenCanvas + scheduler

  onViewportChange({ origin, zoom, viewportSize }) {
    this.#origin = origin;
    this.#zoom = zoom;
    if (viewportSize) {
      this.#baseRenderer.resize(viewportSize.width, viewportSize.height);
      this.#liveRenderer.resize(viewportSize.width, viewportSize.height);
    }
    this.#syncChunkBuffer();
    this.#baseRenderer.invalidateViewport();
    this.#liveRenderer.invalidateViewport();
  }

  onRenderFlush() {
    // transferToImageBitmap 从各 Renderer 的 OffscreenCanvas 提取帧
    const baseBitmap = this.#baseRenderer.canvas.transferToImageBitmap();
    const liveBitmap = this.#liveRenderer.canvas.transferToImageBitmap();
    self.postMessage(
      { type: "render-frame", baseBitmap, liveBitmap, dirtyRects },
      [baseBitmap, liveBitmap],
    );
  }
}
```

> **当前实现补充**：`MonitorProxy` 实际还提供 `startWorkerSync()`。它会在 `createMonitor` RPC resolve 后启动首个 `viewport-change` 同步，并持续发送 `request-render-flush`，驱动 Worker 周期性产出 `render-frame`。

### 视口同步策略

视口状态（origin/zoom）变更频繁，采用 rAF 批量同步，不逐帧发消息：

```
mousemove → 更新本地 origin/zoom（光标反馈可用）
         → schedule rAF
rAF fire  → postMessage({ type: "viewport-change", origin, zoom })
         → Core 侧重新计算加载范围和渲染
```

位移/滚轮等连续操作的中间帧不影响正确性。

#### 通信界线

Monitor 相关功能按通道划分：

| 通道                 | 方向      | 内容                                              | 时机                           |
| -------------------- | --------- | ------------------------------------------------- | ------------------------------ |
| **Board API RPC**    | UI → Core | `createMonitor` / `destroyMonitor`                | 创建/切换/关闭显示器           |
| **推送消息**         | UI → Core | `viewport-change`（origin / zoom / viewportSize） | 视口变更时 rAF 节流发送        |
| **推送消息**         | Core → UI | `render-frame`（ImageBitmap + dirtyRects）        | 每帧渲染完成后                 |
| **MonitorCore 内部** | —         | 区块加载/卸载、dirty rect 合并、渲染调度          | `viewport-change` 响应的副作用 |
| **UI 线程本地**      | —         | UiRenderer 合成、canvas drawImage                 | `render-frame` 接收后          |

不在 Board API 中暴露以下方法：

- `setViewport` / `setZoom` → origin/zoom 在 MonitorProxy 本地管理，通过 `viewport-change` 推送
- `loadChunk` / `unloadChunk` → MonitorCore 内部响应视口变化自动调度
- `getViewportRect` / `getVisibleChunks` → 渲染帧中已隐含，不需要额外查询

## Render Proxy

### 渲染器归属

| 渲染器         | 数据源                 | 渲染目标                          | 归属 |
| -------------- | ---------------------- | --------------------------------- | ---- |
| `BaseRenderer` | 静态图对象（Chunk 内） | `OffscreenCanvas` → `ImageBitmap` | Core |
| `LiveRenderer` | AOM 动态图对象         | `OffscreenCanvas` → `ImageBitmap` | Core |
| `UiRenderer`   | 工具 overlay 数据      | 普通 `Canvas`                     | UI   |

### 渲染流程

```
[UI Thread]                    [Core Worker]
    │                                │
    │── viewport-change ────────────▶│ 更新视口，触发脏区
    │                                │
    │                                │── 遍历 AOM/Chunk 对象
    │                                │── 绘制到 OffscreenCanvas
    │                                │── transferToImageBitmap()
    │◀── render-frame (ImageBitmap) ─│
    │                                │
    │── drawImage(base/live)         │
    │── 绘制 UI overlay              │
    │── requestAnimationFrame        │
```

`transferToImageBitmap` 传输的是 `Transferable` 对象，传输本身零拷贝（仅转移所有权）。但 `transferToImageBitmap()` 入口有一次 GPU 拷贝（从 OffscreenCanvas 当前帧缓冲生成新 ImageBitmap），这是跨线程渲染的标准方案。

性能上远优于 CPU 侧的 `ImageData` 或 `toBlob` 方案。对于白板的渲染密度，开销可接受。配合 rAF 节流可避免一帧内重复触发。

### 脏区传播

脏区计算全部在 Core 线程完成。Core 将合并后的脏区随 `render-frame` 消息发出，UI 侧用 `drawImage` 局部更新。

```typescript
interface RenderFrameMessage {
  type: "render-frame";
  baseBitmap: ImageBitmap;
  liveBitmap: ImageBitmap;
  baseDirtyRects: Rect[];
  liveDirtyRects: Rect[];
}
```

脏区覆盖超过 80% 视口时退化到全帧更新。

## Tool

工具在设备图末端消费信号，无法直接访问 Core 侧的对象 API，只能通过 Board API 操作对象。

### context.acc.boardApi

迁移后工具以 `boardApi` 为主，改为在累计上下文 `context.acc` 中注入 `boardApi`。`boardApi` 由上游 DAG 节点（monitor/board 节点）在 dispatch 时注入 `acc`。

但结合当前代码库，`toolContext` 与 `createDeviceContext` **不应在第一阶段直接删除**：现有 `Tool.createProcessor()`、`DevicesDAG.mountWorkflow()`、`handoff-handler`、以及大量测试都依赖 `board` / `monitor` fallback。更稳妥的做法是先进入一段 **`board` / `boardApi` 并存的兼容期**。

```js
// 兼容期
const board = accumulatedContext.board ?? toolContext.board;
const boardApi = accumulatedContext.boardApi ?? toolContext.boardApi;
```

在 creator / modifier / chooser 全部迁到 `boardApi`，且 `tool.js`、`devices-dag/dag.js`、`prefixs/handoff-handler.js` 相关测试稳定后，再整体移除 `toolContext` 和 `createDeviceContext`。

**P2 当前实现**：Creator 与 Modifier 的写路径保持同步 fire-and-forget；工具 `process()` 不 `await` BoardApi。

```js
process(signalPacket, context) {
  const boardApi = context.acc.boardApi;
  boardApi.createObject("StrokeObject", { ... }); // fire-and-forget
}
```

**P3 仅在 read-RPC 路径上引入 async**：例如 chooser 的 `hitTest/queryObjects`、modifier 的读取型查询。Creator 仍保持同步。

> **注意**：只有当某个工具路径真的变为 `async` 时，DAG dispatcher 才需要补 Promise rejection 保护；这一步属于 P3，而不是 P2。

调用替换对照：

| 当前                                                 | 迁移后                                             |
| ---------------------------------------------------- | -------------------------------------------------- |
| `context.acc.board.allocateObjectId()`               | `context.acc.boardApi.createObject(...)`           |
| `context.acc.board.activeObjectManager.add(...)`     | `context.acc.boardApi.addActiveObjects(...)`       |
| `context.acc.board.activeObjectManager.discard(...)` | `context.acc.boardApi.discardActiveObjects(...)`   |
| `context.acc.board.getObjectById(id)`                | `context.acc.boardApi.queryObjects([id])`          |
| `context.acc.board.applyModifiedObjects(...)`        | `context.acc.boardApi.commitObjects(...)`          |

`context.acc` 中的其他字段：

- `context.acc.monitor` → 保留（UI 侧的 `MonitorProxy`，由上游注入）
- `context.acc.objects` → 保留（当前编辑对象条目列表，兼容 `BasicObject` 或 summary-like 条目）
- `context.acc.resolveOwnerChunkId` → 当前无工具使用，迁移后移除。

### 持有对象的方式

长期方向是：工具以 `objectId` 作为主令牌，不再把 `BasicObject` 实例当作唯一数据源。

但 **P2 当前实现** 为了兼容 handoff、overlay 和既有测试，仍保留一层对象条目兼容：

- Creator 仍保留 `this.obj` / `context.acc.objects`
- Modifier 仍保留 `context.acc.objects`
- 这些条目可以是 `BasicObject` 实例，也可以是 summary-like 对象
- 真正的写路径已经统一切到 `objectId -> boardApi`

因此，P2 的关键不是“立即彻底删除对象条目引用”，而是“让对象条目退化为兼容层，让 `objectId` 成为真正的写入入口”。

### 列表属性操作

笔画路径和多边形顶点当前都统一使用 `"points"` 作为跨线程 list key，支持 append、replace、remove 三种操作。所有操作走 fire-and-forget 推送通道，不阻塞手势帧。

| 方法                                                   | 适用场景                                              |
| ------------------------------------------------------ | ----------------------------------------------------- |
| `boardApi.appendListItem(objectId, key, items)`        | 笔画绘制时追加路径点、多边形添加新顶点                |
| `boardApi.replaceListItem(objectId, key, index, item)` | 多边形拖拽时替换当前顶点位置 |
| `boardApi.removeListItem(objectId, key, index)`        | 撤销多边形上一步顶点、删除路径中的某个点              |

```js
// UI 侧 — 三个操作的 fire-and-forget 使用
onPointerMove(worldPos) {
  // stroke: 追加路径点
  this.boardApi.appendListItem(this.objectId, "points", [
    { x: worldPos.x, y: worldPos.y },
  ]);

  // polygon: 替换当前拖拽的顶点
  this.boardApi.replaceListItem(this.objectId, "points",
    this.currentVertexIndex,
    { x: worldPos.x, y: worldPos.y },
  );
}

onUndoLastVertex() {
  // polygon: 删除上一个顶点
  this.boardApi.removeListItem(this.objectId, "points", lastIndex);
}

// Core 侧 — 统一路由
onMutateListProperty({ objectId, key, operation, index, items }) {
  const obj = this.board.getObjectById(objectId);
  const points = this.resolveGeometryListField(obj, key);
  if (!obj || !Array.isArray(points)) return;

  switch (operation) {
    case "append":
      points.push(...items);
      break;
    case "replace":
      points[index] = items[0];
      break;
    case "remove":
      points.splice(index, 1);
      break;
  }

  this.markDirty(this.#calcScreenRect(obj));
}
```

特点：

- **通用**：不绑定对象类型，`key` 参数指定属性名
- **fire-and-forget**：不 await，不阻塞手势帧
- **连续操作独立发送**：跟手延迟最低

### 命中查询

命中测试委托给 Core 侧的 Board API，UI 侧不遍历对象图：

```js
const hits = await boardApi.hitTest(
  selectionRange, // 可以是 RectangleRange、PathRange、CircleRange 等
  "intersect",
);
```

### 对象修改

当前 `CommonObjectModifierTool`（继承 `GestureBasedObjectModifierTool`）消费 position / displacement / end / success / cancel 信号。结合当前实现，P2 的迁移重点不是“立即彻底删掉所有对象条目”，而是把**写路径**统一切到 `boardApi`，同时保留一层**同步兼容层**供既有手势状态机、handoff 和 overlay 继续工作。

#### 当前实现的关键变化

1. **写路径 BoardApi-first**：位置修改统一走 `setModifiedObjectPosition()`，内部转发到 `boardApi.modifyObject(id, { position })`
2. **提交/撤销 BoardApi-first**：`applyModifiedObjects()` / `umount()` 优先走 `commitObjects` / `discardActiveObjects`
3. **读路径同步兼容层**：通过 `resolveModifiedObjectId`、`resolveModifiedObjectPosition`、`resolveModifiedObjectWorldRect` 兼容 `BasicObject` 与 summary-like 对象
4. **几何刷新分流**：BoardApi 路径下跳过 `liveRenderer.*`，仅保留 overlay 刷新；legacy 路径继续保留旧逻辑
5. **`resolveActiveModifiedObjects` 暂保留**：P2 继续把它作为兼容层，通过 AOM 活动对象索引过滤上下文对象；P3 若 read-RPC 全切，再评估是否收口或移除

#### 当前实现的关键行为

`CommonObjectModifierTool` 仍使用 anchor-based 方式计算位移，不是增量累加：

```js
const dx = position.x - this._anchorPosition.x;
const dy = position.y - this._anchorPosition.y;
this.setModifiedObjectPosition(context, obj, {
  x: basePos.x + dx,
  y: basePos.y + dy,
});
```

内部维护三套缓存：

| 缓存                    | 作用                                      | 何时写入                                                | 何时清除                                        |
| ----------------------- | ----------------------------------------- | ------------------------------------------------------- | ----------------------------------------------- |
| `_anchorPosition`       | 手势锚点（光标起始坐标）                  | `beginModifyGesture`                                    | `completeModifyGesture` / `cancelModifyGesture` |
| `_gestureBasePositions` | 各对象在当前手势中的基准位置              | `beginModifyGesture`                                    | `completeModifyGesture` / `cancelModifyGesture` |
| `_initialPositions`     | 首次手势时对象的初始位置（cancel 回退用） | `beginModifyGesture`（仅首次）或 `onBeforeDisplacement` | `cancelModifyGesture` 或 `success` 后           |

双通道信号的协调保持不变：

- **position 信号**：驱动手势状态机，`updateModifyGesture` 以 anchor 偏移计算绝对位置
- **displacement 信号**：基类 `applyDisplacementToObjects` 直接累加，`onAfterDisplacement` 同步 `_gestureBasePositions`
- **两通道同帧并存**：position 先定位，displacement 再叠

#### P2 / P3 的边界

- **P2 当前实现**：Modifier 不依赖 `queryObjects()`；通过同步兼容层读取 position / worldRect，保持 `process()` 与 hooks 同步
- **P3 后续方向**：只有当 read-RPC 真正进入工具层时，才让 chooser / 读取型 modifier 路径引入 `queryObjects(ids)` / `hitTest(range, mode?)` 与 async 保护

因此，当前 Modifier 的实际落地方式是：

```
position/displacement 信号
       │
       ▼
GestureBasedObjectModifierTool.process（同步）
  │
  ├── withGeometryMutation（同步）
  │     ├── begin/update/applyDisplacement/cancel（同步 hook）
  │     └── setModifiedObjectPosition(...) → boardApi.modifyObject(...)（fire-and-forget）
  │
  ├── afterGeometryMutation
  │     ├── BoardApi 路径：仅 overlay 刷新
  │     └── legacy 路径：liveRenderer.capture/invalidate
  │
  └── success / umount → commitObjects / discardActiveObjects
```

这使 P2 阶段的 Modifier 既能走 `boardApi`，又不必提前把整个手势状态机 async 化。

### 工具 overlay

工具与 `UiRenderer` 同在 UI 线程。**当前实现**已全面支持 summary 兼容 overlay 路径：工具通过 `resolveContextObjects()` 取到当前对象条目，`UiRenderer.createCompatSelectionEntriesForSummaries()` 统一处理 `BasicObject` 实例与 RPC plain summary 条目。`RectangleRange.fromRectLike()` 确保了 plain `boundingBox` / `worldRect` 在 Worker mode 下也能正确推导选框屏幕矩形。

```js
collectUiOverlayEntries({ deviceContext, renderer }) {
  const objects = this.resolveContextObjects(deviceContext);
  return renderer.createCompatSelectionEntriesForObjects(objects, "modifier");
}
```

特点：

- **P2 兼容优先**：先保住现有 handoff / overlay / 测试语义
- **工具自包含**：overlay provider 生命周期仍由 `createUiOverlayBinding` 绑定到工具 processor
- **P3/P2 收尾再清理**：等 chooser 和 summary overlay 路径稳定后，再移除 compat 入口

## 生命周期

### 初始化

```
1. UI 线程：new Worker('core-worker.js', { type: "module" })
2. UI 线程：await board.enableWorkerMode(worker)
3. Core 线程：runtime.start() → postMessage({ type: "ready" })
4. UI 收到 ready，BoardApiRpc 发送 createBoard RPC
5. Core 创建 BoardCore + Worker 内 BoardApi，并安装 monitor-aware renderHooks
6. UI 调用 board.createMonitor(...)（Worker mode 下返回 MonitorProxy）
7. UI → rpc: createMonitor
8. Core 创建 MonitorCore（含 OffscreenCanvas、BaseRenderer、LiveRenderer）
9. createMonitor RPC resolve 后，MonitorProxy.startWorkerSync()
10. MonitorProxy 发送首个 viewport-change，并启动持续 request-render-flush 循环
11. Core flushRenderFrame() → render-frame
12. UI drawImage，白板可见
```

### 销毁

```
1. UI 关闭页面或切换白板
2. MonitorProxy 清理 canvas 引用
3. UI → rpc: destroyBoard
4. Core 保存未落盘数据，释放 OffscreenCanvas
5. Core → rpc-response (ok)
6. UI → worker.terminate()
```

### Worker 崩溃恢复

```
1. UI 检测到 Worker.onerror 或长时无响应
2. UI 保存当前 objectId 列表（来自影子缓存）
3. UI → worker.terminate()
4. UI → new Worker('core-worker.js', { type: "module" })
5. 重新调用 `board.enableWorkerMode(worker)` 并走初始化时序
6. 从文件系统重新加载当前区块的对象
7. UI 将未提交的活跃对象重新创建到 Core
```

## 错误处理

### 消息超时

RPC 调用带超时机制：

```js
class BoardApiRpc {
  #pending = new Map();

  async #call(method, params, timeoutMs = 5000) {
    const msgId = crypto.randomUUID();
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.#pending.delete(msgId);
        reject(new Error(`RPC timeout: ${method}`));
      }, timeoutMs);
      this.#pending.set(msgId, { resolve, reject, timer });
      this.#worker.postMessage({ type: "rpc", msgId, method, params });
    });
  }
}
```

### 幂等性要求

| 操作            | 幂等策略                     |
| --------------- | ---------------------------- |
| `createObject`  | objectId 已存在视为 no-op    |
| `commitObjects` | 已提交的对象再提交视为 no-op |
| `modifyObject`  | 连续两次相同修改结果一致     |
| `hitTest`       | 纯查询，天然幂等             |

### 序列化约束

跨线程数据必须可结构化克隆。`Map`、`Set`、`WeakRef`、DOM 引用等不可直接传递，需先转换。

## 构建与打包

### 当前构建现状

项目使用 Tauri 2，`tauri.conf.json` 中 `frontendDist: "../src"`，无打包工具。JS 模块通过 `<script type="module">` 标签直接从文件系统加载（Tauri 自定义协议，无网络延迟）。

### Worker 入口策略

无需引入打包工具。创建 Worker 入口文件 `src/core-worker.js`，使用 `{ type: "module" }` 选项：

```js
// UI 线程初始化处
const board = new Board({ width: 800, height: 600 });
const worker = new Worker(new URL("../core-worker.js", import.meta.url), {
  type: "module",
});

await board.enableWorkerMode(worker);
const monitor = board.createMonitor(rootElement, { width, height }, "main");
```

`core-worker.js` 作为独立入口，仅 import Core 侧模块：

> **注意**：这里不要直接 import 当前 `src/core/components/orchestration/board.js`。该文件目前仍混有 `DevicesDAG`、`signalsEventBus`、`Board.createMonitor()` DOM 工厂、`boardFileOperateBridge` 等 UI/渲染进程职责。Worker 入口应只 import 新增的 `board-core.js`（或等价拆分后的纯 Core 模块集合）。

```js
// src/core-worker.js
/**
 * @file Core Worker 入口
 * @description Worker 线程入口，加载 Core 侧所有模块并暴露 RPC 接口。
 * @module core-worker
 * @author Zhou Chenyu
 */

import { BoardCore } from "./core/components/orchestration/board-core.js";
// ... 其他 Core 侧模块由 BoardCore 内部按需 import

self.addEventListener("message", (event) => {
  // 消息路由到 BoardCore
});
```

**优点**：与现有架构一致，零构建配置，模块懒加载，文件系统读取无延迟。

### 潜在的打包需求（远期）

如果未来需要压缩传输或合并请求，可使用 Rollup/esbuild 单独为 Worker 生成 bundle，但非迁移阶段的必要项。Tauri 生产构建（`tauri build`）可配置 `beforeBuildCommand` 触发打包。

## RenderScheduler 与 dirty-rect-strategy 归属

### 当前结构

最近的提交已将渲染调度链**内聚到各 Renderer 内部**。每个 Renderer 自管理其 canvas、RenderScheduler、脏区合并策略与缩放感知阈值：

| 渲染器         | scheduler 创建方式                                                  | 脏区策略来源                                                                         |
| -------------- | ------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| `BaseRenderer` | `_initScheduler()`（构造中调用）                                    | `createBaseDirtyRectThresholdStrategy` + `createBaseDirtyRectCanonicalRectsResolver` |
| `LiveRenderer` | `_initScheduler()`（构造中调用）                                    | `createLiveDirtyRectThresholdStrategy`                                               |
| `UiRenderer`   | 构造中直接 `new RenderScheduler({ mergeDirtyRects, flushHandler })` | `createLiveDirtyRectThresholdStrategy`                                               |

`Renderer` 基类提供 `_initScheduler()`、`_createDirtyRectMerger()`、`_getThresholds()`、`_getViewportRect()`、`_getCanonicalRectsForRect()` 钩子，子类通过覆写这些钩子定制各自的脏区策略。

Monitor 不再持有任何 scheduler 或 dirty rect 策略——它仅通过 `renderer.invalidate()` / `renderer.invalidateViewport()` 委托各渲染器触发渲染。

### 迁移后归属

scheduler 和 dirty rect 策略随其所属 Renderer 拆分：

- **BaseRenderer / LiveRenderer 内的 scheduler + 策略**：归 Core。在 Worker 中运行，脏区合并和渲染管线完全在 Core 侧完成。
- **UiRenderer 内的 scheduler + 策略**：归 UI。在主线程运行，合并工具 overlay 脏区并渲染到 DOM canvas。

### dirty-rect-strategy.js 函数归属

`dirty-rect-strategy.js` 导出的函数按依赖链分两类：

| 函数                                        | 依赖                                               | 归属 | 说明                                              |
| ------------------------------------------- | -------------------------------------------------- | ---- | ------------------------------------------------- |
| `createBaseDirtyRectThresholdStrategy`      | 纯函数（缩放计算）                                 | Core | BaseRenderer 构造时使用                           |
| `createLiveDirtyRectThresholdStrategy`      | 纯函数（缩放计算）                                 | 共享 | BaseRenderer、LiveRenderer、**UiRenderer** 均使用 |
| `createDirtyRectThresholdStrategy`          | 纯函数                                             | 共享 | 上述两个工厂内部使用                              |
| `createZoomScaledThresholdStrategy`         | 纯函数                                             | 共享 | 同上                                              |
| `createZoomOffsetThresholdStrategy`         | 纯函数                                             | 共享 | 同上                                              |
| `createDirtyRectPolicyResolver`             | 纯函数                                             | 共享 | 同上                                              |
| `createBaseDirtyRectPolicyResolver`         | → 引用 `createBaseDirtyRectCanonicalRectsResolver` | Core | 仅 BaseRenderer 使用                              |
| `createBaseDirtyRectCanonicalRectsResolver` | → 引用 `ChunkObjectManager`（Core 侧）             | Core | 依赖 chunk 模块，只能在 Core 侧                   |
| `screenRectToWorldRect`                     | 纯函数                                             | Core | 仅 base canonical rect 解析使用                   |
| `collectLoadedChunksForWorldRect`           | → 引用 `ChunkObjectManager`（Core 侧）             | Core | 依赖 chunk 模块，只能在 Core 侧                   |

> **关键发现**：`createLiveDirtyRectThresholdStrategy` 及其依赖链是**纯函数**，不含 DOM/Worker/Chunk 依赖。UiRenderer 在 UI 侧使用它们，这些函数需**两侧可用**（共享或各拷贝一份）。Chunk 相关函数归 Core。

### MonitorCore 内部渲染器结构

由于 scheduler 已内聚到 Renderer，MonitorCore 无需管理调度器——只需持有 Renderer 引用：

```js
class MonitorCore {
  #board;
  #baseRenderer; // 内部持有 scheduler + OffscreenCanvas
  #liveRenderer; // 内部持有 scheduler + OffscreenCanvas
  #chunkLoader;

  constructor({ board, width, height }) {
    this.#board = board;
    this.#chunkLoader = board.createChunkLoader("monitor-main");

    // 各 Renderer 构造时自行初始化 scheduler 和 dirty rect 策略
    this.#baseRenderer = new BaseRenderer(this, {
      canvas: new OffscreenCanvas(width, height),
    });
    this.#liveRenderer = new LiveRenderer(this, board.activeObjectManager, {
      canvas: new OffscreenCanvas(width, height),
    });
  }

  // 视口变更时触发重绘
  onViewportChange({ origin, zoom, viewportSize }) {
    this.#origin = origin;
    this.#zoom = zoom;
    if (viewportSize) {
      this.#baseRenderer.resize(viewportSize.width, viewportSize.height);
      this.#liveRenderer.resize(viewportSize.width, viewportSize.height);
    }
    this.#syncChunkBuffer();
    this.#baseRenderer.invalidateViewport();
    this.#liveRenderer.invalidateViewport();
  }

  // 对象变更时标记 LiveRenderer 脏区
  markLiveDirty(rect) {
    this.#liveRenderer.invalidate(rect);
  }
}
```

## OffscreenCanvas 创建方式

两种可选方案：

### 方案 A：Worker 侧直接创建（推荐）

OffscreenCanvas 通过 Renderer 构造函数的 `{ canvas }` options 注入。在 Core 侧创建 `new OffscreenCanvas(w, h)` 传入：

```js
// Core Worker 内
class MonitorCore {
  constructor({ board, width, height }) {
    // 各 Renderer 构造时自行初始化 scheduler 和 dirty rect 策略
    this.#baseRenderer = new BaseRenderer(this, {
      canvas: new OffscreenCanvas(width, height),
    });
    this.#liveRenderer = new LiveRenderer(this, board.activeObjectManager, {
      canvas: new OffscreenCanvas(width, height),
    });
    // Renderer 内部通过 this._canvas.getContext("2d") 获取上下文
  }
}
```

**优点**：`Renderer._getContext()` 对 `HTMLCanvasElement` 和 `OffscreenCanvas` 返回相同接口的 2D context；`Renderer.resize()` 的 `canvas.width`/`height` 赋值语义一致。实现简单，无跨线程 Canvas 控制权转移。
**缺点**：尺寸变更需要 UI 侧发消息通知 Worker 调用 `renderer.resize()`。

### 方案 B：UI 侧创建后 transferControlToOffscreen

```js
// UI 线程
const baseCanvas = document.createElement("canvas");
const offscreen = baseCanvas.transferControlToOffscreen();
worker.postMessage({ type: "init-offscreen", offscreen }, [offscreen]);
```

**优点**：原 Canvas 大小变更自动同步到 OffscreenCanvas。
**缺点**：需要使用 `transferControlToOffscreen`（Firefox 长期不支持，直至 2024 年 Firefox 125 才支持，兼容性风险）；Canvas 控制权转移后主线程无法再操作该 Canvas。

### 选择与兼容性

**推荐方案 A**。理由：

- 兼容性最佳——`new OffscreenCanvas(w, h)` 支持范围更广（Chrome 69+、Edge 79+、Firefox 105+、Safari 16.4+）
- 语义清晰——Worker 完全拥有渲染上下文，不存在控制权争议
- resize 通过 `viewport-change` 消息中的 `viewportSize` 字段同步即可（见下文）

### 兼容性基线

| API                           | Chrome | Edge | Firefox | Safari |
| ----------------------------- | ------ | ---- | ------- | ------ |
| `new OffscreenCanvas(w, h)`   | 69+    | 79+  | 105+    | 16.4+  |
| `OffscreenCanvas.getContext`  | 69+    | 79+  | 105+    | 16.4+  |
| `transferToImageBitmap`       | 69+    | 79+  | 105+    | 16.4+  |
| `new Worker({type:"module"})` | 80+    | 80+  | 114+    | 15+    |

Tauri 2 默认使用系统 WebView，macOS 上为 WKWebView（Safari），Windows 上为 WebView2（Edge）。当前最低兼容目标：macOS Safari 16.4+ / Windows Edge 79+，上述 API 均在支持范围内。

### 降级策略

若目标平台不支持 `OffscreenCanvas`，回退到同线程渲染模式（即当前架构）。可通过特性检测在初始化时选择：

```js
const supportsOffscreen =
  typeof OffscreenCanvas !== "undefined" &&
  typeof OffscreenCanvas.prototype.transferToImageBitmap === "function";

if (supportsOffscreen) {
  // Worker 模式：Core 在 Worker 中渲染
} else {
  // 同线程模式：保持现有 Monitor 不变
}
```

## Canvas 尺寸变更处理

### 当前实现

Monitor 的 `resizeRenderLayers(width, height)` 已改为**委托各 Renderer 自行 resize**：

```js
// Monitor.resizeRenderLayers（当前代码）
resizeRenderLayers(width, height) {
  let resized = false;
  if (this.baseRenderer?.resize(width, height)) resized = true;
  if (this.liveRenderer?.resize(width, height)) resized = true;
  if (this.uiRenderer?.resize(width, height)) resized = true;
  if (resized) this.requestRenderLayersRefresh();
}
```

每个 Renderer 的 `Renderer.resize()` 操作自己的 `_canvas`（设置 `canvas.width` / `canvas.height`）。`HTMLCanvasElement` 和 `OffscreenCanvas` 的 width/height 赋值语义一致，天然兼容跨线程场景。

### 迁移后处理

```
window resize
  │
  ▼
MonitorProxy.resize(width, height)
  ├── uiRenderer.resize(width, height)       ← UI 侧，操作 DOM canvas
  ├── baseCanvas.width = width               ← DOM canvas（显示用）
  ├── liveCanvas.width = width               ← DOM canvas（显示用）
  ├── 更新本地 viewportSize 缓存
  └── postMessage({ type: "viewport-change", origin, zoom, viewportSize })
          │
          ▼
      MonitorCore 收到消息
          ├── baseRenderer.resize(width, height)   ← Core 侧，操作 OffscreenCanvas
          ├── liveRenderer.resize(width, height)   ← Core 侧，操作 OffscreenCanvas
          ├── 重算区块加载范围
          └── baseRenderer.invalidateViewport() + liveRenderer.invalidateViewport()
```

**关键点**：`Renderer.resize()` 统一了 `HTMLCanvasElement` 和 `OffscreenCanvas` 的尺寸变更接口。MonitorCore 直接调用 `renderer.resize()`，不需要感知底层 canvas 类型。

> **注意**：`OffscreenCanvas` 的 `width`/`height` 赋值会清空画布内容，因此 resize 后必须跟随全帧渲染。

## 渲染帧触发路径与 flush 周期整合

### 当前渲染帧触发路径

Monitor 已不再直接管理 scheduler，渲染由各 Renderer 自行驱动。事件触发简化为调用 Renderer 的 `invalidate()` / `invalidateViewport()`：

1. **视口变更**：`setViewportState` → `baseRenderer.invalidateViewport()` / `liveRenderer.invalidateViewport()` / `uiRenderer.invalidateViewport()`
2. **对象变更**：`board.signalsEventBus` 上的 `object-changed` 事件 → `liveRenderer.invalidate(rect)`
3. **AOM 变更**：`activeObjectManager` 上的 layer 变更事件 → `liveRenderer.invalidate(rect)`
4. **工具 overlay**：`uiRenderer.invalidateViewport()` 由工具通过 `requestUiOverlayRefresh` 触发

每个 Renderer 内部 scheduler 合并脏区后在适当时机调用自己的 `flush()` 方法。

### 迁移后的驱动路径

迁移后，对象变更和 AOM 变更都在 Core 侧，直接标记脏区 → 调度渲染 → 发送 `render-frame`。不再需要跨线程的事件通知。

```
[Core Worker 内部]
对象被修改（modifyObject / appendListItem 等）
  │
  ├── 更新对象属性
  ├── 计算受影响屏幕区域 → markDirty(rect)
  │      ├── 对象在 AOM 中 → LiveRenderer dirty
  │      └── 对象在静态图中 → BaseRenderer dirty
  │
  ├── liveRenderer.invalidate(rect) 或 baseRenderer.invalidate(rect)
  │
  └── (由 renderScheduler 自身合并逻辑决定何时 flush)
        └── flush → transferToImageBitmap → postMessage("render-frame")
```

UI 侧不再需要监听 `object-changed`——渲染帧本身已经包含了最新状态。

### base/live 帧同步

base 帧（静态图）和 live 帧（动态图）的更新频率不同：

- **base 帧**：仅在视口变更（平移/缩放）或对象提交到静态图时更新
- **live 帧**：每次 AOM 对象变更时更新（高频）

两者独立调度，但同一 `render-frame` 消息中可同时携带 baseBitmap 和 liveBitmap。如果仅 live 层有变更，则 baseBitmap 可复用上一帧（不重新 transferToImageBitmap）。

```js
class MonitorCore {
  #lastBaseBitmap = null;
  #lastLiveBitmap = null;

  flushRenderFrame() {
    let baseBitmap = this.#lastBaseBitmap;
    let liveBitmap = this.#lastLiveBitmap;
    const transferList = [];

    if (this.#baseDirty) {
      baseBitmap = this.#baseRenderer.canvas.transferToImageBitmap();
      transferList.push(baseBitmap);
      this.#lastBaseBitmap = baseBitmap;
      this.#baseDirty = false;
    }

    if (this.#liveDirty) {
      liveBitmap = this.#liveRenderer.canvas.transferToImageBitmap();
      transferList.push(liveBitmap);
      this.#lastLiveBitmap = liveBitmap;
      this.#liveDirty = false;
    }

    if (transferList.length > 0) {
      self.postMessage(
        {
          type: "render-frame",
          baseBitmap,
          liveBitmap,
          baseDirtyRects: this.#baseDirtyRects,
          liveDirtyRects: this.#liveDirtyRects,
          frameId: this.#frameId++,
        },
        transferList,
      );
      this.#baseDirtyRects = [];
      this.#liveDirtyRects = [];
    }
  }
}
```

### rAF 调度位置

`requestAnimationFrame` 只能在主线程调用。渲染帧的 rAF 节流由 `MonitorProxy` 负责：

```js
// MonitorProxy (UI 线程)
#pendingFrame = null;
#pendingViewport = null;

requestFrame() {
  if (this.#pendingFrame) return;
  this.#pendingFrame = requestAnimationFrame(() => {
    this.#pendingFrame = null;
    // 如果视口有变更，先发 viewport-change
    if (this.#pendingViewport) {
      this.#worker.postMessage(this.#pendingViewport);
      this.#pendingViewport = null;
    }
    // 请求 Core 侧 flush 渲染帧
    this.#worker.postMessage({ type: "request-render-flush" });
  });
}
```

Core 侧收到 `request-render-flush` 后，执行 `flushRenderFrame()` 发回帧数据。

## 工具 overlay 与 UiRenderer 迁移细节

### 当前 overlay 数据流

```
Tool.collectUiOverlayEntries({ deviceContext, renderer })
  │
  ├── 调用 renderer.createCompatSelectionEntriesForObjects(objects, mode)
  │     └── 生成兼容型 selection 条目（矩形框 + 拖拽手柄坐标）
  │
  └── 返回条目数组 → UiRenderer.flush → 绘制到 uiCanvas
```

当前 overlay 依赖 `BasicObject` 实例（`objects` 参数），因为 `createCompatSelectionEntriesForObjects` 需要读取 `obj.position`、`obj.getBoundingBox()`、`obj.type` 等。

### 后续 overlay 数据流（summary / shadow 方向）

长期方向上，工具可不再依赖真实对象实例，overlay 数据由本地缓存或 shadow/summarized entry 构造：

```js
// 迁移后的 modifier 工具
collectUiOverlayEntries({ deviceContext, renderer, monitor }) {
  if (!this.#gestureBasePositions) return [];

  return [...this.#gestureBasePositions.entries()]
    .filter(([id]) => this.#isOverlayVisible(id, deviceContext))
    .map(([id, pos]) => {
      // 从本地缓存获取 boundingBox 和类型信息
      const shadow = this.#activeObjectShadows.get(id);
      if (!shadow) return null;

      return {
        type: "selection-handle",
        objectId: id,
        objectType: shadow.type,
        position: pos,
        boundingBox: shadow.boundingBox,
        transform: shadow.transform,
      };
    })
    .filter(Boolean);
}
```

### UiRenderer 适配

`UiRenderer` 需要支持新的 overlay 条目格式（不含 `BasicObject` 引用）：

```js
// UiRenderer 新增方法
renderOverlayEntry(ctx, entry) {
  switch (entry.type) {
    case "selection-handle":
      this.#renderSelectionHandle(ctx, entry);
      break;
    case "multi-selection-frame":
      this.#renderMultiSelectionFrame(ctx, entry);
      break;
    // ...
  }
}

#renderSelectionHandle(ctx, entry) {
  const { position, boundingBox, transform } = entry;
  // 直接使用坐标和边界框绘制，不需要访问对象实例
  this.#drawHandleRect(ctx, boundingBox);
  this.#drawHandleAnchors(ctx, boundingBox);
}
```

**过渡策略**：不立即移除 `createCompatSelectionEntriesForObjects`。先新增 summary 驱动的平行入口（如 `renderOverlayEntry`），逐步将工具从"对象实例 overlay"迁移到"summary overlay"。待所有工具迁移完成后，再删除兼容型 API。

## ActiveObjectManager 跨线程同步细节

### 当前 AOM 结构

```
ActiveObjectManager
  ├── layers: Layer[]
  │     ├── id: number
  │     ├── active: boolean
  │     ├── activeObjects: Set<number>     ← objectId 集合
  │     └── inactiveGraph: DirectedGraph   ← 静态图子图
  │
  ├── activeObjectIndex: Map<number, number>  ← objectId → layerId
  ├── staticGraph: DirectedGraph              ← 完整静态图
  └── eventBus: EventBus                      ← 层变更事件
```

AOM 内部持有 `BasicObject` 引用（通过 `Chunk` 或直接引用），`activeObjectIndex` 只存 `objectId`。

### 迁移后的同步模型

AOM 完整迁移到 Core 侧。UI 侧通过 Board API 操作（已在原文档描述）。需要补充的是**同步粒度**：

| 操作                             | RPC 类型        | Core 侧副作用                               |
| -------------------------------- | --------------- | ------------------------------------------- |
| `addActiveObjects(ids)`          | RPC（需 await） | 创建新层或加入现有层，LiveRenderer 自动感知 |
| `discardActiveObjects(ids)`      | RPC（需 await） | 标记层 inactive，LiveRenderer 跳过该层对象  |
| `modifyObject(id, patch)`        | fire-and-forget | 更新对象属性，标记 LiveRenderer 脏区        |
| `appendListItem(id, key, items)` | fire-and-forget | 更新列表属性，标记 LiveRenderer 脏区        |

**设计原则**：结构变更（add/discard）await，内容变更（modify/append）fire-and-forget。结构变更影响层遍历逻辑，需要确认完成后再继续；内容变更仅影响渲染结果，下一帧自动反映。

### 影子副本生命周期

UI 侧 `#activeObjectShadows` 的同步时机：

```
addActiveObjects → await RPC 返回 → 查询 ObjectSummary → 写入 shadows
discardActiveObjects → await RPC 返回 → 删除 shadows 对应条目
commitObjects → await RPC 返回 → 删除 shadows 对应条目
object-changed 推送（Core → UI） → 更新 shadows 中对应条目
```

`object-changed` 推送是 Core → UI 的单向通知，携带变更后对象的 `ObjectSummary`。UI 侧收到后更新影子副本。

> **触发条件**：仅**结构变更**时推送（`addActiveObjects` / `discardActiveObjects` / `commitObjects` / `deleteObjects`）。连续手势中的 `modifyObject` / `appendListItem` 等 fire-and-forget 操作**不触发**推送——这些场景下的 overlay 数据由工具本地缓存直接产生，不需要从 Core 同步。

## 线程间消息协议补充

### 消息类型完整清单

```typescript
// ── 生命周期 ──
interface WorkerReadyMessage {
  type: "ready";
}

// ── RPC ──
interface RpcRequest {
  type: "rpc";
  msgId: string;
  method: string;
  params: Record<string, any>;
}

interface RpcResponse {
  type: "rpc-response";
  msgId: string;
  result?: any;
  error?: { code: string; message: string };
}

// ── UI → Core 推送 ──
interface ViewportChangeMessage {
  type: "viewport-change";
  origin: { x: number; y: number };
  zoom: number;
  viewportSize: { width: number; height: number }; // 强调：尺寸变更通过此字段同步
}

interface RequestRenderFlushMessage {
  type: "request-render-flush";
}

// ── Core → UI 推送 ──
interface RenderFrameMessage {
  type: "render-frame";
  baseBitmap: ImageBitmap;
  liveBitmap: ImageBitmap;
  baseDirtyRects: RectangleRange[];
  liveDirtyRects: RectangleRange[];
  frameId: number;
}

interface ObjectChangedMessage {
  type: "object-changed";
  objectId: number;
  summary: ObjectSummary;
}

// ── fire-and-forget 推送 ──
interface MutateListPropertyMessage {
  type: "mutate-list-property";
  objectId: number;
  key: string;
  operation: "append" | "replace" | "remove";
  index?: number;
  items?: any[];
}
```

### 消息处理顺序

Core 侧 Worker 的 `onmessage` 是单线程事件循环。所有消息（RPC 和推送）按**到达顺序串行处理**，天然避免并发问题：

```js
// Core Worker 侧
self.addEventListener("message", (event) => {
  const msg = event.data;
  switch (msg.type) {
    case "rpc":
      handleRpc(msg);
      break;
    case "viewport-change":
      handleViewportChange(msg);
      break;
    case "mutate-list-property":
      handleMutateListProperty(msg);
      break;
    case "request-render-flush":
      flushRenderFrame();
      break;
  }
});
```

这意味着：在同一个事件循环 tick 中，先到达的 RPC 会在后到达的推送之前完全处理完毕。**不需要**引入应用层锁或消息队列排序。

### 共享类型定义位置

当前项目无 TypeScript，建议在 `src/core/shared/` 下放置 JSDoc typedef 文件：

```
src/core/shared/
  ├── types.js           # ObjectSummary, TileRange, Rect 等通用类型 typedef
  ├── message-types.js   # RpcRequest, RpcResponse, RenderFrameMessage 等消息类型 typedef
  └── board-api-types.js # BoardApi 方法签名 typedef
```

这些文件只含 JSDoc `@typedef`，不含任何可执行代码，两侧均可 import 用于 IDE 类型提示。

## frame 模块归属

`src/core/frame/` 当前仅含文档（`docs/frame-document.md`、`docs/frame-template-document.md`、`docs/guiding-chain-document.md`），未见实现代码。按设计文档描述，`frame` 模块负责「取景框与导引链系统」，属于 UI 层概念（多个 MonitorProxy 的视口联动、画中画等），不涉及 Core 侧对象数据处理。

在拆分表中明确标注：

| 模块    | 归属 | 现状                 |
| ------- | ---- | -------------------- |
| `frame` | UI   | 文档已有，实现待开发 |

迁移不会影响 frame 模块的后续实现——它操作的是 MonitorProxy 实例而非 Core 侧对象。

## 渐进式迁移策略

### Phase 1：共享纯模块验证与类型定义（1-2 天）

目标：逐一验证每个候选共享模块的实际 import 链，确认无 DOM/Worker/Tauri IPC 依赖。对混合文件（如 `dirty-rect-strategy.js` 同时包含共享纯函数和 Chunk 依赖函数）做物理拆分或边界标记。创建跨线程 JSDoc 类型定义文件。

- 逐文件 audit import 链（`range/`、`math.js`、`math-algorithm.js`、`chain.js`、`render-scheduler.js`、`renderer.js`、`dirty-rect-strategy.js`）
- 拆分或显式标记 `dirty-rect-strategy.js` 中共享函数与 Core 专属函数的边界
- 创建 `src/core/shared/types.js`、`board-api-types.js`、`message-types.js`（仅 JSDoc typedef）
- 编写 Node smoke test：`jest-environment node` 下 import 所有共享模块无报错
- 验证现有 `range/` 和 `utils/` 测试继续通过

**详细执行步骤见执行计划 `core-worker-migration-plan.md` Phase 1 章节。**

### Phase 2：同线程 Board API 代理层（2-3 天）

目标：在不动线程的前提下，引入 Board API 作为工具与 Core 模块之间的抽象层。

- 创建 `BoardApi` 类，提供与最终 Worker API 相同的接口签名
- BoardApi 内部直接调用同线程的 `Board` / `ActiveObjectManager` 方法
- 将**一个工具**改造为通过 BoardApi 操作对象；结合当前代码，首个试点更建议选 `CircleCreatorTool`（只有 `position + radius`，比 `StrokeCreatorTool` 的 points 追加语义更简单）
- 运行现有 E2E 测试，确保行为不变

```js
// Phase 2 的 BoardApi（同线程版本，伪代码）
class BoardApi {
  #board;
  constructor(board) {
    this.#board = board;
  }

  async createObject(type, props) {
    const id = this.#board.allocateObjectId();
    const obj = createObjectByType(type, props.position, id); // 需要新增按类型建对象的 helper
    obj.setProperty(props.property ?? {});
    this.#board.activeObjectManager.add(new Set([obj]));
    return id;
  }

  async modifyObject(id, patch) {
    /* 同线程直接调用 */
  }
  async addActiveObjects(ids) {
    /* ... */
  }
  // ...
}
```

**验收标准**：至少一个 creator 工具和对应的测试通过 BoardApi 运行。

### Phase 3：创建 Worker，迁移 Core 模块（3-5 天）

目标：创建 `core-worker.js`，将 Phase 2 的 BoardApi 替换为 RPC 版本。

- 创建 `core-worker.js` 入口
- 实现 RPC 消息路由（`BoardApi` RPC 版本）
- 将新增的 `BoardCore` / AOM / Chunk / objects / hit 加载到 Worker 中，保留现有 `board.js` 在 UI 侧作为 façade / runtime host
- Monitor 拆分为 MonitorProxy（UI）+ MonitorCore（Worker）
- 渲染管线迁移——BaseRenderer / LiveRenderer 使用 OffscreenCanvas
- 逐个迁移工具

**验收标准**：所有现有 E2E 测试通过（可能需要调整测试环境以支持 Worker）。

### Phase 4：性能优化与监测（2-3 天）

目标：引入实际性能基准，优化传输。

- 实现不脏帧复用（base 层不变时不重新 transferToImageBitmap）
- 添加 RPC 延迟埋点
- 添加帧时间埋点（UI 侧 rAF 耗时 / Core 侧渲染耗时）
- 对高频滚动/绘制场景做压力测试

**验收标准**：主线程帧预算 <8ms（UI 合成），Worker RPC p99 <3ms / 同线程 RPC p99 <0.5ms，60fps 无掉帧。

## 开发体验与调试

### Worker 调试

Chrome/Edge DevTools 支持 Worker 调试：

- `chrome://inspect/#workers` → 可单独打开 Worker 的 DevTools
- Worker 中的 `console.log` 会输出到主线程控制台（带 `[Worker]` 前缀）
- Worker 中可设置断点、查看调用栈

### Source Map

无需打包工具时，浏览器直接加载源文件，天然支持断点调试。若将来引入打包，需配置 `//# sourceMappingURL`。

### HMR（热模块替换）

Worker 不支持 Vite/Webpack 的 HMR。修改 Core 模块后需手动刷新页面（或通过 Tauri dev 的自动重载）。但这在开发流程中影响有限：

- Core 模块（objects、chunk、AOM）的修改频率远低于 UI 层的工具和交互逻辑
- 手动刷新在 Tauri 本地开发中耗时 <1 秒（文件系统读取）

**可选的开发辅助**：在 Worker 中监听 `message` 事件，接收 `reload` 指令后执行 `self.location.reload()` 重载 Worker：

```js
// 开发模式下，UI 侧监听文件变更，发送 reload 到 Worker
if (import.meta.env.DEV) {
  self.addEventListener("message", (e) => {
    if (e.data?.type === "dev-reload") {
      self.location.reload();
    }
  });
}
```

### 日志系统

当前 `Logger` 仍基于 `logBus` 事件总线（`src/utils/log/`）。但在 Worker mode 下，`core-worker.js` 直接 import 的 `logBus` 运行于 Worker 自己的模块图中，因此与 UI 线程不是同一个实例。当前实现通过 `logBus.onLevels(["WARN", "ERROR"], ...)` 把错误级别日志回流到主线程。

```js
// Core Worker 侧（当前实现）
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

## 单次 RPC 失败处理

### modifyObject RPC 超时

连续手势中 `modifyObject` 为 fire-and-forget 推送，不等待响应。如果消息因 Worker 繁忙而堆积：

- **不会丢帧**：连续发送的多条 `modifyObject` 消息按顺序在 Worker 中串行处理，Worker 处理最新的一条即可反映最终位置
- **冗余优化**：对于同一 `objectId` 的连续 `modifyObject`，Core 侧可只保留最新一条（合并中间状态）

```js
// Core Worker 侧优化：同一帧内的连续 modify 合并
#pendingModifications = new Map();  // objectId → 最新 patch

onModifyObject({ objectId, patch }) {
  this.#pendingModifications.set(objectId, {
    ...this.#pendingModifications.get(objectId),
    ...patch,
  });
  this.#scheduleFlushModifications();
}

#flushModifications() {
  for (const [objectId, patch] of this.#pendingModifications) {
    const obj = this.#board.getObjectById(objectId);
    if (obj) obj.applyPatch(patch);
  }
  this.#pendingModifications.clear();
}
```

### createObject RPC 超时

这属于 **P3 的潜在问题**。P2 当前实现中，Creator 的 `process()` 保持同步，`boardApi.createObject()` 以同线程 fire-and-forget 方式使用，不在工具内部 `await`。

进入 P3 后，如果 `createObject` 真的跨线程并可能超时，处理策略也不应直接照搬到当前 Creator：

- Creator 仍优先保持 sync fire-and-forget
- 错误由 `BoardApi` / RPC host 记录与上报
- 需要显式回滚时，再由更高层 workflow 或 session 恢复逻辑处理

也就是说，Creator 不应在 P3 里简单演化成“每次创建都在工具内 await + catch”的形态。

### fire-and-forget 消息丢失

`mutate-list-property` 是推送消息，没有响应和重试。丢失的影响：

- **丢失一个点**：路径少一段，对用户不可见（单个 pointer-move 产生的路径点间距 <2px）
- **丢失多边形顶点替换**：顶点停留在上一帧位置，下一帧的 `replaceListItem` 会覆盖

这些丢帧级错误在白板场景中可接受。不需要引入 ACK/重试机制。

## 撤销/重做的前瞻性说明

### UndoTree 当前状态

`UndoTree`（`hit/undo-tree-core.js` + `hit/operation.js`）目前定义数据结构但未集成到交互流程。`AtomOperation` 和 `MolecularOperation` 基类已有框架，`MolecularNode` 树结构已定义。

### 迁移后的 Undo/Redo 交互

UndoTree 在 Core 侧运行，所有对象快照和操作记录在 Worker 内维护。UI 侧通过 Board API 触发：

```js
// 未来 API（暂不实现）
await boardApi.undo();
await boardApi.redo();
```

undo 执行后 Core 侧发回受影响的 `objectId[]` 和渲染帧，UI 侧更新影子副本。

### 操作记录时机

`commitObjects` 是 undo 边界——对象从动态图写入静态图的时刻，触发 UndoTree 记录快照。`modifyObject`（fire-and-forget）不触发 undo 记录，仅在 `commitObjects` 时将累积变更打包为一次操作节点。

## 并发工具操作与消息串行化

### 工具隔离

DAG 保证同一时刻只有一个工具的 `process()` 在运行（设备图按路径串行分发）。但异步 RPC 返回后，工具的回调可能与新信号到达交织：

```
t1: Tool A process(signal1) → await createObject(...)
t2: Tool B process(signal2) → await queryObjects(...)
t3: createObject 返回 → Tool A 继续
t4: queryObjects 返回 → Tool B 继续
```

**这不是问题**：工具 A 和工具 B 操作不同的对象集合（由 DAG 状态机隔离），不存在竞态。

### Core 侧消息串行化

Worker 的 `onmessage` 按到达顺序同步处理每条消息（前文已述）。对于同一 `objectId` 的并发操作：

```
UI 同时发送：
  modifyObject(obj1, { position: { x: 100, y: 0 } })
  modifyObject(obj1, { strokeColor: "red" })

Core 侧串行处理：
  1. 设置 position
  2. 设置 strokeColor
  3. 两次都标记脏区，合并后一次 flush
```

结果确定，不需要额外同步。

## handoff / prefix 与异步工具的交互

### 当前 handoff 流程

`createHandoffSubDAG` 创建三层子树：

```
root (multi-tool prefix 状态机)
  ├── first (creator tool node)
  └── second (modifier tool node)
```

handoff 通过生命周期钩子实现：

- creator 的 `afterCreate` 钩子 → `onToolComplete()` → 状态机切换到 second
- modifier 的 `afterApply` 钩子 → `onToolComplete()` → 状态机切回 first

### 迁移后的变化

**钩子回调不变**：`afterCreate` / `afterApply` 仍然是工具内部的同步事件（在 `process()` 内触发）。P2 当前实现不会因为 BoardApi 接入而强制把这些钩子 async 化。

**对象桥接的变化**：P2 当前 handoff 仍通过 `context.acc.objects` 传递对象条目，保持对 Creator / Modifier / overlay / 测试的兼容；这些条目可以是 `BasicObject`，也可以是 summary-like 对象。真正的写入入口已经切到 `objectId -> boardApi`。

进入 P3 后，若 chooser / modifier 的 read-RPC 路径需要 async 查询，可再评估是否把 `context.acc.objects` 收口为 `objectId[]`、shadow entry 或其他更轻量的结构。

**prefix 节点不变**：prefix 节点（如 `edge-prefix.js`、`multi-tool-handler.js`）运行在 UI 线程，只操作信号包路由，不访问 Core 侧对象。它们不需要变成 async。

## `context.acc` 字段迁移完整对照表

| 当前字段              | P2 当前状态 | 类型 / 形态                        | 说明                                                                                                                  |
| --------------------- | ----------- | ---------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `board`               | ✅ 保留      | `Board`                            | 兼容阶段保留，便于 legacy fallback、测试与 handoff 工作流                                                            |
| `boardApi`            | ✅ 新增      | `BoardApi`                         | 由 DAG dispatch 时注入到 `acc`                                                                                       |
| `monitor`             | ✅ 保留      | `Monitor` / 后续 `MonitorProxy`    | P2 仍保留现有 monitor 能力；P3 再拆分为 Proxy/Core                                                                   |
| `allocateObjectId`    | ✅ 保留      | `Function`                         | Creator 兼容阶段仍可能使用；长期方向再并入 `boardApi.createObject`                                                  |
| `resolveOwnerChunkId` | ✅ 保留      | `Function`                         | Creator 兼容阶段仍保留                                                                                                |
| `objects`             | ✅ 保留      | `Array<BasicObject|ObjectSummary>` | 当前编辑对象条目列表。P2 阶段不强制收口成 `objectId[]`；真正的写路径通过 `objectId` 转发到 `boardApi`              |
| `onToolComplete`      | ✅ 保留 | `Function`     | handoff 回调，不涉及对象引用                                                                                                         |

### `createDeviceContext` 移除影响面

当前 `createDeviceContext` 在 `Tool.createProcessor()` 中调用，负责合并 `handlerContext.acc` 和 `toolContext` 的 board/monitor/allocateObjectId/resolveOwnerChunkId 字段。

移除路径：

1. `Tool.createProcessor` 不再调用 `createDeviceContext`，直接透传 `handlerContext`
2. `boardApi` 由 DAG dispatch 逻辑在构造 `acc` 时注入（类似当前注入 `board`）
3. `toolContext` 参数从 `createProcessor` / `createUiOverlayBinding` / `mountWorkflow` 签名中移除

影响文件清单：

| 文件                                  | 影响                                                                         |
| ------------------------------------- | ---------------------------------------------------------------------------- |
| `tools/tool.js`                       | 移除 `createDeviceContext`，调整 `createProcessor`、`createUiOverlayBinding` |
| `tools/creator/*`                     | 移除 `toolContext` 参数传递                                                  |
| `tools/modifier/*`                    | 同上                                                                         |
| `tools/chooser/*`                     | 同上                                                                         |
| `tools/eraser/*`                      | 同上                                                                         |
| `prefixs/multi-tool-handler.js`       | 移除 `toolContext` 构造                                                      |
| `prefixs/handoff-handler.js`          | 移除 `wrapChooserForHandoff` 中的 `toolContext`                              |
| `components/orchestration/monitor.js` | `mountWorkflow` 签名调整                                                     |

## 对象生命周期与 ID 分配

### objectId 分配策略

当前 `Board.allocateObjectId()` 使用 `CounterPool` 自增分配。迁移后此逻辑在 Core Worker 中运行：

```js
// Core 侧 BoardCore
#idPool = new CounterPool();

allocateObjectId() {
  return this.#idPool.allocate();
}
```

UI 侧通过 `createObject` RPC 获取 ID，不直接调用 `allocateObjectId`。

### 对象生命周期事件

| 事件        | Core 侧处理                                       | UI 侧通知                                      |
| ----------- | ------------------------------------------------- | ---------------------------------------------- |
| 对象创建    | `createObject` RPC → 实例化、注册到 AOM           | RPC 返回 `objectId`                            |
| 对象修改    | fire-and-forget → 更新属性、标记脏区              | 可选 `object-changed` 推送更新影子             |
| 对象提交    | `commitObjects` RPC → AOM → 静态图迁移、undo 记录 | RPC 返回确认                                   |
| 对象删除    | `deleteObjects` RPC → 从 AOM 和静态图移除         | RPC 返回确认                                   |
| Worker 崩溃 | 所有内存对象丢失                                  | 从文件系统重新加载，未提交对象需 UI 侧重新创建 |

### Worker 崩溃后未提交对象的恢复

```
Worker 崩溃前：
  UI 持有 objectId 列表 + 影子缓存（ObjectSummary 快照）

Worker 重启后：
  1. re-createBoard → 从文件加载已提交对象
  2. 遍历 UI 侧未提交的 objectId 列表
  3. 对每个未提交对象：
     a. boardApi.createObject(type, { position, property })  // 来自影子缓存
     b. boardApi.appendListItem(id, key, items)              // 恢复列表属性
     c. boardApi.addActiveObjects([id])                      // 恢复到动态图
  4. 重新走 commitObjects 完成提交
```

**限制**：影子缓存只保存 `ObjectSummary` 的核心字段，完整属性（如 `property` 中的所有键）可能丢失细节。建议将 `ObjectSummary.property` 定义为**完整属性快照**或至少是关键属性的超集。

## 性能量化目标

### 帧预算

| 指标                            | 目标（同线程/P2） | 目标（Worker/P3） | 测量方式                                       |
| ------------------------------- | ----------------- | ----------------- | ---------------------------------------------- |
| UI 线程帧时间（不含 Core 渲染） | <4ms              | <4ms              | `requestAnimationFrame` 回调体内计时           |
| Core 渲染帧时间（单帧）         | <4ms              | <8ms              | Worker 内 `flushRenderFrame` 计时              |
| `transferToImageBitmap` 耗时    | —（无）           | <1ms @1080p       | 单次调用计时                                   |
| RPC 往返延迟（p99）             | <0.5ms            | <3ms              | `performance.now()` 差值                       |
| 视口变更→首帧渲染               | <8ms              | <16ms（一帧内）   | viewport-change 发送到 render-frame 接收的间隔 |
| 路径追加→渲染帧更新             | <8ms              | <16ms             | appendListItem 发送到 render-frame 接收的间隔  |

> **说明**：RPC p99 < 1ms 在真实 Worker 中过于乐观。`postMessage` 本身有 ~0.2-0.5ms 延迟，加上 Worker 侧事件循环排队和结构化克隆开销，p99 < 3ms 更现实。同线程 BoardApi 因无跨线程开销，可做到 <0.5ms。

### 内存

| 指标                               | 目标                                   |
| ---------------------------------- | -------------------------------------- |
| 单个 OffscreenCanvas 内存（1080p） | ~8MB（1920×1080×4 bytes RGBA）         |
| ImageBitmap 传输峰值               | ~16MB（base + live 两张全高清位图）    |
| 影子缓存内存                       | <1MB（1000 对象 × ~1KB/ObjectSummary） |

### 基准测试

迁移完成后，在 `benchmarks/` 下新增：

- `benchmarks/worker-rpc.bench.js`：RPC 往返延迟基准
- `benchmarks/worker-render.bench.js`：不同画布尺寸/对象数量下的渲染帧时间基准

## 当前暂不覆盖的能力边界

以下能力在本次迁移设计中被明确排除在闭环之外。它们不影响核心迁移路径的决策（Board API、线程通信、AOM 同步等），但后续实现时需要补充独立的设计。

### 擦除 / 局部编辑（Eraser / Object Modify）

当前 `ObjectEraserTool` 仅有空壳基类（`src/core/tools/eraser/obj-eraser.js`），无具体实现，因此 Board API 中未定义擦除相关契约。

将来擦除可能需要的 API 形态：

| 需求                           | 可能的 API                                           | 说明                         |
| ------------------------------ | ---------------------------------------------------- | ---------------------------- |
| 整对象擦除                     | `board.deleteObjects(objectIds)`                     | 已存在，复用即可             |
| 局部擦除（切割笔画/多边形）    | `board.partialErase(objectId, eraserPath)`           | 需定义擦除路径格式和切割语义 |
| 对象替换（保留 id 但改变类型） | `board.replaceObject(objectId, nextType, nextProps)` | 跨类型对象替换               |

**当前阶段**：不纳入迁移闭环。ObjectEraserTool 实现时单独设计。

### 多显示器 / 画中画

`board.createMonitor` / `board.destroyMonitor` 已在 API 契约中预留，但未涉及多显示器的视口联动、帧同步和 monitor 间对象拖拽等场景。

**需等 `frame` 模块实现后补充**。

### 撤销 / 重做（Undo / Redo）

`board.undo()` / `board.redo()` 已在 Board API 中预留。UndoTree 数据结构（`hit/undo-tree-core.js` + `hit/operation.js`）已就位。

但以下细节未定义：

- 一次 `commitObjects` 记录一个完整的操作节点，还是需要更细粒度的操作合并
- undo 后是否自动刷新渲染帧
- undo/redo 与 AOM 的交互：回退后对象是否回到 AOM 动态图中

**建议**：UndoTree 的集成在本迁移 Phase 3 之后单独做。

### 对象分组 / Container

当前 `Container` 类（`src/core/objects/container.js`）定义了父子层级关系，但在工具链和迁移设计中未涉及。Group/Container 的操作（addChild、removeChild、flatten）不在 Board API 中暴露。

**后续版本**：若需要 Container 相关的工具交互，需补充独立 API（`board.groupObjects` / `board.ungroupObjects` 等）。

### 对象级动画 / 缓动

未纳入迁移范围。Board API 不支持任何动画或缓动参数。动画逻辑应保留在 UI 侧工具实现中，通过定时修改 `objectId` 的状态配合定时 commit 完成。

### 持久化与文件格式

Core Worker 通过 UI 侧 bridges 读写文件。文件格式（序列化/反序列化）不在本迁移设计中定义——沿用现有 `object-deserializer.js` 的逻辑即可。

### 性能基准的正式工具链

性能量化目标（帧预算、RPC 延迟等）已在文档中标注，但正式的基准测试工具链（`benchmarks/worker-rpc.bench.js` 等）需在 Phase 4 中实现。

---

## 文件级落点（设计视角）

下面这张表不讨论执行顺序，而是回答“迁移完成后，每个关键文件/模块应该落到哪一侧、承担什么角色”。

| 当前文件/模块 | 迁移后落点 | 角色变化 | 备注 |
| ------------- | ---------- | -------- | ---- |
| `src/core/components/orchestration/board.js` | UI | `Board` façade / runtime host | 不再直接承担最终纯 Core 实现 |
| `src/core/components/orchestration/board-core.js`（新增） | Core | 纯 Core board 实现 | 由当前 `board.js` 拆出 |
| `src/core/components/orchestration/monitor.js` | UI 兼容层 | 逐步退化为 façade / 兼容入口 | 减少一次性改动面 |
| `src/core/components/orchestration/monitor-proxy.js`（新增） | UI | 视口副本、UiRenderer、overlay provider、workflow 挂载 | 与 Worker 交互 |
| `src/core/components/orchestration/monitor-core.js`（新增） | Core | chunk buffer、BaseRenderer、LiveRenderer、render-frame 产出 | Worker 内运行 |
| `src/core/components/orchestration/active-object-manager.js` | Core | 纯 Core AOM | 先去渲染副作用，再迁移 |
| `src/core/components/chunk/` | Core | chunk / object 覆盖与加载管理 | Worker 内运行 |
| `src/core/objects/` | Core + 共享部分依赖 | 对象模型主实现 | 实例只在 Core 长驻 |
| `src/core/range/` | 共享 | 纯数学范围类型 | 两侧共享同一实现 |
| `src/core/utils/math.js` | 共享 | 基础数学类型 | 两侧共享 |
| `src/core/utils/math-algorithm.js` | 共享 | 纯算法 | 两侧共享 |
| `src/core/utils/chain.js` | 共享 | 纯工具函数 | 两侧共享 |
| `src/core/utils/path.js` | UI | DAG / workflow 路径工具 | 与设备图强相关 |
| `src/core/components/renderer/base-renderer.js` | Core | OffscreenCanvas 静态层渲染器 | Worker 内运行 |
| `src/core/components/renderer/live-renderer.js` | Core | OffscreenCanvas 动态层渲染器 | Worker 内运行 |
| `src/core/components/renderer/ui-renderer.js` | UI | DOM canvas overlay 渲染器 | 主线程运行 |
| `src/core/components/renderer/renderer.js` | 共享基类 | canvas 抽象骨架 | 需保持 `HTMLCanvasElement` / `OffscreenCanvas` 兼容 |
| `src/core/bridges/file-operate-bridge-renderer.js` | UI | Tauri IPC 渲染进程桥 | Worker 不能直接用 |
| `src/core/bridges/board-api.js`（新增） | UI | 同线程 / RPC 双实现统一入口 | 工具统一只认它 |
| `src/core/bridges/worker-file-io-host.js`（可选新增） | UI | Worker 文件 IO host | 转发给 renderer bridge |
| `src/core/tools/tool.js` | UI | 兼容期上下文注入与 processor 入口 | 最后再删 `createDeviceContext()` |
| `src/core/tools/creator/*` | UI | 从“对象实例直连”迁到 `BoardApi` | 工具长期持有 `objectId` |
| `src/core/tools/modifier/*` | UI | 从“直接改对象”迁到 `queryObjects + modifyObject` | 同步/异步分层 |
| `src/core/tools/chooser/*` | UI | 从“扫描 board/AOM 实例”迁到 `queryObjects/hitTest` | 命中逻辑转向摘要对象 |
| `src/core/devices-dag/` | UI | 设备图与 workflow 宿主 | 不进入 Worker |
| `src/core/devices/` | UI | 设备节点 | 不进入 Worker |
| `src/core/prefixs/` | UI | prefix / handoff / 路由状态机 | 不进入 Worker |
| `src/core/hit/` | Core | UndoTree 与操作记录 | Worker 内运行 |
| `src/core-worker.js`（新增） | Core 入口 | Worker 启动与消息路由 | 只 import 纯 Core 模块 |

## 文件 IO 补充细节

### 当前 bridge 结构

```
src/core/bridges/
  ├── file-operate-bridge-common.js   # 共享工具函数
  ├── file-operate-bridge-main.js     # Tauri 主进程侧（Rust command）
  ├── file-operate-bridge-renderer.js # 渲染进程侧（通过 Tauri IPC invoke）
  └── tests/
```

迁移后 `bridge-renderer` 仍在 UI 线程（它是 Tauri IPC 的唯一通道）。Core Worker 的文件操作通过 RPC 桥接：

```
Core Worker ──rpc: loadChunk(chunkId)──▶ UI 线程
                                           │
                                     file-operate-bridge-renderer
                                           │
                                     tauri IPC invoke
                                           │
                                     Tauri 主进程 → 文件系统
```

### ChunkLoader 迁移

结合当前代码，`ChunkLoader` 本身**并不直接持有** `fileOperateBridge`；当前文件系统桥接入口主要位于 `Board.loadChunkObjectEntries()`、`Board.saveChunkObjectEntries()` 与私有 `#loadChunk()` 这类 Board 侧流程里。迁移后，`ChunkLoader` 仍负责区块持有与缓冲语义，而真正的文件读取/保存应由 `BoardCore` 通过 RPC/host adapter 协调：

```js
// Core Worker 侧 ChunkLoader
class ChunkLoader {
  #fileRpcBridge; // 内部文件 IO 通道，不走 BoardApi 公共契约

  async loadChunk(chunkId) {
    const rawData = await this.#fileRpcBridge.call("loadChunkData", { chunkId });
    return Chunk.deserialize(rawData);
  }
}
```

> **设计决策**：`loadChunkData` 和 `saveChunkData` 不暴露在 Board API 的公共契约中。`ChunkLoader` 通过 `BoardCore` 构造时注入的内部 `fileRpcBridge` 通道访问文件系统。Board API 只处理工具交互相关的操作（对象创建/修改/查询/命中），文件 IO 是内部实现细节。

## 测试策略

### 测试分层

| 层              | 运行环境           | 覆盖范围                                                    |
| --------------- | ----------------------------- | --------------------------------------------------------------------- |
| 单元测试        | Jest (Node)                   | `range/`、共享 `utils/`、`objects/` 纯逻辑、`hit/` 数据结构           |
| Core 集成测试   | Jest (Node)                   | BoardCore API、AOM、Chunk 管理、UndoTree（不涉及渲染）                |
| Worker 通信测试 | Jest (Node) + fake endpoint   | RPC 消息序列化/反序列化、超时处理、ready/createBoard/createMonitor 等 |
| E2E 测试        | Tauri / Playwright（后续补） | 完整交互流程（需真实 Worker 环境）                                    |

### 单元测试调整

`range/` 和 `objects/` 的现有测试已在 Jest (`node` 环境) 下运行，迁移后不变。

`renderer/tests/` 下的测试需要调整：

- `base-renderer.test.js`、`live-renderer.test.js`：将测试中的 Monitor mock 替换为 MonitorCore mock（使用 OffscreenCanvas）
- `ui-renderer.test.js`：保持 UI 侧，将对象引用替换为 ObjectSummary
- `render-scheduler.test.js`：拆分 base/live 侧到 Core，ui 侧留在 UI

### 新测试文件

| 文件                                                           | 覆盖内容                                                                 |
| -------------------------------------------------------------- | ------------------------------------------------------------------------ |
| `src/core/bridges/tests/board-api-rpc.test.js`                 | `BoardApiRpc` 请求-响应、超时、destroy 清理                              |
| `src/core/tests/core-worker-smoke.test.js`                     | Worker runtime ready / createBoard / createObject / createMonitor smoke |
| `src/core/components/orchestration/tests/monitor-core.test.js` | MonitorCore 离线渲染（无 DOM）                                           |
| `src/core/components/orchestration/tests/monitor-proxy.test.js` | MonitorProxy 画布合成（mock Worker）                                   |
| `src/core/components/orchestration/tests/board-worker-mode.test.js` | `Board.enableWorkerMode()` 与 `createMonitor()` 的 Worker mode 接线 |
| `src/templates/demo/tests/whiteboard-demo-worker-mode.test.js` | demo 配置在 Worker mode 下的输入/创建 smoke |


### E2E / 集成测试适配

结合当前仓库，`src/core/components/tests/board-input-flow.test.js` 实际更接近 **jsdom 集成测试**，而非真正的浏览器 E2E。迁移后它仍可保留为“UI façade + MockWorker”的集成测试入口；真正需要引入 Worker mock 的，是这类在 Jest 环境下手动构造 Board/Monitor 的输入流测试：

```js
// 测试中的 Worker mock
class MockWorker {
  constructor() {
    // 在同线程内模拟 Worker 行为
    this.core = new CoreWorkerSimulator();
  }
  postMessage(msg) {
    setTimeout(() => this.core.onMessage(msg), 0);
  }
}
```

这种同线程模拟可以避免 Jest (`node` 环境) 中 `Worker` API 不可用的问题。
