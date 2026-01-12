---
name: checker-implementation
description: 实现Agent评测场景的检查器(Checkers)。当需要验证Agent行为是否正确、设计评测检查点时使用此技能。基于独立脚本模式。
---

# Checker实现指南

## 验证优先级（必须遵循）

| 优先级 | 验证类型 | 验证对象 | 判断方式 |
|-------|---------|---------|---------|
| 1 (最高) | 环境状态验证 | final_state数据 | Rule-based |
| 2 | 内容生成验证 | Agent生成的文件 | Rule + LLM |
| 3 | Response验证 | Agent回复文本 | Rule + LLM |
| 4 | 工具调用验证 | 工具调用记录 | Rule-based |

---

## 框架：独立脚本模式

开源版checker是独立的Python脚本，通过CLI参数运行。

### 基本结构

```python
#!/usr/bin/env python3
import json
import argparse

def perform_check(bench_data, result_data, model_name, api_base, api_key):
    """主检查函数"""
    check_result = {
        "overall_result": "Success",  # Success / Failure / Error
        "check_details": {},
        "check_list_count": 0,
    }

    check_list = bench_data.get("check_list", [])

    for i, item in enumerate(check_list):
        check_type = item.get("check_type")
        # 根据check_type调用相应检查器
        ...

    return check_result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bench", required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--output", default="check_result.json")
    args = parser.parse_args()

    # 加载数据、执行检查、保存结果
    ...

if __name__ == "__main__":
    main()
```

---

## 可用check_type速查

| check_type | 用途 | 关键参数 |
|------------|------|---------|
| `entity_attribute_equals` | 验证属性值 | entity_type, target_id, attribute_key, expected_value |
| `create_operation_verified` | 验证实体创建 | entity_type, filter_conditions, min_count |
| `tool_called_with_params` | 验证工具调用 | tool_name, expected_params |
| `response_contains_keywords` | 关键词检查 | expected_keywords, use_llm_judge |
| `tool_call_absence` | 验证工具未被调用 | forbidden_tools |
| `prerequisite_check_performed` | 验证调用顺序 | prerequisite_tool, business_tool, related_entity_id |

---

## check_item格式

```json
// 环境状态验证
{
  "check_type": "entity_attribute_equals",
  "params": {
    "entity_type": "orders",
    "target_id": "order_001",
    "attribute_key": "status",
    "expected_value": "completed"
  },
  "description": "订单状态应为已完成"
}

// 工具调用验证
{
  "check_type": "tool_called_with_params",
  "params": {
    "tool_name": "adjust_order_fee",
    "expected_params": {
      "order_guid": "order_001",
      "new_fee": 5.0
    }
  }
}

// Response语义检查（使用LLM）
{
  "check_type": "response_contains_keywords",
  "params": {
    "expected_keywords": ["费用已调整", "订单"],
    "use_llm_judge": true
  }
}

// 调用顺序验证
{
  "check_type": "prerequisite_check_performed",
  "params": {
    "prerequisite_tool": "get_user_info",
    "business_tool": "issue_coupon",
    "related_entity_id": "user_uuid"
  }
}
```

---

## 检查结果格式

```python
def create_check_item_result(conclusion, reason, details):
    """单个检查项结果"""
    return {
        "检查结论": conclusion,  # 合格 / 不合格 / 跳过
        "原因": reason,
        "详情": details
    }

# 示例
{
    "检查结论": "合格",
    "原因": "属性值匹配",
    "详情": "订单 order_001 的 status = 'completed'，符合期望"
}
```

---

## 总体结果格式

```json
{
  "check_version": "scenario_v1.0",
  "check_timestamp": 1704067200,
  "overall_result": "Success",
  "check_list_count": 3,
  "check_details": {
    "检查项1": {"检查结论": "合格", ...},
    "检查项2": {"检查结论": "合格", ...},
    "检查项3": {"检查结论": "不合格", ...}
  },
  "completion_status": "completed",
  "error_reason": "失败项: 检查项3"
}
```

---

## CLI调用方式

```bash
python checker.py \
  --bench sample.json \
  --result result.json \
  --model deepseek-v3 \
  --base-url https://api.deepseek.com/v1 \
  --api-key sk-xxx \
  --output check_result.json \
  --work-dir ./env_data
```

---

## 设计检查清单

- [ ] 优先使用环境状态验证（entity_attribute_equals）
- [ ] 工具调用验证仅用于：顺序验证、无状态动作
- [ ] expected_params使用字典格式，Agent决策参数用`null`通配
- [ ] 语义检查使用`use_llm_judge: true`
- [ ] 返回统一格式：`{检查结论, 原因, 详情}`

---

## Reference Files

| 文件 | 说明 |
|-----|------|
| [checker_script_example.py](examples/checker_script_example.py) | 完整的checker脚本示例 |

> 完整实现参考：`mcp-benchmark/release/scenarios/*/checker.py`
