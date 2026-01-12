# 自动样本合成系统产品化方案

> ⚠️ **DEPRECATED** - 本文档已过时，包含早期设计思路和错误目标设定。
>
> **当前有效文档**：
> - 系统目标和原则：`../../README.md`
> - Init Agent行为规范：代码 `agents/init_agent.py::get_system_prompt()`
> - Execute Agent行为规范：代码 `agents/execute_agent.py::get_system_prompt()`
>
> 本文档保留仅供参考历史设计演进。

## 📋 文档版本
- **版本号**: v1.0 (deprecated)
- **创建日期**: 2025-12-31
- **废弃日期**: 2026-01-08
- **负责人**: Universal Scenario Framework Team
- **文档状态**: 已废弃，请参考最新README.md

---

## 🎯 项目目标

**核心目标**: 构建一个能够自动合成高质量Agent评测样本的系统，支持跨层迭代优化和智能问题修复。

**关键需求**:
1. **自动化程度高**: 减少人工介入，提高生产效率
2. **样本质量高**: 生成的样本具有真实业务逻辑和评测难度
3. **可扩展性强**: 支持不同业务场景和能力维度
4. **可恢复性**: 长任务支持中断和恢复
5. **成本可控**: 避免无限循环，迭代次数有上限

---

## 🏗️ 整体架构

### 架构类型: **Harness + 双 Agent 协作**

系统采用 **Orchestrator（Harness）+ Init/Execute 双 Agent** 的架构模式，结合 **状态门控** 和 **跨层迭代优化** 机制。

参考架构图: `architecture_agentic_loop_v4.svg`

### 核心组件

```
┌─────────────────────────────────────────────────────────┐
│         Orchestrator (Harness/Coordinator)              │
│         ├─ 状态管理 (State Machine)                     │
│         ├─ Checkpoint & Resume                          │
│         ├─ 状态门控 (Gate Keeping)                      │
│         └─ Agent 协调                                   │
└──────────────┬──────────────────────────────────────────┘
               │
               ├─── Init Agent (自治)
               │     └─ Layer 1: 场景理解与设计
               │
               └─── Execute Agent (自治)
                     ├─ Layer 2: 组件代码生成
                     ├─ Layer 3: 样本合成
                     ├─ Layer 4: 自动评测与归因
                     └─ 内部决策: 质量收敛与问题路由
```

### 架构说明

**Orchestrator 的定位**：
- ❌ **不是** Leader Agent（不做业务决策）
- ✅ **是** Harness/Coordinator（状态管理 + 质量门控）
- 类比：工头 + 质检员

**Orchestrator 的职责**：
1. **状态管理**：维护全局状态机，记录当前进度
2. **Checkpoint/Resume**：支持任务暂停和恢复
3. **状态门控**：检查前置条件，控制状态转换（如：必须有 unified_scenario_design.yaml 才能进入 Execute）
4. **Agent 协调**：控制 Init/Execute 的切换和 handoff
5. **HITL 管理**：处理 3 个人工介入点的交互

**Init/Execute Agent 的自治性**：
- ✅ **完全自主决策**：不受 Orchestrator 指挥
- ✅ **内部循环控制**：自己决定是否继续迭代
- ✅ **问题归因和路由**：Execute Agent 自己分析问题并决定修复策略
- ✅ **只受 Gate 约束**：只在状态转换时接受 Orchestrator 的前置条件检查

---

## 📊 架构层次详解

### **Layer 1: 场景理解与设计 (Init Phase)**

**执行模式**: 单次执行 + 人工Review

**输入**:
- 用户描述的业务场景

**处理流程**:
1. 深度理解业务场景（参考Bloom Understanding）
2. 设计评测场景结构（参考Bloom Ideation）
3. 生成配置文件（unified_scenario_design.yaml）
4. 生成业务规则文档（BusinessRules.md）
5. 生成格式规范（format_specifications.json）

**输出**:
- unified_scenario_design.yaml
- BusinessRules.md
- format_specifications.json

**人工介入点**:
- ✅ **必须**: 用户Review并确认设计后才能继续

**使用模型**:
- Claude Sonnet 4.5 + Extended Thinking（高质量深度理解）

**Checkpoint**: `scenario_design.checkpoint`

---

### **Layer 2: 组件代码生成 (Execute Phase)**

**执行模式**: 自动生成 + 独立测试 + 自动修复

**输入**:
- unified_scenario_design.yaml

**处理流程**:

**Phase 2.1: 代码生成**
1. **并行生成**（可独立执行）:
   - Tools生成（tools/*.py）
   - Checkers生成（checkers/*.py）
   - Prototypes生成（prototypes/*.py）
   - 数据池生成（data_pools/*.json）

2. **顺序生成**（依赖上述结果）:
   - Multiturn simulator生成
   - Sample generator实现

**Phase 2.2: 自动化单元测试**（新增）
1. **自动生成测试代码**:
   - Tool功能测试（基本功能、参数验证、返回格式、边界情况）
   - Checker逻辑测试（正向case、负向case、阈值测试、边界情况）
   - Tool-Checker集成测试（验证Tool执行后Checker判断正确）

2. **准备测试数据**:
   - 生成小规模测试数据池
   - 包含正常case和边界case

3. **执行测试并生成报告**:
   - 执行所有单元测试（约15秒）
   - 生成详细测试报告
   - 识别测试失败的具体原因

**测试目标**: 及早发现Tool和Checker的低级错误，避免等到样本级评测才发现问题

**输出**:
- tools/*.py
- checkers/*.py
- prototypes/*.py
- data_pools/*.json
- multiturn_simulator.py
- sample_generator.py
- test_report.json（测试报告）

**可自动修复的问题**:
- ✅ Tool参数验证bug
- ✅ Tool返回格式错误
- ✅ Checker阈值设置问题（如浮点数精度）
- ✅ Checker边界判断逻辑简单错误
- ⚠️ 复杂的业务逻辑bug需要回到Layer 1

**人工介入点**:
- ❌ **无需人工介入**: Agent自动生成代码和测试，自动修复失败，测试通过后自动进入Layer 3
- ⚠️ 如果达到硬限制（30次）仍无法通过测试，说明存在Layer 1设计问题，应触发HITL-3返回Init Agent重新设计

**迭代预算**: 软限制10次，硬限制30次

**使用模型**:
- GPT-4o（代码生成任务，成本适中）

**Checkpoint**:
- `tool_{tool_name}.checkpoint`
- `checker_{checker_id}.checkpoint`
- `prototype_{prototype_id}.checkpoint`
- `data_pool.checkpoint`

---

### **Layer 3: 样本合成 (Execute Phase)**

**执行模式**: 组合式生成 + 可自动修复

**输入**:
- Layer 2的所有组件
- unified_scenario_design.yaml中的coverage_matrix

**处理流程**:
1. 根据coverage matrix生成样本维度组合
2. 从data pool中采样实体数据
3. 生成user_simulator_prompt
4. 生成initial_state
5. 计算expected_final_state（Ground Truth）
6. 组装完整的可执行样本

**输出**:
- samples/*.json（每个样本包含完整的执行环境）

**可自动修复的问题**:
- ✅ User simulator prompt太严格（放宽STOP条件）
- ✅ 数据池数据不合理（重新采样）
- ✅ User simulator执行偏离设计（重新生成）

**迭代预算**: 最多3次自动修复

**使用模型**:
- GPT-4o（样本组合和prompt生成）

**Checkpoint**:
- `sample_{sample_id}.checkpoint`

---

### **Layer 4: 自动评测与归因 (Execute Phase)**

**执行模式**: 真实执行 + 自动归因 + 首次人工校验

**输入**:
- samples/*.json

**处理流程**:
1. **真实执行样本**（关键区别于Bloom）:
   - 初始化真实数据库状态
   - 运行用户模拟器 vs 目标模型的对话
   - 使用真实的Python工具代码
   - 记录完整对话历史和工具调用

2. **自动评测**:
   - Checker验证（精确判断）
   - LLM综合评判（补充Checker无法覆盖的部分）

3. **智能归因**（参考两层失败分析框架）:
   - 业务失败原因分析
   - 过程违规行为分析
   - 分类问题根因：Agent能力 vs 样本设计 vs 系统问题 vs 用户模拟器问题

4. **首次归因校验**（新场景必须）:
   - 选取2-3个典型失败case
   - 人工校验LLM归因的准确性
   - 修正错误归因并记录归因模式
   - 建立归因基准线，指导后续自动归因

**输出**:
- 评测结果（成功率、失败case列表）
- 归因分析报告
- 问题分类和修复建议
- attribution_calibration.json（归因校验记录）

**人工介入点**:
- ⚠️ **条件触发 - 首次归因校验**:
  - 触发条件: 新场景的首次评测
  - 校验内容: 人工校验2-3个典型失败case的归因准确性
  - 目的: 建立归因基准线，避免错误归因导致错误修复
  - 频率: 新场景约20%触发（首次必须，后续基于已建立的归因基准）

**归因校验流程**:
```
首次评测完成
    ↓
系统自动归因所有失败case
    ↓
选取2-3个典型case
    ↓
👤 人工校验归因（必须）
    ├─ 归因正确 → 确认
    └─ 归因错误 → 修正并记录模式
    ↓
优化归因prompt
    ↓
继续自动归因其他case
```

**质量阈值**: 成功率 ≥ 85%

**使用模型**:
- 目标模型（被测试的Agent）
- Claude Sonnet 4.5（评测和归因）

**Checkpoint**:
- `evaluation_{iteration}.checkpoint`

---

## 🔄 Orchestrator：状态管理与门控

**定位**: Harness/Coordinator（**不做业务决策**）

**核心职责**:

### 1. 状态管理

维护全局状态机，追踪系统进度：

```python
class WorkflowState(Enum):
    INIT_PHASE = "init_phase"              # Init Agent 工作中
    INIT_HITL_WAITING = "init_hitl"        # 等待 HITL-1
    EXECUTE_PHASE = "execute_phase"        # Execute Agent 工作中
    EXECUTE_HITL_WAITING = "execute_hitl"  # 等待 HITL-2
    LAYER1_PROBLEM_HITL = "layer1_hitl"    # 等待 HITL-3
    COMPLETED = "completed"                # 任务完成
```

### 2. Checkpoint & Resume

**Checkpoint 触发点**：
- HITL 之前（保存等待人工的状态）
- Handoff 时（Init ↔ Execute 切换）
- 每次迭代结束（Execute Agent 完成一轮）
- 用户主动暂停（Ctrl+C）

**Resume 场景**：
```bash
$ python main.py --resume checkpoint_2026-01-04_execute_phase

[恢复任务]
- 场景: leave_application
- 当前状态: Execute Agent 迭代中
- 总迭代: 8次，当前质量: 72%
- 下一步: 继续 Layer 3 优化

是否继续？(y/n)
```

### 3. 状态门控（Gate Keeping）

在状态转换前检查前置条件：

**Init → Execute 的 Gate**：
- ✅ unified_scenario_design.yaml 存在且有效
- ✅ BusinessRules.md 存在
- ✅ format_specifications.json 存在
- ✅ HITL-1 已批准

**Execute → Init 的 Gate**：
- ✅ 已完成至少一轮 Execute 迭代
- ✅ 归因分析已完成
- ✅ 识别出 Layer 1 级别问题
- ✅ HITL-3 已决定修改 Layer 1

**Layer 2 完成的 Gate**：
- ✅ 所有 tools 已生成
- ✅ 所有 checkers 已生成
- ✅ 单元测试已通过

### 4. Execute Agent 的内部决策逻辑

**注意**：以下决策由 **Execute Agent 自己做**，不是 Orchestrator 做：

**问题分类与路由**:

| 问题类型 | 占比 | 路由目标 | 修复方式 | 自动化程度 |
|---------|------|---------|---------|-----------|
| Layer 3问题 | 30% | Layer 3 | 放宽prompt、重采样数据 | ✅ 80-90% |
| Layer 2问题 | 25% | Layer 2 | 调整阈值、修复简单bug | ✅ 60-70% |
| Layer 1问题 | 15% | HITL-3 | 修改场景设计（需人工） | ❌ 人工决策 |
| Agent能力问题 | 20% | N/A | 不修复系统 | N/A |
| 用户模拟器问题 | 10% | Layer 3 | 重新生成simulator | ✅ 100% |

**路由逻辑**（基于动态收敛策略）:
```python
# 优先级从高到低检查
if 成功率 >= 85%:
    输出最终结果
    ✅ 质量达标
elif 质量收敛（连续5次迭代改善<2%）:
    停止迭代
    ⏸️ 质量已到瓶颈，继续无意义
elif 陷入震荡（质量反复上下波动）:
    停止迭代
    ⏸️ 需要改变策略或人工介入
elif Critical问题占比 > 30%:
    停止迭代并触发HITL-3
    ⏸️ 根本性设计问题，需人工重新评估
elif 同一critical问题反复出现 >= 3次:
    停止迭代并触发HITL-3
    ⏸️ 自动修复无效，需人工介入
elif 成本效益比过低:
    停止迭代
    ⏸️ 继续修复不划算
elif 某层达到硬限制:
    停止迭代
    ⏸️ 防止真正失控
elif 可自动修复 and 在软限制内:
    回到对应层自动修复
    继续迭代
elif 可自动修复 but 超过软限制:
    审查是否值得继续
    if 值得: 继续迭代
    else: 停止并给出建议
else:
    停止迭代
    👤 用户选择下一步
```

**核心停止条件**（优先级排序）:
1. ✅ **质量达标**：成功率≥85%
2. 🔄 **质量收敛**：连续5次迭代改善<2%（已到瓶颈）
3. 🔄 **陷入震荡**：质量反复上下波动（需改变策略）
4. ⏸️ **根本性问题**：Critical问题占比>30%或同一问题反复≥3次 → 触发HITL-3
5. 💰 **成本效益差**：继续修复的预期收益<成本
6. 🛑 **硬限制**：Layer达到硬限制（L1:5次，L2:30次，L3:50次，全局:100次）
7. 👤 **用户停止**：用户选择停止

**与旧设计的关键区别**:
- ❌ 旧设计：全局5次就强制停止
- ✅ 新设计：基于质量收敛智能停止，最多允许100次
- ❌ 旧设计：Layer 3只能修复3次
- ✅ 新设计：Layer 3可以修复20次（软限制），最多50次（硬限制）

**Orchestrator 的角色**：
- Orchestrator **不参与**上述决策逻辑
- Execute Agent 完成一轮迭代后，返回结果给 Orchestrator
- Orchestrator 只负责：
  - 记录状态（质量、迭代次数等）
  - 创建 Checkpoint
  - 如果 Execute Agent 返回 "need_layer1_fix"，则触发 HITL-3 并准备 handoff

**详细设计文档**: 参见 `orchestrator_redesign.md`

---

## 🔗 Context 传递策略

### 核心设计原则（v2.0）

双 Agent 架构的关键是合理的 context 传递策略，采用 **"落盘 + 路径传递 + 按需加载"** 机制：

1. **落盘优先**：所有执行数据（样本、轨迹、评测结果、归因分析）完整落盘，永久可追溯
2. **路径传递**：Context 中只传递文件路径和索引，不传递完整内容，保持轻量（2K-5K tokens）
3. **按需加载**：Init Agent 根据问题复杂度自主决定读取深度，建议控制在约40K tokens

**核心价值**：
- ✅ 完整性：所有数据落盘，可调试、可追溯
- ✅ 轻量性：Context 本身很小，不会打满窗口
- ✅ 灵活性：Agent 根据需要自主决定加载策略
- ✅ 工程化：符合生产环境最佳实践

### Handoff 1: Init → Execute

**传递内容（路径方案 v2.0）**：

```json
{
  "version": "2.0",
  "handoff_type": "init_to_execute",
  "user_requirement": "原始用户需求",
  "design_artifacts": {
    "unified_scenario_design_path": "path/to/yaml",
    "business_rules_path": "path/to/BusinessRules.md",
    "format_specifications_path": "path/to/format.json"
  }
}
```

**设计考虑**：
- Execute Agent 只需要知道配置文件路径，自己读取
- 配置文件本身就是完整的设计文档
- Context 大小：约 200-300 tokens

### Handoff 2: Execute → Init

**数据落盘结构**：

```
scenarios/leave_application/execution_outputs/iteration_12/
├── samples/                     # 所有样本
├── execution_traces/            # 每个样本的执行trace（conversation + tools + states）
├── evaluation_results/          # checker结果 + LLM评判
├── attribution_analysis/        # 详细归因分析
├── failure_summary.json         # 失败样本汇总
└── layer1_problems_report.json  # Layer 1问题详细报告
```

**传递内容（路径方案 v2.0）**：

```json
{
  "version": "2.0",
  "handoff_type": "execute_to_init",
  "execution_output_dir": "scenarios/.../execution_outputs/iteration_12",
  "trigger_reason": "Critical问题占比35%，超过30%阈值",
  "iteration_summary": {
    "total_iterations": 12,
    "final_quality": 0.67,
    "total_samples": 27,
    "failed_samples": 18
  },
  "failure_samples_index": [
    {
      "sample_id": "BS_MT_001",
      "sample_path": "samples/BS_MT_001.json",
      "trace_path": "execution_traces/BS_MT_001_trace.json",
      "attribution_path": "attribution_analysis/BS_MT_001_attribution.json",
      "failure_type": "Layer1_BusinessRule",
      "priority": "high"
    }
    // ... 其他失败样本
  ],
  "layer1_problems_report_path": "layer1_problems_report.json",
  "modification_suggestions_summary": [
    "在BusinessRules明确余额扣减时机",
    "调整checker浮点数容忍度"
  ]
}
```

**设计考虑**：
- Context 本身只传路径和索引：2K-5K tokens
- Init Agent 根据需要自主决定读取深度：
  - 可以只读问题报告摘要
  - 可以读取几个典型case的详细内容
  - 可以深度分析所有case
  - 可以对长对话历史按需截断
  - 建议控制在约40K tokens，但可根据问题复杂度调整

**详细设计文档**: 参见 `context_strategy.md`

---

## 👥 人工介入点总览

系统设计了**3个Human-in-the-Loop (HITL)介入点**，遵循"最小化但不可省略"的原则：

### HITL-1: Layer 1场景设计完成（必须，100%触发）
**位置**: Init Phase结束
**触发条件**: Layer 1生成unified_scenario_design.yaml后
**介入方式**:
- 人工Review场景设计的合理性
- 确认业务规则定义
- 验证coverage matrix设计
**后续行动**:
- ✅ 确认 → 进入Execute Phase
- ❌ 拒绝 → 重新设计Layer 1

**为什么必须**:
- 场景设计是创造性工作，需要人类判断
- 设计错误会影响所有后续层
- 确保用户对场景有最终控制权

---

### HITL-2: Layer 4首次归因校验（条件触发，新场景约20%）
**位置**: Layer 4第一次评测完成后
**触发条件**:
- 新场景的首次评测
- 或已有场景增加新的能力维度

**介入方式**:
- 系统选取2-3个典型失败case
- 人工验证LLM归因的准确性
- 修正错误归因模式并记录
- 优化归因prompt

**后续行动**:
- 📝 建立该场景的归因基准线
- 🔄 基于修正后的归因继续迭代

**为什么条件触发**:
- 首次归因可能不准确，会导致错误修复方向
- 建立基准线后，后续归因可以完全自动化
- 老场景如果归因已经稳定，无需每次校验

---

### HITL-3: Layer 1级别问题（条件触发，约15%）
**位置**: 决策层检测到Layer 1级别问题
**触发条件**:
- Critical问题占比>30%
- 同一critical问题反复出现≥3次
- 质量长期无法改善（陷入震荡或收敛于低水平）

**介入方式**:
- 展示Execute Agent的问题分析报告
- 说明为什么自动修复无效（归因为Layer 1设计问题）
- 展示具体的修改建议
- 用户判断是否同意Agent的归因：
  - **y（同意）**: 确实是Layer 1设计问题，同意修改设计
  - **n（不同意）**: 不认同归因或不想改了，接受当前质量

**后续行动**:
- **y（同意修改）** → Handoff回Init Agent，重新设计Layer 1，重置Execute Phase
- **n（接受现状）** → 停止迭代，输出当前状态的评测报告

**为什么条件触发**:
- 85%的问题可通过Layer 2-3自动修复
- 仅在根本性设计缺陷时才需要重新设计

---

### 人工介入点对比

| HITL点 | 触发频率 | 介入类型 | 耗时 | 可跳过 |
|--------|---------|---------|------|--------|
| **HITL-1**: Layer 1设计 | 100% | 必须 | 10-20分钟 | ❌ |
| **HITL-2**: Layer 4首次归因 | ~20% | 条件 | 3-5分钟 | ✅ |
| **HITL-3**: Layer 1问题 | ~15% | 条件 | 15-30分钟 | ✅ |

**总体人工介入时间**:
- 最少：10-20分钟（只有HITL-1，顺利场景）
- 一般：15-25分钟（HITL-1 + HITL-2，新场景）
- 较多：25-50分钟（HITL-1 + HITL-2 + HITL-3，复杂场景）

---

## 🔄 完整执行流程

### 1. 用户输入阶段
```
用户输入: "请生成请假申请场景的评测样本"
    ↓
系统解析需求
```

### 2. Init Phase
```
Layer 1: 场景设计
    ├─ 理解请假业务逻辑
    ├─ 生成unified_scenario_design.yaml
    │   ├─ 定义5个工具（查询员工、创建申请、更新余额等）
    │   ├─ 定义8个checker（申请创建、余额扣减等）
    │   └─ 设计coverage matrix（3个维度 × 3种情况 = 27个组合）
    └─ 生成BusinessRules.md
    ↓
👤 人工Review Checkpoint
    用户确认设计 ✓
```

### 3. Execute Phase - Iteration 1
```
Layer 2: 组件生成（并行）
    ├─ 生成5个tools/*.py
    ├─ 生成8个checkers/*.py
    ├─ 生成prototypes/*.py
    └─ 生成data_pools/employees.json（100个员工数据）
    ↓
Layer 3: 样本合成
    ├─ 根据coverage matrix生成27个样本
    ├─ 每个样本包含: user_simulator_prompt + initial_state + expected_final_state
    └─ Checkpoint: 27个样本
    ↓
Layer 4: 评测
    ├─ 真实执行27个样本
    ├─ 成功率: 18/27 = 67% (未达标)
    └─ 归因分析:
        ├─ 6个失败: "用户模拟器STOP条件太严格" → Layer 3问题
        ├─ 2个失败: "Checker阈值设置错误" → Layer 2问题
        └─ 1个失败: "Agent未收集现金流信息" → Agent能力问题
    ↓
决策层:
    ├─ Layer 3问题可自动修复 ✓
    ├─ Layer 2问题可自动修复 ✓
    └─ 继续迭代
```

### 4. Execute Phase - Iteration 2
```
Layer 2: 修复
    └─ 调整2个checker的阈值
    ↓
Layer 3: 修复
    └─ 放宽6个样本的STOP条件
    ↓
Layer 4: 重新评测
    ├─ 成功率: 23/27 = 85% ✅ 达标！
    └─ 4个仍失败的case归因:
        └─ 全部为"Agent能力问题"（不修复系统）
    ↓
决策层: 成功率达标，停止迭代
```

### 5. 输出最终结果
```
📊 评测报告:
    ├─ 总样本数: 27
    ├─ 成功率: 85%
    ├─ 迭代次数: 2
    ├─ 失败案例归因:
    │   └─ Agent能力问题: 4个（Agent未主动收集必要信息）
    └─ 优化建议:
        └─ 考虑在BusinessRules中更明确强调"必须主动收集现金流信息"
```

---

## 🔧 关键技术决策

### 1. 为什么是分层Agentic Loop而不是纯Workflow？

**纯Workflow的问题**:
- ❌ 无法自动优化样本质量
- ❌ 发现问题必须人工介入
- ❌ 迭代效率低

**纯Agentic Loop的问题**:
- ❌ 复杂度极高
- ❌ 成本难以控制（可能无限循环）
- ❌ 调试困难

**分层Agentic Loop的优势**:
- ✅ 支持跨层自动修复（Layer 2-3问题）
- ✅ 关键决策需人工（Layer 1级别问题）
- ✅ 迭代次数有限（成本可控）
- ✅ 智能问题路由（自动分类和修复）

### 2. 为什么Layer 1必须是单次执行？

**原因**:
- 场景设计是**创造性工作**，需要人类判断
- 自动迭代容易偏离用户意图
- 设计错误的代价很高（后续所有层都会受影响）
- 需要确保用户对场景设计有最终控制权

### 3. 为什么Layer 4要真实执行而不是LLM模拟？

**Bloom的LLM模拟问题**:
- ❌ Tool响应是LLM生成的，无逻辑一致性保证
- ❌ 缺乏Ground Truth，只有LLM主观判断
- ❌ 无法测试复杂的业务规则

**真实执行的优势**:
- ✅ 使用真实的Python代码和数据库
- ✅ 有明确的expected_final_state作为Ground Truth
- ✅ Checker可以精确验证结果
- ✅ 可以支持复杂的多步骤业务流程

### 4. 为什么采用动态收敛策略而非固定次数限制？

**⚠️ 重要设计更新**：经过重新评估，我们采用**基于质量收敛的动态停止策略**，而不是简单的固定次数限制。

**新的迭代策略**:
```python
# 软限制（触发额外审查）
Layer 1: 3次软限制，5次硬限制
Layer 2: 10次软限制，30次硬限制
Layer 3: 20次软限制，50次硬限制
全局:   质量收敛自动停止，100次硬限制（防止真正失控）

# 核心停止条件（优先级从高到低）
1. 质量达标（成功率≥85%）
2. 质量收敛（连续5次迭代改善<2%）
3. 陷入震荡（质量反复上下波动）
4. Critical问题占比过高（>30%）
5. 同一critical问题反复出现≥3次
6. 成本效益比过低
7. 达到硬限制
```

**为什么这样设计**:
- **任务复杂度高**：自动样本合成涉及多个层面的优化，可能需要10-20次甚至更多迭代
- **不同场景差异大**：简单场景可能3-4次就达标，复杂场景可能需要30+次
- **避免浪费**：如果在第6次迭代能达标，固定5次限制会白白浪费前5次努力
- **智能判断**：基于质量改善趋势而非简单计数，更符合实际情况
- **及早识别问题**：通过问题类型分析，及早发现根本性设计缺陷

**关键机制**:
1. **质量收敛检测**：如果连续5次迭代质量改善<2%，自动停止
2. **分层软/硬限制**：Layer 3成本低可迭代50次，Layer 1成本高限制5次
3. **成本效益分析**：如果继续迭代的预期收益<成本，停止
4. **问题类型识别**：critical问题（如业务逻辑不清）需要人工介入

**详细文档**: 参见 `iteration_strategy_redesign.md`

---

## 💡 参考机制的融合使用

### Bloom框架
**借鉴部分**:
- ✅ Layer 1的理解流程（Understanding）
- ✅ Layer 1的场景设计思路（Ideation）
- ✅ Layer 4的评测框架（Judgment）

**不采用部分**:
- ❌ LLM模拟工具响应（改用真实执行）
- ❌ 端到端全自动（增加人工Review点）
- ❌ 单向流程（改为迭代优化）

### Harness机制
**借鉴部分**:
- ✅ Init-Execute分离模式
- ✅ Checkpoint和恢复机制
- ✅ 执行计划（unified_scenario_design.yaml）

**扩展部分**:
- ✅ 跨层反馈循环
- ✅ 智能问题路由
- ✅ 分层修复策略

### Claude Skills机制作为知识库

**核心思想**：将已开发场景的样本、格式文档、代码模板作为Skills资源，形成可复用的知识库。

**Skills资源结构**:
```
scenarios/skills/
├── office_administration_skill/
│   ├── skill.yaml                    # Skill元数据（适用场景、能力覆盖、质量指标）
│   ├── reference_samples/            # 高质量参考样本
│   │   ├── leave_application/
│   │   │   ├── BS_MT_*.json         # 成功样本示例
│   │   │   └── sample_analysis.md   # 样本设计要点
│   ├── format_specifications/        # 格式规范
│   ├── business_rules/               # 业务规则文档
│   ├── code_templates/               # 代码模板（tools/checkers/simulators）
│   ├── design_patterns/              # 设计模式（多步审批、余额检查等）
│   └── lessons_learned/              # 已知问题和解决方案
```

**在各Layer中的应用**:

**Layer 1 - 场景理解与设计**:
- 根据用户输入自动推荐相似场景的BusinessRules
- 提取适用的设计模式（如多步审批、余额检查）
- 提前提示已知坑点（如"需要明确余额扣减时机"）

**Layer 2 - 组件代码生成**:
- 查找相似工具的代码模板（如query_xxx、create_xxx）
- 应用最佳实践（参数验证、错误处理）
- 避免历史bug模式

**Layer 3 - 样本合成**:
- 参考成功样本的user_simulator_prompt风格
- 学习合理的STOP条件设置
- 复用coverage_matrix设计思路

**Layer 4 - 归因分析**:
- 查询相似失败案例的历史归因
- 匹配问题模式快速定位根因
- 推荐已验证的修复方案

**实施方式**:
- 设计SkillsManager负责Skills的加载、匹配、推荐
- 各Layer Agent通过SkillsManager查询相关资源
- 使用LLM进行语义匹配和智能推荐
- 建立反馈循环：新场景成功后自动补充到Skills

**预期价值**:
- 加速新场景开发（减少50-70%的设计时间）
- 提升样本质量（避免重复犯已知错误）
- 知识持续沉淀（每个场景都成为未来参考）
- 智能化推荐（自动找到最相关的参考资源）

**与其他机制的区别**:
- **vs Bloom**: Bloom关注单个场景的生成流程，Skills关注跨场景的知识复用
- **vs Harness**: Harness关注执行控制和恢复，Skills关注设计经验和模板复用
- **适用阶段**: 可在Phase 2-3引入，当积累3个以上场景后价值最大

---

## 📈 预期效果

### 自动化程度
- **Layer 1**: 半自动（需人工Review）
- **Layer 2-3**: 60-90%自动修复率
- **Layer 4**: 全自动执行和评测
- **整体**: 减少70-80%的人工工作量

### 样本质量
- **初次生成成功率**: 60-70%
- **迭代后成功率**: 85%以上
- **Ground Truth准确性**: 100%（由Checker保证）

### 开发效率
- **传统手动开发**: 1个场景需要2-3周
- **自动化系统**: 1个场景需要2-3天（含人工Review）
- **效率提升**: 5-10倍

### 成本控制
- **最大迭代次数**: 5次
- **单次迭代token消耗**: 约50K tokens
- **总体成本**: 可预测和控制

---

## 🚀 实施路线图

### Phase 1: MVP (2-3周)
**目标**: 验证核心架构可行性

**实现内容**:
1. Orchestrator Agent（简化版）
2. Layer 1: ScenarioDesigner
3. Layer 2: ComponentGenerator（基础版）
4. Layer 3: SampleSynthesizer（基础版）
5. Layer 4: AutoEvaluator（基础版）
6. 决策层: 基础的问题分类逻辑

**验证方式**:
- 生成1个完整场景（如请假申请）
- 验证跨层反馈机制
- 评估自动修复效果

### Phase 2: 功能完善 (1个月)
**目标**: 提升自动修复能力和鲁棒性

**实现内容**:
1. 完善智能问题路由逻辑
2. 扩展可自动修复的问题类型
3. 优化各层的代码生成质量
4. 增加更多的Checkpoint机制
5. 实现详细的日志和监控

**验证方式**:
- 生成3-5个不同复杂度的场景
- 统计自动修复成功率
- 收集用户反馈

### Phase 3: 产品化 (2个月)
**目标**: 构建完整的产品级系统

**实现内容**:
1. CLI/GUI界面
2. 配置管理系统
3. 评测报告可视化
4. 用户权限管理
5. 完整的文档和教程
6. 错误处理和恢复机制

**交付物**:
- 可独立部署的系统
- 完整的用户文档
- 培训材料

---

## 📝 附录

### A. 关键文件结构
```
project_root/
├── orchestrator/
│   ├── orchestrator_agent.py
│   └── decision_layer.py
├── layer1_scenario_designer/
│   ├── scenario_designer.py
│   ├── understanding_agent.py
│   └── ideation_agent.py
├── layer2_component_generator/
│   ├── component_generator.py
│   ├── tools_generator.py
│   ├── checkers_generator.py
│   └── templates/
├── layer3_sample_synthesizer/
│   ├── sample_synthesizer.py
│   └── user_simulator_generator.py
├── layer4_auto_evaluator/
│   ├── auto_evaluator.py
│   ├── failure_analyzer.py
│   └── judgment_agent.py
├── checkpoints/
├── logs/
└── docs/
    └── productization/
        ├── architecture_agentic_loop.svg
        └── product_spec.md (本文档)
```

### B. 关键配置示例

**unified_scenario_design.yaml**:
```yaml
scenario_name: "leave_application"
scenario_description: "员工请假申请场景"

tools:
  - name: "query_employee_info"
    description: "查询员工信息和假期余额"
    parameters:
      - name: "employee_id"
        type: "string"
        required: true
  - name: "create_leave_application"
    description: "创建请假申请"
    parameters:
      - name: "employee_id"
        type: "string"
      - name: "leave_type"
        type: "string"
      - name: "start_date"
        type: "string"
      - name: "days"
        type: "integer"

checkers:
  - id: "leave_application_created"
    type: "state_check"
    description: "验证请假申请已创建"
    target_table: "leave_applications"
    expected_count: 1
  - id: "leave_balance_deducted"
    type: "state_check"
    description: "验证假期余额已扣减"
    target_table: "employee_leave_balances"
    validation_logic: "balance_before - days = balance_after"

samples:
  coverage_matrix:
    dimensions:
      - name: "leave_type"
        values: ["annual", "sick", "personal"]
      - name: "balance_status"
        values: ["sufficient", "insufficient", "edge_case"]
      - name: "approval_required"
        values: ["manager_only", "hr_required", "auto_approved"]
```

### C. 参考资料

1. **Anthropic Bloom Framework**:
   - 理解阶段设计
   - 评测框架思路

2. **Anthropic Harness for Long-Running Agents**:
   - https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents
   - Init-Execute分离模式
   - Checkpoint机制

3. **Claude Skills机制**:
   - 渐进式披露模式
   - 知识封装方法

4. **Universal Framework现有SOP**:
   - docs/PROJECT_DEVELOPMENT_STANDARDS_V2.md
   - 成熟的场景开发流程

---

## 📞 联系方式

如有疑问或建议，请联系项目团队。

---

**文档结束**
