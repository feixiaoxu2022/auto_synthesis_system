import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any


@dataclass
class ModelConfig:
    model: Optional[str] = None
    provider: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    temperature: float = 0.0
    timeout: Optional[int] = None
    extra_headers: Optional[Dict[str, str]] = None
    max_tokens: Optional[int] = None
    enable_request_logging: Optional[bool] = None


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        txt = path.read_text(encoding="utf-8").strip()
        return json.loads(txt) if txt else {}
    except Exception:
        return {}


def load_model_config(kind: str = "judge", explicit_path: Optional[str] = None) -> ModelConfig:
    """
    读取模型配置（优先级从高到低）：
    1) 显式路径（JSON）
    2) 环境变量（BENCH_CHECK_MODEL/BASE_URL/API_KEY/PROVIDER 等）
    3) 就近文件：benchkit/model_config.json（与本模块同目录）
    4) 用户级：~/.mcp-benchmark/model_config.json

    字段：model + provider；也兼容自定义 base_url + api_key。
    """
    cfg: Dict[str, Any] = {}

    # 1) 显式路径
    if explicit_path:
        p = Path(explicit_path).expanduser()
        if p.exists():
            cfg.update(_read_json(p))

    # 2) 环境变量（judge vs agent vs simulator），兼容两套命名
    def _to_bool(s: Optional[str]) -> Optional[bool]:
        if s is None:
            return None
        v = str(s).strip().lower()
        if v in ("1", "true", "yes", "y", "on"):
            return True
        if v in ("0", "false", "no", "n", "off"):
            return False
        return None
    if kind == "judge":
        env_cfg = {
            "model": os.getenv("BENCH_CHECK_MODEL"),
            "provider": os.getenv("BENCH_CHECK_PROVIDER"),
            "base_url": os.getenv("BENCH_CHECK_BASE_URL"),
            "api_key": os.getenv("BENCH_CHECK_API_KEY"),
            "temperature": os.getenv("BENCH_CHECK_TEMPERATURE"),
            "timeout": os.getenv("BENCH_CHECK_TIMEOUT_MS"),
            "max_tokens": os.getenv("BENCH_CHECK_MAX_TOKENS"),
            "enable_request_logging": os.getenv("BENCH_CHECK_ENABLE_REQUEST_LOGGING"),
        }
    elif kind == "agent":
        env_cfg = {
            "model": os.getenv("BENCH_AGENT_MODEL"),
            "provider": os.getenv("BENCH_AGENT_PROVIDER"),
            "base_url": os.getenv("BENCH_AGENT_BASE_URL"),
            "api_key": os.getenv("BENCH_AGENT_API_KEY"),
            "temperature": os.getenv("BENCH_AGENT_TEMPERATURE"),
            "timeout": os.getenv("BENCH_AGENT_TIMEOUT_MS"),
            "max_tokens": os.getenv("BENCH_AGENT_MAX_TOKENS"),
            "enable_request_logging": os.getenv("BENCH_AGENT_ENABLE_REQUEST_LOGGING"),
        }
    elif kind == "simulator":
        env_cfg = {
            "model": os.getenv("BENCH_SIM_MODEL"),
            "provider": os.getenv("BENCH_SIM_PROVIDER"),
            "base_url": os.getenv("BENCH_SIM_BASE_URL"),
            "api_key": os.getenv("BENCH_SIM_API_KEY"),
            "temperature": os.getenv("BENCH_SIM_TEMPERATURE"),
            "timeout": os.getenv("BENCH_SIM_TIMEOUT_MS"),
            "max_tokens": os.getenv("BENCH_SIM_MAX_TOKENS"),
            "enable_request_logging": os.getenv("BENCH_SIM_ENABLE_REQUEST_LOGGING"),
        }
    else:
        env_cfg = {}
    # 仅注入非空
    for k, v in env_cfg.items():
        if v is None:
            continue
        if k in ("temperature", "timeout", "max_tokens"):
            try:
                if k == "temperature":
                    cfg[k] = float(v)
                else:
                    cfg[k] = int(v)
            except Exception:
                continue
        elif k == "enable_request_logging":
            b = _to_bool(v)
            if b is not None:
                cfg[k] = b
        else:
            cfg[k] = v

    # 3) 本地 benchkit 目录
    here = Path(__file__).resolve().parent
    local_cfg = here / "model_config.json"
    if local_cfg.exists():
        base_all = _read_json(local_cfg)
        # 支持扁平或 namespaced 结构
        base = base_all.get(kind, base_all) if isinstance(base_all, dict) else {}
        for k, v in (base or {}).items():
            if k in ("judge", "agent"):
                continue
            cfg.setdefault(k, v)

    # 4) 用户级
    home_cfg = Path.home() / ".mcp-benchmark" / "model_config.json"
    if home_cfg.exists():
        base_all = _read_json(home_cfg)
        base = base_all.get(kind, base_all) if isinstance(base_all, dict) else {}
        for k, v in (base or {}).items():
            if k in ("judge", "agent"):
                continue
            cfg.setdefault(k, v)

    return ModelConfig(
        model=cfg.get("model"),
        provider=cfg.get("provider"),
        base_url=cfg.get("base_url"),
        api_key=cfg.get("api_key"),
        temperature=float(cfg.get("temperature", 0.0) or 0.0),
        timeout=int(cfg.get("timeout", 0) or 0) or None,
        extra_headers=cfg.get("extra_headers") if isinstance(cfg.get("extra_headers"), dict) else None,
        max_tokens=int(cfg.get("max_tokens", 0) or 0) or None,
        enable_request_logging=cfg.get("enable_request_logging"),
    )
