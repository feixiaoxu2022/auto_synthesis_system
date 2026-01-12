import json
import os
import shlex
import signal
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Union


def _load_mcpservers(config_path: Union[str, Path]) -> Dict[str, Dict[str, Union[str, List[str]]]]:
    """
    加载 mcpservers.json 或 mcpservers.jsonl 配置。
    期望结构：{"mcpServers": { name: {"command": "python", "args": ["...py", ...] }, ... }}
    """
    p = Path(config_path)
    if not p.exists():
        raise FileNotFoundError(f"找不到 mcpservers 配置: {p}")

    # 支持 .json 与 .jsonl（兼容某些场景的命名）
    with open(p, "r", encoding="utf-8") as f:
        text = f.read().strip()
        try:
            cfg = json.loads(text)
        except json.JSONDecodeError:
            # 兼容极端情况：jsonl 中只有一行对象
            lines = [ln for ln in text.splitlines() if ln.strip()]
            if len(lines) == 1:
                cfg = json.loads(lines[0])
            else:
                raise

    servers = cfg.get("mcpServers") or {}
    if not isinstance(servers, dict) or not servers:
        raise ValueError("mcpServers 配置为空或格式不正确")
    return servers


@dataclass
class LaunchedServer:
    name: str
    popen: subprocess.Popen


@dataclass
class ServerLauncher:
    """
    读取并启动场景下的 MCP 服务进程（发布规范：env/servers.json）。

    - Canonical: release/scenarios/<scenario>/env/servers.json
    - 自动注入环境变量 MCP_ENV_DIR 指向环境目录，
      服务代码可通过 os.environ['MCP_ENV_DIR'] 访问。
    - 负责优雅停止子进程。
    """

    scenario_dir: Union[str, Path]
    platform_dir: Optional[Union[str, Path]] = None
    env: Optional[Dict[str, str]] = None
    processes: List[LaunchedServer] = field(default_factory=list)

    def __post_init__(self):
        self.scenario_dir = Path(self.scenario_dir)
        if self.platform_dir:
            self.platform_dir = Path(self.platform_dir)
        else:
            self.platform_dir = self.scenario_dir / "env"
            if not self.platform_dir.exists():
                raise FileNotFoundError(
                    f"未找到环境目录 'env'：{self.scenario_dir}"
                )

    def _find_config_file(self) -> Path:
        # 优先 json，其次 jsonl（两种在不同场景中均有出现）
        for fname in ("servers.json", "servers.jsonl", "mcpservers.json", "mcpservers.jsonl"):
            p = self.platform_dir / fname
            if p.exists():
                return p
        raise FileNotFoundError(f"未找到 servers.json(.l)/mcpservers.json(.l) 于 {self.platform_dir}")

    def start(self) -> List[LaunchedServer]:
        cfg_path = self._find_config_file()
        servers = _load_mcpservers(cfg_path)

        # 基础环境
        base_env = os.environ.copy()
        base_env["MCP_ENV_DIR"] = str(self.platform_dir)
        if self.env:
            base_env.update(self.env)

        launched: List[LaunchedServer] = []
        for name, spec in servers.items():
            cmd = spec.get("command")
            args = spec.get("args") or []
            if not isinstance(cmd, str) or not isinstance(args, list):
                raise ValueError(f"非法 server 配置: {name} -> {spec}")

            # 替换args中的环境变量占位符（${VAR}格式）
            def replace_env_placeholders(text: str, env: dict) -> str:
                """替换字符串中的${VAR}格式占位符"""
                import re
                def replacer(match):
                    var_name = match.group(1)
                    return env.get(var_name, match.group(0))  # 如果环境变量不存在，保持原样
                return re.sub(r'\$\{([^}]+)\}', replacer, text)

            # 对args中的每个参数进行占位符替换
            replaced_args = [replace_env_placeholders(str(a), base_env) for a in args]

            # 组装命令
            full_cmd = [cmd] + replaced_args
            pop = subprocess.Popen(
                full_cmd,
                cwd=str(self.platform_dir),
                env=base_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            launched.append(LaunchedServer(name=name, popen=pop))
        self.processes = launched
        return launched

    def stop(self):
        for proc in self.processes:
            try:
                if proc.popen.poll() is None:
                    proc.popen.terminate()
                    try:
                        proc.popen.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.popen.kill()
            except Exception:
                pass
        self.processes = []
