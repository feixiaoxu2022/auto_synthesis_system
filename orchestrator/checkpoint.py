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
    state: str
    user_requirement: str
    scenario_name: str

    # 产物
    design_artifacts: Dict[str, str]
    execution_artifacts: Dict[str, str]

    # Step计数
    init_iterations: int
    execute_iterations: int

    # Context
    current_context: Dict[str, Any]

    # Agent 的 messages（用于恢复对话）
    init_agent_messages: Optional[list] = None
    execute_agent_messages: Optional[list] = None

    # Agent 的内部状态（用于恢复标志位等）
    init_agent_state: Optional[Dict[str, Any]] = None
    execute_agent_state: Optional[Dict[str, Any]] = None


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
        init_messages = None
        execute_messages = None
        init_state = None
        execute_state = None

        if orchestrator.init_agent and hasattr(orchestrator.init_agent, '_conversation_history'):
            init_messages = self._serialize_messages(orchestrator.init_agent._conversation_history)
            # 保存InitAgent的内部状态
            init_state = {
                "_design_confirmed": getattr(orchestrator.init_agent, '_design_confirmed', False),
                "_design_files_complete": getattr(orchestrator.init_agent, '_design_files_complete', False),
            }

        if orchestrator.execute_agent and hasattr(orchestrator.execute_agent, '_conversation_history'):
            execute_messages = self._serialize_messages(orchestrator.execute_agent._conversation_history)
            # 保存ExecuteAgent的内部状态
            execute_state = {
                "_need_layer1_fix": getattr(orchestrator.execute_agent, '_need_layer1_fix', False),
                "_layer1_context": getattr(orchestrator.execute_agent, '_layer1_context', {}),
                "_samples_validation_reminded": getattr(orchestrator.execute_agent, '_samples_validation_reminded', False),
            }

        checkpoint = Checkpoint(
            checkpoint_id=self._current_checkpoint_id,
            created_at=datetime.now().isoformat(),
            state=orchestrator.state.value,
            user_requirement=orchestrator.user_requirement,
            scenario_name=orchestrator.scenario_name,
            design_artifacts=orchestrator.design_artifacts,
            execution_artifacts=orchestrator.execution_artifacts,
            init_iterations=orchestrator.init_iterations,
            execute_iterations=orchestrator.execute_iterations,
            current_context=orchestrator.current_context,
            init_agent_messages=init_messages,
            execute_agent_messages=execute_messages,
            init_agent_state=init_state,
            execute_agent_state=execute_state,
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
        data.setdefault("init_agent_state", None)
        data.setdefault("execute_agent_state", None)

        self._current_checkpoint_id = data.get("checkpoint_id")
        return Checkpoint(**data)

    def restore(self, orchestrator, checkpoint: Checkpoint):
        """
        恢复 orchestrator 状态

        Args:
            orchestrator: Orchestrator 实例
            checkpoint: Checkpoint 数据
        """
        from .orchestrator import AgentPhase

        # 状态映射（兼容旧版本checkpoint）
        state_mapping = {
            "init": "init",
            "init_phase": "init",
            "execute": "execute",
            "execute_phase": "execute",
            # 旧状态映射到合理的默认值
            "failed": "execute",  # 失败通常发生在execute阶段
            "completed": "execute",
            "init_hitl": "init",
            "layer1_hitl": "init",
            "need_user_input": "execute",
        }

        state_value = checkpoint.state
        if state_value not in [e.value for e in AgentPhase]:
            # 使用映射表转换
            mapped_state = state_mapping.get(state_value, "execute")
            print(f"[Checkpoint] 旧状态 '{state_value}' 映射到 '{mapped_state}'")
            state_value = mapped_state

        orchestrator.state = AgentPhase(state_value)
        orchestrator.user_requirement = checkpoint.user_requirement
        orchestrator.scenario_name = checkpoint.scenario_name
        orchestrator.design_artifacts = checkpoint.design_artifacts
        orchestrator.execution_artifacts = checkpoint.execution_artifacts
        orchestrator.init_iterations = checkpoint.init_iterations
        orchestrator.execute_iterations = checkpoint.execute_iterations
        orchestrator.current_context = checkpoint.current_context

        # 恢复 agent 的对话历史
        if checkpoint.init_agent_messages and orchestrator.init_agent:
            orchestrator.init_agent._conversation_history = checkpoint.init_agent_messages

        if checkpoint.execute_agent_messages and orchestrator.execute_agent:
            orchestrator.execute_agent._conversation_history = checkpoint.execute_agent_messages

        # 恢复 agent 的内部状态
        if checkpoint.init_agent_state and orchestrator.init_agent:
            for key, value in checkpoint.init_agent_state.items():
                setattr(orchestrator.init_agent, key, value)

        if checkpoint.execute_agent_state and orchestrator.execute_agent:
            for key, value in checkpoint.execute_agent_state.items():
                setattr(orchestrator.execute_agent, key, value)

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
                        "state": data.get("state"),
                        "requirement": data.get("user_requirement", ""),
                        "scenario_name": data.get("scenario_name", ""),
                        "init_iterations": data.get("init_iterations", 0),
                        "execute_iterations": data.get("execute_iterations", 0),
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
