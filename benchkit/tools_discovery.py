import ast
import json
import json
import os
import select
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import asyncio


JSONSchema = Dict[str, Any]


def _annotation_to_type_name(node: Optional[ast.AST]) -> Optional[str]:
    if node is None:
        return None
    # Name: str/int/bool/float
    if isinstance(node, ast.Name):
        return node.id
    # Attribute: typing.List, builtins.str
    if isinstance(node, ast.Attribute):
        # return full attribute name if needed
        parts = []
        cur: Optional[ast.AST] = node
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name):
            parts.append(cur.id)
        return ".".join(reversed(parts))
    # Subscript: Optional[T], List[T], Dict[K,V]
    if isinstance(node, ast.Subscript):
        if isinstance(node.value, ast.Name):
            return node.value.id
        if isinstance(node.value, ast.Attribute):
            return node.value.attr
    # Constant string annotations
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _type_name_to_json_schema(type_name: Optional[str]) -> JSONSchema:
    # conservative mapping
    if not type_name:
        return {}
    base = type_name.split(".")[-1].lower()
    if base in ("str", "string"):
        return {"type": "string"}
    if base in ("int", "integer"):
        return {"type": "integer"}
    if base in ("float", "number"):
        return {"type": "number"}
    if base in ("bool", "boolean"):
        return {"type": "boolean"}
    if base in ("list", "tuple", "set"):
        return {"type": "array"}
    if base in ("dict", "mapping"):
        return {"type": "object"}
    if base in ("optional", "union"):
        # leave flexible; specific inner types are not analyzed here
        return {}
    return {}


def _func_params_to_schema(func: ast.FunctionDef) -> Tuple[JSONSchema, List[str]]:
    properties: Dict[str, Any] = {}
    required: List[str] = []

    # defaults align to last N positional args
    pos_args = [arg.arg for arg in func.args.args]
    # exclude self if present
    if pos_args and pos_args[0] == "self":
        pos_args = pos_args[1:]
        args_nodes = func.args.args[1:]
    else:
        args_nodes = func.args.args

    num_defaults = len(func.args.defaults)
    num_pos = len(args_nodes)
    default_start = num_pos - num_defaults if num_defaults <= num_pos else 0

    for idx, arg in enumerate(args_nodes):
        name = arg.arg
        # annotation mapping
        ann = _annotation_to_type_name(arg.annotation)
        js = _type_name_to_json_schema(ann)
        properties[name] = js
        # required if no default
        if idx < default_start:
            required.append(name)

    # kwonly args
    for i, kw in enumerate(func.args.kwonlyargs):
        name = kw.arg
        ann = _annotation_to_type_name(kw.annotation)
        js = _type_name_to_json_schema(ann)
        properties[name] = js
        # kw_defaults aligns one-to-one; None means no default
        if func.args.kw_defaults and func.args.kw_defaults[i] is None:
            required.append(name)

    schema: JSONSchema = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema, required


def _parse_server_tools(py_path: Path) -> Tuple[str, List[Dict[str, Any]]]:
    """Parse a server python file to extract server name and tools via @mcp.tool() decorators."""
    text = py_path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(py_path))

    server_name: Optional[str] = None
    # find mcp = FastMCP(name="...")
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            func = node.value.func
            if isinstance(func, ast.Name) and func.id == "FastMCP" or (
                isinstance(func, ast.Attribute) and func.attr == "FastMCP"
            ):
                for kw in node.value.keywords or []:
                    if kw.arg == "name" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                        server_name = kw.value.value
                        break
        if server_name:
            break
    if not server_name:
        # fallback to filename stem
        server_name = py_path.stem

    tools: List[Dict[str, Any]] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            # look for decorator like @mcp.tool()
            has_tool_decorator = False
            for dec in node.decorator_list:
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) and dec.func.attr == "tool":
                    has_tool_decorator = True
                    break
            if not has_tool_decorator:
                continue
            func_name = node.name
            params_schema, _ = _func_params_to_schema(node)
            fq_name = f"{server_name}.{func_name}"
            tool_info = {
                "server": server_name,
                "type": "function",
                "function": {
                    "name": fq_name,
                    "description": f"{func_name} (auto-discovered)",
                    "parameters": params_schema,
                },
                "short_name": func_name,
            }
            tools.append(tool_info)

    return server_name, tools


def build_aliases(tools_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_fq: Dict[str, Dict[str, str]] = {}
    by_short: Dict[str, List[str]] = {}
    for t in tools_list:
        fn = t.get("function", {})
        fq_name = fn.get("name")
        short = t.get("short_name") or (fq_name.split(".")[-1] if isinstance(fq_name, str) else None)
        server = t.get("server")
        if not isinstance(fq_name, str) or not isinstance(short, str):
            continue
        by_fq[fq_name] = {"server": server or "", "tool": short, "short": short}
        by_short.setdefault(short, []).append(fq_name)
    return {"by_fq": by_fq, "by_short": by_short}


def _read_servers_config(env_dir: Path) -> Optional[Dict[str, Any]]:
    for fn in ("servers.json", "mcpservers.json", "mcpservers.jsonl"):
        p = env_dir / fn
        if p.exists():
            try:
                text = p.read_text(encoding="utf-8").strip()
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    # jsonl 只有一行对象的容错
                    lines = [ln for ln in text.splitlines() if ln.strip()]
                    if len(lines) == 1:
                        return json.loads(lines[0])
            except Exception:
                continue
    return None


class MCPStdioClient:
    def __init__(self, command: str, args: List[str], cwd: Optional[Path] = None, env: Optional[Dict[str, str]] = None):
        self.command = command
        self.args = args or []
        self.cwd = str(cwd) if cwd else None
        self.env = os.environ.copy()
        if env:
            self.env.update(env)
        self.p: Optional[subprocess.Popen] = None
        self._id = 0
        self._buf = b""
        self._line_mode = False

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def start(self) -> bool:
        try:
            self.p = subprocess.Popen(
                [self.command] + [str(a) for a in self.args],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False,  # binary for framing
                cwd=self.cwd,
                env=self.env,
            )
            # initialize
            req = {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "initialize",
                "params": {
                    "capabilities": {},
                    "clientInfo": {"name": "benchkit-tools-discovery", "version": "0.1"},
                },
            }
            resp = self.send_request(req, timeout=8.0)
            if not resp:
                # fallback to line-delimited mode
                self._line_mode = True
                resp = self.send_request(req, timeout=8.0)
            return bool(resp and resp.get("result"))
        except Exception:
            return False

    def _read_frame(self, timeout: float) -> Optional[Dict[str, Any]]:
        """Read one JSON-RPC message using Content-Length framing.
        Ignore any non-protocol bytes until a header is found.
        """
        if not self.p or not self.p.stdout:
            return None
        stdout = self.p.stdout
        deadline = time.time() + timeout
        header_sep_crlf = b"\r\n\r\n"
        header_sep_lf = b"\n\n"
        while time.time() < deadline:
            # line-delimited fallback mode
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
                # process lines
                while True:
                    nl = self._buf.find(b"\n")
                    if nl < 0:
                        break
                    line = self._buf[:nl].strip()
                    self._buf = self._buf[nl+1:]
                    if not line:
                        continue
                    # attempt to extract json object from line even if mixed with logs
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
            # ensure we have a header
            # choose header separator dynamically
            sep = header_sep_crlf if header_sep_crlf in self._buf else (header_sep_lf if header_sep_lf in self._buf else None)
            if sep is None:
                # read more
                if os.name != "nt":
                    r, _, _ = select.select([stdout], [], [], 0.1)
                    if not r:
                        continue
                chunk = stdout.read1(8192) if hasattr(stdout, 'read1') else stdout.read(8192)
                if not chunk:
                    time.sleep(0.05)
                    continue
                # keep only from first Content-Length if present, else append
                self._buf += chunk
                # try to find content-length header start (case-insensitive); if log noise precedes, trim to first occurrence
                low = self._buf.lower()
                cl_pos = low.find(b"content-length:")
                if cl_pos > 0:
                    self._buf = self._buf[cl_pos:]
                continue
            # parse header
            header, rest = self._buf.split(sep, 1)
            # parse content length
            length = None
            for line in header.split(b"\r\n"):
                if line.lower().startswith(b"content-length:"):
                    try:
                        length = int(line.split(b":", 1)[1].strip())
                    except Exception:
                        length = None
                    break
            if length is None:
                # discard until next potential header
                idx = self._buf.find(b"Content-Length:", 1)
                self._buf = self._buf[idx:] if idx != -1 else b""
                continue
            # ensure we have full body
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
                # timeout on body → fallback to line mode
                self._line_mode = True
                continue
            body = rest[:length]
            self._buf = rest[length:]
            try:
                obj = json.loads(body.decode('utf-8', errors='ignore'))
                return obj
            except Exception:
                # malformed json; continue reading next frame
                continue
        return None

    def _write_frame(self, obj: Dict[str, Any]):
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

    def send_request(self, req: Dict[str, Any], timeout: float = 15.0) -> Optional[Dict[str, Any]]:
        if not self.p:
            return None
        try:
            self._write_frame(req)
            deadline = time.time() + timeout
            main: Optional[Dict[str, Any]] = None
            while time.time() < deadline:
                msg = self._read_frame(timeout=max(0.2, deadline - time.time()))
                if not msg:
                    continue
                # ignore notifications or unrelated messages
                if msg.get("id") == req.get("id"):
                    main = msg
                    break
            return main
        except Exception:
            return None

    def list_tools(self) -> List[Dict[str, Any]]:
        req = {"jsonrpc": "2.0", "id": self._next_id(), "method": "tools/list", "params": {}}
        resp = self.send_request(req, timeout=15.0)
        if not resp or "result" not in resp:
            return []
        return resp["result"].get("tools", []) or []

    def stop(self):
        if self.p and self.p.poll() is None:
            try:
                # graceful shutdown if supported
                req = {"jsonrpc": "2.0", "id": self._next_id(), "method": "shutdown", "params": {}}
                self.send_request(req, timeout=0.3)
            except Exception:
                pass
            try:
                self.p.terminate()
                self.p.wait(timeout=1.0)
            except Exception:
                try:
                    self.p.kill()
                except Exception:
                    pass


def _runtime_discover_with_servers(servers: Dict[str, Any], env_dir: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if not servers:
        return [], {"by_fq": {}, "by_short": {}}

    discovered: List[Dict[str, Any]] = []
    for name, spec in servers.items():
        cmd = spec.get("command")
        args = spec.get("args") or []
        if not isinstance(cmd, str):
            continue
        # 注入环境变量：MCP_ENV_DIR + servers.json中声明的env
        env_extra = {
            "MCP_ENV_DIR": str(env_dir)
        }
        declared_env = spec.get("env") or {}
        if isinstance(declared_env, dict):
            for k, v in declared_env.items():
                # 展开环境变量占位符（如 ${GITHUB_PERSONAL_ACCESS_TOKEN}）
                env_extra[k] = os.path.expandvars(str(v))
        # 展开 args 中的环境变量
        resolved_args = []
        for a in args:
            if isinstance(a, str):
                # 展开环境变量写法（$VAR 或 ${VAR}）
                s = os.path.expandvars(a)
                resolved_args.append(s)
            else:
                resolved_args.append(a)
        client = MCPStdioClient(command=cmd, args=resolved_args, cwd=env_dir, env=env_extra)
        # GitHub MCP Server输出日志到stdout，需要使用line模式
        if 'github' in name.lower():
            client._line_mode = True
        ok = client.start()
        if not ok:
            client.stop()
            continue
        try:
            tools = client.list_tools()
        finally:
            client.stop()
        for t in tools:
            tname = t.get("name") or t.get("function", {}).get("name")
            if not isinstance(tname, str) or not tname:
                continue
            # MCP常见返回是短名 + inputSchema / input_schema
            input_schema = t.get("inputSchema") or t.get("input_schema") or t.get("parameters") or {}
            desc = t.get("description") or t.get("function", {}).get("description", "")
            fq = f"{name}.{tname}"
            discovered.append({
                "server": name,
                "type": "function",
                "function": {
                    "name": fq,
                    "description": desc,
                    "parameters": input_schema if isinstance(input_schema, dict) else {},
                },
                "short_name": tname,
            })

    return discovered, build_aliases(discovered)


def _runtime_discover(scenario_dir: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    env_dir = scenario_dir / "env"
    cfg = _read_servers_config(env_dir) or {}
    servers = (cfg.get("mcpServers") or {}) if isinstance(cfg, dict) else {}
    return _runtime_discover_with_servers(servers, env_dir)


def discover_tools(
    scenario_dir: Path,
    runtime_strict: bool = True,
    allow_fallback: bool = False,
    override_servers: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Discover tools for a scenario.
    Priority:
      1) runtime via MCP (env/servers.json)
      2) manifest.json.tools.tool_list
      3) static parse of env/*.py files for @mcp.tool() decorators
    Returns (tools_list, aliases)
    """
    # 1) runtime via HTTP url if provided
    if override_servers is not None:
        # try http with processes first (start servers then connect)
        tools_httpp, aliases_httpp = _http_discover_with_processes(scenario_dir, override_servers)
        if tools_httpp:
            return tools_httpp, aliases_httpp
        # fallback: http direct (server可能已外部运行)
        tools_http, aliases_http = _http_discover_with_servers(override_servers)
        if tools_http:
            return tools_http, aliases_http
        env_dir = scenario_dir / "env"
        tools_rt, aliases_rt = _runtime_discover_with_servers(override_servers, env_dir)
    else:
        # try read servers.json and http first
        env_dir = scenario_dir / "env"
        cfg = _read_servers_config(env_dir) or {}
        servers = (cfg.get('mcpServers') or {}) if isinstance(cfg, dict) else {}
        tools_httpp, aliases_httpp = _http_discover_with_processes(scenario_dir, servers)
        if tools_httpp:
            return tools_httpp, aliases_httpp
        tools_http, aliases_http = _http_discover_with_servers(servers)
        if tools_http:
            return tools_http, aliases_http
        tools_rt, aliases_rt = _runtime_discover(scenario_dir)
    if tools_rt:
        return tools_rt, aliases_rt
    # 严格运行时：直接返回空，由上层判定失败（推荐）
    if runtime_strict and not allow_fallback:
        return [], {"by_fq": {}, "by_short": {}}

    # 1) manifest
    manifest = scenario_dir / "manifest.json"
    if allow_fallback and manifest.exists():
        try:
            manifest_obj = json.loads(manifest.read_text(encoding="utf-8"))
            tool_list = ((manifest_obj.get("tools") or {}).get("tool_list") or [])
            if isinstance(tool_list, list) and tool_list:
                # normalize short_name if missing
                for t in tool_list:
                    fn = t.get("function", {})
                    if "short_name" not in t and isinstance(fn.get("name"), str):
                        t["short_name"] = fn["name"].split(".")[-1]
                return tool_list, build_aliases(tool_list)
        except Exception:
            pass

    # 2) static parse env/ for @mcp.tool()
    env_dir = scenario_dir / "env"
    if not allow_fallback:
        return [], {"by_fq": {}, "by_short": {}}
    tools_all: List[Dict[str, Any]] = []
    if env_dir.exists():
        for py in sorted(env_dir.glob("*.py")):
            if py.name in ("check.py", "checker.py"):
                continue
            try:
                _, tools = _parse_server_tools(py)
                tools_all.extend(tools)
            except Exception:
                continue

    return tools_all, build_aliases(tools_all)
async def _http_list_tools(url: str) -> List[Dict[str, Any]]:
    try:
        from fastmcp import Client as MCPClient  # type: ignore
    except Exception:
        return []
    try:
        async with MCPClient(url) as client:  # type: ignore
            tools = await client.list_tools()
            return tools or []
    except Exception:
        return []

def _convert_tools_from_fastmcp(server_name: str, raw_tools: List[Any]) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for tool in raw_tools or []:
        # FastMCP Tool object
        if hasattr(tool, 'name'):
            name = getattr(tool, 'name', '')
            desc = getattr(tool, 'description', '')
            params = getattr(tool, 'inputSchema', {})
            if name:
                results.append({
                    'server': server_name,
                    'type': 'function',
                    'function': {
                        'name': f"{server_name}.{name}",
                        'description': desc or '',
                        'parameters': params if isinstance(params, dict) else {}
                    },
                    'short_name': name,
                })
        elif isinstance(tool, dict):
            # Could already be dict
            tname = tool.get('name') or (tool.get('function') or {}).get('name')
            params = tool.get('inputSchema') or tool.get('parameters') or ((tool.get('function') or {}).get('parameters'))
            desc = tool.get('description') or (tool.get('function') or {}).get('description', '')
            if isinstance(tname, str) and tname:
                short = tname.split('.')[-1]
                results.append({
                    'server': server_name,
                    'type': 'function',
                    'function': {
                        'name': f"{server_name}.{short}",
                        'description': desc or '',
                        'parameters': params if isinstance(params, dict) else {}
                    },
                    'short_name': short,
                })
    return results

def _http_discover_with_servers(servers: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    all_tools: List[Dict[str, Any]] = []
    for name, spec in (servers or {}).items():
        url = None
        if isinstance(spec, dict):
            url = spec.get('url') or spec.get('URL') or spec.get('endpoint')
        if not isinstance(url, str) or not url:
            continue
        try:
            raw_tools = asyncio.run(_http_list_tools(url))
        except RuntimeError:
            # already in a loop; create new loop
            loop = asyncio.new_event_loop()
            try:
                raw_tools = loop.run_until_complete(_http_list_tools(url))
            finally:
                loop.close()
        converted = _convert_tools_from_fastmcp(name, raw_tools)
        all_tools.extend(converted)
    return all_tools, build_aliases(all_tools)

def _spawn_process(cmd: str, args: List[str], cwd: Optional[Path], env: Dict[str, str]) -> Optional[subprocess.Popen]:
    try:
        p = subprocess.Popen([cmd] + [str(a) for a in args], cwd=str(cwd) if cwd else None, env=env,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=False)
        return p
    except Exception:
        return None

def _http_discover_with_processes(scenario_dir: Path, servers: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    env_dir = scenario_dir / "env"
    procs: List[Tuple[str, subprocess.Popen]] = []
    results: List[Dict[str, Any]] = []
    try:
        for name, spec in (servers or {}).items():
            url = None
            if isinstance(spec, dict):
                url = spec.get('url') or spec.get('URL') or spec.get('endpoint')
            if not isinstance(url, str) or not url:
                continue
            cmd = spec.get('command'); args = spec.get('args') or []
            if not isinstance(cmd, str) or not isinstance(args, list):
                continue
            env_extra = os.environ.copy()
            env_extra['MCP_ENV_DIR'] = str(env_dir)
            # 展开 args 中的环境变量
            resolved_args = []
            for a in args:
                if isinstance(a, str):
                    s = os.path.expandvars(a)
                    resolved_args.append(s)
                else:
                    resolved_args.append(a)
            p = _spawn_process(cmd, resolved_args, env_dir, env_extra)
            if p:
                procs.append((name, p))
        # attempt http list_tools per server with url (retry for readiness)
        all_tools: List[Dict[str, Any]] = []
        for name, spec in (servers or {}).items():
            url = None
            if isinstance(spec, dict):
                url = spec.get('url') or spec.get('URL') or spec.get('endpoint')
            if not isinstance(url, str) or not url:
                continue
            raw_tools: List[Any] = []
            for attempt in range(10):
                try:
                    raw_tools = asyncio.run(_http_list_tools(url))
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    try:
                        raw_tools = loop.run_until_complete(_http_list_tools(url))
                    finally:
                        loop.close()
                if raw_tools:
                    break
                time.sleep(0.5)
            converted = _convert_tools_from_fastmcp(name, raw_tools)
            all_tools.extend(converted)
        return all_tools, build_aliases(all_tools)
    finally:
        # stop processes
        for _, p in procs:
            try:
                if p.poll() is None:
                    p.terminate()
                    try:
                        p.wait(timeout=1.0)
                    except Exception:
                        p.kill()
            except Exception:
                pass
