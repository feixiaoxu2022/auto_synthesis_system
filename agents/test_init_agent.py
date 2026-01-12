"""
Init Agent单元测试 - 测试工具和核心流程
"""
import json
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from agents import InitAgent, AgentResult


class TestInitAgentTools(unittest.TestCase):
    """测试Init Agent的工具函数"""

    def setUp(self):
        """测试前准备"""
        self.test_output_dir = Path("test_outputs")
        self.test_output_dir.mkdir(exist_ok=True)
        self.agent = InitAgent(output_dir=str(self.test_output_dir))

    def tearDown(self):
        """测试后清理"""
        if self.test_output_dir.exists():
            shutil.rmtree(self.test_output_dir)

    def test_create_scenario_directory(self):
        """测试创建场景目录"""
        result = self.agent._create_scenario_directory("test_scenario")
        data = json.loads(result)

        self.assertTrue(data["success"])
        self.assertTrue((self.test_output_dir / "test_scenario").exists())
        self.assertTrue((self.test_output_dir / "test_scenario" / "tools").exists())
        self.assertTrue((self.test_output_dir / "test_scenario" / "samples").exists())

    def test_write_yaml_without_directory(self):
        """测试未创建目录时写入YAML"""
        result = self.agent._write_yaml("test: content")
        data = json.loads(result)

        self.assertIn("error", data)

    def test_write_yaml_with_directory(self):
        """测试创建目录后写入YAML"""
        self.agent._create_scenario_directory("test_scenario")
        result = self.agent._write_yaml("test: content")
        data = json.loads(result)

        self.assertTrue(data["success"])
        self.assertTrue((self.test_output_dir / "test_scenario" / "unified_scenario_design.yaml").exists())

    def test_write_business_rules(self):
        """测试写入BusinessRules.md"""
        self.agent._create_scenario_directory("test_scenario")
        result = self.agent._write_business_rules("# Business Rules\n\nRule 1...")
        data = json.loads(result)

        self.assertTrue(data["success"])
        content = (self.test_output_dir / "test_scenario" / "BusinessRules.md").read_text()
        self.assertIn("Business Rules", content)

    def test_write_format_spec(self):
        """测试写入format_specifications.json"""
        self.agent._create_scenario_directory("test_scenario")
        spec = json.dumps({"entities": {"user": {"fields": []}}})
        result = self.agent._write_format_spec(spec)
        data = json.loads(result)

        self.assertTrue(data["success"])

    def test_complete_design_missing_files(self):
        """测试缺少必要文件时调用complete_design"""
        self.agent._create_scenario_directory("test_scenario")
        # 只写入部分文件
        self.agent._write_yaml("test: content")

        result = self.agent._complete_design("测试总结")
        data = json.loads(result)

        self.assertFalse(data["success"])
        self.assertIn("BusinessRules.md", str(data["error"]))

    def test_complete_design_success(self):
        """测试完整流程后调用complete_design"""
        self.agent._create_scenario_directory("test_scenario")
        self.agent._write_yaml("test: content")
        self.agent._write_business_rules("# Rules")
        self.agent._write_format_spec("{}")

        result = self.agent._complete_design("测试总结")
        data = json.loads(result)

        self.assertTrue(data["success"])
        self.assertIn("artifacts", data)
        self.assertEqual(data["artifacts"]["scenario_name"], "test_scenario")

    def test_list_skill_files(self):
        """测试列出skill文件"""
        # 这个测试依赖实际的skills目录
        result = self.agent._list_skill_files("scenario_design_sop")
        data = json.loads(result)

        # 即使目录不存在也应该返回结构化结果
        self.assertTrue("files" in data or "error" in data)


class TestInitAgentSystemPrompt(unittest.TestCase):
    """测试系统提示词生成"""

    def setUp(self):
        self.agent = InitAgent()

    def test_basic_prompt(self):
        """测试基本提示词"""
        prompt = self.agent.get_system_prompt({"user_requirement": "测试需求"})

        self.assertIn("Init Agent", prompt)
        self.assertIn("unified_scenario_design.yaml", prompt)
        self.assertIn("BusinessRules.md", prompt)

    def test_prompt_with_feedback(self):
        """测试带反馈的提示词"""
        context = {
            "user_requirement": "测试需求",
            "feedback_from_execute": {
                "trigger_reason": "Critical问题过多",
                "modification_suggestions_summary": ["调整规则"],
                "execution_output_dir": "/path/to/outputs"
            }
        }
        prompt = self.agent.get_system_prompt(context)

        self.assertIn("Execute Agent反馈", prompt)
        self.assertIn("Critical问题过多", prompt)


class TestInitAgentMessageBuilding(unittest.TestCase):
    """测试消息构建"""

    def setUp(self):
        self.agent = InitAgent()

    def test_initial_message(self):
        """测试初始消息"""
        context = {"user_requirement": "设计一个会议室预订场景", "iteration": 1}
        message = self.agent.build_initial_message(context)

        self.assertIn("会议室预订", message)
        self.assertIn("参考资料", message)

    def test_iteration_message(self):
        """测试迭代消息"""
        context = {
            "user_requirement": "测试",
            "iteration": 2,
            "feedback_from_execute": {"trigger_reason": "测试原因"}
        }
        message = self.agent.build_initial_message(context)

        self.assertIn("第 2 次设计迭代", message)
        self.assertIn("反馈", message)


class TestInitAgentIntegration(unittest.TestCase):
    """集成测试（需要API Key）"""

    @unittest.skip("需要ANTHROPIC_API_KEY环境变量")
    def test_real_agent_run(self):
        """真实API调用测试"""
        import os
        if not os.environ.get("ANTHROPIC_API_KEY"):
            self.skipTest("需要ANTHROPIC_API_KEY")

        agent = InitAgent(output_dir="test_outputs")
        result = agent.run({"user_requirement": "设计一个简单的待办事项管理场景"})

        self.assertEqual(result.status, "completed")
        self.assertIn("scenario_name", result.artifacts)


if __name__ == "__main__":
    unittest.main(verbosity=2)
