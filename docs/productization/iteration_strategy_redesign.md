# 迭代策略重新设计：基于质量收敛的动态停止

## 🎯 设计目标

**核心原则**：让系统**智能地**决定何时停止，而不是简单粗暴地设定"最多N次"。

---

## ❌ 原设计的问题

### 问题1：迭代预算设置过低
```python
# 原设计
Layer 1: 1次修改
Layer 2: 2次自动修复
Layer 3: 3次自动修复
全局: 5次迭代
```

**问题**：
- 任务复杂度高，5次迭代远远不够
- 一个复杂场景可能需要10-20次迭代才能达到85%成功率
- Layer 3样本修复成本很低，限制3次没有道理

### 问题2：固定阈值缺乏灵活性
```python
if iteration >= 5:
    return "达到最大迭代次数，停止"
```

**问题**：
- 如果第6次迭代能达标呢？白白浪费前5次的努力
- 不同场景复杂度差异巨大，统一限制不合理
- 没有考虑"质量改善速度"这个关键指标

---

## ✅ 新设计：多维度动态停止策略

### 策略1: 质量收敛检测（核心）

**核心思想**：如果连续N次迭代质量不再提升，说明已经到达瓶颈，应该停止。

```python
class QualityConvergenceDetector:
    def __init__(self):
        self.quality_history = []  # 记录每次迭代的成功率
        self.convergence_window = 5  # 观察窗口
        self.min_improvement = 0.02  # 最小改善幅度（2%）

    def should_stop(self, current_success_rate):
        """基于质量收敛判断是否停止"""
        self.quality_history.append(current_success_rate)

        # 1. 如果已经达标，立即停止
        if current_success_rate >= 0.85:
            return True, "质量达标（≥85%）"

        # 2. 如果迭代次数太少，继续
        if len(self.quality_history) < self.convergence_window:
            return False, "继续迭代（样本量不足）"

        # 3. 检查最近N次迭代的质量改善
        recent_history = self.quality_history[-self.convergence_window:]
        max_improvement = max(recent_history) - min(recent_history)

        if max_improvement < self.min_improvement:
            return True, f"质量收敛（{self.convergence_window}次内改善<{self.min_improvement*100}%）"

        # 4. 检查是否陷入震荡（质量上下波动）
        if self._is_oscillating(recent_history):
            return True, "陷入震荡，需要人工介入"

        return False, "质量仍在改善，继续迭代"

    def _is_oscillating(self, history):
        """检测质量是否在震荡（上下反复）"""
        if len(history) < 4:
            return False

        # 简单的震荡检测：连续3次方向改变
        changes = [history[i+1] - history[i] for i in range(len(history)-1)]
        direction_changes = sum(1 for i in range(len(changes)-1)
                               if changes[i] * changes[i+1] < 0)
        return direction_changes >= 3
```

**优势**：
- ✅ 不设硬性上限，让质量自然收敛
- ✅ 自动识别"继续迭代无意义"的时机
- ✅ 避免震荡（反复在几个问题间横跳）

---

### 策略2: 分层预算软限制

**核心思想**：不是"禁止超过N次"，而是"超过N次需要额外审查"。

```python
class LayerBudgetManager:
    def __init__(self):
        # 软限制：超过后触发额外检查
        self.soft_limits = {
            "layer1": 3,   # Layer 1修改3次后需要重新评估场景设计
            "layer2": 10,  # Layer 2修复10次后可能是工具设计有问题
            "layer3": 20,  # Layer 3修复20次后可能是coverage matrix有问题
        }

        # 硬限制：绝对不能超过（防止真正的失控）
        self.hard_limits = {
            "layer1": 5,
            "layer2": 30,
            "layer3": 50,
        }

        self.layer_counters = {"layer1": 0, "layer2": 0, "layer3": 0}

    def can_retry(self, layer, root_cause):
        """判断是否允许重试，并给出建议"""
        current_count = self.layer_counters[layer]
        soft_limit = self.soft_limits[layer]
        hard_limit = self.hard_limits[layer]

        # 硬限制：绝对禁止
        if current_count >= hard_limit:
            return False, f"{layer}已达硬限制({hard_limit}次)，必须停止"

        # 软限制：需要额外审查
        if current_count >= soft_limit:
            # 分析是否值得继续
            if self._is_worthwhile(layer, root_cause):
                return True, f"{layer}超过软限制({soft_limit}次)，但问题可修复，继续"
            else:
                return False, f"{layer}超过软限制且问题类型不适合自动修复，建议人工介入"

        # 未达软限制：允许
        return True, f"{layer}在预算内({current_count}/{soft_limit})，继续"

    def _is_worthwhile(self, layer, root_cause):
        """判断超过软限制后是否值得继续修复"""
        # Layer 3的简单问题值得继续
        if layer == "layer3" and root_cause["complexity"] == "simple":
            return True

        # Layer 2如果是同一个工具反复出错，不值得继续
        if layer == "layer2" and root_cause.get("repeated_tool_error"):
            return False

        # Layer 1如果是根本性的场景设计问题，不值得继续
        if layer == "layer1" and root_cause["category"] == "fundamental_design_flaw":
            return False

        return True
```

**关键区别**：
- ❌ 旧设计：Layer 3修复3次就禁止
- ✅ 新设计：Layer 3修复20次才触发审查，50次才强制停止

---

### 策略3: 成本效益分析

**核心思想**：如果继续迭代的"预期收益"低于"成本"，应该停止。

```python
class CostBenefitAnalyzer:
    def __init__(self):
        # 各层修复的平均成本（token消耗）
        self.fix_costs = {
            "layer1": 50000,   # Layer 1修改成本高
            "layer2": 10000,   # Layer 2代码生成成本中等
            "layer3": 2000,    # Layer 3样本调整成本低
        }

        # 历史修复效果（每次修复平均提升多少成功率）
        self.fix_effectiveness = {
            "layer1": 0.15,  # Layer 1修改平均提升15%
            "layer2": 0.08,  # Layer 2修复平均提升8%
            "layer3": 0.05,  # Layer 3修复平均提升5%
        }

    def should_continue(self, layer, current_success_rate, cost_budget_remaining):
        """基于成本效益判断是否继续"""
        fix_cost = self.fix_costs[layer]
        expected_improvement = self.fix_effectiveness[layer]

        # 预期效果：如果修复后能达标
        if current_success_rate + expected_improvement >= 0.85:
            # 即使成本高也值得尝试
            if cost_budget_remaining >= fix_cost:
                return True, f"预期修复后达标（{current_success_rate:.1%} → {current_success_rate+expected_improvement:.1%}）"

        # 成本效益比：每1%改善需要多少成本
        cost_per_percent = fix_cost / (expected_improvement * 100)

        # 如果成本效益比太差（比如Layer 2修复1%需要1000+ tokens）
        if cost_per_percent > 1500 and current_success_rate < 0.70:
            return False, f"成本效益比过低（{cost_per_percent:.0f} tokens/1%改善），建议重新设计"

        return True, "成本效益合理，继续"
```

---

### 策略4: 问题类型分类停止

**核心思想**：某些问题类型根本不适合自动修复，应该及早停止。

```python
class ProblemTypeAnalyzer:
    def __init__(self):
        # 定义问题严重程度
        self.problem_severity = {
            # Layer 1问题
            "fundamental_design_flaw": "critical",        # 根本性设计缺陷
            "business_logic_unclear": "critical",         # 业务逻辑不清晰
            "capability_mismatch": "high",                # 能力维度选择错误

            # Layer 2问题
            "tool_design_error": "high",                  # 工具设计错误
            "checker_logic_flaw": "medium",               # Checker逻辑缺陷
            "threshold_issue": "low",                     # 阈值设置问题

            # Layer 3问题
            "simulator_prompt_strict": "low",             # 用户模拟器太严格
            "data_pool_insufficient": "low",              # 数据池不够
            "coverage_missing": "medium",                 # coverage遗漏
        }

    def should_stop_early(self, problem_distribution):
        """基于问题类型分布判断是否提前停止"""
        critical_count = sum(1 for p in problem_distribution
                           if self.problem_severity.get(p["type"]) == "critical")

        total_count = len(problem_distribution)

        # 如果超过30%是critical问题，说明场景设计有根本性问题
        if critical_count / total_count > 0.3:
            return True, f"Critical问题占比过高({critical_count}/{total_count})，建议重新设计场景"

        # 如果同一个critical问题反复出现3次以上
        critical_problems = [p for p in problem_distribution
                           if self.problem_severity.get(p["type"]) == "critical"]
        problem_counts = {}
        for p in critical_problems:
            key = (p["type"], p.get("affected_component"))
            problem_counts[key] = problem_counts.get(key, 0) + 1

        if any(count >= 3 for count in problem_counts.values()):
            return True, "同一critical问题反复出现≥3次，自动修复无效"

        return False, "问题类型分布合理，继续迭代"
```

---

## 🎯 综合决策引擎

将以上4个策略整合：

```python
class IterationDecisionEngine:
    def __init__(self):
        self.quality_detector = QualityConvergenceDetector()
        self.budget_manager = LayerBudgetManager()
        self.cost_analyzer = CostBenefitAnalyzer()
        self.problem_analyzer = ProblemTypeAnalyzer()

        self.global_iteration_count = 0
        self.global_hard_limit = 100  # 全局硬限制（防止真正失控）

    def decide_next_action(self, evaluation_result, fix_plan, cost_budget):
        """综合决策：是否继续迭代，以及如何修复"""
        self.global_iteration_count += 1

        # 0. 全局硬限制检查
        if self.global_iteration_count >= self.global_hard_limit:
            return {
                "action": "stop",
                "reason": f"达到全局硬限制({self.global_hard_limit}次)，强制停止",
                "suggestion": "检查系统是否存在根本性问题"
            }

        # 1. 质量收敛检测（最优先）
        should_stop, reason = self.quality_detector.should_stop(
            evaluation_result["success_rate"]
        )
        if should_stop:
            return {
                "action": "stop",
                "reason": reason,
                "final_success_rate": evaluation_result["success_rate"]
            }

        # 2. 问题类型分析（及早识别根本性问题）
        should_stop_early, reason = self.problem_analyzer.should_stop_early(
            evaluation_result["root_causes"]
        )
        if should_stop_early:
            return {
                "action": "stop",
                "reason": reason,
                "suggestion": "需要人工重新评估场景设计"
            }

        # 3. 分层预算检查
        for layer, fixes in fix_plan.items():
            if not fixes:
                continue

            can_retry, reason = self.budget_manager.can_retry(
                layer, fixes[0]  # 检查第一个修复任务
            )
            if not can_retry:
                return {
                    "action": "stop",
                    "reason": reason,
                    "suggestion": f"考虑调整{layer}的设计策略"
                }

        # 4. 成本效益分析
        for layer, fixes in fix_plan.items():
            if not fixes:
                continue

            should_continue, reason = self.cost_analyzer.should_continue(
                layer,
                evaluation_result["success_rate"],
                cost_budget
            )
            if not should_continue:
                return {
                    "action": "stop",
                    "reason": reason,
                    "suggestion": "成本效益比过低，建议人工介入"
                }

        # 5. 所有检查通过，继续迭代
        return {
            "action": "continue",
            "reason": f"质量仍在改善（当前{evaluation_result['success_rate']:.1%}）",
            "fix_plan": fix_plan
        }
```

---

## 📊 新旧对比

| 维度 | 旧设计（固定次数） | 新设计（动态收敛） |
|------|------------------|------------------|
| **Layer 1** | 硬限制1次 | 软限制3次，硬限制5次 |
| **Layer 2** | 硬限制2次 | 软限制10次，硬限制30次 |
| **Layer 3** | 硬限制3次 | 软限制20次，硬限制50次 |
| **全局** | 硬限制5次 | 质量收敛自动停止，硬限制100次 |
| **停止依据** | 次数达到 | 质量收敛、成本效益、问题类型 |
| **灵活性** | ❌ 低（一刀切） | ✅ 高（智能判断） |
| **适应性** | ❌ 不区分场景复杂度 | ✅ 根据实际情况调整 |

---

## 🎯 实际运行示例

### 场景1：简单场景，快速收敛
```
Iteration 1: 70% → Layer 3修复
Iteration 2: 78% → Layer 3修复
Iteration 3: 83% → Layer 2修复
Iteration 4: 87% ✅ 质量达标，停止

总迭代：4次（远低于新设计的限制）
```

### 场景2：复杂场景，需要多次迭代
```
Iteration 1: 55% → Layer 3修复
Iteration 2: 60% → Layer 3修复
Iteration 3: 63% → Layer 2修复
...
Iteration 15: 78% → Layer 3修复
Iteration 16: 81% → Layer 2修复
Iteration 17: 83% → Layer 3修复
Iteration 18: 86% ✅ 质量达标，停止

总迭代：18次
旧设计会在第5次强制停止（只有63%，浪费前面的努力）
新设计允许继续，直到质量达标
```

### 场景3：根本性问题，及早停止
```
Iteration 1: 50% → 30% critical问题（business_logic_unclear）
Iteration 2: 52% → Layer 1修改
Iteration 3: 54% → 仍有28% critical问题
Iteration 4: 56% → 同一critical问题第3次出现

🛑 提前停止："同一critical问题反复出现≥3次，自动修复无效"
建议：需要人工重新评估场景设计

旧设计可能会继续到第5次才停止
新设计及早识别根本性问题，避免无效迭代
```

---

## 💡 关键改进点

1. **去掉过低的硬限制** - Layer 3从3次提升到50次硬限制
2. **引入软限制** - 超过后触发审查，而不是直接禁止
3. **质量收敛检测** - 智能判断何时"继续无意义"
4. **成本效益分析** - 基于实际收益决定是否继续
5. **问题类型识别** - 及早发现根本性问题，避免浪费
6. **震荡检测** - 防止在几个问题间反复横跳

---

## 🚀 实施建议

1. **Phase 1 MVP**：先实现质量收敛检测和分层软/硬限制
2. **Phase 2**：增加成本效益分析
3. **Phase 3**：完善问题类型识别和震荡检测

---

**结论**：用"智能收敛"代替"简单计数"，让系统更灵活、更适应不同复杂度的场景。
