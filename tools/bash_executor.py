"""
Shell执行工具 - 基于Wenning实现适配

安全受限的shell命令执行
"""
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Dict, Any, Optional, Set


class BashExecutor:
    """安全受限的Shell执行工具"""

    name = "bash"
    description = (
        "执行shell命令（安全受限）。"
        "适用：批量文件操作、快速查找（find/grep）、管道处理、系统工具调用。"
        "禁止：rm、sudo、pip install、ssh等危险命令。"
    )

    # 危险命令模式
    DANGEROUS_PATTERNS = [
        # 基础危险命令
        r"\bsudo\b",
        r"\brm\s+-rf\b",  # 只禁止rm -rf，允许简单rm
        r"\bchmod\b",
        r"\bchown\b",
        r"\bmkfs\b",
        r"\bmount\b",
        r"\bumount\b",
        r"\bshutdown\b|\breboot\b",
        r"\bscp\b|\bssh\b",
        # 包管理命令
        r"\bpip\s+install\b",
        r"\bpip3\s+install\b",
        r"\bconda\s+install\b",
        r"\bnpm\s+install\b",
        r"\byarn\s+(add|install)\b",
        r"\bapt-get\s+install\b",
        r"\byum\s+install\b",
        r"\bbrew\s+install\b",
    ]

    def __init__(self, work_dir: Path, timeout: int = 120):
        self.work_dir = work_dir
        self.timeout = timeout
        self.work_dir.mkdir(parents=True, exist_ok=True)

    def _is_dangerous(self, cmd: str) -> Optional[str]:
        """检查命令是否包含危险模式"""
        for pattern in self.DANGEROUS_PATTERNS:
            if re.search(pattern, cmd, re.IGNORECASE):
                return pattern

        # 禁止向上级/绝对路径进行重定向
        if any(tok in cmd for tok in [">>", ">", "2>"]):
            if "../" in cmd or cmd.count("/") > 0 and cmd.split(">")[-1].strip().startswith("/"):
                return "redirect-outside-cwd"

        # 禁止mv到上级
        if re.search(r"\bmv\b[^\n]*\.\./", cmd):
            return "mv-parent"

        return None

    def execute(self, command: str, timeout: int = None) -> Dict[str, Any]:
        """执行shell命令"""
        if not command or not command.strip():
            return {"error": "缺少command参数"}

        cmd = command.strip()
        timeout = timeout or self.timeout

        # 安全检查
        danger = self._is_dangerous(cmd)
        if danger:
            return {"error": f"命令包含受限模式: {danger}"}

        # 记录执行前的文件
        try:
            pre_files: Set[str] = {p.name for p in self.work_dir.iterdir() if p.is_file()}
        except Exception:
            pre_files = set()

        start_ns = time.time_ns()

        try:
            result = subprocess.run(
                ["bash", "-c", cmd],
                cwd=str(self.work_dir),
                capture_output=True,
                text=True,
                timeout=timeout,
                env={**os.environ}
            )
        except subprocess.TimeoutExpired:
            return {"error": f"命令执行超时（限制{timeout}s）"}
        except Exception as e:
            return {"error": f"执行失败: {str(e)}"}

        # 检测新生成的文件
        try:
            post_paths = [p for p in self.work_dir.iterdir() if p.is_file()]
            post_files = {p.name for p in post_paths}
            # 新文件 = 执行后存在但执行前不存在
            new_files_set = post_files - pre_files
            # 修改过的文件 = 修改时间在执行开始之后
            changed = [
                p.name for p in post_paths
                if getattr(p.stat(), 'st_mtime_ns', int(p.stat().st_mtime * 1e9)) >= (start_ns - 5_000_000)
            ]
            generated_files = sorted(list({*new_files_set, *set(changed)}))
        except Exception:
            generated_files = []

        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
            "work_dir": str(self.work_dir),
            "generated_files": generated_files
        }
