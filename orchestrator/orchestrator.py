"""
Orchestrator - Coordinator for sample synthesis system.

核心职责:
1. Agent生命周期管理
2. Checkpoint管理 - 支持Resume
3. 用户交互协调

不负责:
- 业务决策（由Agent自己决定）
- 代码生成
- 评测执行
"""
import json
from typing import Dict, Any, Optional, Protocol
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class AgentResult:
    """Agent执行结果"""
    status: str  # "completed" | "need_approval" | "failed"
    artifacts: Dict[str, str] = field(default_factory=dict)  # 生成的文件路径
    message: str = ""
    context: Optional[Dict[str, Any]] = None  # 附加上下文信息


class AgentProtocol(Protocol):
    """Agent接口协议"""
    def run(self, context: Dict[str, Any], continue_from_checkpoint: bool = False) -> AgentResult:
        """执行Agent任务"""
        ...


class Orchestrator:
    """
    Orchestrator - 单Agent协调器

    职责:
    - Agent生命周期管理
    - Checkpoint 管理（支持 Resume）
    - 用户交互协调
    """

    def __init__(self,
                 agent: AgentProtocol,
                 work_dir: str = "work",
                 checkpoint_dir: str = "checkpoints",
                 auto_checkpoint: bool = True):
        self.agent = agent
        self.work_dir = Path(work_dir)

        # 状态
        self.user_requirement = ""
        self.scenario_name = ""

        # 产物路径
        self.artifacts: Dict[str, str] = {}

        # 迭代计数
        self.iterations = 0

        # Checkpoint 管理
        from .checkpoint import CheckpointManager
        self.checkpoint_manager = CheckpointManager(checkpoint_dir)
        self.auto_checkpoint = auto_checkpoint

        # 注入checkpoint保存回调到Agent
        if self.agent and hasattr(self.agent, 'on_tool_call_complete'):
            self.agent.on_tool_call_complete = lambda: self._save_checkpoint()

    def _save_checkpoint(self, force_new: bool = False):
        """保存 checkpoint"""
        if self.auto_checkpoint:
            self.checkpoint_manager.save(self, force_new=force_new)

    @classmethod
    def resume(cls,
               agent: AgentProtocol,
               checkpoint_id: Optional[str] = None,
               checkpoint_dir: str = "checkpoints",
               work_dir: str = "work") -> Optional["Orchestrator"]:
        """
        从 checkpoint 恢复

        Args:
            agent: Agent 实例
            checkpoint_id: 指定 checkpoint ID，None 则使用 latest
            checkpoint_dir: checkpoint 目录
            work_dir: 工作目录

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
            agent=agent,
            work_dir=work_dir,
            checkpoint_dir=checkpoint_dir,
        )

        # 恢复状态
        manager.restore(orchestrator, checkpoint)
        orchestrator.checkpoint_manager = manager

        print(f"[Resume] 从 checkpoint {checkpoint.checkpoint_id} 恢复")
        print(f"  需求: {orchestrator.user_requirement[:50]}...")
        print(f"  迭代: {orchestrator.iterations}")

        return orchestrator

    def run(self, user_requirement: str) -> Dict[str, Any]:
        """
        主执行入口

        Args:
            user_requirement: 用户需求描述

        Returns:
            执行结果
        """
        self.user_requirement = user_requirement
        self.iterations += 1

        # 构建context
        context = {
            "user_requirement": user_requirement,
            "iteration": self.iterations,
            "work_dir": str(self.work_dir),
        }

        print(f"\n[Orchestrator] 执行 Agent (第 {self.iterations} 次)")

        # 运行Agent
        result = self.agent.run(context, continue_from_checkpoint=False)

        # 保存产物
        if result.artifacts:
            self.artifacts.update(result.artifacts)
            if "scenario_name" in result.artifacts:
                self.scenario_name = result.artifacts["scenario_name"]

        # 保存checkpoint
        self._save_checkpoint(force_new=True)

        return self._build_final_result(result)

    def continue_with_input(self, new_input: str) -> Dict[str, Any]:
        """
        用户继续输入，传给Agent处理

        Args:
            new_input: 用户的新输入

        Returns:
            执行结果
        """
        self.iterations += 1

        print(f"\n[Orchestrator] 继续执行 (第 {self.iterations} 次)")
        print(f"  用户输入: {new_input[:50]}...")
        print(f"  Checkpoint ID: {self.checkpoint_manager._current_checkpoint_id}")

        # 特殊命令：手动compact
        if new_input.strip().lower() == "/compact":
            print("[Orchestrator] 触发手动compact")
            if self.agent and hasattr(self.agent, 'manual_compact'):
                success = self.agent.manual_compact()
                if success:
                    self._save_checkpoint()  # 保存压缩后的状态
            return self._build_final_result()

        # 构建context
        context = {
            "user_requirement": new_input,
            "iteration": self.iterations,
            "work_dir": str(self.work_dir),
            "artifacts": self.artifacts,
        }

        # Resume时使用已保存的对话历史
        result = self.agent.run(context, continue_from_checkpoint=True)

        # 更新产物
        if result.artifacts:
            self.artifacts.update(result.artifacts)
            if "scenario_name" in result.artifacts:
                self.scenario_name = result.artifacts["scenario_name"]

        # 保存checkpoint（继续使用当前checkpoint_id）
        self._save_checkpoint()

        return self._build_final_result(result)

    def _build_final_result(self, result: Optional[AgentResult] = None) -> Dict[str, Any]:
        """构建最终结果"""
        return {
            "status": result.status if result else "in_progress",
            "scenario_name": self.scenario_name,
            "artifacts": self.artifacts,
            "iterations": self.iterations,
            "message": result.message if result else "",
        }


# ============================================================
# 测试用Mock Agent
# ============================================================

class MockAgent:
    """Mock Agent - 用于测试Orchestrator"""

    def __init__(self, should_succeed: bool = True):
        self.should_succeed = should_succeed
        self.call_count = 0
        self.last_context = None

    def run(self, context: Dict[str, Any], continue_from_checkpoint: bool = False) -> AgentResult:
        self.call_count += 1
        self.last_context = context
        print(f"[MockAgent] 被调用，第 {self.call_count} 次")
        print(f"  context keys: {list(context.keys())}")
        print(f"  continue_from_checkpoint: {continue_from_checkpoint}")

        if self.should_succeed:
            return AgentResult(
                status="completed",
                artifacts={
                    "scenario_name": "test_scenario",
                    "samples_path": "work/test_scenario/samples/eval.jsonl",
                    "evaluation_result": "work/test_scenario/evaluation_outputs/",
                },
                message="任务完成"
            )
        else:
            return AgentResult(
                status="failed",
                message="模拟失败"
            )


if __name__ == "__main__":
    # 测试: 简单流程
    print("\n" + "="*60)
    print("测试: 简单流程")
    print("="*60)

    orchestrator = Orchestrator(
        agent=MockAgent(should_succeed=True),
        work_dir="test_work"
    )

    result = orchestrator.run("设计一个会议室预订场景的评测样本")
    print(f"\n最终结果: {json.dumps(result, ensure_ascii=False, indent=2)}")
