"""
Bikeshare样本生成器 - 格式转换核心代码
=====================================

本文件展示如何将样本输出为开源版格式（扁平结构、JSONL）。
算法逻辑参考：Prototype驱动 + 规则引擎模式

关键修改点：
1. format_sample() - 输出扁平结构，移除extra_info嵌套
2. build_environment() - content为JSONL字符串而非JSON对象
3. save_samples() - 输出为eval.jsonl而非单个.json文件
"""

import json
from typing import Dict, List, Any
from pathlib import Path

# 假设规则引擎从同目录导入
# import rule_engine


def build_environment(initial_state: Dict) -> List[Dict]:
    """
    构建环境数据（开源版格式）

    关键变化：content 是 JSONL 字符串，而非 JSON 对象
    """
    environment = []

    # users.jsonl
    if initial_state.get('users'):
        users_content = '\n'.join(
            json.dumps(user, ensure_ascii=False)
            for user in initial_state['users']
        )
        environment.append({
            "path": "users.jsonl",
            "type": "file",
            "content": users_content
        })

    # orders.jsonl
    if initial_state.get('orders'):
        orders_content = '\n'.join(
            json.dumps(order, ensure_ascii=False)
            for order in initial_state['orders']
        )
        environment.append({
            "path": "orders.jsonl",
            "type": "file",
            "content": orders_content
        })

    # bikes.jsonl
    if initial_state.get('bikes'):
        bikes_content = '\n'.join(
            json.dumps(bike, ensure_ascii=False)
            for bike in initial_state['bikes']
        )
        environment.append({
            "path": "bikes.jsonl",
            "type": "file",
            "content": bikes_content
        })

    # maintenance_tickets.jsonl (如果有)
    if initial_state.get('maintenance_tickets'):
        tickets_content = '\n'.join(
            json.dumps(ticket, ensure_ascii=False)
            for ticket in initial_state['maintenance_tickets']
        )
        environment.append({
            "path": "maintenance_tickets.jsonl",
            "type": "file",
            "content": tickets_content
        })

    return environment


def format_sample(
    sample_id: str,
    prototype: Dict,
    initial_state: Dict,
    system_prompt: str,
    formatted_query: str,
    check_list: List[Dict]
) -> Dict[str, Any]:
    """
    格式化样本为开源版扁平结构

    关键变化：
    - 移除 extra_info 嵌套
    - servers/environment/check_list 直接在顶层
    - environment 使用 JSONL 格式
    - 新增 extension 字段用于扩展元数据
    """
    return {
        # === 核心字段（顶层） ===
        "data_id": sample_id,
        "query": formatted_query,
        "system": system_prompt,

        # MCP服务列表
        "servers": ["bikeshare_customer_service"],

        # 环境数据（JSONL格式）
        "environment": build_environment(initial_state),

        # 检查点列表
        "check_list": check_list,

        # 用户模拟器（多轮场景使用，单轮可省略）
        # "user_simulator_prompt": "...",

        # 扩展字段（用于场景特定元数据）
        "extension": {
            "sub_scenario": f"智能客服-{prototype['rule_id']}-{prototype['expected_outcome']['type']}",
            "level_of_difficulty": "medium",
            "rule_id": prototype['rule_id']
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

    # 1. 准备初始状态（从数据池匹配得到）
    initial_state = {
        "users": [{
            "uuid": "usr_001",
            "name": "王晶",
            "user_loyalty_level": "gold",
            "user_credit_score": 75,
            "data.bk_close_lock_count_30day": 2,
            "coupons": []
        }],
        "orders": [{
            "order_guid": "ord_001",
            "user_uuid": "usr_001",
            "bike_id": "bk_001",
            "骑行状态": "进行中",
            "fee": 4.5
        }],
        "bikes": [{
            "bike_id": "bk_001",
            "status": "in_use",
            "is_faulty": False
        }],
        "maintenance_tickets": []
    }

    # 2. 准备prototype信息
    prototype = {
        "rule_id": "1.1",
        "description": "普通用户关锁失败场景",
        "expected_outcome": {"type": "standard_close_lock"}
    }

    # 3. 准备其他参数
    system_prompt = "# 智能客服业务规则库\n\n你是一名专业的B端智能客服..."
    formatted_query = "锁怎么都关不上！\n\n[系统识别相关订单：ord_001]"

    # 4. 调用规则引擎计算check_list（实际项目中）
    # check_list = rule_engine.calculate_ground_truth(scenario_info, initial_state)['check_list']
    check_list = [
        {
            "check_type": "entity_attribute_equals",
            "params": {
                "entity_type": "orders",
                "target_id": "ord_001",
                "attribute_key": "骑行状态",
                "expected_value": "已结束"
            },
            "description": "校验点源于规则1.1：应成功为用户远程关锁"
        }
    ]

    # 5. 格式化样本
    sample = format_sample(
        sample_id="BS_001",
        prototype=prototype,
        initial_state=initial_state,
        system_prompt=system_prompt,
        formatted_query=formatted_query,
        check_list=check_list
    )

    # 6. 保存
    save_samples([sample], Path("./samples"))

    return sample


if __name__ == "__main__":
    sample = generate_sample_example()
    print(json.dumps(sample, ensure_ascii=False, indent=2))
