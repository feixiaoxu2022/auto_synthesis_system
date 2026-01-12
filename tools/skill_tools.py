"""
技能库工具 - 获取SOP、模板、最佳实践
"""
import json
from pathlib import Path
from typing import Dict, Any, List


class UseSkill:
    """技能库工具 - 获取参考资源"""

    name = "use_skill"
    description = """获取技能库资源（SOP、模板、最佳实践）。每个skill提供特定领域的实现指南。

**可用Skills（按使用时机分类）**：

Init Agent专用：
- business_rules_authoring: 【编写业务规则文档时】编写BusinessRules.md的完整指南（模板+示例）
- scenario_design_sop: 【设计场景结构时】场景设计完整流程（4步SOP+难度提升策略）

Execute Agent专用：
- tool_implementation: 【生成tools/*.py时】实现场景专用工具（BaseAtomicTool模板+示例）
- checker_implementation: 【生成checkers/*.py时】实现验证检查器（BaseChecker模板+评分逻辑）
- sample_authoring: 【合成样本文件时】编写高质量测试样本（generator模板+用户模拟器设计）
- evaluation_execution: 【执行benchkit评测时】运行自动化评测（executor/evaluator命令和配置）
- failure_analysis: 【分析评测失败原因时】失败案例归因分析（8步分析流程+决策树）
- execute_to_init_context: 【需要反馈Layer 1设计问题时】Execute→Init反馈格式规范（简化版）

**返回内容**：SKILL.md主文档 + 可用子资源列表（templates/examples/sop/references）
**进一步阅读**：使用file_reader读取具体模板或示例文件
"""

    # 技能类型到目录的映射
    SKILL_MAPPING = {
        # Init Agent技能
        "business_rules_authoring": "business_rules_authoring",
        "scenario_design_sop": "scenario_design_sop",
        # Execute Agent技能
        "tool_implementation": "tool_implementation",
        "checker_implementation": "checker_implementation",
        "sample_authoring": "sample_authoring",
        "evaluation_execution": "evaluation_execution",
        "failure_analysis": "failure_analysis",
        "execute_to_init_context": "execute_to_init_context",
    }

    def __init__(self, skills_dir: Path):
        self.skills_dir = skills_dir

    def list_skills(self) -> Dict[str, Any]:
        """列出所有可用技能"""
        available = []
        for skill_type, dir_name in self.SKILL_MAPPING.items():
            skill_path = self.skills_dir / dir_name
            if skill_path.exists():
                available.append({
                    "skill_type": skill_type,
                    "directory": dir_name,
                    "exists": True
                })
            else:
                available.append({
                    "skill_type": skill_type,
                    "directory": dir_name,
                    "exists": False
                })
        return {"skills": available}

    def execute(self, skill_type: str) -> Dict[str, Any]:
        """获取指定技能的资源"""
        if skill_type not in self.SKILL_MAPPING:
            return {
                "error": f"未知的技能类型: {skill_type}",
                "available_types": list(self.SKILL_MAPPING.keys())
            }

        skill_dir_name = self.SKILL_MAPPING[skill_type]
        skill_path = self.skills_dir / skill_dir_name

        if not skill_path.exists():
            return {"error": f"技能目录不存在: {skill_path}"}

        # 读取SKILL.md作为主要内容
        skill_md = skill_path / "SKILL.md"
        if skill_md.exists():
            content = skill_md.read_text(encoding="utf-8")
        else:
            # 如果没有SKILL.md，列出目录下的文件
            files = list(skill_path.rglob("*"))
            file_list = [str(f.relative_to(skill_path)) for f in files if f.is_file()]
            content = f"技能目录 {skill_dir_name} 包含以下文件:\n" + "\n".join(f"- {f}" for f in file_list)

        # 列出可用的子资源
        available_resources: List[str] = []
        resource_files: Dict[str, List[str]] = {}

        for subdir in ["templates", "examples", "sop", "references"]:
            subpath = skill_path / subdir
            if subpath.exists():
                available_resources.append(subdir)
                # 列出子目录中的文件
                files_in_subdir = [f.name for f in subpath.iterdir() if f.is_file()]
                if files_in_subdir:
                    resource_files[subdir] = files_in_subdir

        return {
            "skill_type": skill_type,
            "skill_directory": skill_dir_name,
            "content": content,
            "available_resources": available_resources,
            "resource_files": resource_files,
            "tip": f"使用file_reader读取具体文件，路径格式: skills/{skill_dir_name}/<subdir>/<filename>"
        }


class SkillFileReader:
    """技能文件读取器 - 直接读取skills目录下的文件"""

    def __init__(self, skills_dir: Path):
        self.skills_dir = skills_dir

    def read(self, skill_name: str, file_path: str) -> Dict[str, Any]:
        """读取技能目录下的指定文件

        Args:
            skill_name: 技能名称（目录名）
            file_path: 相对于技能目录的文件路径

        Returns:
            文件内容或错误信息
        """
        # 安全检查
        if ".." in file_path:
            return {"error": "不允许使用'..'进行路径穿越"}

        full_path = self.skills_dir / skill_name / file_path

        if not full_path.exists():
            # 尝试列出可用文件
            skill_path = self.skills_dir / skill_name
            if skill_path.exists():
                files = [str(f.relative_to(skill_path)) for f in skill_path.rglob("*") if f.is_file()]
                return {
                    "error": f"文件不存在: {file_path}",
                    "available_files": files[:20]  # 限制数量
                }
            else:
                return {"error": f"技能目录不存在: {skill_name}"}

        try:
            content = full_path.read_text(encoding="utf-8")
            return {
                "content": content,
                "path": str(full_path),
                "skill_name": skill_name,
                "file_path": file_path
            }
        except Exception as e:
            return {"error": f"读取失败: {str(e)}"}

    def list_files(self, skill_name: str, subdir: str = "") -> Dict[str, Any]:
        """列出技能目录下的文件

        Args:
            skill_name: 技能名称
            subdir: 子目录（可选）

        Returns:
            文件列表或错误信息
        """
        skill_path = self.skills_dir / skill_name
        if subdir:
            skill_path = skill_path / subdir

        if not skill_path.exists():
            return {"error": f"目录不存在: {skill_path}"}

        files = []
        dirs = []
        for item in skill_path.iterdir():
            if item.is_file():
                files.append(item.name)
            elif item.is_dir() and not item.name.startswith("."):
                dirs.append(item.name)

        return {
            "skill_name": skill_name,
            "subdir": subdir or "(root)",
            "files": sorted(files),
            "directories": sorted(dirs)
        }
