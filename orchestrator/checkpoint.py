"""
Checkpoint Manager - 状态持久化，支持 Resume
"""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict


@dataclass
class Checkpoint:
    """Checkpoint 数据结构"""
    # 基本信息
    checkpoint_id: str
    created_at: str

    # Orchestrator 状态
    user_requirement: str
    scenario_name: str

    # 产物
    artifacts: Dict[str, str]

    # 迭代计数
    iterations: int

    # Agent 的 messages（用于恢复对话）
    agent_messages: Optional[list] = None

    # Agent 的内部状态（用于恢复标志位等）
    agent_state: Optional[Dict[str, Any]] = None


class CheckpointManager:
    """
    Checkpoint 管理器

    功能：
    - 自动保存状态
    - 恢复到最近的 checkpoint
    - 列出历史 checkpoint
    """

    def __init__(self, checkpoint_dir: str = "checkpoints"):
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self._current_checkpoint_id: Optional[str] = None

    def _generate_id(self) -> str:
        """生成 checkpoint ID"""
        return datetime.now().strftime("%Y%m%d_%H%M%S")

    def _serialize_messages(self, messages):
        """
        将消息列表转换为可JSON序列化的格式

        处理 Anthropic SDK 的对象（TextBlock, ToolUseBlock等）
        """
        if not messages:
            return None

        serialized = []
        for msg in messages:
            if isinstance(msg, dict):
                # 已经是字典，检查content
                serialized_msg = {"role": msg["role"]}
                content = msg.get("content")

                if isinstance(content, str):
                    serialized_msg["content"] = content
                elif isinstance(content, list):
                    # 处理content列表中的对象
                    serialized_content = []
                    for block in content:
                        if isinstance(block, dict):
                            serialized_content.append(block)
                        elif hasattr(block, 'model_dump'):
                            # Pydantic对象，使用model_dump
                            serialized_content.append(block.model_dump())
                        elif hasattr(block, '__dict__'):
                            # 普通对象，转换为字典
                            serialized_content.append(vars(block))
                        else:
                            # 其他情况，尝试直接使用
                            serialized_content.append(block)
                    serialized_msg["content"] = serialized_content
                else:
                    serialized_msg["content"] = content

                serialized.append(serialized_msg)
            else:
                # 非字典消息，尝试转换
                serialized.append({"error": "unexpected message type"})

        return serialized

    def save(self, orchestrator, force_new: bool = False) -> str:
        """
        保存 checkpoint

        Args:
            orchestrator: Orchestrator 实例
            force_new: 是否强制创建新 checkpoint（否则覆盖当前）

        Returns:
            checkpoint_id
        """
        if force_new or self._current_checkpoint_id is None:
            self._current_checkpoint_id = self._generate_id()

        # 获取 agent 的对话历史（序列化为可JSON保存的格式）
        agent_messages = None
        agent_state = None

        if orchestrator.agent and hasattr(orchestrator.agent, '_conversation_history'):
            agent_messages = self._serialize_messages(orchestrator.agent._conversation_history)

            # 保存Agent的内部状态（通用，从ExecuteAgent继承）
            agent_state = {
                "_samples_validation_reminded": getattr(orchestrator.agent, '_samples_validation_reminded', False),
            }

        checkpoint = Checkpoint(
            checkpoint_id=self._current_checkpoint_id,
            created_at=datetime.now().isoformat(),
            user_requirement=orchestrator.user_requirement,
            scenario_name=orchestrator.scenario_name,
            artifacts=orchestrator.artifacts,
            iterations=orchestrator.iterations,
            agent_messages=agent_messages,
            agent_state=agent_state,
        )

        # 保存到文件
        filepath = self.checkpoint_dir / f"{self._current_checkpoint_id}.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(asdict(checkpoint), f, ensure_ascii=False, indent=2)

        # 同时保存为 latest
        latest_path = self.checkpoint_dir / "latest.json"
        with open(latest_path, "w", encoding="utf-8") as f:
            json.dump(asdict(checkpoint), f, ensure_ascii=False, indent=2)

        return self._current_checkpoint_id

    def load(self, checkpoint_id: Optional[str] = None) -> Optional[Checkpoint]:
        """
        加载 checkpoint

        Args:
            checkpoint_id: 指定 ID，None 则加载 latest

        Returns:
            Checkpoint 或 None
        """
        if checkpoint_id:
            filepath = self.checkpoint_dir / f"{checkpoint_id}.json"
        else:
            filepath = self.checkpoint_dir / "latest.json"

        if not filepath.exists():
            return None

        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 向后兼容：补充新增字段的默认值
        data.setdefault("agent_state", None)

        self._current_checkpoint_id = data.get("checkpoint_id")
        return Checkpoint(**data)

    def restore(self, orchestrator, checkpoint: Checkpoint):
        """
        恢复 orchestrator 状态

        Args:
            orchestrator: Orchestrator 实例
            checkpoint: Checkpoint 数据
        """
        orchestrator.user_requirement = checkpoint.user_requirement
        orchestrator.scenario_name = checkpoint.scenario_name
        orchestrator.artifacts = checkpoint.artifacts
        orchestrator.iterations = checkpoint.iterations

        # 恢复 agent 的对话历史
        if checkpoint.agent_messages and orchestrator.agent:
            orchestrator.agent._conversation_history = checkpoint.agent_messages

        # 恢复 agent 的内部状态
        if checkpoint.agent_state and orchestrator.agent:
            for key, value in checkpoint.agent_state.items():
                setattr(orchestrator.agent, key, value)

    def list_checkpoints(self) -> list:
        """列出所有 checkpoint"""
        checkpoints = []
        for f in self.checkpoint_dir.glob("*.json"):
            if f.name == "latest.json":
                continue
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                    checkpoints.append({
                        "id": data.get("checkpoint_id"),
                        "created_at": data.get("created_at"),
                        "requirement": data.get("user_requirement", ""),
                        "scenario_name": data.get("scenario_name", ""),
                        "iterations": data.get("iterations", 0),
                    })
            except Exception:
                pass

        # 按时间倒序
        checkpoints.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return checkpoints

    def get_latest_id(self) -> Optional[str]:
        """获取最近的 checkpoint ID"""
        latest_path = self.checkpoint_dir / "latest.json"
        if not latest_path.exists():
            return None

        with open(latest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("checkpoint_id")
