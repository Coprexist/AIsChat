# 能力懒加载：skills/tools 版本化 + 增量变更注入

> 2026-08-06 珑哥定（原话记录）：
>
> "那不如对比一下每一个AI当前LLM的skills或者tools是否有差异。不过版本更好，这样给每一个LLM存储一下版本号，然后和现有版本号进行对比，如果有差异就注入差异的skills和tools变更通知；注入成功后将版本号更新；compact之后skills和tools直接用最新的就行。这样甚至还能保证每次注入的都有新变化的且只有新变化的，例如我之前注入过一次，那么这次只会注入变化后再变化的；之前变化了的而这次没有变化的变化也在我的LLM里面。"

## 背景问题

平台或世界改动 skills/tools 时，目前**没有懒加载保证**：
- tools 每次请求现算（`get_allowed_tools`），平台/世界一改，下一次请求就带新定义 → 该 AI 所有对话的前缀缓存直接断
- 现有 `pending_system_prompt` 只覆盖 system prompt（已实现：AI 自修改暂存，压缩时切到 current），
  **tools/skills 没有等价机制**（确认：v2.0.5 pending_system_prompt 真实生效于 executor 压缩后 `apply_pending_config`）

## 机制（珑哥方案）

### 版本号（每个 AI 存两份）
- **known_version**（告知进度）：AI 已收到变更通知的版本——控制**增量注入**
- **effective_version**（生效进度）：AI 当前请求实际使用的工具定义版本——控制 **tools 数组**（compact 前保持旧定义，前缀缓存稳定）

### 变更流程
1. 能力源（平台工具 / 世界 skill）变更 → 生成新版本 + 变更摘要（changelog）
2. AI 响应时对比：`known < latest` → 注入**差异部分**（v_known+1 → v_latest 的 changelog 摘要，追加 system 消息）
   ——每次注入的都是新变化、只有新变化；之前注入过的不会重复
3. **注入成功（消息进入上下文）→ known_version 更新为 latest**
4. **compact 之后**：上下文重建（缓存本来就断）→ effective_version = latest，工具定义直接用最新，无需再走增量

### 不变式
- 请求 payload 的 tools 数组 = effective_version 的定义（compact 前不动 → 前缀缓存稳定）
- 变更告知 = 动态尾部 system 消息（不影响前缀）
- 删除的工具：执行时兜底"该工具已下线"（AI 自然学会不用）
- 平台代码发布：旧版本定义保留在 DB，重启后旧对话继续用旧定义请求，等自然 compact 切新版

## 数据模型

- `capability_versions`：**统一能力源版本表**（source, version, changelog, definitions JSONB nullable, created_at）
  - 能力源 = **平台**（platform：内置工具定义）+ **每个世界**（world-{id}：世界 skills 生成的工具定义）
  - 世界 skills/tools **同样版本化**：世界 skill 目录哈希变化 → 新版本 + changelog（新增/修改/删除的 skill 摘要）
  - 平台源存 definitions（内置工具定义快照）；世界源同样存 definitions（该世界 skills 转出的工具定义）——旧版本保留，compact 前照旧用
- `agents.cap_known_versions` JSONB：{source: version} 告知进度
- `agents.cap_effective_versions` JSONB：{source: version} 生效进度

## 落地范围

1. 平台启动：注册内置工具 → 生成定义 → 哈希对比 → 变更则写新版本（旧版本保留）
2. 世界 skill 目录：变更检测（哈希）→ capability_versions 写新版本（含工具定义快照）
3. 注入：build_messages / world_chat_service 时检测落后 → 追加变更通知 system 消息 → 更新 known
4. compact：executor 压缩成功后 effective = latest（扩展 apply_pending_config）
5. 群 AI 世界能力：world_command 稳定工具（缓存友好）+ 能力清单尾部化（后续）
