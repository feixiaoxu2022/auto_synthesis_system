#!/usr/bin/env python3
"""
MCP Agent执行器 - 连接MCP服务器并执行任务
"""
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional
import requests

logger = logging.getLogger(__name__)


class MCPAgent:
    """MCP Agent - 通过LLM调用MCP工具完成任务"""

    def __init__(
        self,
        mcp_client,
        model: str,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        max_turns: int = 30,
        temperature: float = 0.0
    ):
        """
        初始化Agent

        Args:
            mcp_client: MCPClient实例
            model: 模型名称（如gpt-4、claude-3-5-sonnet-20241022）
            base_url: API基础URL（可选）
            api_key: API密钥
            max_turns: 最大对话轮数
            temperature: 采样温度
        """
        self.mcp_client = mcp_client
        self.model = model
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.max_turns = max_turns
        self.temperature = temperature
        self.tools = []
        self._load_tools()

    def _load_tools(self):
        """从MCP服务器加载工具列表并转换为OpenAI格式"""
        mcp_tools = self.mcp_client.list_tools()
        logger.info(f"从MCP服务器加载了 {len(mcp_tools)} 个工具")

        for tool in mcp_tools:
            # MCP工具转OpenAI工具格式
            openai_tool = {
                "type": "function",
                "function": {
                    "name": tool.get("name", ""),
                    "description": tool.get("description", ""),
                    "parameters": tool.get("inputSchema", {
                        "type": "object",
                        "properties": {},
                        "required": []
                    })
                }
            }
            self.tools.append(openai_tool)

    def _call_llm(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """调用LLM API，支持429/5xx重试"""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
        }

        # 添加工具定义
        if self.tools:
            payload["tools"] = self.tools
            payload["tool_choice"] = "auto"

        # 重试配置
        max_retries = 3
        base_delay = 1.0  # 初始延迟1秒

        for attempt in range(max_retries):
            try:
                response = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=120
                )
                response.raise_for_status()
                return response.json()

            except requests.exceptions.HTTPError as e:
                status_code = e.response.status_code if e.response else None

                # 提取响应体错误详情
                error_detail = ""
                if e.response:
                    try:
                        error_detail = e.response.text[:500]  # 限制长度避免日志过长
                    except:
                        pass

                # 429 Too Many Requests 或 5xx 服务器错误可重试
                if status_code in [429, 500, 502, 503, 504]:
                    if attempt < max_retries - 1:
                        # 计算退避时间
                        retry_after = None
                        if e.response and 'Retry-After' in e.response.headers:
                            try:
                                retry_after = int(e.response.headers['Retry-After'])
                            except ValueError:
                                pass

                        delay = retry_after if retry_after else base_delay * (2 ** attempt)
                        logger.warning(f"LLM API返回{status_code}，{delay:.1f}秒后重试 (第{attempt + 1}/{max_retries}次)")
                        if error_detail:
                            logger.debug(f"响应详情: {error_detail}")
                        time.sleep(delay)
                        continue
                    else:
                        # 最后一次重试也失败
                        logger.error(f"LLM API调用失败(已重试{max_retries}次): HTTP {status_code} - {e}")
                        if error_detail:
                            logger.error(f"响应详情: {error_detail}")
                        raise

                # 其他HTTP错误（不可重试），直接抛出
                logger.error(f"LLM API调用失败(不可重试): HTTP {status_code} - {e}")
                if error_detail:
                    logger.error(f"响应详情: {error_detail}")
                raise

            except Exception as e:
                # 非HTTP错误（网络问题等）
                logger.error(f"LLM API调用失败(网络错误): {e}")
                import traceback
                logger.debug(f"异常栈:\n{traceback.format_exc()}")
                raise

    def solve(self, query: str, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        """
        执行任务

        Args:
            query: 用户查询
            system_prompt: 系统提示词

        Returns:
            执行结果，包含:
            - response: Agent最终回复
            - tool_call_list: 工具调用列表
            - conversation_history: 对话历史
            - execution_status: 执行状态（success/error）
        """
        # 初始化消息列表
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": query})

        # 完整的对话轨迹（包含system和user）
        trajectory = []
        if system_prompt:
            trajectory.append({"role": "system", "content": system_prompt})
        trajectory.append({"role": "user", "content": query})

        # 工具调用日志（便捷查看）
        tool_call_list = []
        final_response = ""

        try:
            for turn in range(self.max_turns):
                logger.info(f"Turn {turn + 1}/{self.max_turns}")

                # 调用LLM
                llm_response = self._call_llm(messages)
                choice = llm_response.get("choices", [{}])[0]
                message = choice.get("message", {})

                # 记录到trajectory
                assistant_msg = {
                    "role": "assistant",
                    "content": message.get("content")
                }
                if message.get("tool_calls"):
                    assistant_msg["tool_calls"] = message.get("tool_calls")
                trajectory.append(assistant_msg)

                # 检查是否有工具调用
                tool_calls = message.get("tool_calls")
                if not tool_calls:
                    # 没有工具调用，任务完成
                    final_response = message.get("content", "")
                    logger.info(f"任务完成，最终回复: {final_response[:100]}...")
                    break

                # 处理工具调用
                messages.append(message)  # 添加assistant消息到历史

                for tool_call in tool_calls:
                    tool_id = tool_call.get("id", "")
                    function = tool_call.get("function", {})
                    tool_name = function.get("name", "")
                    arguments_str = function.get("arguments", "{}")

                    try:
                        arguments = json.loads(arguments_str)
                    except json.JSONDecodeError:
                        arguments = {}
                        logger.warning(f"工具参数解析失败: {arguments_str}")

                    logger.info(f"调用工具: {tool_name}({arguments})")

                    # 通过MCP客户端调用工具
                    tool_result = self.mcp_client.call_tool(tool_name, arguments)

                    logger.info(f"工具返回: {tool_name} -> {json.dumps(tool_result, ensure_ascii=False)[:200]}...")

                    # 记录工具调用（拆分server_name和name）
                    if "__" in tool_name:
                        server_name, pure_tool_name = tool_name.split("__", 1)
                    else:
                        server_name = None
                        pure_tool_name = tool_name

                    tool_call_list.append({
                        "server_name": server_name,
                        "name": pure_tool_name,
                        "arguments": json.dumps(arguments, ensure_ascii=False),
                        "result": json.dumps(tool_result, ensure_ascii=False)
                    })

                    # 添加工具结果到消息历史
                    tool_message = {
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "content": json.dumps(tool_result, ensure_ascii=False)
                    }
                    messages.append(tool_message)

                    # 记录到trajectory
                    trajectory.append(tool_message)

                # 如果达到最大轮数
                if turn == self.max_turns - 1:
                    logger.warning(f"达到最大轮数 {self.max_turns}，强制结束")
                    final_response = "任务未完成：达到最大推理轮数限制"

            return {
                "response": final_response,
                "conversation_history": trajectory,
                "tool_call_list": tool_call_list,
                "execution_status": "success"
            }

        except Exception as e:
            logger.error(f"执行失败: {e}")
            return {
                "response": f"执行错误: {str(e)}",
                "conversation_history": trajectory,
                "tool_call_list": tool_call_list,
                "execution_status": "error",
                "error": str(e)
            }
