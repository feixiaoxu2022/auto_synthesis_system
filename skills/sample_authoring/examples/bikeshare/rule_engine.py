"""
规则引擎 (Rule Engine)

将 BusinessRules_Plus.md 的自然语言规则翻译成精确的代码逻辑，
生成符合 format_extended.resource.json 规范的 check_list，并附带详细的自然语言解释。
"""

from typing import Dict, List, Any, Optional
import json
from datetime import datetime, timezone

# --- 固定基准时间 ---
# 为确保样本生成的稳定性和可重现性，使用固定的基准时间
# 必须与main.py中的FIXED_REFERENCE_TIME保持一致
FIXED_REFERENCE_TIME = datetime(2025, 7, 3, 14, 0, 0, tzinfo=timezone.utc)

# 兼容评测Checker的固定金额开关与常量
# 业务规则常量（与BusinessRules_Plus一致）
# 规则ID到自然语言的映射，用于生成可读性强的描述
RULE_EXPLANATIONS = {
    "1.1": "标准流程：普通用户关锁失败",
    "1.2": "风控拒绝：用户30天内关锁申诉次数超4次",
    "1.3A": "Agent责任制：禁停区关锁但车辆有故障，可处理",
    "1.3B": "Agent责任制：禁停区关锁但车辆无故障，应拒绝",
    "2.1": "Agent责任制：费用申诉的48小时时效性检查",
    "2.2": "复杂判断：违规停车费申诉豁免逻辑",
    "2.3": "小额计费异议快速处理",
    "3.1_severe": "上下文决策：骑行中报修严重安全故障",
    "3.1_general": "上下文决策：骑行中报修一般功能故障",
    "3.1_minor": "上下文决策：骑行中报修轻微问题",
    "3.2": "Agent责任制：重复报修检查",
    "4.1": "VIP复合危机处理",
    "5.1": "增值服务：主动关怀VIP用户临期优惠券",
    "6.1": "动态服务补偿矩阵",
    "7.1": "情绪安抚：识别用户负面情绪并发放安抚券"
}

def calculate_ground_truth(scenario_info: Dict[str, Any], initial_state: Dict[str, Any]) -> Dict[str, Any]:
    """
    根据场景信息和初始状态，计算预期的check_list和可读性描述

    Returns:
        Dict[str, Any]: 包含 "check_list" 和 "environment_description" 的字典
    """
    scenario_type = scenario_info.get('type', '')
    user_uuid = scenario_info.get('user_uuid')
    order_guid = scenario_info.get('order_guid')
    bike_id = scenario_info.get('bike_id')

    user = _find_entity_by_id(initial_state.get('users', []), 'uuid', user_uuid)
    order = _find_entity_by_id(initial_state.get('orders', []), 'order_guid', order_guid)
    bike = _find_entity_by_id(initial_state.get('bikes', []), 'bike_id', bike_id)

    if not user:
        return {"check_list": [], "environment_description": "错误：场景必须有关联用户。"}

    # 路由到具体的规则处理函数
    result = None
    if scenario_type == 'close_lock_failure':
        result = _calculate_close_lock_failure_logic(user, order, bike, scenario_info)

    elif scenario_type == 'fee_dispute_parking_violation':
        result = _calculate_parking_violation_dispute_logic(user, order)

    elif scenario_type == 'fee_dispute_billing_error':
        result = _calculate_billing_error_dispute_logic(user, order)

    elif scenario_type in ['bike_maintenance_severe_safety', 'bike_maintenance_general_function', 'bike_maintenance_minor_issue']:
        result = _calculate_maintenance_logic(user, order, bike, scenario_info)

    elif scenario_type == 'vip_composite_crisis':
        result = _calculate_vip_composite_crisis_logic(user, order, bike, scenario_info)

    elif scenario_type == 'proactive_care':
        result = _calculate_proactive_care_logic(user, scenario_info)

    elif scenario_type == 'emotion_appeasement':
        result = _calculate_emotion_appeasement_logic(user, order, bike, scenario_info)

    elif scenario_type == 'close_lock_with_appeasement':
        result = _calculate_close_lock_with_appeasement_logic(user, order, bike, scenario_info)

    elif scenario_type == 'in_trip_severe_fault_with_double_appeasement':
        result = _calculate_in_trip_severe_fault_with_double_appeasement_logic(user, order, bike, scenario_info)

    else:
        # 默认返回空
        return {"check_list": [], "environment_description": "未知的场景类型或未实现该场景的规则逻辑。"}

    # 规则5.1：主动关怀 - 统一后置检查
    # 在成功解决问题后，如果VIP用户有临期大额优惠券，应主动提醒
    # 排除已经专门处理5.1的场景，避免重复添加
    if result and scenario_type != 'proactive_care':
        if _should_trigger_proactive_care(user):
            checks = result.get('check_list', [])
            # 检查是否已有5.1相关检查（避免重复）
            has_proactive_care_check = any('主动' in str(check.get('description', '')) or
                                          ('优惠券' in str(check.get('description', '')) and '过期' in str(check.get('description', '')))
                                          for check in checks)

            if not has_proactive_care_check:
                checks.append({
                    "check_type": "response_contains_keywords",
                    "params": {"expected_keywords": ["优惠券", "即将过期", "提醒"]},
                    "description": f"校验点源于规则 {RULE_EXPLANATIONS['5.1']}：为VIP用户成功解决问题后，应主动提醒其有大额优惠券即将过期。"
                })
                result['check_list'] = checks

    return result if result else {"check_list": [], "environment_description": "未知的场景类型或未实现该场景的规则逻辑。"}


def _get_entity_setup_reason(entity_name: str, entity: Dict[str, Any], relevant_rules: List[str]) -> str:
    """生成单个实体的环境设置原因"""
    reasons = []
    if entity_name == "user":
        level = entity.get('user_loyalty_level', 'bronze')
        credit = entity.get('user_credit_score', 0)
        appeals = entity.get('data.bk_close_lock_count_30day', 0)
        violations = entity.get('recent_parking_violation_count_90d', 0)
        reasons.append(f"用户等级设为'{level}'(信用分{credit})")
        if appeals > 0:
            reasons.append(f"30天内申诉次数为{appeals}次")
        if violations > 0:
            reasons.append(f"90天内违停次数为{violations}次")
    
    elif entity_name == "order":
        is_hotspot = entity.get('destination_is_hotspot', False)
        in_no_parking = entity.get('is_in_no_parking_zone', False)
        completion_time_str = entity.get('completion_timestamp')
        if is_hotspot:
            reasons.append("订单目的地设为'已知疑难点'")
        if in_no_parking:
            reasons.append("订单车辆停在'禁停区'")
        if completion_time_str:
            # 处理不同的时间格式
            if completion_time_str.endswith('Z'):
                completion_dt = datetime.fromisoformat(completion_time_str.replace('Z', '+00:00'))
            elif '+' in completion_time_str or completion_time_str.endswith('00:00'):
                completion_dt = datetime.fromisoformat(completion_time_str)
            else:
                # naive datetime
                completion_dt = datetime.fromisoformat(completion_time_str)
                
            # 确保比较的是同一类型的datetime
            if completion_dt.tzinfo is None:
                # 如果是naive datetime，假设是UTC时间
                completion_dt = completion_dt.replace(tzinfo=timezone.utc)
                
            time_diff_hours = (FIXED_REFERENCE_TIME - completion_dt).total_seconds() / 3600
            timeliness = "48小时内" if time_diff_hours <= 48 else "超过48小时"
            reasons.append(f"订单完成时间距今{timeliness}")

    elif entity_name == "bike":
        has_malfunction = entity.get('_meta', {}).get('has_bike_malfunction', False)
        if has_malfunction:
            reasons.append("单车状态设为'有故障'")

    return f"设置 {', '.join(reasons)}，旨在测试规则: {', '.join([RULE_EXPLANATIONS[r] for r in relevant_rules])}。"


def _calculate_close_lock_failure_logic(user: Dict, order: Dict, bike: Dict, scenario_info: Dict) -> Dict:
    """处理关锁失败场景的逻辑"""
    checks = []
    reasons = []
    
    appeal_count = user.get('data.bk_close_lock_count_30day', 0)
    is_in_no_parking = order.get('is_in_no_parking_zone', False) if order else False
    has_malfunction = scenario_info.get('has_bike_malfunction', False)
    
    env_rules = ["1.1"]
    
    # 规则 1.2: 风控
    if appeal_count > 4:
        env_rules.append("1.2")
        checks.append({
            "check_type": "response_contains_keywords",
            "params": {"expected_keywords": ["转接人工", "抱歉"]},
            "description": f"校验点源于规则 {RULE_EXPLANATIONS['1.2']}：由于用户申诉次数（{appeal_count}次）> 4次，应触发风控并拒绝服务。"
        })
        env_desc = _get_entity_setup_reason("user", user, ["1.2"])
        return {"check_list": checks, "environment_description": env_desc}

    # 规则 1.3: 禁停区
    if is_in_no_parking:
        if has_malfunction:
            # 规则 1.3A: 禁停区 + 故障 = 可处理
            env_rules.append("1.3A")
            env_rules.append("3.2")
            reasons.append(f"规则 {RULE_EXPLANATIONS['1.3A']}：虽然在禁停区，但因车辆故障，应继续处理。")
            checks.append({
                "check_type": "entity_attribute_equals",
                "params": {"entity_type": "orders", "target_id": order['order_guid'], "attribute_key": "骑行状态", "expected_value": "已结束"},
                "description": f"校验点源于规则 {RULE_EXPLANATIONS['1.3A']}：即使在禁停区，但因车辆有故障，应成功为用户关锁。"
            })
            checks.append({
                "check_type": "prerequisite_check_performed",
                "params": {
                    "prerequisite_tool": "get_bike_info",
                    "business_tool": "create_maintenance_ticket"
                },
                "description": f"校验点源于规则 {RULE_EXPLANATIONS['3.2']}：创建维修工单前，必须先查询单车信息检查last_maintenance_timestamp。"
            })
            checks.append({
                "check_type": "maintenance_ticket_exists",
                "params": {"bike_id": bike['bike_id']},
                "description": f"校验点源于规则 {RULE_EXPLANATIONS['1.3A']}：在处理禁停区关锁的同时，应为故障车辆创建维修工单。"
            })
        else:
            # 规则 1.3B: 禁停区 + 无故障 = 拒绝
            env_rules.append("1.3B")
            checks.append({
                "check_type": "response_contains_keywords",
                "params": {"expected_keywords": ["禁停区", "无法关锁", "移动"]},
                "description": f"校验点源于规则 {RULE_EXPLANATIONS['1.3B']}：由于车辆在禁停区且无故障，应拒绝远程关锁请求。"
            })
            env_desc = _get_entity_setup_reason("order", order, ["1.3B"])
            return {"check_list": checks, "environment_description": env_desc}
    else:
        # 规则 1.1: 标准流程
        reasons.append(f"规则 {RULE_EXPLANATIONS['1.1']}：用户申诉次数（{appeal_count}次）≤ 4次，符合标准处理流程。")
        checks.append({
            "check_type": "entity_attribute_equals",
            "params": {"entity_type": "orders", "target_id": order['order_guid'], "attribute_key": "骑行状态", "expected_value": "已结束"},
            "description": f"校验点源于规则 {RULE_EXPLANATIONS['1.1']}：应成功为用户远程关锁。"
        })

    env_desc = _get_entity_setup_reason("user", user, env_rules)
    if order:
        env_desc += " " + _get_entity_setup_reason("order", order, env_rules)
    if bike and has_malfunction:
        env_desc += " " + _get_entity_setup_reason("bike", bike, env_rules)
        
    return {"check_list": checks, "environment_description": env_desc}

def _calculate_parking_violation_dispute_logic(user: Dict, order: Dict) -> Dict:
    """处理违停费申诉场景的逻辑"""
    checks = []
    env_rules = ["2.1", "2.2"] # Base rules for this scenario

    # 规则 2.1: 申诉时效性
    completion_dt = datetime.fromisoformat(order['completion_timestamp'])
    if completion_dt.tzinfo is None:
        completion_dt = completion_dt.replace(tzinfo=timezone.utc)
    if (FIXED_REFERENCE_TIME - completion_dt).total_seconds() > 48 * 3600:
        checks.append({
            "check_type": "response_contains_keywords",
            "params": {"expected_keywords": ["超过", "48小时", "时效"]},
            "description": f"校验点源于规则 {RULE_EXPLANATIONS['2.1']}：因申诉已超48小时，应被拒绝。"
        })
        env_desc = _get_entity_setup_reason("order", order, ["2.1"])
        return {"check_list": checks, "environment_description": env_desc}

    # 规则 2.2: 复杂布尔逻辑
    is_hotspot = order.get('destination_is_hotspot', False)
    credit_score = user.get('user_credit_score', 0)
    violation_count = user.get('recent_parking_violation_count_90d', 0)
    
    condition_met = is_hotspot or (credit_score > 85 and violation_count == 0)

    if condition_met:
        # 豁免：按标准退还违停罚款5元
        original_fee = order.get('fee', 0)
        fine = 5.0  # 标准违停罚款
        expected_fee = original_fee - fine
        checks.append({
            "check_type": "entity_attribute_equals",
            "params": {"entity_type": "orders", "target_id": order['order_guid'], "attribute_key": "fee", "expected_value": expected_fee},
            "description": f"校验点源于规则 {RULE_EXPLANATIONS['2.2']}：满足豁免条件，应退还{fine}元违停费。"
        })
    else:
        # 拒绝申诉 - 检测标准话术中的关键表达
        checks.append({
            "check_type": "response_contains_keywords",
            "params": {"expected_keywords": ["理解您的感受", "违停处理政策", "无法满足", "豁免条件", "官方渠道"]},
            "description": f"校验点源于规则 {RULE_EXPLANATIONS['2.2']}：不满足豁免条件时，应使用标准话术礼貌地拒绝申诉请求。"
        })
    
    env_desc = _get_entity_setup_reason("user", user, env_rules) + " " + _get_entity_setup_reason("order", order, env_rules)
    return {"check_list": checks, "environment_description": env_desc}

def _calculate_billing_error_dispute_logic(user: Dict, order: Dict) -> Dict:
    """处理计费错误申诉场景的逻辑"""
    checks = []
    env_rules = ["2.1", "2.3", "6.1"]

    # 规则 2.1: 申诉时效性
    completion_dt = datetime.fromisoformat(order['completion_timestamp'])
    if completion_dt.tzinfo is None:
        completion_dt = completion_dt.replace(tzinfo=timezone.utc)
    if (FIXED_REFERENCE_TIME - completion_dt).total_seconds() > 48 * 3600:
        # 规则2.1：超过48小时，直接拒绝
        checks.append({
            "check_type": "response_contains_keywords",
            "params": {"expected_keywords": ["超过", "48小时", "时效"]},
            "description": f"校验点源于规则 {RULE_EXPLANATIONS['2.1']}：因申诉已超48小时，应被拒绝。"
        })
        env_desc = _get_entity_setup_reason("order", order, ["2.1"]) 
        return {"check_list": checks, "environment_description": env_desc}

    # 规则 2.3: 小额计费异议
    discrepancy = order.get('billing_discrepancy_amount', 0)
    credit_score = user.get('user_credit_score', 0)
    complaint_count = user.get('recent_complaint_count_30d', 0)
    
    condition_met = discrepancy > 0 and discrepancy <= 5 and credit_score > 70 and complaint_count < 2
    
    env_desc_parts = {
        "user": f"用户信用分设置为{credit_score}，30天内投诉次数为{complaint_count}次",
        "order": f"订单计费差额设置为{discrepancy}元"
    }
    
    if condition_met:
        original_fee = order.get('fee', 0)
        expected_fee = original_fee - discrepancy
        # 规则2.3：固定发放5元无门槛骑行券（规则明确指定了面额，不适用规则6.1）
        coupon_val = 5.0
        
        checks.append({
            "check_type": "entity_attribute_equals",
            "params": {"entity_type": "orders", "target_id": order['order_guid'], "attribute_key": "fee", "expected_value": expected_fee},
            "description": f"校验点源于规则 {RULE_EXPLANATIONS['2.3']}：满足小额异议快速处理条件，应修正订单费用。"
        })
        if coupon_val > 0:
            checks.append({
                "check_type": "user_coupon_received",
                "params": {"user_id": user['uuid'], "expected_coupon_type": "无门槛骑行券", "expected_coupon_value": coupon_val},
                "description": f"校验点源于规则 {RULE_EXPLANATIONS['2.3']} 和 {RULE_EXPLANATIONS['6.1']}：修正费用后，应发放一张{coupon_val}元补偿券。"
            })
    else:
        # 不满足快速处理条件，应引导用户等待审核
        checks.append({
            "check_type": "response_contains_keywords",
            "params": {"expected_keywords": ["核实", "处理中", "请稍候"]},
            "description": f"校验点源于规则 {RULE_EXPLANATIONS['2.3']}：因不满足快速处理条件，应告知用户问题已记录待核实。"
        })
        
    env_desc = f"设置 {env_desc_parts['user']}、{env_desc_parts['order']}，旨在测试规则: {RULE_EXPLANATIONS['2.3']} (小额计费异议快速处理)。"
    return {"check_list": checks, "environment_description": env_desc}

def _calculate_maintenance_logic(user: Dict, order: Dict, bike: Dict, scenario_info: Dict) -> Dict:
    """处理所有车辆报修场景的统一逻辑"""
    checks = []
    fault_severity = scenario_info.get('fault_severity')
    is_on_trip = order.get('骑行状态') == '进行中' if order else False
    
    env_rules = []
    env_desc_parts = {"user": f"用户等级为'{user.get('user_loyalty_level')}'，信用分{user.get('user_credit_score')}"}
    
    # 规则 3.2: 重复报修检查
    if bike and bike.get('last_maintenance_timestamp'):
        last_maintenance_dt = datetime.fromisoformat(bike['last_maintenance_timestamp'])
        if last_maintenance_dt.tzinfo is None:
            last_maintenance_dt = last_maintenance_dt.replace(tzinfo=timezone.utc)
        if (FIXED_REFERENCE_TIME - last_maintenance_dt).total_seconds() < 24 * 3600:
            env_rules.append("3.2")
            env_desc_parts["bike"] = "单车状态设为'24小时内已有报修记录'"
            
            # 添加工具调用禁止检查
            checks.append({
                "check_type": "tool_call_absence",
                "params": {"forbidden_tools": ["create_maintenance_ticket"]},
                "description": f"校验点源于规则 {RULE_EXPLANATIONS['3.2']}：不应重复调用创建工单的工具。"
            })
            
            # 添加响应关键词检查
            checks.append({
                "check_type": "response_contains_keywords",
                "params": {"expected_keywords": ["已经安排", "处理中", "感谢反馈"]},
                "description": f"校验点源于规则 {RULE_EXPLANATIONS['3.2']}：因24小时内有重复报修，应告知用户情况，无需重复创建工单。"
            })
            
            env_desc = f"设置 {env_desc_parts['bike']}，旨在测试规则: {RULE_EXPLANATIONS['3.2']}。"
            return {"check_list": checks, "environment_description": env_desc}

    # 非重复报修，创建工单
    bike_id = scenario_info.get('bike_id') or (bike.get('bike_id') if bike else None)
    if bike_id:
        # 规则3.2要求：必须先检查24小时内是否有报修记录
        checks.append({
            "check_type": "prerequisite_check_performed",
            "params": {
                "prerequisite_tool": "get_bike_info",
                "business_tool": "create_maintenance_ticket"
            },
            "description": f"校验点源于规则 {RULE_EXPLANATIONS['3.2']}：Agent必须先查询单车信息检查维修时间，再决定是否创建工单。"
        })
        
        checks.append({
            "check_type": "maintenance_ticket_exists",
            "params": {"bike_id": bike_id},
            "description": "校验点源于车辆报修基础规则：应为故障车辆创建维修工单。"
        })

    # 根据故障等级和上下文处理
    if fault_severity == 'severe_safety':
        rule_id = "3.1_severe"
        coupon_type = "特殊关怀券"
        issue_type_for_comp = "severe_safety"
    elif fault_severity == 'general_function':
        rule_id = "3.1_general"
        coupon_type = "无门槛骑行券"
        issue_type_for_comp = "general_function"
    else: # minor_issue
        rule_id = "3.1_minor"
        coupon_type = None  # 轻微问题不发放优惠券，但骑行中依然要免除费用

    env_rules.append(rule_id)
    env_desc_parts["bike"] = f"单车故障严重性设为'{fault_severity}'"
    
    # 骑行中报修：必须先免除费用，再创建工单
    if is_on_trip and order:
        env_desc_parts["order"] = "用户状态设为'骑行中'"
        
        # 规则3.1：骑行中报修必须先免除当前订单费用（包括轻微问题）
        checks.append({
             "check_type": "entity_attribute_equals",
             "params": {"entity_type": "orders", "target_id": order['order_guid'], "attribute_key": "fee", "expected_value": 0},
             "description": f"校验点源于规则 {RULE_EXPLANATIONS[rule_id]}：由于用户在骑行中报修，应将当前订单费用免除。"
        })
        
        # 发放优惠券（除轻微问题外）
        if coupon_type:
            coupon_amount = _get_compensation_amount(user, issue_type_for_comp)
            if coupon_amount > 0:
                checks.append({
                    "check_type": "user_coupon_received",
                    "params": {
                        "user_id": user['uuid'],
                        "expected_coupon_type": coupon_type,
                        "expected_coupon_value": coupon_amount
                    },
                    "description": f"校验点源于规则 {RULE_EXPLANATIONS[rule_id]} 和 {RULE_EXPLANATIONS['6.1']}：骑行中报修{fault_severity}故障，应发放一张{coupon_amount}元'{coupon_type}'。"
                })
    else:
        env_desc_parts["order"] = "用户状态设为'未骑行'" if not is_on_trip else "用户无进行中订单"

    env_desc = f"设置 {', '.join(env_desc_parts.values())}，旨在测试规则: {', '.join([RULE_EXPLANATIONS[r] for r in env_rules])}。"
    return {"check_list": checks, "environment_description": env_desc}

def _get_compensation_amount(user: Dict, issue_type: str) -> float:
    """根据动态补偿矩阵计算金额 (规则 6.1)。
    约定：严重安全故障(severe)严格按文档的动态矩阵返回；一般功能(general)在兼容模式下可返回固定面额。
    """
    level = user.get('user_loyalty_level', 'bronze')
    credit = user.get('user_credit_score', 0)

    # 严重安全故障：始终按动态矩阵
    if 'severe' in issue_type:
        if level in ['diamond', 'platinum']:
            return 20.0 if credit > 85 else (15.0 if credit >= 70 else 12.0)
        else:
            return 15.0 if credit > 85 else (10.0 if credit >= 70 else 8.0)

    # 一般功能故障：按动态矩阵
    if 'general' in issue_type:
        if level in ['diamond', 'platinum']:
            return 10.0 if credit > 85 else (8.0 if credit >= 70 else 5.0)
        else:
            if credit > 85: return 5.0
            if credit >= 70: return 3.0
            return 0.0

    return 0.0


def _find_entity_by_id(entities: List[Dict[str, Any]], id_field: str, id_value: str) -> Optional[Dict[str, Any]]:
    """根据ID在列表中查找实体"""
    if not id_value or not entities:
        return None
    for entity in entities:
        if entity.get(id_field) == id_value:
            return entity
    return None

def _calculate_vip_composite_crisis_logic(user: Dict, order: Dict, bike: Dict, scenario_info: Dict) -> Dict:
    """处理VIP复合危机场景的逻辑 (规则4.1)"""
    checks = []
    env_rules = ["4.1", "1.1", "6.1"]  # 复合危机包含关锁和补偿

    # 首先执行关锁逻辑
    appeal_count = user.get('data.bk_close_lock_count_30day', 0)
    is_in_no_parking = order.get('is_in_no_parking_zone', False) if order else False
    has_malfunction = scenario_info.get('has_bike_malfunction', True)  # 复合危机通常包含故障

    # 记录是否已添加维修工单检查,避免重复
    has_maintenance_check = False

    # 规则1.1或1.3：处理关锁
    if is_in_no_parking and has_malfunction:
        # 禁停区+故障，可以处理
        checks.append({
            "check_type": "entity_attribute_equals",
            "params": {"entity_type": "orders", "target_id": order['order_guid'], "attribute_key": "骑行状态", "expected_value": "已结束"},
            "description": f"校验点源于规则 {RULE_EXPLANATIONS['4.1']}：VIP复合危机中的关锁处理，应成功为用户关锁。"
        })
        checks.append({
            "check_type": "maintenance_ticket_exists",
            "params": {"bike_id": bike['bike_id']},
            "description": f"校验点源于规则 {RULE_EXPLANATIONS['4.1']}：VIP复合危机中的故障处理，应创建维修工单。"
        })
        has_maintenance_check = True
    else:
        # 标准关锁流程
        checks.append({
            "check_type": "entity_attribute_equals",
            "params": {"entity_type": "orders", "target_id": order['order_guid'], "attribute_key": "骑行状态", "expected_value": "已结束"},
            "description": f"校验点源于规则 {RULE_EXPLANATIONS['4.1']}：VIP复合危机中的关锁处理，应成功为用户关锁。"
        })

    # 规则4.1：在复合危机中，应免除本次行程全部费用
    if order:
        checks.append({
            "check_type": "entity_attribute_equals",
            "params": {"entity_type": "orders", "target_id": order['order_guid'], "attribute_key": "fee", "expected_value": 0},
            "description": f"校验点源于规则 {RULE_EXPLANATIONS['4.1']}：复合危机中应免除当前订单的全部费用（fee=0）。"
        })

    # 规则4.1：创建维修工单（先查车后建单）
    bike_id = scenario_info.get('bike_id') or (bike.get('bike_id') if bike else None)
    checks.append({
        "check_type": "prerequisite_check_performed",
        "params": {
            "prerequisite_tool": "get_bike_info",
            "business_tool": "create_maintenance_ticket"
        },
        "description": f"校验点源于规则 {RULE_EXPLANATIONS['3.2']}：复合危机中也应先查询单车信息，再创建维修工单。"
    })
    # 只有在之前没添加过维修工单检查时才添加
    if bike_id and not has_maintenance_check:
        checks.append({
            "check_type": "maintenance_ticket_exists",
            "params": {"bike_id": bike_id},
            "description": f"校验点源于规则 {RULE_EXPLANATIONS['4.1']}：复合危机中应为故障车辆创建维修工单。"
        })

    # 规则4.1 + 6.1：VIP复合危机特殊补偿（发放无门槛骑行券）
    # 规则4.1未明确优惠券面额，应用规则6.1动态补偿矩阵
    level = user.get('user_loyalty_level', 'bronze')
    coupon_val = _get_compensation_amount(user, 'general')
    if coupon_val > 0:
        checks.append({
            "check_type": "user_coupon_received",
            "params": {"user_id": user['uuid'], "expected_coupon_type": "无门槛骑行券", "expected_coupon_value": coupon_val},
            "description": f"校验点源于规则 {RULE_EXPLANATIONS['4.1']} 和 {RULE_EXPLANATIONS['6.1']}：VIP复合危机处理完成后，应发放{coupon_val}元无门槛骑行券作为补偿。"
        })

    env_desc = f"设置 用户等级为'{level}'（信用分{user.get('user_credit_score', 0)}），模拟VIP用户遭遇关锁失败+车辆故障的复合危机，旨在测试规则: {RULE_EXPLANATIONS['4.1']} (VIP复合危机处理)。"
    return {"check_list": checks, "environment_description": env_desc}

def _calculate_proactive_care_logic(user: Dict, scenario_info: Dict) -> Dict:
    """处理主动关怀场景的逻辑 (规则5.1)
    
    注意：由于prototype中明确指定了user_loyalty_level为diamond/platinum，
    所以进入此函数的用户必然是VIP用户，无需再检查用户等级。
    """
    checks = []
    
    level = user.get('user_loyalty_level', 'bronze')
    
    # 规则5.1：主动关怀VIP用户临期优惠券
    # 需要先解决用户的主要问题（如关锁）
    checks.append({
        "check_type": "tool_called_with_params",
        "params": {
            "tool_name": "close_lock_and_bill",
            "expected_params": {
                "order_guid": scenario_info.get("order_guid"),
                "user_uuid": user.get("uuid")
            }
        },
        "description": "校验点：应以正确参数调用远程关锁计费工具，先解决用户的关锁问题。"
    })
    
    # 主动关怀：提醒用户有临期优惠券
    checks.append({
        "check_type": "response_contains_keywords",
        "params": {"expected_keywords": ["优惠券", "即将过期", "提醒"]},
        "description": f"校验点源于规则 {RULE_EXPLANATIONS['5.1']}：解决问题后，应主动提醒用户有优惠券将过期。"
    })
    
    env_desc = f"设置 用户等级为'{level}'，有10元以上优惠券在3天内过期，模拟系统在解决用户问题后主动关怀场景，旨在测试规则: {RULE_EXPLANATIONS['5.1']} (增值服务：主动关怀VIP用户临期优惠券)。"
    return {"check_list": checks, "environment_description": env_desc}

def _calculate_emotion_appeasement_logic(user: Dict, order: Dict, bike: Dict, scenario_info: Dict) -> Dict:
    """处理情绪安抚场景的逻辑 (规则7.1)"""
    checks = []
    env_rules = ["7.1", "6.1"]
    
    level = user.get('user_loyalty_level', 'bronze')
    has_angry_emotion = scenario_info.get('has_angry_emotion', True)  # 默认识别到愤怒情绪
    
    # 规则7.1：情绪安抚逻辑
    if has_angry_emotion:
        # 首先应识别并安抚情绪
        checks.append({
            "check_type": "response_contains_keywords",
            "params": {"expected_keywords": ["理解", "抱歉", "安抚", "耐心"]},
            "description": f"校验点源于规则 {RULE_EXPLANATIONS['7.1']}：应识别用户愤怒情绪并进行情绪安抚。"
        })
        
        # 根据用户等级发放安抚券
        appeasement_coupon_val = _get_appeasement_coupon_amount(user)
        if appeasement_coupon_val > 0:
            checks.append({
                "check_type": "user_coupon_received",
                "params": {"user_id": user['uuid'], "expected_coupon_type": "用户关怀券", "expected_coupon_value": appeasement_coupon_val},
                "description": f"校验点源于规则 {RULE_EXPLANATIONS['7.1']} 和 {RULE_EXPLANATIONS['6.1']}：识别愤怒情绪后应发放{appeasement_coupon_val}元用户关怀券。"
            })
    
    env_desc = f"设置 用户等级为'{level}'，用户表现出愤怒情绪，旨在测试规则: {RULE_EXPLANATIONS['7.1']} (情绪安抚：识别用户负面情绪并发放安抚券)。"
    return {"check_list": checks, "environment_description": env_desc}

def _calculate_close_lock_with_appeasement_logic(user: Dict, order: Dict, bike: Dict, scenario_info: Dict) -> Dict:
    """处理关锁+情绪安抚组合场景的逻辑 (规则1.1+7.1)"""
    checks = []
    env_rules = ["1.1", "7.1", "6.1"]
    
    # 首先执行标准关锁逻辑
    appeal_count = user.get('data.bk_close_lock_count_30day', 0)
    level = user.get('user_loyalty_level', 'bronze')
    
    # 规则1.1：标准关锁流程
    checks.append({
        "check_type": "entity_attribute_equals",
        "params": {"entity_type": "orders", "target_id": order['order_guid'], "attribute_key": "骑行状态", "expected_value": "已结束"},
        "description": f"校验点源于规则 {RULE_EXPLANATIONS['1.1']}：应成功为用户远程关锁。"
    })

    # 规则7.1：情绪安抚
    has_angry_emotion = scenario_info.get('has_angry_emotion', True)
    if has_angry_emotion:
        checks.append({
            "check_type": "response_contains_keywords",
            "params": {"expected_keywords": ["理解", "抱歉", "安抚", "耐心"]},
            "description": f"校验点源于规则 {RULE_EXPLANATIONS['7.1']}：应识别用户愤怒情绪并进行情绪安抚。"
        })
        
        # 额外的情绪安抚券
        appeasement_coupon_val = _get_appeasement_coupon_amount(user)
        if appeasement_coupon_val > 0:
            checks.append({
                "check_type": "user_coupon_received",
                "params": {"user_id": user['uuid'], "expected_coupon_type": "用户关怀券", "expected_coupon_value": appeasement_coupon_val},
                "description": f"校验点源于规则 {RULE_EXPLANATIONS['7.1']} 和 {RULE_EXPLANATIONS['6.1']}：情绪安抚应额外发放{appeasement_coupon_val}元用户关怀券。"
            })
    
    env_desc = f"设置 用户等级为'{level}'(信用分{user.get('user_credit_score', 0)})，用户愤怒地申诉关锁失败，旨在测试规则: {', '.join([RULE_EXPLANATIONS[r] for r in env_rules])}。"
    return {"check_list": checks, "environment_description": env_desc}

def _get_appeasement_coupon_amount(user: Dict) -> float:
    """根据用户等级计算情绪安抚券金额 (规则7.1配套)。严格按 BusinessRules_Plus.md：
    - diamond/platinum: 10
    - gold/silver: 5
    - bronze: 0（不发券）

    """
    level = user.get('user_loyalty_level', 'bronze')
    if level in ['diamond', 'platinum']:
        return 10.0
    if level in ['gold', 'silver']:
        return 5.0
    return 0.0  # bronze 不发券

def _should_trigger_proactive_care(user: Dict) -> bool:
    """检查是否应触发规则5.1（主动关怀）

    规则5.1：在为diamond或platinum用户成功解决任何问题后，
    必须检查其账户，若发现有面额不小于10元的优惠券将在未来3天内过期，应主动提醒用户。

    Args:
        user: 用户信息字典

    Returns:
        bool: True表示应该提醒用户关于即将过期的大额优惠券
    """
    # 检查1：用户必须是VIP（diamond或platinum）
    level = user.get('user_loyalty_level', 'bronze')
    if level not in ['diamond', 'platinum']:
        return False

    # 检查2：用户必须有优惠券
    coupons = user.get('coupons', [])
    if not coupons:
        return False

    # 检查3：是否有≥10元且在3天内过期的优惠券
    three_days_later = FIXED_REFERENCE_TIME.timestamp() + 3 * 24 * 3600

    for coupon in coupons:
        coupon_value = coupon.get('value', 0)
        expiry_date_str = coupon.get('expiry_date', '')

        if coupon_value < 10:
            continue

        if not expiry_date_str:
            continue

        try:
            expiry_dt = datetime.fromisoformat(expiry_date_str.replace('Z', '+00:00'))
            if expiry_dt.tzinfo is None:
                expiry_dt = expiry_dt.replace(tzinfo=timezone.utc)

            expiry_timestamp = expiry_dt.timestamp()

            # 优惠券在3天内过期（但还没过期）
            if FIXED_REFERENCE_TIME.timestamp() < expiry_timestamp <= three_days_later:
                return True
        except (ValueError, AttributeError):
            continue

    return False

def _calculate_in_trip_severe_fault_with_double_appeasement_logic(user: Dict, order: Dict, bike: Dict, scenario_info: Dict) -> Dict:
    """处理骑行中严重故障+情绪安抚组合场景的逻辑 (规则3.1+6.1+7.1)"""
    checks = []
    env_rules = ["3.1_severe", "6.1", "7.1"]
    
    user_level = user.get('user_loyalty_level', 'bronze')
    user_credit = user.get('user_credit_score', 0)
    bike_id = scenario_info.get('bike_id') or (bike.get('bike_id') if bike else None)
    
    # ===== 第一部分：严重故障维修逻辑 (规则3.1+6.1) =====
    
    # 规则3.2要求：必须先检查24小时内是否有报修记录
    if bike_id:
        checks.append({
            "check_type": "prerequisite_check_performed",
            "params": {
                "prerequisite_tool": "get_bike_info",
                "business_tool": "create_maintenance_ticket"
            },
            "description": f"校验点源于规则 {RULE_EXPLANATIONS['3.2']}：Agent必须先查询单车信息检查维修时间，再决定是否创建工单。"
        })
        
        checks.append({
            "check_type": "maintenance_ticket_exists",
            "params": {"bike_id": bike_id},
            "description": "校验点源于车辆报修基础规则：应为故障车辆创建维修工单。"
        })

    # 规则3.1：骑行中报修必须先免除当前订单费用
    if order:
        checks.append({
            "check_type": "entity_attribute_equals",
            "params": {"entity_type": "orders", "target_id": order['order_guid'], "attribute_key": "fee", "expected_value": 0},
            "description": f"校验点源于规则 {RULE_EXPLANATIONS['3.1_severe']}：由于用户在骑行中报修严重安全故障，应将当前订单费用免除。"
        })
        
        # 规则6.1：发放特殊关怀券（严重安全故障补偿）
        coupon_amount = _get_compensation_amount(user, "severe_safety")
        if coupon_amount > 0:
            checks.append({
                "check_type": "user_coupon_received",
                "params": {
                    "user_id": user['uuid'],
                    "expected_coupon_type": "特殊关怀券",
                    "expected_coupon_value": coupon_amount
                },
                "description": f"校验点源于规则 {RULE_EXPLANATIONS['3.1_severe']} 和 {RULE_EXPLANATIONS['6.1']}：骑行中报修严重安全故障，应发放一张{coupon_amount}元'特殊关怀券'。"
            })
    
    # ===== 第二部分：情绪安抚逻辑 (规则7.1) =====
    
    # 识别并安抚用户愤怒情绪
    checks.append({
        "check_type": "response_contains_keywords",
        "params": {"expected_keywords": ["理解", "抱歉", "安抚", "耐心"]},
        "description": f"校验点源于规则 {RULE_EXPLANATIONS['7.1']}：应识别用户愤怒情绪并进行情绪安抚。"
    })
    
    # 规则7.1：发放用户关怀券（情绪安抚）
    appeasement_coupon_val = _get_appeasement_coupon_amount(user)
    if appeasement_coupon_val > 0:
        checks.append({
            "check_type": "user_coupon_received",
            "params": {"user_id": user['uuid'], "expected_coupon_type": "用户关怀券", "expected_coupon_value": appeasement_coupon_val},
            "description": f"校验点源于规则 {RULE_EXPLANATIONS['7.1']} 和 {RULE_EXPLANATIONS['6.1']}：识别愤怒情绪后应发放{appeasement_coupon_val}元用户关怀券。"
        })
    
    env_desc = f"设置 用户等级为'{user_level}'(信用分{user_credit})，用户在骑行中愤怒地报修严重安全故障，旨在测试规则: {', '.join([RULE_EXPLANATIONS[r] for r in env_rules])}。"
    return {"check_list": checks, "environment_description": env_desc} 
