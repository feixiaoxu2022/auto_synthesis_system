"""
Orchestrator - Harness/Coordinator for dual-agent sample synthesis system.

核心职责:
1. Phase管理 - 维护Agent执行阶段（Init/Execute）
2. Agent协调 - 控制Init/Execute切换
3. Checkpoint管理 - 支持Resume

不负责:
- 业务决策（由Agent自己决定）
- 代码生成
- 评测执行
"""
import json
from enum import Enum
from typing import Dict, Any, Optional, Protocol
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


class AgentPhase(Enum):
    """Agent执行阶段"""
    INIT = "init"              # Init Agent工作中
    EXECUTE = "execute"        # Execute Agent工作中


@dataclass
class AgentResult:
    """Agent执行结果"""
    status: str  # "completed" | "need_approval" | "need_layer1_fix" | "failed"
    artifacts: Dict[str, str] = field(default_factory=dict)  # 生成的文件路径
    message: str = ""
    context_for_handoff: Optional[Dict[str, Any]] = None  # 传递给下一个Agent的context


class AgentProtocol(Protocol):
    """Agent接口协议"""
    def run(self, context: Dict[str, Any]) -> AgentResult:
        """执行Agent任务"""
        ...


class Orchestrator:
    """
    Orchestrator - Harness模式协调器

    不做业务决策，只做:
    - 状态管理
    - Agent协调
    - HITL交互
    - 门控检查
    - Checkpoint 管理（支持 Resume）
    """

    def __init__(self,
                 init_agent: Optional[AgentProtocol] = None,
                 execute_agent: Optional[AgentProtocol] = None,
                 output_dir: str = "outputs",
                 checkpoint_dir: str = "checkpoints",
                 auto_checkpoint: bool = True):
        self.init_agent = init_agent
        self.execute_agent = execute_agent
        self.output_dir = Path(output_dir)

        # 状态
        self.state = AgentPhase.INIT
        self.user_requirement = ""
        self.scenario_name = ""

        # 产物路径
        self.design_artifacts: Dict[str, str] = {}
        self.execution_artifacts: Dict[str, str] = {}

        # Step计数
        self.init_iterations = 0
        self.execute_iterations = 0

        # Context（Agent间传递）
        self.current_context: Dict[str, Any] = {}

        # Checkpoint 管理
        from .checkpoint import CheckpointManager
        self.checkpoint_manager = CheckpointManager(checkpoint_dir)
        self.auto_checkpoint = auto_checkpoint

        # 注入checkpoint保存回调到Agent
        if self.init_agent and hasattr(self.init_agent, 'on_tool_call_complete'):
            self.init_agent.on_tool_call_complete = lambda: self._save_checkpoint()
        if self.execute_agent and hasattr(self.execute_agent, 'on_tool_call_complete'):
            self.execute_agent.on_tool_call_complete = lambda: self._save_checkpoint()

    def _save_checkpoint(self, force_new: bool = False):
        """保存 checkpoint"""
        if self.auto_checkpoint:
            self.checkpoint_manager.save(self, force_new=force_new)

    @classmethod
    def resume(cls,
               init_agent: Optional[AgentProtocol] = None,
               execute_agent: Optional[AgentProtocol] = None,
               checkpoint_id: Optional[str] = None,
               checkpoint_dir: str = "checkpoints",
               output_dir: str = "outputs") -> Optional["Orchestrator"]:
        """
        从 checkpoint 恢复

        Args:
            init_agent: Init Agent 实例
            execute_agent: Execute Agent 实例
            checkpoint_id: 指定 checkpoint ID，None 则使用 latest
            checkpoint_dir: checkpoint 目录
            output_dir: 输出目录

        Returns:
            恢复的 Orchestrator 实例，或 None（如果没有 checkpoint）
        """
        from .checkpoint import CheckpointManager

        manager = CheckpointManager(checkpoint_dir)
        checkpoint = manager.load(checkpoint_id)

        if checkpoint is None:
            print("[Resume] 没有找到可用的 checkpoint")
            return None

        # 创建实例
        orchestrator = cls(
            init_agent=init_agent,
            execute_agent=execute_agent,
            output_dir=output_dir,
            checkpoint_dir=checkpoint_dir,
        )

        # 恢复状态
        manager.restore(orchestrator, checkpoint)
        orchestrator.checkpoint_manager = manager

        print(f"[Resume] 从 checkpoint {checkpoint.checkpoint_id} 恢复")
        print(f"  状态: {orchestrator.state.value}")
        print(f"  需求: {orchestrator.user_requirement[:50]}...")
        print(f"  Steps: init={orchestrator.init_iterations}, execute={orchestrator.execute_iterations}")

        return orchestrator

    def run(self, user_requirement: str) -> Dict[str, Any]:
        """
        主执行循环 - 自动处理phase转换

        支持双向转换：
        - INIT → EXECUTE（设计完成）
        - EXECUTE → INIT（发现Layer 1问题）
        """
        self.user_requirement = user_requirement

        # 循环处理phase转换，直到没有新的phase切换
        max_auto_transitions = 5  # 最多5次转换（INIT→EXECUTE→INIT→EXECUTE...）
        transitions = 0

        while transitions < max_auto_transitions:
            prev_state = self.state
            print(f"\n[状态] {self.state.value}")

            if self.state == AgentPhase.INIT:
                self._handle_init_phase()
            elif self.state == AgentPhase.EXECUTE:
                self._handle_execute_phase()

            # 检查state是否变化
            if self.state != prev_state:
                transitions += 1
                print(f"[Orchestrator] Phase自动切换: {prev_state.value} → {self.state.value}")
            else:
                # state没变化，说明当前phase完成但没有触发转换
                break

        # 执行完后保存checkpoint
        self._save_checkpoint(force_new=True)
        return self._build_final_result()

    def continue_with_input(self, new_input: str) -> Dict[str, Any]:
        """
        用户继续输入，传给Agent处理

        Args:
            new_input: 用户的新输入

        Returns:
            执行结果
        """
        print(f"\n[continue_with_input] 用户输入: {new_input[:50]}...")
        print(f"[continue_with_input] 当前state: {self.state.value}")
        print(f"[continue_with_input] Checkpoint ID: {self.checkpoint_manager._current_checkpoint_id}")

        # 特殊命令：手动compact
        if new_input.strip().lower() == "/compact":
            print("[continue_with_input] 触发手动compact")
            current_agent = self.init_agent if self.state == AgentPhase.INIT else self.execute_agent
            if current_agent:
                success = current_agent.manual_compact()
                if success:
                    self._save_checkpoint()  # 保存压缩后的状态
            return self._build_final_result()

        # 简化：根据当前state调用对应Agent（不再判断对话历史）
        if self.state == AgentPhase.INIT:
            print("[continue_with_input] 继续Init Agent")
            self.init_iterations += 1
            context = {
                "user_requirement": new_input,
                "iteration": self.init_iterations,
                "output_dir": str(self.output_dir),
            }
            # Resume时使用已保存的对话历史
            result = self.init_agent.run(context, continue_from_checkpoint=True)

            # 如果Init Agent生成了设计产物，切换到Execute
            if result.artifacts and result.artifacts.get("scenario_name"):
                self.design_artifacts = result.artifacts
                self.scenario_name = result.artifacts.get("scenario_name", "unknown")
                self.state = AgentPhase.EXECUTE

        elif self.state == AgentPhase.EXECUTE:
            print("[continue_with_input] 继续Execute Agent")
            self.execute_iterations += 1
            context = {
                "user_requirement": new_input,
                "design_artifacts": self.design_artifacts,
                "iteration": self.execute_iterations,
            }
            # Resume时使用已保存的对话历史
            result = self.execute_agent.run(context, continue_from_checkpoint=True)

            # 检查是否需要反馈给Init（Layer 1问题）
            if result.status == "need_layer1_fix":
                print(f"[Execute Phase] 识别出Layer 1问题，切换回Init进行设计修改")
                print(f"  触发原因: {result.context_for_handoff.get('trigger_reason', '未提供')}")
                self.state = AgentPhase.INIT
                self.current_context = self._build_execute_to_init_context(result)

        self._save_checkpoint()  # 不force_new，继续使用当前checkpoint_id
        return self._build_final_result()

    def _handle_init_phase(self):
        """处理Init Phase - 运行Init Agent"""
        self.init_iterations += 1

        if self.init_agent is None:
            print("[错误] Init Agent未设置")
            return

        # 构建context
        context = {
            "user_requirement": self.user_requirement,
            "iteration": self.init_iterations,
            "output_dir": str(self.output_dir),
        }

        # 运行Init Agent（Agent自己根据_conversation_history判断是否resume）
        result = self.init_agent.run(context)

        # 检查是否有设计产出
        if result.artifacts and result.artifacts.get("scenario_name"):
            self.design_artifacts = result.artifacts
            self.scenario_name = result.artifacts.get("scenario_name", "unknown")
            self.current_context = self._build_init_to_execute_context(result)
            self.state = AgentPhase.EXECUTE
            print(f"[Init Phase] 设计完成: {self.scenario_name}")

    def _handle_execute_phase(self):
        """处理Execute Phase - 运行Execute Agent"""
        self.execute_iterations += 1

        if self.execute_agent is None:
            print("[错误] Execute Agent未设置")
            return

        # 构建context
        context = self.current_context.copy()
        context["iteration"] = self.execute_iterations

        # 运行Execute Agent（Agent自己根据_conversation_history判断是否resume）
        result = self.execute_agent.run(context)

        # 保存执行产物
        if result.artifacts:
            self.execution_artifacts = result.artifacts

        # 检查是否需要反馈给Init（Layer 1问题）
        if result.status == "need_layer1_fix":
            print(f"[Execute Phase] 识别出Layer 1问题，切换回Init进行设计修改")
            print(f"  触发原因: {result.context_for_handoff.get('trigger_reason', '未提供')}")
            self.state = AgentPhase.INIT
            self.current_context = self._build_execute_to_init_context(result)

    def _build_init_to_execute_context(self, result: AgentResult) -> Dict[str, Any]:
        """构建Init -> Execute的Context"""
        return {
            "handoff_type": "init_to_execute",
            "user_requirement": self.user_requirement,
            "design_artifacts": self.design_artifacts,
            "timestamp": datetime.now().isoformat(),
        }

    def _build_execute_to_init_context(self, result: AgentResult) -> Dict[str, Any]:
        """构建Execute -> Init的反馈Context"""
        handoff = result.context_for_handoff or {}
        return {
            "handoff_type": "execute_to_init",
            "user_requirement": self.user_requirement,
            "output_dir": str(self.output_dir),
            "feedback_from_execute": {
                "trigger_reason": handoff.get("trigger_reason", "未提供原因"),
                "problem_details": handoff.get("problem_details", ""),
                "modification_suggestions": handoff.get("modification_suggestions", []),
                "execution_output_dir": handoff.get("execution_output_dir", ""),
                "timestamp": datetime.now().isoformat(),
            }
        }

    def _build_final_result(self) -> Dict[str, Any]:
        """构建最终结果"""
        return {
            "status": self.state.value,
            "scenario_name": self.scenario_name,
            "design_artifacts": self.design_artifacts,
            "execution_artifacts": self.execution_artifacts,
            "iterations": {
                "init": self.init_iterations,
                "execute": self.execute_iterations,
            }
        }


# ============================================================
# 测试用Mock Agent
# ============================================================

class MockInitAgent:
    """Mock Init Agent - 用于测试Orchestrator"""

    def __init__(self, should_succeed: bool = True):
        self.should_succeed = should_succeed
        self.call_count = 0
        self.last_context = None

    def run(self, context: Dict[str, Any], continue_from_checkpoint: bool = False) -> AgentResult:
        self.call_count += 1
        self.last_context = context
        print(f"[MockInitAgent] 被调用，第 {self.call_count} 次")
        print(f"  context keys: {list(context.keys())}")

        if self.should_succeed:
            return AgentResult(
                status="completed",
                artifacts={
                    "scenario_name": "test_scenario",
                    "unified_scenario_design_path": "outputs/test_scenario/unified_scenario_design.yaml",
                    "business_rules_path": "outputs/test_scenario/BusinessRules.md",
                },
                message="设计完成"
            )
        else:
            return AgentResult(
                status="failed",
                message="模拟失败"
            )


class MockExecuteAgent:
    """Mock Execute Agent - 用于测试Orchestrator"""

    def __init__(self, result_sequence: list = None):
        """
        result_sequence: 结果序列，如 ["completed"] 或 ["need_layer1_fix", "completed"]
        """
        self.result_sequence = result_sequence or ["completed"]
        self.call_count = 0
        self.last_context = None

    def run(self, context: Dict[str, Any], continue_from_checkpoint: bool = False) -> AgentResult:
        self.call_count += 1
        self.last_context = context
        print(f"[MockExecuteAgent] 被调用，第 {self.call_count} 次")
        print(f"  context keys: {list(context.keys())}")

        # 获取当前应返回的结果
        idx = min(self.call_count - 1, len(self.result_sequence) - 1)
        result_type = self.result_sequence[idx]

        if result_type == "completed":
            return AgentResult(
                status="completed",
                artifacts={
                    "samples_path": "outputs/test_scenario/samples/eval.jsonl",
                    "evaluation_result": "outputs/test_scenario/execution_outputs/",
                },
                message="评测完成，成功率85%"
            )
        elif result_type == "need_layer1_fix":
            return AgentResult(
                status="need_layer1_fix",
                message="识别出Layer1问题",
                context_for_handoff={
                    "trigger_reason": "Critical问题占比35%，超过30%阈值",
                    "modification_suggestions_summary": [
                        "在BusinessRules明确余额扣减时机",
                        "调整checker容忍度"
                    ]
                }
            )
        else:
            return AgentResult(
                status="failed",
                message="模拟失败"
            )


if __name__ == "__main__":
    # 测试1: 简单流程（Init -> HITL1 -> Execute -> Completed）
    print("\n" + "="*60)
    print("测试1: 简单流程")
    print("="*60)

    orchestrator = Orchestrator(
        init_agent=MockInitAgent(should_succeed=True),
        execute_agent=MockExecuteAgent(result_sequence=["completed"])
    )

    result = orchestrator.run("设计一个会议室预订场景")
    print(f"\n最终结果: {json.dumps(result, ensure_ascii=False, indent=2)}")
