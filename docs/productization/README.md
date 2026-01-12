# 自动样本合成系统产品化文档目录

## 📚 文档结构

本目录包含自动样本合成系统（Automated Agent Evaluation Sample Synthesis System）的完整产品化设计文档。

---

## 🎯 核心文档

### 1. [product_specification.md](./product_specification.md) - 产品规格说明书 ⭐⭐⭐⭐⭐
**最重要的文档**，包含完整的产品化方案设计。

**内容概览**：
- 项目目标与核心需求
- 分层Agentic Loop完整架构设计
- 各层详细规格说明（Layer 1-4 + 决策层）
- 智能问题路由机制
- 迭代预算与停止条件
- 技术决策rationale
- 实施路线图（3个Phase）

**适合人群**：
- 想要全面了解系统设计的所有人
- 负责架构设计的技术Leader
- 需要评估方案可行性的决策者

**关键章节**：
- 🏗️ 整体架构（第24行）
- 📊 架构层次详解（第52行）
- 🔧 关键技术决策（第318行）
- 🚀 实施路线图（第438行）

---

### 2. [architecture_agentic_loop.svg](./architecture_agentic_loop.svg) - 架构可视化图 ⭐⭐⭐⭐
**系统架构的视觉呈现**，展示跨层迭代优化的完整流程。

**图表内容**：
- Orchestrator Agent（全局决策中心）
- Init Phase：Layer 1场景理解与设计
- Execute Phase：Layer 2-4的迭代循环
- 决策层：智能问题路由
- 反馈箭头：展示问题如何路由回各层修复
- 人工介入点：标注需要人工Review的环节

**适合人群**：
- 需要快速理解系统架构的技术人员
- 向非技术人员展示系统设计
- 架构Review和讨论

**关键要素**：
- 蓝色区域：Init Phase（单次执行）
- 绿色区域：Execute Phase（迭代循环）
- 黄色框：人工Review Checkpoint
- 粉色虚线箭头：问题修复的反馈路径

---

### 3. [iteration_strategy_redesign.md](./iteration_strategy_redesign.md) - 迭代策略重新设计 ⭐⭐⭐⭐⭐
**🔥 重要设计更新**：基于质量收敛的动态停止策略，替代原来过于保守的固定次数限制。

**核心改进**：
- 从"全局5次硬限制"改为"质量收敛自动停止，100次硬限制"
- 引入软限制（触发审查）和硬限制（强制停止）两层机制
- Layer 3从"3次硬限制"提升到"20次软限制，50次硬限制"
- 4个智能停止策略：质量收敛检测、成本效益分析、问题类型识别、震荡检测

**适合人群**：
- 所有参与实施的人（这是关键设计决策）
- 关心"为什么不限定死迭代次数"的人
- 需要理解系统如何智能停止的开发者

**关键洞察**：
- 任务复杂度高，固定5次远远不够
- 简单场景4次达标，复杂场景可能需要30+次
- 用"质量是否改善"而非"迭代了多少次"来判断

---

### 4. [bloom_case_study.md](./bloom_case_study.md) - Bloom框架案例研究 ⭐⭐⭐⭐
**深度分析Anthropic Bloom框架的实际案例**，提取设计经验和改进方向。

**内容概览**：
- Bloom框架的4阶段流程详解
- personal-work-assistant场景完整分析
- 可借鉴的5个优秀设计模式
- Bloom的4个局限性及改进方案
- 对产品化系统的具体启示
- 与Universal Framework的对比

**适合人群**：
- 想深入理解Bloom框架的研究人员
- 负责Layer设计的开发者（特别是Layer 1和Layer 3）
- 需要了解"为什么这样设计"的团队成员

**关键发现**：
- ✅ 借鉴：渐进式难度、自然交互、多能力交织
- ⚠️ 改进：真实执行代替LLM模拟、增加Ground Truth
- 💡 启示：Layer 1需深度理解、Layer 3需自然风格

---

## 📊 辅助文档

### 4. [architecture_overview.svg](./architecture_overview.svg) - 架构概览图
**简化版架构图**，展示4个Layer的基本关系和参考机制融合。

**适合**：初次接触项目的人快速了解整体结构。

---

### 5. [mvp_implementation_guide.md](./mvp_implementation_guide.md) - MVP实施指南
**Phase 1 MVP的详细实施计划**（如果已有）。

**内容**：
- MVP目标和验证点
- 核心模块实现计划
- 测试策略

---

### 6. [universal_framework_productization.md](./universal_framework_productization.md) - 产品化早期讨论
**早期的产品化思路探讨**（历史文档）。

**说明**：这是在确定最终方案前的初步讨论，主要保留作为设计演进的历史记录。

---

## 🗺️ 文档阅读路径

### 路径1：快速了解（15分钟）
推荐给：项目新成员、需要快速overview的人

1. 阅读本README了解文档结构
2. 查看 `architecture_agentic_loop.svg` 理解整体架构
3. 阅读 `product_specification.md` 的"项目目标"和"整体架构"章节

### 路径2：技术深入（1-2小时）
推荐给：负责实施的技术人员

1. 完整阅读 `product_specification.md`
2. 对照 `architecture_agentic_loop.svg` 理解各层交互
3. 阅读 `bloom_case_study.md` 中"对产品化系统的启示"章节
4. 查看对应Layer的详细规格说明

### 路径3：设计研究（2-3小时）
推荐给：架构师、研究人员

1. 先读 `bloom_case_study.md` 了解参考框架分析
2. 完整阅读 `product_specification.md`
3. 重点关注"关键技术决策"章节的rationale
4. 对比Bloom和Universal Framework的设计差异

---

## 🔑 关键概念速查

### 分层Agentic Loop
- **定义**：结合Workflow（Layer 1）和Agentic Loop（Layer 2-4）的混合架构
- **核心特点**：Init-Execute分离、跨层反馈、智能路由、成本可控
- **详细说明**：product_specification.md 第24行

### 智能问题路由
- **作用**：根据归因结果自动将问题路由到对应层修复
- **路由逻辑**：Layer 3问题→自动修复、Layer 2问题→自动修复、Layer 1问题→人工介入
- **详细说明**：product_specification.md 第200行

### Ground Truth
- **Bloom的局限**：LLM主观判断，缺乏精确验证
- **我们的方案**：expected_final_state提供精确的Ground Truth
- **详细对比**：bloom_case_study.md 第XX行

### 迭代预算（已更新）
- **旧设计**：Layer 1=1次、Layer 2=2次、Layer 3=3次、全局=5次（过于保守）
- **新设计**：采用软限制+硬限制两层机制
  - **Layer 1**: 3次软限制，5次硬限制
  - **Layer 2**: 10次软限制，30次硬限制
  - **Layer 3**: 20次软限制，50次硬限制
  - **全局**: 质量收敛自动停止，100次硬限制
- **核心停止条件**：质量达标（85%）、质量收敛（连续5次改善<2%）、陷入震荡、根本性问题
- **详细说明**：iteration_strategy_redesign.md

### Skills知识库机制
- **定位**：将已开发场景的样本、格式文档、代码模板作为可复用的知识库
- **资源类型**：参考样本、业务规则、格式规范、代码模板、设计模式、经验教训
- **应用方式**：
  - Layer 1：推荐相似场景的BusinessRules和设计模式
  - Layer 2：提供代码模板和最佳实践
  - Layer 3：参考成功的样本模式和prompt风格
  - Layer 4：查询历史归因经验快速定位根因
- **预期价值**：减少50-70%设计时间、避免重复错误、知识持续沉淀
- **详细说明**：product_specification.md 第451行

---

## 📞 文档维护

### 文档版本
- product_specification.md: v1.0 (2025-12-31)
- bloom_case_study.md: v1.0 (2025-12-31)
- architecture_agentic_loop.svg: v2.0 (2025-12-31，字体放大版本)

### 更新记录
- 2025-12-31: 初始版本创建，核心文档完成
- 2025-12-31: 增加Bloom案例研究文档
- 2025-12-31: 创建文档导航README

### 后续计划
- [ ] Phase 1 MVP实施后，增加实际开发经验总结
- [ ] 补充各Layer的详细设计文档
- [ ] 增加常见问题FAQ

---

## 🎯 下一步行动

根据当前项目进度，建议的下一步：

### 如果要开始实施
1. 成立开发小组，分配各Layer负责人
2. 阅读 `product_specification.md` 的"实施路线图"章节
3. 按Phase 1 MVP计划开始核心模块开发

### 如果要继续设计
1. 深入阅读 `bloom_case_study.md` 的"具体行动项"
2. 基于启示优化各Layer的设计细节
3. 补充Layer级别的详细设计文档

### 如果要评审方案
1. 组织架构评审会议
2. 使用 `architecture_agentic_loop.svg` 讲解整体设计
3. 重点讨论"关键技术决策"的合理性

---

**文档目录结束**
