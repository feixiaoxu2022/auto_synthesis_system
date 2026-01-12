# Universal Framework Agent化 MVP实现指南

## 🎯 MVP目标

**2周内验证可行性**: 
从自然语言描述 → 自动生成完整场景 → 运行评测 → 得到报告

---

## 🏗️ 技术架构

```
┌─────────────────────────────────────────────────────────┐
│                    MVP Architecture                      │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  1. Init Agent (Claude Opus 4.5)                        │
│     输入: 自然语言业务描述                               │
│     输出: execution_plan.json                            │
│            ↓                                             │
│  2. Code Generator (Claude Haiku 4.5)                   │
│     输入: execution_plan.json                            │
│     输出: 完整的scenario代码                             │
│            ↓                                             │
│  3. Executor (现有Universal Framework)                  │
│     输入: scenario目录                                   │
│     输出: evaluation_results.json                        │
│                                                           │
└─────────────────────────────────────────────────────────┘
```

---

## 📝 Step-by-Step实现

### Step 1: Init Agent - 生成执行计划 (3天)

#### 1.1 设计Prompt Template

```python
# prompts/init_agent_prompt.py

INIT_AGENT_SYSTEM_PROMPT = """
你是一个Universal Scenario Framework的场景设计专家。
你的任务是根据用户的自然语言描述,生成完整的execution_plan。

execution_plan必须包含:
1. scenario_name: 场景名称
2. understanding: 业务理解
3. tools_design: 工具设计(包含SQL实现)
4. db_schema: 数据库设计
5. samples: 测试样本配置
6. checklist: 验证清单

参考Universal Framework的现有场景作为示例。
"""

def generate_init_prompt(user_description, reference_scenarios):
    """生成Init Agent的prompt"""
    
    prompt = f"""
{INIT_AGENT_SYSTEM_PROMPT}

# 参考场景示例

{format_reference_scenarios(reference_scenarios)}

# 用户描述

{user_description}

# 任务

请生成完整的execution_plan.json,确保:
1. tools设计包含完整的SQL实现
2. db_schema设计合理,字段类型正确
3. samples覆盖正常case和边界case
4. checklist明确,可验证

请直接输出JSON格式的execution_plan。
"""
    return prompt
```

#### 1.2 参考场景加载

```python
# init_agent/scenario_reference.py

def load_reference_scenarios(scenario_names=["leave_application", "booking_system"]):
    """加载现有场景作为参考"""
    
    references = []
    for name in scenario_names:
        scenario_path = f"scenarios/{name}"
        
        # 读取关键文件
        business_rules = read_file(f"{scenario_path}/BusinessRules.md")
        tools = read_file(f"{scenario_path}/tools/*.py")
        db_schema = extract_db_schema(f"{scenario_path}/db/")
        sample = read_file(f"{scenario_path}/samples/sample_001.json")
        
        references.append({
            "name": name,
            "business_rules": business_rules,
            "tools": tools,
            "db_schema": db_schema,
            "sample_example": sample
        })
    
    return references
```

#### 1.3 Init Agent实现

```python
# init_agent/agent.py

class InitAgent:
    """Init阶段Agent,负责深度理解和规划"""
    
    def __init__(self, model="claude-opus-4-5"):
        self.model = model
        self.reference_scenarios = load_reference_scenarios()
    
    def generate_plan(self, user_description: str) -> dict:
        """生成execution_plan"""
        
        # 1. 构造prompt
        prompt = generate_init_prompt(
            user_description,
            self.reference_scenarios
        )
        
        # 2. 调用Claude生成plan
        response = litellm_chat(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=16000,
            reasoning_effort="high"  # 使用extended thinking
        )
        
        # 3. 解析JSON
        plan_json = extract_json(response.content)
        
        # 4. 验证plan的完整性
        self.validate_plan(plan_json)
        
        return plan_json
    
    def validate_plan(self, plan: dict):
        """验证plan的完整性"""
        required_fields = [
            "scenario_name",
            "tools_design",
            "db_schema",
            "samples"
        ]
        
        for field in required_fields:
            if field not in plan:
                raise ValueError(f"Missing required field: {field}")
        
        # 验证tools_design包含SQL
        for tool in plan["tools_design"]:
            if "implementation" not in tool:
                raise ValueError(f"Tool {tool['name']} missing implementation")
```

---

### Step 2: Code Generator - 自动生成代码 (4天)

#### 2.1 Tools代码生成

```python
# code_generator/tools_generator.py

TOOLS_TEMPLATE = '''
"""
Auto-generated tools for {scenario_name}
Generated at: {timestamp}
"""

from typing import Dict, Any, Optional, List
import sqlite3
import json
from datetime import datetime

class {tool_class_name}:
    """Tools for {scenario_name}"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
    
{tool_methods}
'''

def generate_tools_code(tools_design: List[dict], scenario_name: str) -> str:
    """根据tools_design生成完整的Python代码"""
    
    tool_methods = []
    for tool in tools_design:
        method_code = generate_tool_method(tool)
        tool_methods.append(method_code)
    
    code = TOOLS_TEMPLATE.format(
        scenario_name=scenario_name,
        timestamp=datetime.now().isoformat(),
        tool_class_name=to_camel_case(scenario_name) + "Tools",
        tool_methods="\n\n".join(tool_methods)
    )
    
    return code

def generate_tool_method(tool: dict) -> str:
    """生成单个tool方法"""
    
    # 使用Claude生成方法实现
    prompt = f"""
根据以下tool设计,生成Python方法实现:

Tool名称: {tool['name']}
描述: {tool['description']}
参数: {tool['parameters']}
返回: {tool['returns']}
SQL实现: {tool['implementation']}

要求:
1. 方法名使用snake_case
2. 添加类型标注
3. 添加docstring
4. 包含错误处理
5. 使用sqlite3执行SQL
6. 返回Dict[str, Any]格式

请直接输出Python方法代码。
"""
    
    response = litellm_chat(
        model="claude-haiku-4-5",  # 用便宜的模型生成代码
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2000
    )
    
    return response.content
```

#### 2.2 DB初始化代码生成

```python
# code_generator/db_generator.py

def generate_db_init(db_schema: dict, scenario_name: str) -> str:
    """生成DB初始化代码"""
    
    create_tables = []
    for table_name, fields in db_schema.items():
        sql = generate_create_table_sql(table_name, fields)
        create_tables.append(sql)
    
    code = f'''
"""
Auto-generated DB initialization for {scenario_name}
"""

import sqlite3
from pathlib import Path

def init_db(db_path: str):
    """Initialize database schema"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create tables
{indent("\n".join(create_tables), 4)}
    
    conn.commit()
    conn.close()
'''
    
    return code

def generate_create_table_sql(table_name: str, fields: dict) -> str:
    """生成CREATE TABLE语句"""
    
    field_defs = []
    for field_name, field_type in fields.items():
        field_defs.append(f"    {field_name} {field_type}")
    
    sql = f'''
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS {table_name} (
{", ".join(field_defs)}
        )
    """)
'''
    return sql
```

#### 2.3 Sample配置生成

```python
# code_generator/sample_generator.py

def generate_sample_files(samples_config: List[dict], scenario_name: str) -> List[tuple]:
    """生成sample JSON文件"""
    
    sample_files = []
    
    for i, sample in enumerate(samples_config, 1):
        sample_id = sample.get("id", f"SAMPLE_{i:03d}")
        
        # 构建完整的sample结构
        full_sample = {
            "sample_id": sample_id,
            "description": sample["description"],
            "initial_state": sample["initial_state"],
            "user_simulator_prompt": sample["user_simulator_prompt"],
            "expected_outcome": sample["expected_outcome"],
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "scenario": scenario_name
            }
        }
        
        filename = f"{sample_id}.json"
        content = json.dumps(full_sample, indent=2, ensure_ascii=False)
        
        sample_files.append((filename, content))
    
    return sample_files
```

#### 2.4 Checker代码生成

```python
# code_generator/checker_generator.py

def generate_checker_code(checklist: dict, tools_design: List[dict]) -> str:
    """生成Checker代码"""
    
    prompt = f"""
根据以下checklist和tools设计,生成Checker验证代码:

Checklist:
{json.dumps(checklist, indent=2)}

Available Tools:
{json.dumps([t['name'] for t in tools_design])}

要求:
1. 继承BaseChecker类
2. 实现check()方法
3. 返回详细的验证结果
4. 包含失败原因分析

请生成完整的Python代码。
"""
    
    response = litellm_chat(
        model="claude-haiku-4-5",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=4000
    )
    
    return response.content
```

---

### Step 3: Executor - 执行和验证 (3天)

#### 3.1 文件生成和目录结构

```python
# executor/file_writer.py

class ScenarioBuilder:
    """构建完整的scenario目录"""
    
    def __init__(self, execution_plan: dict, output_dir: str):
        self.plan = execution_plan
        self.output_dir = Path(output_dir)
        self.scenario_name = plan["scenario_name"]
    
    def build(self):
        """生成完整的scenario目录"""
        
        scenario_path = self.output_dir / self.scenario_name
        scenario_path.mkdir(parents=True, exist_ok=True)
        
        # 1. 生成tools
        tools_code = generate_tools_code(
            self.plan["tools_design"],
            self.scenario_name
        )
        self.write_file(
            scenario_path / "tools" / f"{self.scenario_name}_tools.py",
            tools_code
        )
        
        # 2. 生成DB init
        db_init_code = generate_db_init(
            self.plan["db_schema"],
            self.scenario_name
        )
        self.write_file(
            scenario_path / "db" / "init_db.py",
            db_init_code
        )
        
        # 3. 生成samples
        sample_files = generate_sample_files(
            self.plan["samples"],
            self.scenario_name
        )
        for filename, content in sample_files:
            self.write_file(
                scenario_path / "samples" / filename,
                content
            )
        
        # 4. 生成checker
        checker_code = generate_checker_code(
            self.plan.get("checklist", {}),
            self.plan["tools_design"]
        )
        self.write_file(
            scenario_path / "checkers" / f"{self.scenario_name}_checker.py",
            checker_code
        )
        
        # 5. 生成BusinessRules.md
        self.generate_business_rules(scenario_path)
        
        return scenario_path
    
    def write_file(self, path: Path, content: str):
        """写文件,自动创建目录"""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
```

#### 3.2 运行评测

```python
# executor/runner.py

class EvaluationRunner:
    """运行生成的scenario评测"""
    
    def __init__(self, scenario_path: str):
        self.scenario_path = Path(scenario_path)
        self.scenario_name = self.scenario_path.name
    
    def run(self, target_model: str = "claude-sonnet-4"):
        """运行评测"""
        
        # 1. 初始化DB
        self.init_database()
        
        # 2. 加载samples
        samples = self.load_samples()
        
        # 3. 运行每个sample
        results = []
        for sample in samples:
            result = self.run_single_sample(sample, target_model)
            results.append(result)
        
        # 4. 生成报告
        report = self.generate_report(results)
        
        return report
    
    def init_database(self):
        """初始化数据库"""
        init_module = import_module(
            f"scenarios.{self.scenario_name}.db.init_db"
        )
        init_module.init_db(self.db_path)
    
    def run_single_sample(self, sample: dict, target_model: str):
        """运行单个sample"""
        
        # 使用现有的Universal Framework executor
        from evaluation_tools.executor import execute_sample
        
        result = execute_sample(
            scenario_name=self.scenario_name,
            sample_id=sample["sample_id"],
            target_model=target_model
        )
        
        return result
```

---

### Step 4: 命令行接口 (2天)

```python
# cli/main.py

import click
from init_agent.agent import InitAgent
from code_generator.generator import CodeGenerator
from executor.runner import EvaluationRunner

@click.group()
def cli():
    """Universal Framework Agent CLI"""
    pass

@cli.command()
@click.argument('description_file')
@click.option('--output', default='execution_plan.json')
def init(description_file, output):
    """生成execution plan"""
    
    # 读取用户描述
    with open(description_file, 'r') as f:
        description = f.read()
    
    # 生成plan
    agent = InitAgent()
    plan = agent.generate_plan(description)
    
    # 保存plan
    with open(output, 'w') as f:
        json.dump(plan, f, indent=2, ensure_ascii=False)
    
    click.echo(f"✅ Execution plan saved to {output}")

@cli.command()
@click.argument('plan_file')
@click.option('--output-dir', default='scenarios')
def generate(plan_file, output_dir):
    """根据plan生成scenario代码"""
    
    # 读取plan
    with open(plan_file, 'r') as f:
        plan = json.load(f)
    
    # 生成代码
    builder = ScenarioBuilder(plan, output_dir)
    scenario_path = builder.build()
    
    click.echo(f"✅ Scenario generated at {scenario_path}")

@cli.command()
@click.argument('scenario_path')
@click.option('--model', default='claude-sonnet-4')
def run(scenario_path, model):
    """运行评测"""
    
    runner = EvaluationRunner(scenario_path)
    results = runner.run(target_model=model)
    
    click.echo(f"✅ Evaluation completed")
    click.echo(f"Results: {results['summary']}")

@cli.command()
@click.argument('description_file')
@click.option('--model', default='claude-sonnet-4')
def auto(description_file, model):
    """一键执行: init + generate + run"""
    
    # 1. Init
    click.echo("Step 1/3: Generating execution plan...")
    # ... (调用init)
    
    # 2. Generate
    click.echo("Step 2/3: Generating code...")
    # ... (调用generate)
    
    # 3. Run
    click.echo("Step 3/3: Running evaluation...")
    # ... (调用run)
    
    click.echo("✅ All done!")

if __name__ == '__main__':
    cli()
```

---

## 📝 使用示例

### 1. 创建场景描述文件

```yaml
# my_scenario.yaml

scenario_description: |
  测试Agent的请假管理能力。
  
  业务规则:
  - 员工有年假12天,病假10天
  - 请假需要提前3天申请
  - 余额不足时拒绝
  - 请假需要经理审批
  
  核心功能:
  1. 查询请假余额
  2. 提交请假申请
  3. 修改请假申请

test_goals:
  - 测试正常请假流程
  - 测试余额不足场景
  - 测试临界值处理
```

### 2. 一键执行

```bash
# 方式1: 分步执行
python cli/main.py init my_scenario.yaml
python cli/main.py generate execution_plan.json
python cli/main.py run scenarios/leave_application

# 方式2: 一键执行
python cli/main.py auto my_scenario.yaml --model claude-sonnet-4
```

### 3. 查看结果

```bash
# 查看生成的代码
tree scenarios/leave_application/

# 查看评测结果
cat scenarios/leave_application/evaluation_outputs/*/evaluation_results/evaluation_*.json
```

---

## ✅ MVP验收标准

完成以下demo即可算MVP成功:

1. ✅ 输入自然语言描述
2. ✅ 自动生成execution_plan
3. ✅ 自动生成完整scenario代码(tools/db/samples/checker)
4. ✅ 代码可以正常运行
5. ✅ 得到评测结果报告

**关键指标**:
- 从描述到结果 < 20分钟
- 生成的代码准确率 > 80%
- 评测可以正常执行

---

## 🎯 后续优化方向

MVP完成后可以逐步优化:

1. **Plan质量提升**
   - 增加更多参考场景
   - 优化prompt engineering
   - 添加plan验证机制

2. **代码生成优化**
   - 支持更复杂的业务逻辑
   - 改进SQL生成质量
   - 添加代码测试生成

3. **执行优化**
   - 支持断点恢复(Harness机制)
   - 失败自动replan
   - 并行执行多个sample

4. **产品化**
   - Web UI界面
   - 实时进度展示
   - Plan模板库
   - 多模型对比

