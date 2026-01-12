#!/usr/bin/env python3
"""
测试Resume交互模式
"""
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from orchestrator import Orchestrator, AgentPhase
from orchestrator.checkpoint import CheckpointManager
from agents import InitAgent, ExecuteAgent


def test_continue_with_input():
    """测试continue_with_input在不同状态下的行为"""
    print("\n" + "="*60)
    print("测试 continue_with_input() 方法")
    print("="*60 + "\n")

    # 创建mock orchestrator
    from orchestrator.orchestrator import MockInitAgent, MockExecuteAgent

    orchestrator = Orchestrator(
        init_agent=MockInitAgent(should_succeed=True),
        execute_agent=MockExecuteAgent(result_sequence=["completed"]),
        output_dir="outputs",
        auto_checkpoint=False  # 关闭自动checkpoint以简化测试
    )

    # Test 1: 无对话历史时，应该启动新的Init流程
    print("\n[Test 1] 无对话历史 - 启动新流程")
    orchestrator.state = AgentPhase.EXECUTE
    orchestrator.scenario_name = "test_scenario"
    orchestrator.design_artifacts = {"scenario_name": "test_scenario"}

    result = orchestrator.continue_with_input("修改BusinessRules，增加新规则")
    print(f"  结果状态: {orchestrator.state.value}")
    # 无历史时，会启动新的Init流程，MockInitAgent完成后转到EXECUTE
    print(f"  ✓ Test 1 通过") if orchestrator.state == AgentPhase.EXECUTE else print(f"  ✗ Test 1 失败")

    # Test 2: 模拟Init Agent有历史
    print("\n[Test 2] Init Agent有历史 - 继续Init")
    orchestrator2 = Orchestrator(
        init_agent=MockInitAgent(should_succeed=True),
        execute_agent=MockExecuteAgent(result_sequence=["completed"]),
        output_dir="outputs",
        auto_checkpoint=False
    )
    orchestrator2.state = AgentPhase.INIT
    # 模拟Init Agent有对话历史
    orchestrator2.init_agent._conversation_history = [{"role": "user", "content": "之前的对话"}]

    result = orchestrator2.continue_with_input("继续设计")
    print(f"  结果状态: {orchestrator2.state.value}")
    # Init Agent完成后会转到EXECUTE
    print(f"  ✓ Test 2 通过") if orchestrator2.state == AgentPhase.EXECUTE else print(f"  ✗ Test 2 失败")

    # Test 3: 模拟Execute Agent有历史
    print("\n[Test 3] Execute Agent有历史 - 继续Execute")
    orchestrator3 = Orchestrator(
        init_agent=MockInitAgent(should_succeed=True),
        execute_agent=MockExecuteAgent(result_sequence=["completed"]),
        output_dir="outputs",
        auto_checkpoint=False
    )
    orchestrator3.state = AgentPhase.EXECUTE
    orchestrator3.design_artifacts = {"scenario_name": "test_scenario"}
    # 模拟Execute Agent有对话历史
    orchestrator3.execute_agent._conversation_history = [{"role": "user", "content": "之前的执行"}]

    result = orchestrator3.continue_with_input("继续执行")
    print(f"  结果状态: {orchestrator3.state.value}")
    # Execute Agent继续工作，状态保持EXECUTE
    print(f"  ✓ Test 3 通过") if orchestrator3.state == AgentPhase.EXECUTE else print(f"  ✗ Test 3 失败")

    print("\n" + "="*60)
    print("测试完成")
    print("="*60 + "\n")


def test_checkpoint_save_restore():
    """测试checkpoint保存和恢复"""
    print("\n" + "="*60)
    print("测试 Checkpoint 保存和恢复")
    print("="*60 + "\n")

    from orchestrator.orchestrator import MockInitAgent, MockExecuteAgent

    # 创建orchestrator并运行
    print("[Step 1] 创建并运行orchestrator...")
    orchestrator = Orchestrator(
        init_agent=MockInitAgent(should_succeed=True),
        execute_agent=MockExecuteAgent(result_sequence=["completed"]),
        output_dir="outputs",
        checkpoint_dir="test_checkpoints",
        auto_checkpoint=True
    )

    result = orchestrator.run("测试场景")
    print(f"  状态: {orchestrator.state.value}")
    print(f"  场景: {orchestrator.scenario_name}")

    # 获取checkpoint ID
    manager = CheckpointManager(checkpoint_dir="test_checkpoints")
    checkpoint_id = manager.get_latest_id()
    print(f"  Checkpoint ID: {checkpoint_id}")

    # 恢复orchestrator
    print("\n[Step 2] 从checkpoint恢复...")
    restored = Orchestrator.resume(
        init_agent=MockInitAgent(should_succeed=True),
        execute_agent=MockExecuteAgent(result_sequence=["completed"]),
        checkpoint_id=checkpoint_id,
        checkpoint_dir="test_checkpoints",
        output_dir="outputs"
    )

    if restored:
        print(f"  ✓ 恢复成功")
        print(f"  状态: {restored.state.value}")
        print(f"  场景: {restored.scenario_name}")
        print(f"  需求: {restored.user_requirement[:30]}...")
        print(f"  迭代: Init={restored.init_iterations}, Execute={restored.execute_iterations}")
    else:
        print(f"  ✗ 恢复失败")

    print("\n" + "="*60)
    print("测试完成")
    print("="*60 + "\n")

    # 清理测试checkpoint
    import shutil
    shutil.rmtree("test_checkpoints", ignore_errors=True)


def test_old_state_compatibility():
    """测试旧状态的兼容性"""
    print("\n" + "="*60)
    print("测试旧状态兼容性")
    print("="*60 + "\n")

    from orchestrator.orchestrator import MockInitAgent, MockExecuteAgent
    from orchestrator.checkpoint import CheckpointManager, Checkpoint
    from orchestrator import AgentPhase

    # 创建包含旧状态的checkpoint
    old_states = ["failed", "completed", "init_phase", "execute_phase"]

    for old_state in old_states:
        print(f"\n[测试] 旧状态: {old_state}")

        # 手动创建一个旧格式的checkpoint
        checkpoint = Checkpoint(
            checkpoint_id="test_old_state",
            created_at="2026-01-01T00:00:00",
            state=old_state,
            user_requirement="测试需求",
            scenario_name="test_scenario",
            design_artifacts={},
            execution_artifacts={},
            init_iterations=1,
            execute_iterations=1,
            current_context={},
        )

        # 创建orchestrator
        orchestrator = Orchestrator(
            init_agent=MockInitAgent(should_succeed=True),
            execute_agent=MockExecuteAgent(result_sequence=["completed"]),
            output_dir="outputs",
            auto_checkpoint=False
        )

        # 恢复状态
        manager = CheckpointManager(checkpoint_dir="test_checkpoints")
        manager.restore(orchestrator, checkpoint)

        # 验证状态已正确映射
        print(f"  映射后状态: {orchestrator.state.value}")
        assert orchestrator.state in [AgentPhase.INIT, AgentPhase.EXECUTE], f"状态映射失败: {orchestrator.state}"
        print(f"  ✓ 映射成功")

    print("\n" + "="*60)
    print("旧状态兼容性测试完成")
    print("="*60 + "\n")


if __name__ == "__main__":
    try:
        test_continue_with_input()
        test_checkpoint_save_restore()
        test_old_state_compatibility()
        print("\n✓ 所有测试通过\n")
    except Exception as e:
        print(f"\n✗ 测试失败: {e}\n")
        import traceback
        traceback.print_exc()
