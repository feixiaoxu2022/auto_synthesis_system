"""
Orchestrator单元测试 - 验证状态流转和Agent协调
"""
import unittest
from unittest.mock import patch, MagicMock
from orchestrator import Orchestrator, WorkflowState, AgentResult


class MockInitAgent:
    """测试用Init Agent"""
    def __init__(self, should_succeed=True):
        self.should_succeed = should_succeed
        self.call_count = 0
        self.last_context = None

    def run(self, context):
        self.call_count += 1
        self.last_context = context
        if self.should_succeed:
            return AgentResult(
                status="completed",
                artifacts={
                    "scenario_name": "test_scenario",
                    "unified_scenario_design_path": "outputs/test/design.yaml",
                },
                message="设计完成"
            )
        return AgentResult(status="failed", message="设计失败")


class MockExecuteAgent:
    """测试用Execute Agent"""
    def __init__(self, result_sequence=None):
        self.result_sequence = result_sequence or ["completed"]
        self.call_count = 0
        self.last_context = None

    def run(self, context):
        self.call_count += 1
        self.last_context = context
        idx = min(self.call_count - 1, len(self.result_sequence) - 1)
        result_type = self.result_sequence[idx]

        if result_type == "completed":
            return AgentResult(
                status="completed",
                artifacts={"samples_path": "outputs/test/samples.jsonl"},
                message="执行完成"
            )
        elif result_type == "need_layer1_fix":
            return AgentResult(
                status="need_layer1_fix",
                message="需要修改设计",
                context_for_handoff={
                    "trigger_reason": "Critical问题占比超标",
                    "modification_suggestions_summary": ["调整规则"]
                }
            )
        return AgentResult(status="failed", message="执行失败")


class TestOrchestratorStateTransitions(unittest.TestCase):
    """状态流转测试"""

    def test_initial_state(self):
        """测试初始状态"""
        orch = Orchestrator()
        self.assertEqual(orch.state, WorkflowState.INIT_PHASE)

    @patch('builtins.input', return_value='y')
    def test_happy_path_completed(self, mock_input):
        """测试正常流程: INIT -> HITL1(y) -> EXECUTE -> COMPLETED"""
        init_agent = MockInitAgent(should_succeed=True)
        exec_agent = MockExecuteAgent(result_sequence=["completed"])

        orch = Orchestrator(init_agent=init_agent, execute_agent=exec_agent)
        result = orch.run("测试需求")

        self.assertEqual(orch.state, WorkflowState.COMPLETED)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(init_agent.call_count, 1)
        self.assertEqual(exec_agent.call_count, 1)

    @patch('builtins.input', return_value='n')
    def test_hitl1_reject_loops_back(self, mock_input):
        """测试HITL1拒绝: INIT -> HITL1(n) -> INIT (循环)"""
        init_agent = MockInitAgent(should_succeed=True)
        exec_agent = MockExecuteAgent()

        orch = Orchestrator(init_agent=init_agent, execute_agent=exec_agent)

        # 模拟: 第一次n拒绝，第二次y批准
        with patch('builtins.input', side_effect=['n', 'y']):
            result = orch.run("测试需求")

        self.assertEqual(orch.state, WorkflowState.COMPLETED)
        self.assertEqual(init_agent.call_count, 2)  # Init被调用两次

    @patch('builtins.input', return_value='q')
    def test_hitl1_quit(self, mock_input):
        """测试HITL1退出: INIT -> HITL1(q) -> FAILED"""
        init_agent = MockInitAgent(should_succeed=True)

        orch = Orchestrator(init_agent=init_agent)
        result = orch.run("测试需求")

        self.assertEqual(orch.state, WorkflowState.FAILED)
        self.assertEqual(result["status"], "failed")

    def test_init_agent_failure(self):
        """测试Init Agent失败"""
        init_agent = MockInitAgent(should_succeed=False)

        orch = Orchestrator(init_agent=init_agent)
        result = orch.run("测试需求")

        self.assertEqual(orch.state, WorkflowState.FAILED)

    @patch('builtins.input', side_effect=['y', 'y', 'y'])
    def test_layer1_problem_returns_to_init(self, mock_input):
        """测试Layer1问题: INIT->HITL1(y)->EXEC->HITL3(y)->INIT->HITL1(y)->EXEC->COMPLETED"""
        init_agent = MockInitAgent(should_succeed=True)
        exec_agent = MockExecuteAgent(result_sequence=["need_layer1_fix", "completed"])

        orch = Orchestrator(init_agent=init_agent, execute_agent=exec_agent)
        result = orch.run("测试需求")

        self.assertEqual(orch.state, WorkflowState.COMPLETED)
        self.assertEqual(init_agent.call_count, 2)  # Init被调用两次
        self.assertEqual(exec_agent.call_count, 2)  # Execute被调用两次

    @patch('builtins.input', side_effect=['y', 'n'])
    def test_layer1_problem_accept_current(self, mock_input):
        """测试Layer1问题接受当前结果: EXECUTE -> HITL3(n) -> COMPLETED"""
        init_agent = MockInitAgent(should_succeed=True)
        exec_agent = MockExecuteAgent(result_sequence=["need_layer1_fix"])

        orch = Orchestrator(init_agent=init_agent, execute_agent=exec_agent)
        result = orch.run("测试需求")

        self.assertEqual(orch.state, WorkflowState.COMPLETED)
        self.assertEqual(init_agent.call_count, 1)
        self.assertEqual(exec_agent.call_count, 1)


class TestContextPassing(unittest.TestCase):
    """Context传递测试"""

    @patch('builtins.input', return_value='y')
    def test_init_to_execute_context(self, mock_input):
        """测试Init->Execute的Context传递"""
        init_agent = MockInitAgent()
        exec_agent = MockExecuteAgent()

        orch = Orchestrator(init_agent=init_agent, execute_agent=exec_agent)
        orch.run("测试需求")

        # 验证Execute Agent收到的context包含设计产物
        exec_context = exec_agent.last_context
        self.assertEqual(exec_context["handoff_type"], "init_to_execute")
        self.assertIn("design_artifacts", exec_context)
        self.assertEqual(exec_context["user_requirement"], "测试需求")

    @patch('builtins.input', side_effect=['y', 'y', 'y'])
    def test_execute_to_init_context(self, mock_input):
        """测试Execute->Init的Context传递（Layer1问题）"""
        init_agent = MockInitAgent()
        exec_agent = MockExecuteAgent(result_sequence=["need_layer1_fix", "completed"])

        orch = Orchestrator(init_agent=init_agent, execute_agent=exec_agent)
        orch.run("测试需求")

        # 验证第二次Init收到Execute的反馈
        self.assertEqual(init_agent.call_count, 2)
        second_init_context = init_agent.last_context
        self.assertIn("feedback_from_execute", second_init_context)


class TestIterationTracking(unittest.TestCase):
    """Step计数测试"""

    @patch('builtins.input', side_effect=['y', 'y', 'y'])
    def test_iteration_counts(self, mock_input):
        """测试Step计数正确"""
        init_agent = MockInitAgent()
        exec_agent = MockExecuteAgent(result_sequence=["need_layer1_fix", "completed"])

        orch = Orchestrator(init_agent=init_agent, execute_agent=exec_agent)
        result = orch.run("测试需求")

        self.assertEqual(result["iterations"]["init"], 2)
        self.assertEqual(result["iterations"]["execute"], 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
