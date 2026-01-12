#!/usr/bin/env python3
"""
基础功能测试
"""
import os
import sys
from pathlib import Path

# 确保可以导入模块
sys.path.insert(0, str(Path(__file__).parent))

def test_init_agent_simple():
    """测试 Init Agent 简单问答"""
    from agents import InitAgent

    print("=" * 60)
    print("测试: Init Agent 简单问答")
    print("=" * 60)

    # 从环境变量或使用默认模型
    model = os.environ.get("MODEL", "claude-sonnet-4-5-20250929")
    print(f"使用模型: {model}")

    agent = InitAgent(
        output_dir="outputs",
        skills_dir="skills",
        max_iterations=5,  # 限制迭代次数
        model=model
    )

    # 测试简单问题
    context = {
        "user_requirement": "你好，你是谁？你能做什么？",
        "iteration": 1,
        "output_dir": "outputs"
    }

    result = agent.run(context)

    print(f"\n结果状态: {result.status}")
    print(f"消息: {result.message[:500] if result.message else 'None'}...")

    return result.status == "completed"


def test_orchestrator_mock():
    """测试 Orchestrator 与 Mock Agent"""
    from orchestrator import Orchestrator
    from orchestrator.orchestrator import MockInitAgent, MockExecuteAgent

    print("\n" + "=" * 60)
    print("测试: Orchestrator Mock 流程")
    print("=" * 60)

    orchestrator = Orchestrator(
        init_agent=MockInitAgent(should_succeed=True),
        execute_agent=MockExecuteAgent(result_sequence=["completed"]),
        output_dir="outputs"
    )

    # Mock 不需要人工交互，直接运行
    # 但需要 patch HITL 方法
    def auto_approve_hitl1():
        from orchestrator import WorkflowState
        orchestrator.state = WorkflowState.EXECUTE_PHASE

    def auto_approve_hitl3():
        from orchestrator import WorkflowState
        orchestrator.state = WorkflowState.COMPLETED

    orchestrator._handle_hitl1 = auto_approve_hitl1
    orchestrator._handle_hitl3 = auto_approve_hitl3

    result = orchestrator.run("测试需求")

    print(f"\n结果: {result}")

    return result.get("status") == "completed"


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("运行基础功能测试")
    print("=" * 60 + "\n")

    tests = [
        ("Mock Orchestrator", test_orchestrator_mock),
        ("Init Agent 简单问答", test_init_agent_simple),
    ]

    results = []
    for name, test_fn in tests:
        try:
            passed = test_fn()
            results.append((name, "PASS" if passed else "FAIL"))
        except Exception as e:
            import traceback
            traceback.print_exc()
            results.append((name, f"ERROR: {e}"))

    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    for name, status in results:
        print(f"  {name}: {status}")
