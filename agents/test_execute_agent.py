"""
Execute Agent单元测试 - 测试工具和核心流程
"""
import json
import shutil
import unittest
from pathlib import Path

from agents import ExecuteAgent


class TestExecuteAgentTools(unittest.TestCase):
    """测试Execute Agent的工具函数"""

    def setUp(self):
        """测试前准备"""
        self.test_dir = Path("test_execute_outputs")
        self.test_dir.mkdir(exist_ok=True)

        # 创建测试场景目录结构
        self.scenario_dir = self.test_dir / "test_scenario"
        for subdir in ["tools", "checkers", "data_pools", "samples", "execution_outputs"]:
            (self.scenario_dir / subdir).mkdir(parents=True, exist_ok=True)

        # 创建测试设计文件
        (self.scenario_dir / "unified_scenario_design.yaml").write_text("test: yaml")
        (self.scenario_dir / "BusinessRules.md").write_text("# Rules")

        self.agent = ExecuteAgent()

    def tearDown(self):
        """测试后清理"""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_read_design_file(self):
        """测试读取设计文件"""
        yaml_path = str(self.scenario_dir / "unified_scenario_design.yaml")
        result = self.agent._read_design_file(yaml_path)
        data = json.loads(result)

        self.assertIn("content", data)
        self.assertEqual(data["content"], "test: yaml")
        self.assertEqual(self.agent.scenario_dir, self.scenario_dir)

    def test_read_design_file_not_exist(self):
        """测试读取不存在的文件"""
        result = self.agent._read_design_file("/not/exist/file.yaml")
        data = json.loads(result)

        self.assertIn("error", data)

    def test_generate_tool(self):
        """测试生成Tool代码"""
        # 先设置scenario_dir
        self.agent._read_design_file(str(self.scenario_dir / "unified_scenario_design.yaml"))

        result = self.agent._generate_tool("my_tool", "def my_tool(): pass")
        data = json.loads(result)

        self.assertTrue(data["success"])
        self.assertTrue((self.scenario_dir / "tools" / "my_tool.py").exists())

    def test_generate_checker(self):
        """测试生成Checker代码"""
        self.agent._read_design_file(str(self.scenario_dir / "unified_scenario_design.yaml"))

        result = self.agent._generate_checker("my_checker", "def check(): pass")
        data = json.loads(result)

        self.assertTrue(data["success"])
        self.assertTrue((self.scenario_dir / "checkers" / "my_checker.py").exists())

    def test_generate_data_pool(self):
        """测试生成数据池"""
        self.agent._read_design_file(str(self.scenario_dir / "unified_scenario_design.yaml"))

        data_content = '{"id": 1, "name": "test"}\n{"id": 2, "name": "test2"}'
        result = self.agent._generate_data_pool("users", data_content)
        data = json.loads(result)

        self.assertTrue(data["success"])
        self.assertTrue((self.scenario_dir / "data_pools" / "users.jsonl").exists())

    def test_generate_samples(self):
        """测试生成样本"""
        self.agent._read_design_file(str(self.scenario_dir / "unified_scenario_design.yaml"))

        samples = '{"data_id": "S001", "query": "test"}\n{"data_id": "S002", "query": "test2"}'
        result = self.agent._generate_samples(samples)
        data = json.loads(result)

        self.assertTrue(data["success"])
        self.assertEqual(data["sample_count"], 2)
        self.assertTrue((self.scenario_dir / "samples" / "eval.jsonl").exists())

    def test_run_evaluation(self):
        """测试运行评测"""
        self.agent._read_design_file(str(self.scenario_dir / "unified_scenario_design.yaml"))

        # 先生成样本
        samples = '{"data_id": "S001", "query": "test"}\n{"data_id": "S002", "query": "test2"}'
        self.agent._generate_samples(samples)

        # 运行评测
        result = self.agent._run_evaluation()
        data = json.loads(result)

        self.assertTrue(data["success"])
        self.assertEqual(data["total_samples"], 2)
        self.assertIn("success_rate", data)

    def test_analyze_failures(self):
        """测试分析失败案例"""
        self.agent._read_design_file(str(self.scenario_dir / "unified_scenario_design.yaml"))
        self.agent.current_iteration = 1

        result = self.agent._analyze_failures(["S001", "S002"])
        data = json.loads(result)

        self.assertEqual(data["total_failures"], 2)
        self.assertIn("attribution", data)

    def test_complete_execution(self):
        """测试完成执行"""
        self.agent._read_design_file(str(self.scenario_dir / "unified_scenario_design.yaml"))

        result = self.agent._complete_execution("测试完成", 0.85)
        data = json.loads(result)

        self.assertTrue(data["success"])
        self.assertTrue(self.agent._execution_completed)

    def test_request_layer1_fix(self):
        """测试请求返回Init"""
        self.agent._read_design_file(str(self.scenario_dir / "unified_scenario_design.yaml"))
        self.agent.current_iteration = 1

        result = self.agent._request_layer1_fix("Critical问题过多", ["修改规则1", "修改规则2"])
        data = json.loads(result)

        self.assertTrue(data["success"])
        self.assertEqual(data["action"], "return_to_init")
        self.assertTrue(self.agent._need_layer1_fix)


class TestExecuteAgentSystemPrompt(unittest.TestCase):
    """测试系统提示词"""

    def setUp(self):
        self.agent = ExecuteAgent()

    def test_basic_prompt(self):
        """测试基本提示词"""
        prompt = self.agent.get_system_prompt({})

        self.assertIn("Execute Agent", prompt)
        self.assertIn("Layer 2", prompt)
        self.assertIn("Layer 3", prompt)
        self.assertIn("Layer 4", prompt)


class TestExecuteAgentCompletion(unittest.TestCase):
    """测试完成检查"""

    def setUp(self):
        self.test_dir = Path("test_execute_outputs2")
        self.test_dir.mkdir(exist_ok=True)
        self.scenario_dir = self.test_dir / "test_scenario"
        self.scenario_dir.mkdir(parents=True, exist_ok=True)
        self.agent = ExecuteAgent()
        self.agent.scenario_dir = self.scenario_dir

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_check_completion_completed(self):
        """测试完成状态检查"""
        self.agent._execution_completed = True
        self.agent._execution_artifacts = {"samples_path": "test"}

        result = self.agent.check_completion("", {})

        self.assertIsNotNone(result)
        self.assertEqual(result.status, "completed")

    def test_check_completion_need_layer1_fix(self):
        """测试需要Layer1修复状态检查"""
        self.agent._need_layer1_fix = True
        self.agent._layer1_context = {
            "trigger_reason": "测试",
            "modification_suggestions_summary": []
        }

        result = self.agent.check_completion("", {})

        self.assertIsNotNone(result)
        self.assertEqual(result.status, "need_layer1_fix")

    def test_check_completion_not_done(self):
        """测试未完成状态"""
        result = self.agent.check_completion("", {})
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
