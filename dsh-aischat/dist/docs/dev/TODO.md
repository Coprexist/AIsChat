# 📋 开发待办

> 维护：本文件记录当前积压的开发任务。完成一项勾掉一项（`- [x]`）。
> 关联记忆：dsh-mneme 侧另有同步存档（侧边栏双板块重构：26d4421c）。

---

## 🔲 侧边栏双板块重构（dsh-aischat 客户端架构改造）

### 需求（用户 2026-08 凌晨确认）

侧边栏两大板块**平级**：

1. **工作区** —— 本身做成可折叠/展开结构，展开后是工作区文件夹和对话（保持 DSH 现有工作区浏览）；
2. **AIsChat** —— 折叠展开外观与工作区**一模一样**，展开后排列置顶私信 / 置顶群聊 / 私信 / 群聊 + 联系人。

点开一个默认折叠另一个。这是对当前"全屏 board 方案"的优化：不再全屏覆盖，AIsChat 直接住在侧边栏里，与工作区平级。

### 官方 slot 架构硬约束（已验证）

- `sidebar.workspaces` 是 **single 槽**，被官方 WorkspaceBrowser（priority 0）占用，**不能 co-register**。
- `sidebar` 也是 single；替换整个侧边栏需重声明 children（sidebar.workspaces / sidebar.settings / sidebar.footer.action），但 children 已被官方声明，**重声明会 throw**（SlotCore.register 检查 `childRec.spec`）。
- 唯一官方机制：**用更低 priority（如 -2）"影子替换" `sidebar.workspaces`**，最低 priority 渲染，官方注册保留（删注册即还原）。
  - 社区验证：`dsh-organizer-sidebar`（npm）即用 priority -2 影子替换并完全自绘工作区浏览区域。

### 社区参考

- [build-deepseek-harness-plugin](https://github.com/oil-oil/build-deepseek-harness-plugin) `references/client-slots-and-theme.md`：sidebar 是 single、替换会丢子槽、优先 `sidebar.footer.action`；不默认替换 root/sidebar/conversation/details。
- `dsh-organizer-sidebar`（npm，v1.0.6）：`priority: -2` 注册 `sidebar.workspaces`，自绘整个浏览区域，官方注册保留。**验证了影子替换可行**。
- `@linxin666/dsh-client-ui-task-board`：DOM hack 插侧边栏入口（`document.querySelector("[data-pane=sidebar]")`）——**不优雅，排除**。
- 官方 master 无侧边栏板块切换（tab/board）类槽，官方不打算做多板块。

### 推荐方案（待用户确认两点后实施）

影子替换 `sidebar.workspaces`（priority -2），自绘"双板块容器"：

1. **板块头区**：`工作区 | AIsChat` 两个折叠展开按钮，外观完全仿官方板块头（sectionHeader 样式 + 文件夹 chevron）。
2. **工作区面板**：用官方 hooks（`useSessions` / `useWorkspaces` standard props）自绘工作区文件夹 + 对话列表，点击仍打开 DSH 会话。
3. **AIsChat 面板**：复用现有联系人列表（置顶私信/置顶群聊/私信/群聊 + 联系人），点击后在主区域渲染对话 + composer（发送到选中的 AIsChat 对话，不碰 DSH 会话语义）。

### 代价 / 风险

- 替换后工作区浏览 = **自绘简版**：官方搜索、拖拽排序、右键菜单、新建工作区对话框等功能会丢失，除非额外复刻。
- 若用户要求**完整保留官方工作区全部功能**，则需换设计（AIsChat 只做折叠展开入口 + 联系人列表，与官方工作区上下排列）——交互上不完全是"平级板块"。

### 待用户决策

- [ ] **a) 板块交互细节**：互斥折叠（点开一个折叠另一个）vs 各自独立折叠？
- [ ] **b) 工作区面板**：自绘简版（功能有损）vs 完整复刻官方（工作量大）？

### 实施步骤（决策后）

- [ ] 1. 改 `dsh-aischat` 客户端：去掉全屏 board（shell.overlay 方案），改为 sidebar 内双板块容器
- [ ] 2. 影子替换 `sidebar.workspaces`（priority -2），自绘板块头 + 工作区列表 + AIsChat 列表
- [ ] 3. 主区域渲染：选中 AIsChat 对话时主区域显示该对话（沿用现有消息/composer 逻辑）
- [ ] 4. 重建（scripts/build.mjs）→ 同步 profile（/root/.dsh/profiles/web/node_modules/dsh-aischat/）→ 页面刷新验证
- [ ] 5. 验证：工作区可正常开会话；AIsChat 板块外观与工作区一致；点开一个折叠另一个；聊天收发正常

---

## 🔲 阶段 2 插件化跟进项（可选）

- [ ] world 分类落地（协议里已留占位，本阶段不实现 —— YAGNI）
- [ ] 前端插件 UI（皮肤/技能插件的用户配置界面）
- [ ] Git 提交本轮变更（提交前检查 .gitignore 排除敏感文件：.env、token.txt 等）
