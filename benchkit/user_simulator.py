import os
from dataclasses import dataclass
from typing import Dict, List, Any, Optional

try:
    from litellm import completion
except Exception:  # pragma: no cover
    completion = None  # type: ignore


from .model_config import load_model_config


STOP_DEFAULT = "###STOP###"


@dataclass
class SimulatorSpec:
    prompt: str
    style: str = "reactive"  # reactive | proactive | strict_minimal
    stop_condition: str = STOP_DEFAULT
    max_rounds: int = 8


class LLMUserSimulator:
    """
    多轮用户模拟器（LLM驱动）。

    用法：
    - sim = LLMUserSimulator()
    - first = sim.reset(system, user_input, spec)
    - next = sim.step(agent_message)
    - 若返回 STOP 则结束。
    """

    def __init__(self, model: Optional[str] = None, provider: Optional[str] = None):
        mc = load_model_config(kind="simulator")
        self.model = model or mc.model
        self.provider = provider or mc.provider
        self.messages: List[Dict[str, Any]] = []
        self.spec: Optional[SimulatorSpec] = None
        self.round = 0

    def _build_system(self, system_prompt: str, spec: SimulatorSpec) -> str:
        base = [
            "You are the USER in a conversation with an Agent.",
            "Follow the behavior instructions strictly.",
        ]
        # 行为规范
        if spec.style == "reactive":
            base.append("Only provide information when asked. Do not reveal everything at once.")
        elif spec.style == "strict_minimal":
            base.append("Respond in minimal necessary information. Do not add extra details.")
        else:
            base.append("Be cooperative and provide relevant information proactively if needed.")
        base.append("When the task goal is satisfied, output the stop token exactly.")
        base.append(f"Stop token: {spec.stop_condition}")
        # 用户模拟器附加提示
        if spec.prompt:
            base.append("User Simulator Instructions:\n" + spec.prompt)
        # 将场景system放入，帮助模拟器对齐语境
        base.append("Context for the task (agent system prompt):\n" + system_prompt)
        return "\n".join(base)

    def _llm(self, messages: List[Dict[str, Any]]) -> str:
        if completion is None:
            raise RuntimeError("litellm not installed; please pip install litellm")
        res = completion(
            model=self.model,
            custom_llm_provider=self.provider,
            messages=messages,
        )
        msg = res.choices[0].message
        return msg.content

    def reset(self, system_prompt: str, user_input: str, spec_dict: Dict[str, Any]) -> str:
        self.spec = SimulatorSpec(
            prompt=spec_dict.get("prompt", ""),
            style=spec_dict.get("style", "reactive"),
            stop_condition=spec_dict.get("stop_condition", STOP_DEFAULT),
            max_rounds=int(spec_dict.get("max_rounds", 8) or 8),
        )
        sys_text = self._build_system(system_prompt, self.spec)
        self.messages = [
            {"role": "system", "content": sys_text},
            {"role": "user", "content": user_input},
        ]
        self.round = 0
        return self._llm(self.messages)

    def step(self, agent_message: str) -> str:
        if not self.spec:
            raise RuntimeError("Simulator not initialized; call reset() first")
        if self.round >= self.spec.max_rounds:
            return self.spec.stop_condition
        self.messages.append({"role": "assistant", "content": agent_message})
        self.messages.append({"role": "user", "content": "(continue)"})
        self.round += 1
        out = self._llm(self.messages)
        return out

