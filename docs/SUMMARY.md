# AIsChat 文档目录

> **版本**: v3.2.0 | **更新**: 2026-08-10

---

## 📚 文档分类

### 一、产品介绍

| 文档 | 适用人群 | 说明 |
|------|---------|------|
| [README.md](../README.md) | 所有人 | 项目入口，快速开始、核心能力、技术栈 |
| [ABOUT.md](./ABOUT.md) | 所有人 | 产品理念介绍，适合分享给朋友 |
| [ROADMAP.md](../ROADMAP.md) | 所有人 | 路线图，已实现和规划中的功能 |

### 二、用户指南

| 文档 | 适用人群 | 说明 |
|------|---------|------|
| [用户手册.md](./guides/用户手册.md) | 终端用户 | 创建 AI、群聊、私信、记忆、用量等操作指南 |
| [管理与开发者手册.md](./guides/管理与开发者手册.md) | 管理员/开发者 | 部署、架构、排错、WebSocket |
| [创建 AI 流程设计.md](./guides/create_ai_flow_design.md) | 前端开发者 | 三档预设 + 子选项 + 详细设置的交互设计 |
| [故障排查手册.md](./guides/troubleshooting.md) | 管理员/开发者 | 常见问题诊断流程图、错误码速查、一键诊断脚本 |
| [备份与恢复指南.md](./guides/backup_and_recovery.md) | 管理员 | 3-2-1 备份策略、时点恢复、灾难恢复方案 |
| [WebSocket 事件文档.md](./guides/ws_events.md) | 前端/集成开发者 | 所有 WS 事件的 payload 格式、时序图、重连策略 |
| [测试策略文档.md](./guides/test_strategy.md) | 开发者/QA | 测试金字塔、单/集成/E2E 测试规范、CI/CD 集成 |

### 三、服务模块设计

#### 3.1 聊天底层服务

| 文档 | 适用人群 | 说明 |
|------|---------|------|
| [chat_service_design.md](./chat_service/design/chat_service_design.md) | 开发者 | 消息管道、可达性管理、连接管理、联邦协议、ChatApi |
| [federation_url_rotation_protocol.md](./chat_service/protocol/federation_url_rotation_protocol.md) | 联邦开发者 | 联邦连接 URL 轮换与安全策略 |

#### 3.2 AI 底层服务

| 文档 | 适用人群 | 说明 |
|------|---------|------|
| [ai_service_design.md](./ai_service/design/ai_service_design.md) | 开发者 | LLM 调用、工具执行、流式响应、配置管理、额度消耗 |

#### 3.3 AI 薄大脑控制系统

| 文档 | 适用人群 | 说明 |
|------|---------|------|
| [brain_controller_design.md](./brain_controller/design/brain_controller_design.md) | 开发者 | 心跳管理、状态机、冲突仲裁、人格锚点、资源调度 |
| [emotion_state_design.md](./brain_controller/design/emotion_state_design.md) | 开发者 | 情感向量（Plutchik 8 轴）、跨状态情感同步、交接体系、工具按状态隔离 |

#### 3.4 AI 记忆系统

| 文档 | 适用人群 | 说明 |
|------|---------|------|
| [memory_system_design.md](./memory_system/design/memory_system_design.md) | 开发者 | 双重记忆架构、结构化记忆、记忆分发、遗忘机制 |
| [memory_system_overview.md](./memory_system/design/memory_system_overview.md) | 开发者 | 记忆系统核心设计理念 |

#### 3.5 AI 模块化技能管理系统

| 文档 | 适用人群 | 说明 |
|------|---------|------|
| [skill_manager_design.md](./skill_manager/design/skill_manager_design.md) | 开发者 | Skill 分层、声明式依赖、模板引擎、多维触发器、注意力系统 |

### 四、子系统专题

| 文档 | 适用人群 | 说明 |
|------|---------|------|
| [兑换码系统.md](./兑换码系统.md) | 开发者 | 兑换码系统设计与实现 |
| [文件存储与协作系统.md](./文件存储与协作系统.md) | 开发者 | 文件上传、协作模式、引用追踪、配额管理 |

### 四·五、群视界（Group World）专题

| 文档 | 适用人群 | 说明 |
|------|---------|------|
| [群视界设计文档](./group_world/design/group_world_design.md) | 开发者 | 总设计：世界模型、群视界机器人、阶段规划 |
| [群视界实现文档](./group_world/implementation.md) | 开发者 | 实现现状 + 阶段 2 架构决策与踩坑（ADR 风格） |
| [群视界阶段 2 规划](./group_world/plan_phase2.md) | 开发者 | 阶段 2 清单（2.1-2.5 已完成）与估算 |
| [群视界 API 文档](./group_world/api/world_api_docs.md) | 开发者 / 世界 AI | 9 大分区接口手册（变量/文件/积木/群聊/受控 API…） |

### 五、探索与讨论

| 文档 | 适用人群 | 说明 |
|------|---------|------|
| [AIsChat 基于 Agent 的项目探索与架构探讨.md](./exploration/AIsChat 基于 Agent 的项目探索与架构探讨.md) | 研究者/开发者 | 项目探索与架构讨论（原始对话） |
| [AIsChat 重构设计文档.md](./exploration/AIsChat 重构设计文档.md) | 开发者 | 重构设计总览（精简版） |

### 六、技术参考

| 文档 | 适用人群 | 说明 |
|------|---------|------|
| [CODE_WIKI.md](./CODE_WIKI.md) | 开发者/维护者 | **代码 Wiki**：项目架构、模块职责、关键类与函数、依赖关系、API 端点、数据模型、配置部署 |
| [LEARNING_ROADMAP.md](./LEARNING_ROADMAP.md) | 新开发者 | **学习路线图**：5 阶段阶梯式学习，每阶段有目标、必读文件、Mermaid 图表、动手实践任务 |

### 七、项目参考

| 文档 | 适用人群 | 说明 |
|------|---------|------|
| [项目全景报告.md](./reference/项目全景报告.md) | AI 智能体/用户/企业 | 产品白皮书：核心亮点、能力矩阵、架构全景、用户画像 |
| [项目参考.md](./reference/项目参考.md) | 开发者 | 参考项目架构思路和设计亮点 |

### 八、归档文档

| 文档 | 归档位置 | 说明 |
|------|---------|------|
| AI认知架构三空间模型.md | [archive/old_designs/](./archive/old_designs/) | 内容已整合到记忆系统和薄大脑文档 |
| AI对话链机制.md | [archive/old_designs/](./archive/old_designs/) | 内容已整合到聊天服务和薄大脑文档 |
| 记忆架构设计.md | [archive/old_designs/](./archive/old_designs/) | 内容已整合到记忆系统文档 |
| 流式响应系统.md | [archive/old_designs/](./archive/old_designs/) | 内容已整合到 AI 底层服务文档 |
| Skill 的三层设计.md | [archive/old_designs/](./archive/old_designs/) | 内容已整合到技能管理系统文档 |
| AI上下文与状态管理设计.md | [archive/old_designs/](./archive/old_designs/) | 内容已整合到薄大脑文档 |

---

## 🧭 阅读路线

### 快速了解
1. **README.md** → 5 分钟了解项目核心能力
2. **ABOUT.md** → 理解产品理念和价值主张

### 日常使用
1. **用户手册.md** → 完整操作指南

### 部署运维
1. **管理与开发者手册.md** → 从部署到精通
2. **部署合规建议书.md** → 中国境内内容标识 / 拟人化互动服务法规对照与操作建议
3. **故障排查手册.md** → 遇到问题先看这里
4. **备份与恢复指南.md** → 数据安全保障

### 前端开发
1. **WebSocket 事件文档.md** → 实时通信完整参考
2. **测试策略文档.md** → 测试规范和 CI/CD 集成

### 代码学习（新开发者推荐）
1. **CODE_WIKI.md** → 代码 Wiki，了解架构、模块、API、数据模型
2. **LEARNING_ROADMAP.md** → 学习路线图，按 5 阶段循序渐进
3. **项目全景报告.md** → 产品全景，理解设计理念和能力边界

### 深入技术
1. **chat_service_design.md** → 聊天底层服务
2. **ai_service_design.md** → AI 底层服务
3. **brain_controller_design.md** → 薄大脑控制系统
4. **memory_system_design.md** → 记忆系统
5. **skill_manager_design.md** → 技能管理系统

---

## 📝 文档规范

### 文件命名
- **设计/实现类文档**：使用蛇形命名（snake_case），如 `chat_service_design.md`
- **其他文档**：使用中文标题，如 `用户手册.md`

### 语言规范
- 使用中文撰写
- 术语统一，避免歧义
- 代码块使用正确的语言标记
- 图表使用 Mermaid 语法

### 结构规范（设计类文档）
1. 文档标题
2. 元信息（服务定位、版本、日期、文档规范）
3. 目录（带锚点链接）
4. 正文章节（按逻辑顺序组织）
5. 关键文件索引
6. API 端点（如适用）

### 更新流程
- 修改文档时同步更新版本号
- 重要变更记录在 CHANGELOG.md
- 跨文档引用使用相对路径

---

*文档版本: v3.2.0 | 最后更新: 2026-08-10*
