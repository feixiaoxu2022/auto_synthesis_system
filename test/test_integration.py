"""
端到端集成测试 - 测试完整工作流
"""
import json
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator import Orchestrator, WorkflowState
from orchestrator.orchestrator import MockInitAgent, MockExecuteAgent


class TestEndToEndWorkflow(unittest.TestCase):
    """端到端工作流测试"""

    def setUp(self):
        self.test_output_dir = Path("test_e2e_outputs")
        self.test_output_dir.mkdir(exist_ok=True)

    def tearDown(self):
        if self.test_output_dir.exists():
            shutil.rmtree(self.test_output_dir)

    @patch('builtins.input', return_value='y')
    def test_simple_flow_mock(self, mock_input):
        """测试简单流程（Mock Agent）"""
        init_agent = MockInitAgent(should_succeed=True)
        exec_agent = MockExecuteAgent(result_sequence=["completed"])

        orchestrator = Orchestrator(
            init_agent=init_agent,
            execute_agent=exec_agent,
            output_dir=str(self.test_output_dir)
        )

        result = orchestrator.run("设计一个会议室预订场景")

        # 验证结果
        self.assertEqual(result["status"], "completed")
        self.assertEqual(init_agent.call_count, 1)
        self.assertEqual(exec_agent.call_count, 1)

    @patch('builtins.input', side_effect=['y', 'y', 'y'])
    def test_layer1_fix_flow_mock(self, mock_input):
        """测试Layer1修复流程（Mock Agent）"""
        init_agent = MockInitAgent(should_succeed=True)
        exec_agent = MockExecuteAgent(result_sequence=["need_layer1_fix", "completed"])

        orchestrator = Orchestrator(
            init_agent=init_agent,
            execute_agent=exec_agent,
            output_dir=str(self.test_output_dir)
        )

        result = orchestrator.run("设计一个复杂场景")

        # 验证结果
        self.assertEqual(result["status"], "completed")
        self.assertEqual(init_agent.call_count, 2)  # Init被调用两次
        self.assertEqual(exec_agent.call_count, 2)  # Execute被调用两次
        self.assertEqual(result["iterations"]["init"], 2)
        self.assertEqual(result["iterations"]["execute"], 2)

    @patch('builtins.input', return_value='q')
    def test_user_quit(self, mock_input):
        """测试用户退出"""
        init_agent = MockInitAgent(should_succeed=True)
        exec_agent = MockExecuteAgent()

        orchestrator = Orchestrator(
            init_agent=init_agent,
            execute_agent=exec_agent,
            output_dir=str(self.test_output_dir)
        )

        result = orchestrator.run("测试退出")

        self.assertEqual(result["status"], "failed")

    def test_init_agent_failure(self):
        """测试Init Agent失败"""
        init_agent = MockInitAgent(should_succeed=False)

        orchestrator = Orchestrator(
            init_agent=init_agent,
            output_dir=str(self.test_output_dir)
        )

        result = orchestrator.run("测试失败")

        self.assertEqual(result["status"], "failed")


class TestWorkflowStateTransitions(unittest.TestCase):
    """状态转换测试"""

    @patch('builtins.input', return_value='y')
    def test_state_sequence_happy_path(self, mock_input):
        """测试正常流程状态序列"""
        init_agent = MockInitAgent()
        exec_agent = MockExecuteAgent()

        orchestrator = Orchestrator(init_agent=init_agent, execute_agent=exec_agent)

        # 记录状态变化
        states = []
        original_handle_init = orchestrator._handle_init_phase

        def track_init():
            states.append(orchestrator.state)
            original_handle_init()

        orchestrator._handle_init_phase = track_init

        orchestrator.run("测试")

        # 验证最终状态
        self.assertEqual(orchestrator.state, WorkflowState.COMPLETED)


class TestContextPassing(unittest.TestCase):
    """Context传递集成测试"""

    @patch('builtins.input', return_value='y')
    def test_init_to_execute_context(self, mock_input):
        """测试Init到Execute的Context传递"""
        init_agent = MockInitAgent()
        exec_agent = MockExecuteAgent()

        orchestrator = Orchestrator(init_agent=init_agent, execute_agent=exec_agent)
        orchestrator.run("测试Context传递")

        # 验证Execute Agent收到的context
        exec_context = exec_agent.last_context
        self.assertEqual(exec_context["handoff_type"], "init_to_execute")
        self.assertIn("design_artifacts", exec_context)

    @patch('builtins.input', side_effect=['y', 'y', 'y'])
    def test_execute_to_init_context(self, mock_input):
        """测试Execute到Init的Context传递（Layer1问题）"""
        init_agent = MockInitAgent()
        exec_agent = MockExecuteAgent(result_sequence=["need_layer1_fix", "completed"])

        orchestrator = Orchestrator(init_agent=init_agent, execute_agent=exec_agent)
        orchestrator.run("测试Layer1修复")

        # 验证第二次Init收到Execute的反馈
        second_init_context = init_agent.last_context
        self.assertIn("feedback_from_execute", second_init_context)
        self.assertIn("trigger_reason", second_init_context["feedback_from_execute"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
