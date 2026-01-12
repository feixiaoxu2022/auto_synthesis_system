"""
智能任务分配样本生成器 - 格式转换核心代码
=========================================

本文件展示如何将样本输出为开源版格式（扁平结构、JSONL）。
算法逻辑参考：CSP约束求解模式

关键修改点：
1. _convert_to_evaluation_format() - 输出扁平结构，移除extra_info嵌套
2. build_environment() - content为JSONL字符串而非JSON对象
3. save_samples() - 输出为eval.jsonl而非单个.json文件
"""

import json
from typing import Dict, List, Any
from pathlib import Path

# 假设CSP算法从同目录导入
# from assignment_algorithm import ScenarioGenerator


def build_environment(sample: Dict) -> List[Dict]:
    """
    构建环境数据（开源版格式）

    关键变化：
    - content 是 JSONL 字符串，而非 JSON 对象
    - 每个实体类型一个文件
    """
    environment = []

    # workers.jsonl
    if sample.get('workers'):
        workers_content = '\n'.join(
            json.dumps(worker, ensure_ascii=False)
            for worker in sample['workers']
        )
        environment.append({
            "path": "workers.jsonl",
            "type": "file",
            "content": workers_content
        })

    # tasks.jsonl
    if sample.get('tasks'):
        tasks_content = '\n'.join(
            json.dumps(task, ensure_ascii=False)
            for task in sample['tasks']
        )
        environment.append({
            "path": "tasks.jsonl",
            "type": "file",
            "content": tasks_content
        })

    # assignments.jsonl (初始为空)
    environment.append({
        "path": "assignments.jsonl",
        "type": "file",
        "content": ""  # 初始状态为空，Agent需要通过工具创建
    })

    return environment


def generate_check_list(sample: Dict) -> List[Dict]:
    """
    根据预期分配结果生成检查点

    与原始算法保持一致，只是格式调整
    """
    check_list = []
    expected_assignments = sample.get("expected_assignments", [])
    workers = sample.get("workers", [])
    tasks = sample.get("tasks", [])

    # 创建快速查找映射
    worker_map = {w["worker_id"]: w for w in workers}
    task_map = {t["task_id"]: t for t in tasks}

    # 为每个任务分配添加检查点
    for assignment in expected_assignments:
        task_id = assignment["task_id"]
        worker_id = assignment["worker_id"]

        # 任务状态更新检查
        check_list.append({
            "check_type": "entity_attribute_equals",
            "params": {
                "entity_type": "tasks",
                "target_id": task_id,
                "attribute_key": "status",
                "expected_value": "assigned"
            },
            "description": f"验证任务{task_id}状态更新为assigned"
        })

        # 分配人员检查
        check_list.append({
            "check_type": "entity_attribute_equals",
            "params": {
                "entity_type": "tasks",
                "target_id": task_id,
                "attribute_key": "assigned_worker_id",
                "expected_value": worker_id
            },
            "description": f"验证任务{task_id}分配给{worker_id}"
        })

    # 计算每个工作人员的最终预期负载
    worker_final_workloads = {}
    for worker in workers:
        worker_id = worker["worker_id"]
        initial_workload = worker.get("current_workload_hours", 0)

        total_assigned_hours = 0
        for assignment in expected_assignments:
            if assignment["worker_id"] == worker_id:
                task = task_map.get(assignment["task_id"], {})
                total_assigned_hours += task.get("required_hours", 0)

        if total_assigned_hours > 0:
            expected_final_workload = round(initial_workload + total_assigned_hours, 2)
            worker_final_workloads[worker_id] = expected_final_workload

    # 添加最终负载检查点
    for worker_id, expected_workload in worker_final_workloads.items():
        initial_workload = worker_map[worker_id].get("current_workload_hours", 0)
        check_list.append({
            "check_type": "entity_attribute_equals",
            "params": {
                "entity_type": "workers",
                "target_id": worker_id,
                "attribute_key": "current_workload_hours",
                "expected_value": expected_workload
            },
            "description": f"验证工作人员{worker_id}的最终负载从{initial_workload}小时更新为{expected_workload}小时"
        })

    return check_list


def assess_difficulty(sample: Dict) -> str:
    """评估样本难度"""
    tasks = sample["tasks"]

    urgent_tasks = len([t for t in tasks if t.get("urgency_level", 0) >= 8])
    complex_tasks = len([t for t in tasks if t.get("complexity_score", 0) >= 7])
    dependent_tasks = len([t for t in tasks if t.get("dependencies")])

    if urgent_tasks >= 2 or complex_tasks >= 2 or dependent_tasks >= 2:
        return "hard"
    elif urgent_tasks >= 1 or complex_tasks >= 1 or dependent_tasks >= 1:
        return "medium"
    else:
        return "easy"


def convert_to_evaluation_format(
    sample: Dict,
    index: int,
    query: str,
    system_prompt: str,
    prefix: str = "ITA_SCHED"
) -> Dict[str, Any]:
    """
    将算法输出转换为开源版扁平格式

    关键变化：
    - 移除 extra_info 嵌套
    - servers/environment/check_list 直接在顶层
    - environment 使用 JSONL 格式
    - 新增 extension 字段用于扩展元数据
    """
    sample_id = f"{prefix}_{index:03d}"

    return {
        # === 核心字段（顶层） ===
        "data_id": sample_id,
        "query": query,
        "system": system_prompt,

        # MCP服务列表
        "servers": ["intelligent_task_service"],

        # 环境数据（JSONL格式）
        "environment": build_environment(sample),

        # 检查点列表
        "check_list": generate_check_list(sample),

        # 扩展字段（用于场景特定元数据）
        "extension": {
            "sub_scenario": "智能任务分配-基于原则的分配",
            "level_of_difficulty": assess_difficulty(sample),
            "task_count": len(sample.get("tasks", [])),
            "worker_count": len(sample.get("workers", [])),
            "assignment_count": len(sample.get("expected_assignments", []))
        }
    }


def save_samples(samples: List[Dict], output_dir: Path):
    """
    保存样本为JSONL格式

    关键变化：
    - 输出单个 eval.jsonl 文件
    - 每行一个样本（JSON格式）
    - 不再输出单独的 .json 文件
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "eval.jsonl"

    with open(output_file, 'w', encoding='utf-8') as f:
        for sample in samples:
            f.write(json.dumps(sample, ensure_ascii=False) + '\n')

    print(f"已生成 {len(samples)} 个样本: {output_file}")


# =========================================
# 使用示例
# =========================================

def generate_sample_example():
    """演示如何使用上述函数生成样本"""

    # 1. 准备算法输出的原始样本数据
    raw_sample = {
        "workers": [
            {
                "worker_id": "W001",
                "worker_name": "张工",
                "capabilities": ["python", "java"],
                "experience_level": "senior",
                "current_workload_hours": 20,
                "max_workload_hours": 40
            },
            {
                "worker_id": "W002",
                "worker_name": "李工",
                "capabilities": ["python", "frontend"],
                "experience_level": "mid",
                "current_workload_hours": 15,
                "max_workload_hours": 40
            }
        ],
        "tasks": [
            {
                "task_id": "T001",
                "task_name": "后端API开发",
                "required_capabilities": ["python"],
                "urgency_level": 8,
                "complexity_score": 6,
                "required_hours": 8,
                "dependencies": [],
                "status": "pending"
            },
            {
                "task_id": "T002",
                "task_name": "前端页面优化",
                "required_capabilities": ["frontend"],
                "urgency_level": 5,
                "complexity_score": 4,
                "required_hours": 4,
                "dependencies": [],
                "status": "pending"
            }
        ],
        "expected_assignments": [
            {
                "task_id": "T001",
                "worker_id": "W001",
                "rationale": "张工为senior级别，具备python能力，当前负载20h可承接8h任务"
            },
            {
                "task_id": "T002",
                "worker_id": "W002",
                "rationale": "李工具备frontend能力，当前负载15h可承接4h任务"
            }
        ]
    }

    # 2. 准备其他参数
    query = "请帮忙分配一下待处理的任务"
    system_prompt = "# 智能任务分配业务规则\n\n你是一名智能任务分配助手..."

    # 3. 转换为开源版格式
    sample = convert_to_evaluation_format(
        sample=raw_sample,
        index=1,
        query=query,
        system_prompt=system_prompt,
        prefix="ITA_SCHED"
    )

    # 4. 保存
    save_samples([sample], Path("./samples"))

    return sample


if __name__ == "__main__":
    sample = generate_sample_example()
    print(json.dumps(sample, ensure_ascii=False, indent=2))
