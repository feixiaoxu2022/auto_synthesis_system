"""
开源版Checker实现示例 - 共享单车客服场景
==========================================

本文件展示开源版checker的核心实现模式。
提取自: mcp-benchmark/release/scenarios/bikeshare/checker.py

核心模式：
1. 独立脚本，接受CLI参数
2. 支持多种check_type的检查器
3. 使用LiteLLM做语义检查
4. 统一的结果格式
"""

import json
import argparse
from typing import Dict, List, Any
from pathlib import Path

# =========================================
# 1. 检查结果格式
# =========================================

def create_check_result_template() -> Dict:
    """创建标准检查结果模板"""
    return {
        "check_version": "scenario_v1.0",
        "check_timestamp": 0,
        "check_details": {},
        "overall_result": "Success",  # Success / Failure / Error
        "error_reason": "",
        "check_list_count": 0,
        "completion_status": "in_progress",  # in_progress / completed / failed
        "completion_reason": ""
    }


def create_check_item_result(conclusion: str, reason: str, details: str) -> Dict:
    """创建单个检查项结果"""
    return {
        "检查结论": conclusion,  # 合格 / 不合格 / 跳过
        "原因": reason,
        "详情": details
    }


# =========================================
# 2. 数据状态检查器 (JSONL文件对比)
# =========================================

class JSONLDataChecker:
    """JSONL数据文件状态检查器"""

    def __init__(self, env_before: List[Dict], env_after: List[Dict]):
        """
        Args:
            env_before: 执行前的环境数据列表
            env_after: 执行后的环境数据列表
        """
        self.data_before = self._load_env_data(env_before)
        self.data_after = self._load_env_data(env_after)

    def _load_env_data(self, env_list: List[Dict]) -> Dict[str, List[Dict]]:
        """解析环境数据"""
        result = {}
        for item in env_list:
            path = item.get("path", "")
            content = item.get("content", "")
            # 解析JSONL内容
            records = []
            for line in content.strip().split("\n"):
                if line.strip():
                    records.append(json.loads(line))
            result[path] = records
        return result

    def check_entity_attribute_equals(self, check_item: Dict) -> Dict:
        """
        检查实体属性是否等于预期值

        check_item示例:
        {
            "check_type": "entity_attribute_equals",
            "params": {
                "entity_type": "orders",
                "target_id": "order_001",
                "attribute_key": "status",
                "expected_value": "completed"
            }
        }
        """
        params = check_item.get("params", {})
        entity_type = params.get("entity_type")
        target_id = params.get("target_id")
        attribute_key = params.get("attribute_key")
        expected_value = params.get("expected_value")

        # 文件映射
        file_mapping = {
            "users": "users.jsonl",
            "orders": "orders.jsonl",
        }

        # ID字段映射
        id_mapping = {
            "users": "uuid",
            "orders": "order_guid",
        }

        target_file = file_mapping.get(entity_type)
        id_field = id_mapping.get(entity_type)
        records = self.data_after.get(target_file, [])

        # 查找目标实体
        target_entity = None
        for record in records:
            if record.get(id_field) == target_id:
                target_entity = record
                break

        if not target_entity:
            return create_check_item_result(
                "不合格", "实体不存在",
                f"未找到ID为 {target_id} 的 {entity_type} 实体"
            )

        # 检查属性
        actual_value = target_entity.get(attribute_key)
        if actual_value == expected_value:
            return create_check_item_result(
                "合格", "属性值匹配",
                f"属性 {attribute_key} = '{actual_value}'，符合期望"
            )
        else:
            return create_check_item_result(
                "不合格", "属性值不匹配",
                f"属性 {attribute_key} = '{actual_value}'，期望 '{expected_value}'"
            )

    def check_create_operation_verified(self, check_item: Dict) -> Dict:
        """
        检查创建操作是否验证成功（对比执行前后新增的实体）

        check_item示例:
        {
            "check_type": "create_operation_verified",
            "params": {
                "entity_type": "maintenance_tickets",
                "filter_conditions": {"status": "open"},
                "min_count": 1
            }
        }
        """
        params = check_item.get("params", {})
        entity_type = params.get("entity_type")
        filter_conditions = params.get("filter_conditions", {})
        min_count = params.get("min_count", 1)

        # 文件映射
        file_mapping = {
            "users": "users.jsonl",
            "orders": "orders.jsonl",
            "maintenance_tickets": "maintenance_tickets.jsonl"
        }

        # ID字段映射
        id_mapping = {
            "users": "uuid",
            "orders": "order_guid",
            "maintenance_tickets": "ticket_id"
        }

        target_file = file_mapping.get(entity_type)
        id_field = id_mapping.get(entity_type)

        before_records = self.data_before.get(target_file, [])
        after_records = self.data_after.get(target_file, [])

        # 找到执行前的ID集合
        before_ids = {record.get(id_field) for record in before_records}

        # 找到新增的记录（执行后有但执行前没有）
        new_records = []
        for record in after_records:
            record_id = record.get(id_field)
            if record_id and record_id not in before_ids:
                # 检查过滤条件
                if all(record.get(k) == v for k, v in filter_conditions.items()):
                    new_records.append(record)

        if len(new_records) >= min_count:
            return create_check_item_result(
                "合格", "创建操作成功",
                f"成功创建 {len(new_records)} 个 {entity_type} 实体"
            )
        else:
            return create_check_item_result(
                "不合格", "创建数量不足",
                f"创建了 {len(new_records)} 个，不满足最小数量 {min_count}"
            )


# =========================================
# 3. 工具调用检查器
# =========================================

class ToolCalledWithParamsChecker:
    """工具调用参数检查器"""

    def check(self, params: Dict, conversation_history: List[Dict]) -> Dict:
        """
        检查工具是否以正确参数被调用

        params示例:
        {
            "tool_name": "adjust_order_fee",
            "expected_params": {"order_guid": "order_001", "new_fee": 5.0}
        }
        """
        tool_name = params.get("tool_name")
        expected_params = params.get("expected_params", {})

        # 从对话历史中查找工具调用
        for message in conversation_history:
            if message.get("role") == "assistant" and "tool_calls" in message:
                for tool_call in message["tool_calls"]:
                    if tool_call.get("function", {}).get("name") == tool_name:
                        arguments = tool_call.get("function", {}).get("arguments", {})
                        if isinstance(arguments, str):
                            try:
                                arguments = json.loads(arguments)
                            except json.JSONDecodeError:
                                continue

                        # 检查参数匹配（None作为通配符）
                        matched = all(
                            arguments.get(k) == v
                            for k, v in expected_params.items()
                            if v is not None
                        )

                        if matched:
                            return create_check_item_result(
                                "合格", "工具调用参数匹配",
                                f"工具 '{tool_name}' 使用正确参数调用"
                            )

        return create_check_item_result(
            "不合格", "工具未被调用或参数不匹配",
            f"未找到工具 '{tool_name}' 的正确调用"
        )


class ToolCallAbsenceChecker:
    """工具调用缺失检查器 - 验证指定工具未被调用"""

    def check(self, params: Dict, conversation_history: List[Dict]) -> Dict:
        """
        检查指定的工具是否没有被调用

        params示例:
        {
            "forbidden_tools": ["issue_coupon", "adjust_order_fee"]
        }
        """
        forbidden_tools = params.get("forbidden_tools", [])

        # 搜索对话历史中的工具调用
        called_forbidden_tools = []

        for message in conversation_history:
            if message.get("role") == "assistant" and "tool_calls" in message:
                for tool_call in message["tool_calls"]:
                    tool_name = tool_call.get("function", {}).get("name", "")
                    if tool_name in forbidden_tools:
                        called_forbidden_tools.append(tool_name)

        if not called_forbidden_tools:
            return create_check_item_result(
                "合格", "未调用禁止工具",
                f"Agent正确地没有调用禁止的工具: {forbidden_tools}"
            )
        else:
            return create_check_item_result(
                "不合格", "调用了禁止工具",
                f"Agent调用了禁止的工具: {called_forbidden_tools}"
            )


class PrerequisiteCheckPerformedChecker:
    """前置检查验证器 - 验证Agent在执行业务操作前进行了必要的前置检查"""

    def check(self, params: Dict, conversation_history: List[Dict]) -> Dict:
        """
        检查Agent是否在执行业务操作前进行了必要的前置检查

        params示例:
        {
            "prerequisite_tool": "get_user_info",
            "business_tool": "issue_coupon",
            "related_entity_id": "user_uuid"
        }
        """
        prerequisite_tool = params.get("prerequisite_tool")
        business_tool = params.get("business_tool")
        related_entity_id = params.get("related_entity_id")

        # 找到所有工具调用及其时间顺序
        tool_calls_timeline = []

        for i, message in enumerate(conversation_history):
            if message.get("role") == "assistant" and "tool_calls" in message:
                for tool_call in message["tool_calls"]:
                    tool_name = tool_call.get("function", {}).get("name", "")
                    call_params = {}
                    try:
                        call_params = json.loads(
                            tool_call.get("function", {}).get("arguments", "{}")
                        )
                    except json.JSONDecodeError:
                        pass

                    tool_calls_timeline.append({
                        "message_index": i,
                        "tool_name": tool_name,
                        "params": call_params
                    })

        # 查找前置检查和业务操作的调用
        prerequisite_calls = [c for c in tool_calls_timeline if c["tool_name"] == prerequisite_tool]
        business_calls = [c for c in tool_calls_timeline if c["tool_name"] == business_tool]

        if not business_calls:
            return create_check_item_result(
                "跳过", "业务工具未被调用",
                f"业务工具 '{business_tool}' 未被调用，无需检查前置条件"
            )

        # 检查是否存在正确的调用顺序
        for business_call in business_calls:
            # 找到在此业务调用之前的前置检查
            prior_checks = [
                c for c in prerequisite_calls
                if c["message_index"] < business_call["message_index"]
            ]

            if prior_checks:
                # 如果指定了entity_id，检查是否针对同一实体
                if related_entity_id:
                    check_entity = prior_checks[-1]["params"].get(related_entity_id)
                    business_entity = business_call["params"].get(related_entity_id)
                    if check_entity and check_entity == business_entity:
                        return create_check_item_result(
                            "合格", "前置检查已执行",
                            f"Agent在调用 '{business_tool}' 前正确调用了 '{prerequisite_tool}'"
                        )
                else:
                    return create_check_item_result(
                        "合格", "前置检查已执行",
                        f"Agent在调用 '{business_tool}' 前调用了 '{prerequisite_tool}'"
                    )

        return create_check_item_result(
            "不合格", "未执行前置检查",
            f"Agent在调用 '{business_tool}' 前未调用 '{prerequisite_tool}'"
        )


# =========================================
# 4. 响应关键词检查器 (支持LLM语义判断)
# =========================================

class ResponseContainsKeywordsChecker:
    """响应关键词检查器"""

    def __init__(self, model_name=None, api_base=None, api_key=None):
        self.model_name = model_name
        self.api_base = api_base
        self.api_key = api_key

    def check(self, params: Dict, result_data: Dict) -> Dict:
        """
        检查响应是否包含关键词

        params示例:
        {
            "expected_keywords": ["费用已调整", "订单"],
            "use_llm_judge": true  # 是否使用LLM语义判断
        }
        """
        expected_keywords = params.get("expected_keywords", [])
        use_llm = params.get("use_llm_judge", False)
        response = result_data.get("response", "")

        if use_llm and self.model_name:
            # LLM语义判断模式
            return self._check_with_llm(expected_keywords, response)
        else:
            # 简单字符串匹配模式
            return self._check_simple(expected_keywords, response)

    def _check_simple(self, keywords: List[str], response: str) -> Dict:
        """简单字符串匹配"""
        found = [kw for kw in keywords if kw in response]
        missing = [kw for kw in keywords if kw not in response]

        if not missing:
            return create_check_item_result(
                "合格", "包含所有关键词",
                f"响应包含: {found}"
            )
        else:
            return create_check_item_result(
                "不合格", "缺少关键词",
                f"响应缺少: {missing}"
            )

    def _check_with_llm(self, keywords: List[str], response: str) -> Dict:
        """LLM语义判断"""
        # TODO: 调用LiteLLM进行语义判断
        # 参考完整实现中的 request_llm_with_litellm 函数
        pass


# =========================================
# 5. 主检查流程
# =========================================

def perform_check(bench_data: Dict, result_data: Dict,
                  model_name: str, api_base: str, api_key: str,
                  work_dir: str = ".") -> Dict:
    """
    执行完整检查流程

    Args:
        bench_data: 样本数据(包含check_list)
        result_data: 执行结果数据
        model_name: LLM模型名称
        api_base: LLM API地址
        api_key: LLM API密钥
        work_dir: 工作目录
    """
    check_result = create_check_result_template()

    try:
        # 获取检查列表
        check_list = bench_data.get("check_list", [])
        check_result["check_list_count"] = len(check_list)

        # 获取环境数据
        env_before = bench_data.get("environment", [])
        env_after = load_env_after_from_disk(work_dir)

        # 获取对话历史（用于工具调用相关检查）
        conversation_history = result_data.get("conversation_history", [])

        # 创建检查器
        data_checker = JSONLDataChecker(env_before, env_after)
        tool_checker = ToolCalledWithParamsChecker()
        tool_absence_checker = ToolCallAbsenceChecker()
        prerequisite_checker = PrerequisiteCheckPerformedChecker()
        response_checker = ResponseContainsKeywordsChecker(model_name, api_base, api_key)

        # 执行各项检查
        for i, item in enumerate(check_list):
            check_idx = f"检查项{i + 1}"
            check_type = item.get("check_type")

            if check_type == "entity_attribute_equals":
                check_result["check_details"][check_idx] = \
                    data_checker.check_entity_attribute_equals(item)

            elif check_type == "create_operation_verified":
                check_result["check_details"][check_idx] = \
                    data_checker.check_create_operation_verified(item)

            elif check_type == "tool_called_with_params":
                check_result["check_details"][check_idx] = \
                    tool_checker.check(item.get("params", {}), conversation_history)

            elif check_type == "tool_call_absence":
                check_result["check_details"][check_idx] = \
                    tool_absence_checker.check(item.get("params", {}), conversation_history)

            elif check_type == "prerequisite_check_performed":
                check_result["check_details"][check_idx] = \
                    prerequisite_checker.check(item.get("params", {}), conversation_history)

            elif check_type == "response_contains_keywords":
                check_result["check_details"][check_idx] = \
                    response_checker.check(item.get("params", {}), result_data)

            else:
                check_result["check_details"][check_idx] = create_check_item_result(
                    "跳过", f"不支持的检查类型: {check_type}", ""
                )

        # 计算总体结果
        failed_items = [
            k for k, v in check_result["check_details"].items()
            if v["检查结论"] == "不合格"
        ]

        if failed_items:
            check_result["overall_result"] = "Failure"
            check_result["error_reason"] = f"失败项: {', '.join(failed_items)}"
        else:
            check_result["overall_result"] = "Success"

        check_result["completion_status"] = "completed"

    except Exception as e:
        check_result["overall_result"] = "Error"
        check_result["error_reason"] = str(e)
        check_result["completion_status"] = "failed"

    return check_result


def load_env_after_from_disk(work_dir: str) -> List[Dict]:
    """从磁盘加载执行后环境数据"""
    env_after = []
    expected_files = ["users.jsonl", "orders.jsonl"]

    for filename in expected_files:
        file_path = Path(work_dir) / filename
        if file_path.exists():
            content = file_path.read_text(encoding="utf-8")
            env_after.append({"path": filename, "content": content})

    return env_after


# =========================================
# 6. CLI入口
# =========================================

def main():
    parser = argparse.ArgumentParser(description="场景自动评估检查脚本")
    parser.add_argument("--bench", required=True, help="bench.json文件路径")
    parser.add_argument("--result", required=True, help="result.json文件路径")
    parser.add_argument("--model", required=True, help="检查用的模型名称")
    parser.add_argument("--base-url", required=True, help="模型API base URL")
    parser.add_argument("--api-key", required=True, help="模型API密钥")
    parser.add_argument("--output", default="check_result.json", help="输出文件路径")
    parser.add_argument("--work-dir", default=".", help="工作目录")
    args = parser.parse_args()

    # 加载输入文件
    with open(args.bench, "r", encoding="utf-8") as f:
        bench_data = json.load(f)
    with open(args.result, "r", encoding="utf-8") as f:
        result_data = json.load(f)

    # 执行检查
    check_result = perform_check(
        bench_data, result_data,
        args.model, args.base_url, args.api_key,
        args.work_dir
    )

    # 保存结果
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(check_result, f, ensure_ascii=False, indent=2)

    print(f"检查完成: {check_result['overall_result']}")


if __name__ == "__main__":
    main()
