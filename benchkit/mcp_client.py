#!/usr/bin/env python3
"""
MCP客户端 - 通过stdio JSON-RPC连接MCP服务器
"""
import json
import logging
import os
import select
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import jsonschema
    JSONSCHEMA_AVAILABLE = True
except ImportError:
    JSONSCHEMA_AVAILABLE = False

logger = logging.getLogger(__name__)


class MCPClient:
    """MCP服务器客户端 - stdio JSON-RPC通信"""

    def __init__(self, command: str, args: List[str], cwd: Optional[Path] = None, env: Optional[Dict[str, str]] = None):
        self.command = command
        self.args = args
        self.cwd = str(cwd) if cwd else None
        self.env = os.environ.copy()
        if env:
            self.env.update(env)
        self.p: Optional[subprocess.Popen] = None
        self._id = 0
        self._buf = b""
        self._line_mode = True  # FastMCP默认使用line-delimited模式
        self._tool_schemas: Dict[str, Dict] = {}  # 存储工具的input schema

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def start(self) -> bool:
        """启动MCP服务器并初始化"""
        try:
            logger.debug(f"启动MCP服务器: {self.command} {self.args}, cwd={self.cwd}")
            self.p = subprocess.Popen(
                [self.command] + [str(a) for a in self.args],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False,
                cwd=self.cwd,
                env=self.env,
            )
            # 等待进程启动
            time.sleep(0.5)
            if self.p.poll() is not None:
                stderr = self.p.stderr.read().decode('utf-8', errors='ignore') if self.p.stderr else ""
                logger.error(f"MCP服务器进程异常退出: {stderr}")
                return False

            # 发送initialize请求
            req = {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "mcp-benchmark-agent", "version": "1.0"},
                },
            }
            logger.debug("发送initialize请求")
            resp = self.send_request(req, timeout=8.0)
            if not resp:
                logger.debug("未收到响应，尝试line-delimited模式")
                # 回退到line-delimited模式
                self._line_mode = True
                resp = self.send_request(req, timeout=8.0)
            if resp:
                logger.debug(f"收到初始化响应: {resp}")
            else:
                logger.error("初始化超时，未收到响应")
                # 尝试非阻塞读取stderr查看错误（避免hang住）
                if self.p and self.p.stderr:
                    try:
                        # 使用select检查是否有数据可读（仅非Windows系统）
                        if os.name != "nt":
                            readable, _, _ = select.select([self.p.stderr], [], [], 0.1)
                            if readable:
                                stderr = self.p.stderr.read(1024).decode('utf-8', errors='ignore')
                                if stderr:
                                    logger.error(f"MCP服务器stderr: {stderr}")
                        else:
                            # Windows系统直接跳过，避免阻塞
                            pass
                    except Exception as e:
                        logger.debug(f"读取stderr失败: {e}")

                # 强制终止进程，避免hang住后续流程
                if self.p:
                    try:
                        logger.debug("强制终止超时的MCP服务器进程")
                        self.p.kill()  # 立即kill，不等待
                        self.p.wait(timeout=1.0)
                    except Exception as e:
                        logger.debug(f"终止进程时出错: {e}")
                    finally:
                        self.p = None

                return False

            if not resp.get("result"):
                return False

            # 发送initialized通知（MCP 2024-11-05协议要求）
            logger.debug("发送initialized通知")
            notif = {
                "jsonrpc": "2.0",
                "method": "notifications/initialized"
            }
            self._write_frame(notif)
            time.sleep(0.1)  # 给服务器一点时间处理通知

            return True
        except Exception as e:
            logger.error(f"启动MCP服务器失败: {e}", exc_info=True)
            # 读取stderr查看详细错误
            if self.p and self.p.stderr:
                try:
                    stderr = self.p.stderr.read(4096).decode('utf-8', errors='ignore')
                    if stderr:
                        logger.error(f"MCP服务器stderr: {stderr}")
                except Exception:
                    pass
            return False

    def _read_frame(self, timeout: float) -> Optional[Dict[str, Any]]:
        """读取一个JSON-RPC消息（Content-Length framing）"""
        if not self.p or not self.p.stdout:
            return None
        stdout = self.p.stdout
        deadline = time.time() + timeout
        header_sep_crlf = b"\r\n\r\n"
        header_sep_lf = b"\n\n"

        while time.time() < deadline:
            # line-delimited回退模式
            if self._line_mode:
                if os.name != "nt":
                    r, _, _ = select.select([stdout], [], [], 0.1)
                    if not r:
                        continue
                chunk = stdout.read1(4096) if hasattr(stdout, 'read1') else stdout.read(4096)
                if not chunk:
                    time.sleep(0.02)
                    continue
                self._buf += chunk
                # 处理行
                while True:
                    nl = self._buf.find(b"\n")
                    if nl < 0:
                        break
                    line = self._buf[:nl].strip()
                    self._buf = self._buf[nl+1:]
                    if not line:
                        continue
                    # 尝试从行中提取JSON
                    try:
                        return json.loads(line.decode('utf-8', errors='ignore'))
                    except Exception:
                        try:
                            s = line.decode('utf-8', errors='ignore')
                            start = s.find('{')
                            end = s.rfind('}')
                            if start != -1 and end != -1 and end > start:
                                return json.loads(s[start:end+1])
                        except Exception:
                            continue
                continue

            # Content-Length模式
            sep = header_sep_crlf if header_sep_crlf in self._buf else (header_sep_lf if header_sep_lf in self._buf else None)
            if sep is None:
                if os.name != "nt":
                    r, _, _ = select.select([stdout], [], [], 0.1)
                    if not r:
                        continue
                chunk = stdout.read1(8192) if hasattr(stdout, 'read1') else stdout.read(8192)
                if not chunk:
                    time.sleep(0.05)
                    continue
                self._buf += chunk
                # 清理日志噪音
                low = self._buf.lower()
                cl_pos = low.find(b"content-length:")
                if cl_pos > 0:
                    self._buf = self._buf[cl_pos:]
                continue

            # 解析header
            header, rest = self._buf.split(sep, 1)
            length = None
            for line in header.split(b"\r\n"):
                if line.lower().startswith(b"content-length:"):
                    try:
                        length = int(line.split(b":", 1)[1].strip())
                    except Exception:
                        length = None
                    break
            if length is None:
                idx = self._buf.find(b"Content-Length:", 1)
                self._buf = self._buf[idx:] if idx != -1 else b""
                continue

            # 确保读取完整body
            while len(rest) < length and time.time() < deadline:
                if os.name != "nt":
                    r, _, _ = select.select([stdout], [], [], 0.1)
                    if not r:
                        continue
                chunk = stdout.read1(length - len(rest)) if hasattr(stdout, 'read1') else stdout.read(length - len(rest))
                if not chunk:
                    time.sleep(0.02)
                    continue
                rest += chunk
            if len(rest) < length:
                self._line_mode = True
                continue
            body = rest[:length]
            self._buf = rest[length:]
            try:
                obj = json.loads(body.decode('utf-8', errors='ignore'))
                return obj
            except Exception:
                continue
        return None

    def _write_frame(self, obj: Dict[str, Any]):
        """写入一个JSON-RPC消息"""
        if not self.p or not self.p.stdin:
            return
        payload = json.dumps(obj).encode('utf-8')
        if self._line_mode:
            self.p.stdin.write(payload + b"\n")
        else:
            header = (
                f"Content-Length: {len(payload)}\r\n"
                f"Content-Type: application/json; charset=utf-8\r\n\r\n"
            ).encode('ascii')
            self.p.stdin.write(header + payload)
        self.p.stdin.flush()

    def send_request(self, req: Dict[str, Any], timeout: float = 10.0) -> Optional[Dict[str, Any]]:
        """发送请求并等待响应"""
        req_id = req.get("id")
        self._write_frame(req)
        deadline = time.time() + timeout
        while time.time() < deadline:
            resp = self._read_frame(timeout=deadline - time.time())
            if resp and resp.get("id") == req_id:
                return resp
        return None

    def list_tools(self) -> List[Dict[str, Any]]:
        """获取工具列表"""
        req = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/list",
            "params": {}
        }
        resp = self.send_request(req, timeout=10.0)
        if resp and resp.get("result"):
            tools = resp["result"].get("tools", [])
            # 存储每个工具的schema用于参数验证
            for tool in tools:
                tool_name = tool.get("name", "")
                input_schema = tool.get("inputSchema", {})
                if tool_name and input_schema:
                    self._tool_schemas[tool_name] = input_schema
            return tools
        return []

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """调用工具（增加严格的参数类型验证）"""
        # 严格的参数类型验证（模拟内部平台行为）
        if JSONSCHEMA_AVAILABLE and tool_name in self._tool_schemas:
            schema = self._tool_schemas[tool_name]
            try:
                # 使用jsonschema进行严格验证，不做类型强制转换
                jsonschema.validate(instance=arguments, schema=schema)
            except jsonschema.ValidationError as e:
                # 模拟内部平台的错误格式
                error_msg = f"Input validation error: {e.message}"
                logger.warning(f"参数验证失败 {tool_name}: {error_msg}")
                return {
                    "content": [{
                        "type": "text",
                        "text": error_msg
                    }],
                    "isError": True
                }

        # 参数验证通过，调用工具
        req = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }
        resp = self.send_request(req, timeout=60.0)
        if resp and "result" in resp:
            return resp["result"]
        elif resp and "error" in resp:
            return {"error": resp["error"]}
        return {"error": "No response from MCP server"}

    def stop(self):
        """停止MCP服务器"""
        if self.p:
            self.p.terminate()
            try:
                self.p.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.p.kill()
            self.p = None


class MultiMCPClient:
    """多MCP服务器聚合客户端 - 管理多个MCP服务器并合并工具"""

    def __init__(self):
        self.clients: List[MCPClient] = []
        self._tool_to_client: Dict[str, MCPClient] = {}
        self._server_to_client: Dict[str, MCPClient] = {}
        self._tool_to_server: Dict[str, str] = {}

    def add_client(self, server_name: str, client: MCPClient) -> bool:
        """添加一个MCP客户端

        Args:
            server_name: 服务器名称（如"HotelBooking"、"AirlineBooking"）
            client: MCP客户端实例
        """
        if not client.start():
            return False
        self.clients.append(client)
        self._server_to_client[server_name] = client

        # 构建工具到客户端的映射（包含服务器前缀）
        tools = client.list_tools()
        for tool in tools:
            tool_name = tool.get("name", "")
            if tool_name:
                # 使用带服务器前缀的完整名称
                full_tool_name = f"{server_name}__{tool_name}"
                self._tool_to_client[full_tool_name] = client
                self._tool_to_server[full_tool_name] = server_name
                # 同时保留不带前缀的映射（向后兼容）
                if tool_name not in self._tool_to_client:
                    self._tool_to_client[tool_name] = client
        return True

    def list_tools(self) -> List[Dict[str, Any]]:
        """获取所有MCP服务器的工具列表（合并），工具名包含服务器前缀"""
        all_tools = []
        for server_name, client in self._server_to_client.items():
            tools = client.list_tools()
            for tool in tools:
                # 复制工具信息并添加服务器前缀
                tool_with_prefix = tool.copy()
                original_name = tool.get("name", "")
                if original_name:
                    tool_with_prefix["name"] = f"{server_name}__{original_name}"
                all_tools.append(tool_with_prefix)
        return all_tools

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """调用工具（路由到正确的客户端）

        支持带服务器前缀的工具名（如"HotelBooking.review_list"）和不带前缀的工具名（向后兼容）
        """
        # 先尝试带前缀的工具名
        client = self._tool_to_client.get(tool_name)
        if client:
            # 如果是带前缀的，需要提取原始工具名
            if "__" in tool_name:
                _, original_tool_name = tool_name.split("__", 1)
                return client.call_tool(original_tool_name, arguments)
            else:
                return client.call_tool(tool_name, arguments)

        return {"error": f"Tool '{tool_name}' not found in any MCP server"}

    def stop(self):
        """停止所有MCP服务器"""
        for client in self.clients:
            client.stop()
        self.clients.clear()
        self._tool_to_client.clear()
        self._server_to_client.clear()
        self._tool_to_server.clear()
