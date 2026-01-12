# Skills物料组织方案

## 素材来源盘点

### 1. 整体SOP
- **文件**: `docs/PROJECT_DEVELOPMENT_STANDARDS_V2.md` (1915行)
- **内容结构**:
  - Step 1: 构建Agent准备 (85-170行)
  - Step 2: 场景设计生成 (170-717行) ⭐ BusinessRules + Format规范
  - Step 3: 组件并行生成 (717-1157行) ⭐ Tools + Checkers + Samples
  - Step 4: 自动验证 (1157-1716行)
  - Step 5: 人工评测 (1716-1808行)
  - 模板文件体系 (1808-1859行)

### 2. 代码和规范模板
- **目录**: `templates/`
- **关键文件**:
  - `format_specifications/` - 格式规范模板
    - universal_format_template.json
    - checker_parameter_specifications.json
    - multiturn_format_specification.json
    - db_schema_template.json
  - `docs/best_practices/` - 最佳实践
    - user_simulator_design.md
    - SEMANTIC_CHECKER_GUIDE.md
    - SAMPLE_QUALITY_ASSURANCE_GUIDE.md
  - `scripts/` - 代码模板
    - sample_generator_template.py
    - rule_engine_template.py
  - `prototypes/` - 原型模板
    - prototype_template.json

### 3. 已有场景样本
- **目录**: `scenarios/*/samples_for_open_benchmark/`
- **场景列表**:
  - ad_campaign (广告营销)
  - bikeshare (共享单车)
  - crm (客户关系管理)
  - data_analysis (数据分析)
  - education_administration (教育管理)
  - 等...

### 4. 样本合成经验
- **文件**: `docs/SAMPLE_GENERATION_SOP_AND_BEST_PRACTICES.md`
- **预计内容**: 样本生成SOP、质量标准、常见问题

### 5. 难度提升经验
- **文件**: `docs/productization/五种难度提升思路.md`
- **预计内容**: 场景复杂度设计、能力测试策略

---

## 8个技能的物料映射方案

### Init Agent技能 (Layer 1相关)

#### 1. business_rules_authoring/
**目标**: teach Claude how to write comprehensive business rules documents

**物料来源**:
- **SKILL.md主文档**: 从`PROJECT_DEVELOPMENT_STANDARDS_V2.md` Step 2提取BusinessRules相关章节
- **templates/**:
  - 需要创建`BusinessRules_template.md`（从已有场景中提取共性结构）
- **examples/**:
  - 从`scenarios/bikeshare/BusinessRules.md`（优秀案例）
  - 从`scenarios/crm/BusinessRules.md`
  - 从`scenarios/education_administration/BusinessRules.md`
- **sop/**:
  - 编写流程：需求分析 → 规则定义 → 格式规范 → 验证清单
  - 质量检查清单

#### 2. format_specification_guide/
**目标**: teach Claude how to define data format specifications

**物料来源**:
- **SKILL.md主文档**: 从`PROJECT_DEVELOPMENT_STANDARDS_V2.md` Step 2提取Format规范相关章节
- **templates/**:
  - `templates/format_specifications/universal_format_template.json`
  - `templates/format_specifications/checker_parameter_specifications.json`
  - `templates/format_specifications/db_schema_template.json`
- **examples/**:
  - 从各场景的`format_specifications/`目录提取优秀示例
- **sop/**:
  - 格式设计原则
  - 验证规则编写规范

#### 3. scenario_design_sop/
**目标**: teach Claude the complete scenario design workflow

**物料来源**:
- **SKILL.md主文档**:
  - `PROJECT_DEVELOPMENT_STANDARDS_V2.md` Step 2整体流程
  - `五种难度提升思路.md`全文
- **templates/**:
  - 场景设计checklist模板
  - unified_scenario_design.yaml模板（需要创建）
- **examples/**:
  - 完整的场景设计案例（bikeshare作为标杆）
- **sop/**:
  - 场景理解 → 能力映射 → 规则设计 → 难度设置 → 验证
  - 决策点和权衡考虑

#### 4. init_to_execute_context/
**目标**: teach Claude the context handoff format from Init to Execute Agent

**物料来源**:
- **SKILL.md主文档**:
  - `docs/productization/context_strategy.md` 中InitToExecuteContext部分
- **templates/**:
  - InitToExecuteContext JSON模板
- **examples/**:
  - 完整示例（包含各字段说明）
- **sop/**:
  - 字段填写规范
  - 验证清单

---

### Execute Agent技能 (Layer 2-4相关)

#### 5. tool_implementation/
**目标**: teach Claude how to implement scenario-specific tools

**物料来源**:
- **SKILL.md主文档**: 从`PROJECT_DEVELOPMENT_STANDARDS_V2.md` Step 3提取Tools相关章节
- **templates/**:
  - 需要创建`tool_template.py`（BaseAtomicTool继承）
  - 参数schema标准格式
- **examples/**:
  - 从各场景`src/tools/`目录提取优秀工具实现
  - 如：`scenarios/bikeshare/src/tools/`
- **sop/**:
  - 工具设计原则
  - 参数定义规范
  - 错误处理标准
  - 单元测试要求

#### 6. checker_implementation/
**目标**: teach Claude how to implement validation checkers

**物料来源**:
- **SKILL.md主文档**: 从`PROJECT_DEVELOPMENT_STANDARDS_V2.md` Step 3提取Checkers相关章节
- **templates/**:
  - `templates/docs/best_practices/SEMANTIC_CHECKER_GUIDE.md`
  - 需要创建`checker_template.py`（BaseChecker继承）
- **examples/**:
  - 从各场景`src/evaluation/checkers/`目录提取
- **sop/**:
  - 检查器类型选择（state-based/semantic/procedural）
  - 评分逻辑规范
  - 失败原因记录标准

#### 7. sample_authoring/
**目标**: teach Claude how to write high-quality test samples

**物料来源**:
- **SKILL.md主文档**:
  - `docs/SAMPLE_GENERATION_SOP_AND_BEST_PRACTICES.md`全文
  - `PROJECT_DEVELOPMENT_STANDARDS_V2.md` Step 3中样本相关章节
- **templates/**:
  - `templates/scripts/sample_generator_template.py`
  - `templates/prototypes/prototype_template.json`
  - `templates/format_specifications/multiturn_user_simulator_guide.md`
- **examples/**:
  - 从`scenarios/*/samples_for_open_benchmark/`中精选优秀样本
  - 覆盖不同难度级别和场景类型
- **sop/**:
  - 样本设计流程
  - user_simulator_prompt编写规范
  - expected_state完整性要求
  - 质量验证标准

#### 8. execute_to_init_context/
**目标**: teach Claude the context feedback format from Execute to Init Agent

**物料来源**:
- **SKILL.md主文档**:
  - `docs/productization/context_strategy.md` 中ExecuteToInitContext部分
- **templates/**:
  - ExecuteToInitContext JSON模板
  - layer1_problems_report JSON模板
- **examples/**:
  - 完整反馈示例
  - 失败样本索引示例
- **sop/**:
  - 失败原因分类规范
  - 改进建议格式要求
  - 优先级判断标准

---

## 实施步骤

### Phase 1: 准备阶段
1. 创建skills目录结构
2. 创建skills.json索引文件

### Phase 2: 拆分和组织SOP内容
1. 从`PROJECT_DEVELOPMENT_STANDARDS_V2.md`提取各技能相关章节
2. 重新组织为独立的SKILL.md文档
3. 保持引用关系和完整性

### Phase 3: 整理模板文件
1. 复制templates/目录下的相关文件到对应技能的templates/
2. 创建缺失的模板文件（如tool_template.py, checker_template.py）

### Phase 4: 提取优秀示例
1. 从已有场景中精选优秀示例
2. 添加注释说明（为什么好、关键设计点）
3. 组织到各技能的examples/目录

### Phase 5: 编写SOP子文档
1. 为每个技能编写详细的执行流程
2. 包含决策点、检查清单、常见问题

### Phase 6: 验证和测试
1. 测试Agent能否正确use_skill
2. 验证物料的完整性和可用性
3. 收集反馈迭代优化

---

## 目录结构预览

```
skills/
├── skills.json
├── business_rules_authoring/
│   ├── SKILL.md
│   ├── templates/
│   │   └── BusinessRules_template.md
│   ├── examples/
│   │   ├── bikeshare_BusinessRules.md
│   │   ├── crm_BusinessRules.md
│   │   └── education_admin_BusinessRules.md
│   └── sop/
│       ├── writing_workflow.md
│       └── quality_checklist.md
├── format_specification_guide/
│   ├── SKILL.md
│   ├── templates/
│   │   ├── universal_format_template.json
│   │   ├── checker_parameter_specifications.json
│   │   └── db_schema_template.json
│   ├── examples/
│   │   └── (从各场景提取)
│   └── sop/
│       └── design_principles.md
├── scenario_design_sop/
│   ├── SKILL.md (Step 2整体流程)
│   ├── templates/
│   │   └── unified_scenario_design_template.yaml
│   ├── examples/
│   │   └── bikeshare_complete_design/
│   └── sop/
│       ├── difficulty_enhancement_strategies.md (五种难度提升思路)
│       └── decision_points.md
├── init_to_execute_context/
│   ├── SKILL.md
│   ├── templates/
│   │   └── init_to_execute_context.json
│   ├── examples/
│   │   └── complete_handoff_example.json
│   └── sop/
│       └── field_filling_guide.md
├── tool_implementation/
│   ├── SKILL.md
│   ├── templates/
│   │   ├── tool_template.py
│   │   └── tool_schema_template.json
│   ├── examples/
│   │   └── (从各场景src/tools/提取)
│   └── sop/
│       ├── design_principles.md
│       └── testing_requirements.md
├── checker_implementation/
│   ├── SKILL.md
│   ├── templates/
│   │   ├── checker_template.py
│   │   └── SEMANTIC_CHECKER_GUIDE.md
│   ├── examples/
│   │   └── (从各场景checkers/提取)
│   └── sop/
│       └── checker_type_selection.md
├── sample_authoring/
│   ├── SKILL.md (SAMPLE_GENERATION_SOP全文)
│   ├── templates/
│   │   ├── sample_generator_template.py
│   │   ├── prototype_template.json
│   │   └── multiturn_user_simulator_guide.md
│   ├── examples/
│   │   ├── simple_samples/
│   │   ├── medium_samples/
│   │   └── complex_samples/
│   └── sop/
│       ├── quality_assurance.md
│       └── user_simulator_design.md
└── execute_to_init_context/
    ├── SKILL.md
    ├── templates/
    │   ├── execute_to_init_context.json
    │   └── layer1_problems_report.json
    ├── examples/
    │   └── complete_feedback_example.json
    └── sop/
        ├── failure_classification.md
        └── priority_assignment.md
```

---

## 关键设计决策

### 1. SKILL.md的粒度
- **原则**: 每个SKILL.md应该是自包含的，Agent读取后能立即开始工作
- **内容**: 目标、核心概念、步骤流程、注意事项、参考资源
- **长度**: 控制在2000-4000 tokens，确保一次性能加载

### 2. templates/的组织
- **原则**: 提供可直接复制使用的模板，减少Agent摸索时间
- **内容**: 包含注释说明、占位符标记、必填/可选字段说明

### 3. examples/的选择标准
- **质量第一**: 只选择经过验证的优秀案例
- **多样性**: 覆盖不同复杂度、不同领域
- **带注释**: 说明设计亮点和关键决策

### 4. sop/的详细程度
- **流程清晰**: step-by-step，有决策树
- **包含检查清单**: 每个阶段的验收标准
- **常见问题**: FAQ和troubleshooting

---

## 下一步行动

1. **确认方案**: 评审本组织方案，确定是否有调整
2. **创建目录结构**: 建立skills/的完整目录树
3. **拆分SOP内容**: 开始从PROJECT_DEVELOPMENT_STANDARDS_V2.md提取内容
4. **逐个构建技能**: 按照Init Agent → Execute Agent的顺序完成
