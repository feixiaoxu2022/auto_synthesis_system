"""
数据池生成器模板
================

输出格式：JSONL（每行一条JSON记录）
输出位置：工作目录下的 data_pools/ 目录

复制此文件后，按以下步骤修改：
1. [CONFIG] 区：修改 SYSTEM_TIME、OUTPUT_DIR、ENTITY_COUNTS
2. [DISTRIBUTIONS] 区：根据 unified_scenario_design.yaml 的 entities 定义分布
3. [GENERATORS] 区：为每个实体实现生成函数
4. [RELATIONS] 区：处理实体间引用关系

注意：OUTPUT_DIR 应指向工作目录下的 data_pools/ 相对路径或绝对路径
"""

import json
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Tuple


# ============================================
# [CONFIG] 基础配置 - 必须修改
# ============================================

# TODO: 从 unified_scenario_design.yaml 的 runtime_config.system_time 获取
SYSTEM_TIME = datetime(2024, 1, 1, 9, 0, 0)

# TODO: 修改为工作目录下的 data_pools/ 路径
# 方式1（相对路径）：OUTPUT_DIR = Path("data_pools")
# 方式2（绝对路径）：OUTPUT_DIR = Path("/absolute/path/to/working_dir/data_pools")
OUTPUT_DIR = Path("data_pools")  # 默认使用相对路径

# TODO: 定义各实体生成数量
ENTITY_COUNTS = {
    # "entity_name": count,
}


# ============================================
# [DISTRIBUTIONS] 分布配置 - 根据业务规则定义
# ============================================

# TODO: 从 YAML 的 entities.*.attributes.*.distribution 提取
# 枚举字段分布
ENUM_DISTRIBUTIONS = {
    # "field_name": {"value1": 0.5, "value2": 0.3, "value3": 0.2},
}

# 数值字段分层（确保边界值覆盖）
NUMERIC_TIERS = {
    # "field_name": [
    #     (0.2, (0, 10)),     # 20% 在 0-10 区间
    #     (0.5, (11, 50)),    # 50% 在 11-50 区间
    #     (0.3, (51, 100)),   # 30% 在 51-100 区间
    # ],
}


# ============================================
# [UTILS] 工具函数 - 无需修改
# ============================================

def weighted_choice(distribution: Dict[str, float]) -> str:
    """按权重随机选择枚举值"""
    items = list(distribution.keys())
    weights = list(distribution.values())
    return random.choices(items, weights=weights, k=1)[0]


def tiered_random(tiers: List[Tuple[float, Tuple[int, int]]]) -> int:
    """分层随机数，确保各区间覆盖"""
    tier = random.choices([t[1] for t in tiers], weights=[t[0] for t in tiers], k=1)[0]
    return random.randint(tier[0], tier[1])


def gen_id(prefix: str, index: int, width: int = 3) -> str:
    """生成标准ID: PREFIX_001"""
    return f"{prefix}_{index:0{width}d}"


def random_time_before(base: datetime, max_days: int = 30) -> datetime:
    """基准时间之前的随机时间"""
    return base - timedelta(days=random.randint(1, max_days), hours=random.randint(0, 23))


def random_time_after(base: datetime, max_days: int = 14) -> datetime:
    """基准时间之后的随机时间"""
    return base + timedelta(days=random.randint(1, max_days), hours=random.randint(9, 18))


# ============================================
# [GENERATORS] 实体生成函数 - 必须实现
# ============================================

def generate_primary_entity(count: int) -> List[Dict[str, Any]]:
    """
    生成主实体（如 employees, users, advertisers）

    TODO: 根据 unified_scenario_design.yaml 的 entities 定义实现

    示例结构：
    {
        "entity_id": "ENT_001",
        "name": "...",
        "enum_field": weighted_choice(ENUM_DISTRIBUTIONS["enum_field"]),
        "numeric_field": tiered_random(NUMERIC_TIERS["numeric_field"]),
        "created_at": "2024-01-01 09:00:00"
    }
    """
    entities = []
    for i in range(1, count + 1):
        entity = {
            "id": gen_id("ENT", i),
            # TODO: 添加其他字段
        }
        entities.append(entity)
    return entities


def generate_secondary_entity(primary_entities: List[Dict], count: int) -> List[Dict[str, Any]]:
    """
    生成关联实体（如 orders, applications, bookings）

    注意：必须引用 primary_entities 中真实存在的 ID

    TODO: 实现具体生成逻辑
    """
    entities = []
    for i in range(1, count + 1):
        # 随机选择一个主实体建立关联
        primary = random.choice(primary_entities)

        entity = {
            "id": gen_id("SEC", i),
            "primary_id": primary["id"],  # 外键引用
            # TODO: 添加其他字段
        }
        entities.append(entity)
    return entities


def generate_with_dependencies(count: int) -> List[Dict[str, Any]]:
    """
    生成有依赖关系的实体（如 tasks with dependencies）

    策略：分层生成
    1. 先生成 70% 无依赖实体
    2. 再基于已有实体生成 30% 有依赖实体
    """
    entities = []

    # Step 1: 无依赖实体
    independent_count = int(count * 0.7)
    for i in range(independent_count):
        entity = {
            "id": gen_id("DEP", i),
            "dependencies": None,
            "created_time": random_time_before(SYSTEM_TIME),
        }
        entities.append(entity)

    # Step 2: 有依赖实体（引用已存在的实体）
    for i in range(independent_count, count):
        dep_entity = random.choice(entities)
        entity = {
            "id": gen_id("DEP", i),
            "dependencies": [dep_entity["id"]],
            "created_time": dep_entity["created_time"] + timedelta(hours=random.randint(1, 24)),
        }
        entities.append(entity)

    return entities


# ============================================
# [VALIDATION] 验证函数 - 无需修改
# ============================================

def validate_data_pool(data: Dict[str, List]) -> bool:
    """验证数据池完整性"""
    errors = []

    # 1. ID唯一性
    for entity_type, entities in data.items():
        if not entities:
            continue
        id_field = next((k for k in entities[0].keys() if "id" in k.lower()), None)
        if id_field:
            ids = [e.get(id_field) for e in entities]
            if len(ids) != len(set(ids)):
                errors.append(f"{entity_type}: 存在重复ID")

    # 2. 外键引用有效性（需要自定义检查逻辑）
    # TODO: 根据实际实体关系添加验证

    if errors:
        print("❌ 验证失败:")
        for err in errors:
            print(f"  - {err}")
        return False

    print("✅ 数据池验证通过")
    return True


def print_stats(data: Dict[str, List]) -> None:
    """打印数据统计"""
    print("\n📊 数据统计:")
    for entity_type, entities in data.items():
        print(f"  {entity_type}: {len(entities)} 条")


# ============================================
# [MAIN] 主函数 - 修改实体生成调用
# ============================================

def main():
    print(f"🚀 生成数据池 (基准时间: {SYSTEM_TIME})")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # TODO: 按依赖顺序调用生成函数
    # 1. 先生成被引用实体
    # primary = generate_primary_entity(ENTITY_COUNTS["primary"])

    # 2. 再生成引用方实体
    # secondary = generate_secondary_entity(primary, ENTITY_COUNTS["secondary"])

    # 组装数据池
    data_pool = {
        # "primary": primary,
        # "secondary": secondary,
    }

    # 验证
    if not validate_data_pool(data_pool):
        return

    print_stats(data_pool)

    # 保存为JSONL格式
    for name, entities in data_pool.items():
        path = OUTPUT_DIR / f"{name}.jsonl"
        with open(path, 'w', encoding='utf-8') as f:
            for entity in entities:
                f.write(json.dumps(entity, ensure_ascii=False) + '\n')
        print(f"✅ 保存 {path}")


if __name__ == "__main__":
    main()
