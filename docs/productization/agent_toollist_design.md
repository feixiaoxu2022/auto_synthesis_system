# Agent Toollist Design

本文档定义Init Agent和Execute Agent的工具配置，基于Wenning已有工具进行适配和复用。

---

## 工具配置对比

| 工具 | Init Agent | Execute Agent | 说明 |
|------|-----------|--------------|------|
| **file_reader** | ✅ | ✅ | 读取文件内容，支持多种格式 |
| **file_writer** | ✅ | ✅ | 创建新文件或覆盖已有文件 |
| **file_editor** | ✅ | ✅ | 编辑已有文件（替换或行范围模式） |
| **bash** | ❌ | ✅ | 执行shell命令，运行测试和评测 |
| **use_skill** | ✅ | ✅ | 获取技能库资源（SOP、模板、最佳实践） |

---

## Init Agent Toollist

### 角色与职责
- 负责场景设计（Layer 1）
- 基于用户需求生成设计 + 基于反馈修改设计
- 交付：场景目录 + yaml + BusinessRules + format + InitToExecuteContext

### 工具配置

#### 1. file_reader
**用途**：
- 读取ExecuteToInitContext（Execute Agent反馈）
- 读取evaluation_outputs中的失败样本JSON
- 读取trace文件分析问题根因
- 读取现有BusinessRules/format进行修改

**配置要点**：
- 支持JSON、Markdown、Text格式
- 需要conversation_id隔离
- 安全限制：max_bytes、max_lines

**复用Wenning实现**：✅ 直接复用

#### 2. file_writer
**用途**：
- 创建BusinessRules.md（业务规则文档）
- 创建format规范文件
- 创建场景配置yaml
- 生成InitToExecuteContext.json（传递给Execute Agent）

**配置要点**：
- 输出到场景目录：`scenarios/{scenario_name}/`
- 强制conversation_id隔离
- 支持UTF-8编码

**复用Wenning实现**：✅ 直接复用，需调整base_dir指向scenarios目录

#### 3. file_editor
**用途**：
- 基于Execute Agent反馈修改BusinessRules
- 调整format规范
- 修正场景配置

**配置要点**：
- 支持两种模式：
  - 替换模式（old_string → new_string）
  - 行范围模式（指定行号范围）
- 需要验证修改前后的上下文一致性

**复用Wenning实现**：✅ 直接复用

#### 4. use_skill
**用途**：
- 获取BusinessRules.md编写指南和最佳实践
- 获取format规范文档标准结构
- 获取场景设计SOP和注意事项
- 获取InitToExecuteContext标准格式模板

**配置要点**：
- 从技能库检索（skills/目录，索引文件）
- 包含：SOP、模板、最佳实践、统一配置、示例
- 确保生成的设计文档符合框架标准

**需要的技能类型**：
- `business_rules_authoring` - 业务规则编写指南（标准结构、必需章节、示例）
- `format_specification_guide` - 格式规范编写指南（数据格式、验证规则）
- `scenario_design_sop` - 场景设计SOP（流程、决策点、质量标准）
- `init_to_execute_context` - Context交接格式（必需字段、数据结构）

**实现方式**：基于Wenning的PromptTemplateRetriever改造，扩展技能库

---

## Execute Agent Toollist

### 角色与职责
- 负责执行评测修复（Layer 2-4）
- 生成组件（tools、checkers、samples）
- 运行评测并分析失败原因
- 迭代修复直至成功率达标

### 工具配置

#### 1. file_reader
**用途**：
- 读取InitToExecuteContext（Init Agent设计）
- 读取BusinessRules和format规范
- 读取现有tools/checkers/samples代码
- 读取评测输出结果

**配置要点**：
- 支持JSON、Python、Markdown格式
- 需要conversation_id隔离
- 安全限制：max_bytes、max_lines

**复用Wenning实现**：✅ 直接复用

#### 2. file_writer
**用途**：
- 创建tools/*.py（场景专用工具）
- 创建checkers/*.py（验证检查器）
- 创建samples/*.json（测试样本）
- 生成ExecuteToInitContext.json（反馈给Init Agent）

**配置要点**：
- 输出到场景目录：`scenarios/{scenario_name}/tools/`, `samples/`, `checkers/`
- 强制conversation_id隔离
- 支持UTF-8编码

**复用Wenning实现**：✅ 直接复用，需调整base_dir指向scenarios目录

#### 3. file_editor
**用途**：
- 修复tools中的bug
- 调整checkers的验证逻辑
- 修改samples的配置参数

**配置要点**：
- 支持两种模式：
  - 替换模式（修复代码bug）
  - 行范围模式（重写代码片段）
- 需要验证修改前后的上下文一致性

**复用Wenning实现**：✅ 直接复用

#### 4. bash
**用途**：
- 执行Python脚本测试生成的tools功能
- 运行pytest验证checkers逻辑
- 执行评测脚本分析结果（run_evaluation.sh）
- 使用命令行工具进行数据分析（grep、awk等）

**配置要点**：
- 在本地环境直接执行shell命令
- 工作目录：`scenarios/{scenario_name}/execution_outputs/iteration_N/`
- 超时限制：默认120s，可配置
- 安全考虑：限制某些危险命令

**常用命令示例**：
- `python tools/my_tool.py --test` - 测试工具
- `pytest checkers/test_checker.py -v` - 运行测试
- `bash scripts/run_evaluation.sh` - 执行评测
- `ls -lh samples/` - 查看生成的样本

**实现方式**：subprocess.run()执行，记录stdout/stderr

#### 5. use_skill
**用途**：
- 获取tools实现最佳实践和代码模板
- 获取checkers实现规范和示例
- 获取samples编写指南和标准结构
- 获取ExecuteToInitContext反馈格式

**配置要点**：
- 从技能库检索（skills/目录，索引文件）
- 包含：代码模板、实现SOP、最佳实践、示例代码
- 确保生成的代码符合框架规范

**需要的技能类型**：
- `tool_implementation` - 工具实现指南（BaseAtomicTool继承、execute方法、参数schema）
- `checker_implementation` - 检查器实现指南（BaseChecker继承、check方法、结果格式）
- `sample_authoring` - 样本编写指南（JSON结构、user_simulator_prompt规范、expected_state）
- `execute_to_init_context` - Context交接格式（execution_output_dir、failure_samples、layer1_problems）

**实现方式**：基于Wenning的PromptTemplateRetriever改造，扩展技能库

---

## 工具适配要点

### 1. 路径配置适配

Wenning的工具使用`output_dir / conversation_id`结构，需要适配到场景框架：

```python
# Wenning原有结构
work_dir = output_dir / conversation_id

# Init Agent适配
work_dir = scenarios_base_dir / scenario_name

# Execute Agent适配
work_dir = scenarios_base_dir / scenario_name / "execution_outputs" / f"iteration_{N}"
```

### 2. conversation_id使用

- **Wenning**: conversation_id用于隔离不同用户会话
- **场景框架**:
  - Init Agent: 可以使用固定ID或场景名称
  - Execute Agent: 使用`iteration_{N}`标识不同迭代

### 3. 安全限制保持

Wenning的安全限制机制保持不变：
- file_reader: max_bytes=10MB, max_lines=5000
- file_writer: 禁止绝对路径，禁止".."
- file_editor: 验证上下文一致性
- code_executor: timeout限制，subprocess隔离

---

## System Prompt中的工具描述

### Init Agent System Prompt片段

```markdown
## Available Tools

你可以使用以下工具完成场景设计工作：

### file_reader
读取文件内容，支持Text、JSON、Markdown格式。
参数：filename（必需）、max_lines（可选，默认1000）

使用场景：
- 读取ExecuteToInitContext了解Execute Agent反馈
- 分析失败样本JSON找出问题根因
- 查看现有BusinessRules准备修改

### file_writer
创建新文件或覆盖已有文件。
参数：filename（必需）、content（必需）、encoding（可选，默认utf-8）

使用场景：
- 创建BusinessRules.md定义业务规则
- 生成format规范文件
- 输出InitToExecuteContext.json传递给Execute Agent

### file_editor
编辑已有文件，支持替换模式和行范围模式。
参数：filename（必需）、mode（"replace"/"line_range"）、old_string/new_string或start_line/end_line/new_content

使用场景：
- 基于Execute反馈修改BusinessRules
- 调整format规范细节
- 修正场景配置参数

### use_skill
获取技能库资源，包含SOP、模板、最佳实践和示例代码。
参数：skill_type（必需，从enum中选择）

使用场景：
- 创建BusinessRules前，获取business_rules_authoring了解编写规范
- 生成format规范前，获取format_specification_guide
- 输出InitToExecuteContext前，获取init_to_execute_context确保格式正确

可用技能类型：
- business_rules_authoring：业务规则编写指南
- format_specification_guide：格式规范编写指南
- scenario_design_sop：场景设计SOP
- init_to_execute_context：Context交接格式
```

### Execute Agent System Prompt片段

```markdown
## Available Tools

你可以使用以下工具完成组件生成和评测工作：

### file_reader
读取文件内容，支持Text、JSON、Python、Markdown格式。
参数：filename（必需）、max_lines（可选，默认1000）

使用场景：
- 读取InitToExecuteContext了解设计要求
- 查看BusinessRules和format规范
- 分析评测输出结果

### file_writer
创建新文件或覆盖已有文件。
参数：filename（必需）、content（必需）、encoding（可选，默认utf-8）

使用场景：
- 创建tools/*.py实现场景专用工具
- 生成checkers/*.py实现验证逻辑
- 创建samples/*.json定义测试样本
- 输出ExecuteToInitContext.json反馈给Init Agent

### file_editor
编辑已有文件，支持替换模式和行范围模式。
参数：filename（必需）、mode（"replace"/"line_range"）、old_string/new_string或start_line/end_line/new_content

使用场景：
- 修复tools中的bug
- 调整checkers验证逻辑
- 修改samples配置参数

### bash
执行shell命令，运行测试和评测脚本。
参数：command（必需）、timeout（可选，默认120s）

使用场景：
- 测试生成的tools：`python tools/my_tool.py --test`
- 运行pytest验证：`pytest checkers/test_checker.py -v`
- 执行评测脚本：`bash scripts/run_evaluation.sh`
- 数据分析命令：`ls -lh samples/` 或 `grep -r "error" logs/`

注意事项：
- 工作目录在execution_outputs/iteration_N/下
- 命令执行结果会返回stdout和stderr
- 超时会抛出异常

### use_skill
获取技能库资源，包含代码模板、实现SOP和最佳实践。
参数：skill_type（必需，从enum中选择）

使用场景：
- 创建tools前，获取tool_implementation了解实现规范
- 生成checkers前，获取checker_implementation
- 创建samples前，获取sample_authoring确保字段完整
- 输出ExecuteToInitContext前，获取execute_to_init_context

可用技能类型：
- tool_implementation：工具实现指南（BaseAtomicTool继承）
- checker_implementation：检查器实现指南（BaseChecker继承）
- sample_authoring：样本编写指南（JSON结构规范）
- execute_to_init_context：Context交接格式
```

---

## 实现注意事项

### 1. 工具初始化配置

```python
# Init Agent工具初始化
init_tools = {
    "file_reader": FileReader(
        config=init_config,
        base_dir=scenarios_base_dir / scenario_name
    ),
    "file_writer": FileWriter(
        config=init_config,
        base_dir=scenarios_base_dir / scenario_name
    ),
    "file_editor": FileEditor(
        config=init_config,
        base_dir=scenarios_base_dir / scenario_name
    ),
    "use_skill": UseSkill(
        config=init_config,
        skills_dir=project_root / "skills"
    )
}

# Execute Agent工具初始化
execute_tools = {
    "file_reader": FileReader(
        config=execute_config,
        base_dir=scenarios_base_dir / scenario_name
    ),
    "file_writer": FileWriter(
        config=execute_config,
        base_dir=scenarios_base_dir / scenario_name
    ),
    "file_editor": FileEditor(
        config=execute_config,
        base_dir=scenarios_base_dir / scenario_name
    ),
    "bash": Bash(
        config=execute_config,
        work_dir=scenarios_base_dir / scenario_name / "execution_outputs" / f"iteration_{N}"
    ),
    "use_skill": UseSkill(
        config=execute_config,
        skills_dir=project_root / "skills"
    )
}
```

### 2. 错误处理

工具调用失败时，Agent应该：
- **file_reader失败**：检查文件路径是否正确，是否超过大小限制
- **file_writer失败**：检查目录权限，文件名是否合法
- **file_editor失败**：检查old_string是否存在，上下文是否匹配
- **bash失败**：分析stderr输出，修复命令或脚本bug，检查超时设置
- **use_skill失败**：检查skill_type是否存在，技能库是否正确配置

### 3. 落盘数据与工具配合

- 所有关键数据必须通过file_writer落盘
- Agent需要详细信息时，通过file_reader按需访问
- Summary中保留关键路径，避免在Context中存储大量数据

### 4. 技能库扩展计划

需要在`skills/`目录创建以下技能，供use_skill工具使用：

#### Init Agent技能

1. **business_rules_authoring/**
   - SKILL.md：业务规则编写指南
   - templates/：标准结构模板
   - examples/：优秀案例参考
   - sop/：编写流程和检查清单

2. **format_specification_guide/**
   - SKILL.md：格式规范编写指南
   - templates/：数据格式模板
   - examples/：格式规范示例
   - sop/：验证规则编写规范

3. **scenario_design_sop/**
   - SKILL.md：场景设计完整SOP
   - templates/：场景配置模板
   - examples/：成功场景案例
   - sop/：决策点和质量标准

4. **init_to_execute_context/**
   - SKILL.md：Context交接格式说明
   - templates/：标准JSON结构
   - examples/：完整示例
   - sop/：字段填写规范

#### Execute Agent技能

5. **tool_implementation/**
   - SKILL.md：工具实现指南
   - templates/：BaseAtomicTool代码模板
   - examples/：各类工具实现示例
   - sop/：参数schema编写规范

6. **checker_implementation/**
   - SKILL.md：检查器实现指南
   - templates/：BaseChecker代码模板
   - examples/：各类检查器示例
   - sop/：评分逻辑和失败原因规范

7. **sample_authoring/**
   - SKILL.md：样本编写指南
   - templates/：样本JSON标准结构
   - examples/：各类场景样本示例
   - sop/：user_simulator_prompt编写规范

8. **execute_to_init_context/**
   - SKILL.md：Context反馈格式说明
   - templates/：标准JSON结构
   - examples/：反馈示例
   - sop/：失败原因分类规范

#### 技能索引文件

创建`skills/skills.json`：

```json
{
  "skills": {
    "business_rules_authoring": {
      "title": "业务规则编写指南",
      "description": "teach Claude how to write comprehensive business rules documents",
      "category": "init_agent",
      "path": "business_rules_authoring/SKILL.md"
    },
    "format_specification_guide": {
      "title": "格式规范编写指南",
      "description": "teach Claude how to define data format specifications",
      "category": "init_agent",
      "path": "format_specification_guide/SKILL.md"
    },
    "scenario_design_sop": {
      "title": "场景设计SOP",
      "description": "teach Claude the complete scenario design workflow",
      "category": "init_agent",
      "path": "scenario_design_sop/SKILL.md"
    },
    "init_to_execute_context": {
      "title": "Init到Execute Context交接",
      "description": "teach Claude the context handoff format from Init to Execute Agent",
      "category": "init_agent",
      "path": "init_to_execute_context/SKILL.md"
    },
    "tool_implementation": {
      "title": "工具实现指南",
      "description": "teach Claude how to implement scenario-specific tools",
      "category": "execute_agent",
      "path": "tool_implementation/SKILL.md"
    },
    "checker_implementation": {
      "title": "检查器实现指南",
      "description": "teach Claude how to implement validation checkers",
      "category": "execute_agent",
      "path": "checker_implementation/SKILL.md"
    },
    "sample_authoring": {
      "title": "样本编写指南",
      "description": "teach Claude how to write high-quality test samples",
      "category": "execute_agent",
      "path": "sample_authoring/SKILL.md"
    },
    "execute_to_init_context": {
      "title": "Execute到Init Context反馈",
      "description": "teach Claude the context feedback format from Execute to Init Agent",
      "category": "execute_agent",
      "path": "execute_to_init_context/SKILL.md"
    }
  }
}
```

---

## 总结

- **Init Agent**: 使用file_reader、file_writer、file_editor、use_skill完成场景设计和修改
- **Execute Agent**: 额外使用bash执行命令和评测，使用use_skill获取代码实现指南
- **工具复用**: file_reader/writer/editor复用Wenning实现，bash使用subprocess.run()
- **技能库扩展**: 需要创建8个技能目录，每个包含SKILL.md、templates、examples、sop
- **命名优化**:
  - `use_skill` 替代 `retrieve_prompt_template`（更准确、优雅）
  - `bash` 替代 `code_executor`（更灵活、符合本地场景）
- **落盘优先**: 工具配合落盘优先原则，减轻Context压力
