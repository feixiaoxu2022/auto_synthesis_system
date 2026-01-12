---
name: execute-to-init-context
description: Execute Agent向Init Agent反馈Layer 1设计问题时的Context协议（简化版）
---

# Execute → Init Context 协议（简化版）

## 何时使用

当Execute Agent在执行过程中发现**设计层面的问题**需要修改时使用，包括：

| 问题类型 | 示例 |
|---------|------|
| **业务规则不明确** | BusinessRules中未明确说明余额扣减时机 |
| **Tools定义不合理** | 某个工具缺少必要的返回字段 |
| **Checkers设计错误** | 验证条件与业务规则冲突 |
| **Coverage Matrix缺失** | 未覆盖关键能力测试点 |

**不应使用的场景**（这些是执行问题，不是设计问题）：
- ❌ 代码实现bug（Execute Agent自己修）
- ❌ 样本质量问题（Execute Agent自己调整）
- ❌ 环境配置问题（Execute Agent自己解决）

---

## 反馈流程

```
Execute Agent识别问题
    ↓
调用 _request_layer1_fix(trigger_reason, suggestions)
    ↓
返回 AgentResult(status="need_layer1_fix", context_for_handoff={...})
    ↓
Orchestrator检测到status
    ↓
切换回INIT状态，构建feedback context
    ↓
Init Agent接收feedback，修改设计
```

---

## Context 数据结构（简化版）

**Execute Agent返回的 context_for_handoff**：

```python
{
    "trigger_reason": str,              # 触发原因简述（1句话）
    "problem_details": str,             # 问题详细描述
    "modification_suggestions": List[str],  # 具体修改建议列表
    "execution_output_dir": str,        # 执行输出目录（可选，供Init查看详细数据）
}
```

**Init Agent接收的 feedback_from_execute**：

Orchestrator会自动构建并传递：
```python
{
    "handoff_type": "execute_to_init",
    "trigger_reason": "...",
    "problem_details": "...",
    "modification_suggestions": ["建议1", "建议2", ...],
    "execution_output_dir": "...",
    "timestamp": "..."
}
```

---

## 使用示例

### Execute Agent中请求反馈

```python
def _request_layer1_fix(self, trigger_reason: str, suggestions: List[str]) -> None:
    """请求Layer 1修改"""
    self._need_layer1_fix = True
    self._layer1_context = {
        "trigger_reason": trigger_reason,
        "problem_details": "详细问题描述...",
        "modification_suggestions": suggestions,
        "execution_output_dir": str(self.execution_output_dir)
    }
```

### Init Agent中处理反馈

```python
if context.get("feedback_from_execute"):
    feedback = context["feedback_from_execute"]

    # 1. 了解问题
    trigger_reason = feedback["trigger_reason"]
    problem_details = feedback["problem_details"]
    suggestions = feedback["modification_suggestions"]

    # 2. 修改设计文件
    # 例如：更新 BusinessRules.md 明确业务规则

    # 3. 通知用户并请求确认
```

---

## 关键原则

1. **修改建议要具体**：不要说"请优化"，要说"在BusinessRules第3节增加余额扣减规则说明"
2. **聚焦设计问题**：只反馈需要修改YAML/BusinessRules/format_spec的问题
3. **一次性传递**：所有信息通过context传递，不需要额外的文件

---

## 完整示例

```python
context_for_handoff = {
    "trigger_reason": "BusinessRules中请假余额扣减时机不明确",
    "problem_details": "当前BusinessRules没有明确说明余额扣减发生在申请创建时还是审批通过后，导致Agent行为不一致",
    "modification_suggestions": [
        "在BusinessRules.md的'业务规则'章节明确：余额扣减必须在申请创建时立即生效",
        "在unified_scenario_design.yaml的create_leave_application工具中添加注释说明扣减时机",
        "确保所有checker验证余额时都基于创建时扣减的假设"
    ],
    "execution_output_dir": "outputs/leave_application_scenario/execution_20260108"
}
```
