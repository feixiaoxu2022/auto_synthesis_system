#!/usr/bin/env python3
"""
MCP-Benchmark Agent执行器 - 批量执行样本任务
"""
import argparse
import json
import logging
import os
import shutil
import sys
import tempfile
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock
from typing import Dict, List, Optional

# 兼容包内/脚本执行两种方式
try:
    from .mcp_client import MCPClient, MultiMCPClient
    from .agent import MCPAgent
except Exception:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from mcp_client import MCPClient, MultiMCPClient  # type: ignore
    from agent import MCPAgent  # type: ignore


def setup_logging(verbose: bool = False):
    """设置日志"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - [%(threadName)-10s] - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    # 减少第三方库日志
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)


def inject_github_token(system_prompt: str) -> str:
    """
    将system prompt中的GitHub敏感信息占位符替换为真实值

    Args:
        system_prompt: 可能包含占位符的system prompt

    Returns:
        替换后的system prompt
    """
    if not isinstance(system_prompt, str):
        return system_prompt

    # 替换GitHub token占位符
    token = os.environ.get('GITHUB_PERSONAL_ACCESS_TOKEN', '')
    if token and '${GITHUB_PERSONAL_ACCESS_TOKEN}' in system_prompt:
        system_prompt = system_prompt.replace('${GITHUB_PERSONAL_ACCESS_TOKEN}', token)

    # 替换GitHub owner占位符
    owner = os.environ.get('GITHUB_OWNER', '')
    if '${GITHUB_OWNER}' in system_prompt:
        system_prompt = system_prompt.replace('${GITHUB_OWNER}', owner)

    return system_prompt


def load_samples(samples_file: Path) -> List[Dict]:
    """加载样本文件（JSONL格式）"""
    samples = []
    with open(samples_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            samples.append(json.loads(line))
    return samples


def load_server_config(scenario_dir: Path) -> Optional[Dict]:
    """加载MCP服务器配置"""
    # 优先级：env/servers.json > servers.json
    candidates = [
        scenario_dir / "env" / "servers.json",
        scenario_dir / "servers.json"
    ]
    for config_file in candidates:
        if config_file.exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
    return None


def get_completed_samples(results_dir: Path) -> set:
    """获取已完成的样本ID"""
    completed = set()
    if not results_dir.exists():
        return completed
    for result_file in results_dir.glob("*.json"):
        try:
            with open(result_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                data_id = data.get("data_id")
                if data_id:
                    completed.add(data_id)
        except Exception:
            pass
    return completed


def prepare_environment(sample: Dict, env_dir: Path):
    """准备样本环境数据（直接在env_dir下写入）"""

    # 读取environment字段（列表格式）
    environment = sample.get("environment", [])

    if not environment:
        return

    # 收集数据库文件信息（用于后续更新servers.json）
    db_files = []

    # 直接在env_dir下写入环境文件和目录
    for dep in environment:
        dep_type = dep.get("type")
        dep_path = env_dir / dep.get("path")

        if dep_type == "directory":
            # 创建目录
            dep_path.mkdir(parents=True, exist_ok=True)
        elif dep_type == "file":
            # 确保父目录存在
            dep_path.parent.mkdir(parents=True, exist_ok=True)
            # 写入文件内容
            content = dep.get("content", "")
            with open(dep_path, 'w', encoding='utf-8') as f:
                f.write(content)
        elif dep_type == "binary":
            # 二进制文件（Excel、PDF等）：content是base64编码
            dep_path.parent.mkdir(parents=True, exist_ok=True)
            content = dep.get("content", "")
            if content:
                import base64
                binary_data = base64.b64decode(content)
                with open(dep_path, 'wb') as f:
                    f.write(binary_data)
        elif dep_type == "db":
            # 数据库初始化：执行SQL语句创建schema和插入数据
            dep_path.parent.mkdir(parents=True, exist_ok=True)
            content = dep.get("content", "")
            if content:
                # 使用命令行方式执行SQL（可以正确处理#注释）
                # Python的sqlite3.executescript()不支持#注释，会报错"unrecognized token: '#'"
                import tempfile
                import subprocess

                # 创建临时SQL文件
                with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False, encoding='utf-8') as f:
                    f.write(content)
                    sql_file = f.name

                try:
                    # 使用sqlite3命令行工具执行SQL文件
                    result = subprocess.run(
                        ['sqlite3', str(dep_path)],
                        stdin=open(sql_file, 'r', encoding='utf-8'),
                        capture_output=True,
                        text=True,
                        encoding='utf-8'
                    )

                    if result.returncode != 0:
                        raise RuntimeError(f"SQLite initialization failed: {result.stderr}")
                finally:
                    # 删除临时SQL文件
                    import os
                    try:
                        os.unlink(sql_file)
                    except Exception:
                        pass
            # 记录数据库文件名
            db_files.append(dep.get("path"))
        elif dep_type == "sh":
            # Shell脚本：写入文件并设置执行权限
            dep_path.parent.mkdir(parents=True, exist_ok=True)
            content = dep.get("content", "")
            with open(dep_path, 'w', encoding='utf-8') as f:
                f.write(content)
            # 设置执行权限
            import os
            os.chmod(dep_path, 0o755)
            logging.info(f"部署shell脚本: {dep.get('path')}")

    # SQL场景特殊处理：动态更新servers.json中的db-path参数
    if db_files:
        servers_json = env_dir / "servers.json"
        if servers_json.exists():
            try:
                with open(servers_json, 'r', encoding='utf-8') as f:
                    servers_config = json.load(f)

                # 查找sqlite服务器配置并更新db-path
                for server_name, server_config in servers_config.get("mcpServers", {}).items():
                    if "sqlite" in server_name.lower() and "args" in server_config:
                        # 找到--db-path参数位置并更新为实际的数据库文件
                        args = server_config["args"]
                        for i, arg in enumerate(args):
                            if arg == "--db-path" and i + 1 < len(args):
                                # 使用第一个数据库文件（通常一个样本只用一个db）
                                args[i + 1] = db_files[0]
                                logging.info(f"动态更新sqlite db-path为: {db_files[0]}")
                                break

                # 写回servers.json
                with open(servers_json, 'w', encoding='utf-8') as f:
                    json.dump(servers_config, f, indent=2, ensure_ascii=False)

            except Exception as e:
                logging.warning(f"更新servers.json中的db-path失败: {e}")


def save_final_environment(env_dir: Path, results_dir: Path, data_id: str):
    """
    保存执行后的环境数据

    Args:
        env_dir: MCP服务器工作目录
        results_dir: 结果保存目录
        data_id: 样本ID
    """
    env_save_dir = results_dir / f"{data_id}_env"
    env_save_dir.mkdir(parents=True, exist_ok=True)

    import shutil

    # 复制所有数据文件
    for file in env_dir.iterdir():
        if file.is_file():
            # 跳过test_开头的文件
            # 保留servers.json配置文件（部分场景的checker需要用它启动MCP服务器来验证结果）
            if file.name.startswith("test_"):
                continue
            # 复制数据文件（.jsonl, .db, .sqlite等）和配置文件（servers.json）
            shutil.copy(file, env_save_dir / file.name)

    # 复制所有子目录（如file_system_output, file_system_mock_data等）
    for item in env_dir.iterdir():
        if item.is_dir() and not item.name.endswith("_env"):
            # 复制整个目录树
            dest_dir = env_save_dir / item.name
            if dest_dir.exists():
                shutil.rmtree(dest_dir)
            shutil.copytree(item, dest_dir)


def execute_sample(
    sample: Dict,
    mcp_client: MCPClient,
    agent: MCPAgent,
    results_dir: Path,
    env_dir: Optional[Path] = None
) -> Dict:
    """
    执行单个样本

    Args:
        sample: 样本数据
        mcp_client: MCP客户端
        agent: Agent实例
        results_dir: 结果保存目录
        env_dir: 环境数据目录（可选）

    Returns:
        执行结果摘要
    """
    data_id = sample.get("data_id")
    query = sample.get("query", "")
    # 如果顶层query为空，尝试从extra_info.query获取（如local_file_dir_process场景）
    if not query:
        query = sample.get("extra_info", {}).get("query", "")
    system_prompt = sample.get("system", "")  # 使用"system"而非"system_prompt"

    # 注入GitHub token（如果system_prompt中包含占位符）
    system_prompt = inject_github_token(system_prompt)

    logging.info(f"开始执行样本: {data_id}")
    start_time = time.time()

    try:
        # 执行任务
        result = agent.solve(query=query, system_prompt=system_prompt)

        # 构造结果文件
        execution_time = time.time() - start_time
        result_data = {
            "data_id": data_id,
            "response": result.get("response", ""),
            "conversation_history": result.get("conversation_history", []),
            "tool_call_list": result.get("tool_call_list", []),
            "execution_status": result.get("execution_status", "error"),
            "execution_time": execution_time
        }

        # 包含样本的关键字段（checker需要）
        for key in ["check_list", "environment", "query", "system", "servers"]:
            if key in sample:
                result_data[key] = sample[key]

        # 如果有环境目录，添加到结果中（指向保存的执行后环境）
        if env_dir:
            result_data["env_dir"] = str(results_dir / f"{data_id}_env")

            # 收集final_state（执行后的环境数据）
            final_state = {}
            import json as _json
            for jsonl_file in env_dir.glob("*.jsonl"):
                if jsonl_file.name.startswith("test_"):
                    continue
                data_type = jsonl_file.stem
                final_state[data_type] = {}
                try:
                    with open(jsonl_file, 'r', encoding='utf-8') as f:
                        for line in f:
                            if line.strip():
                                record = _json.loads(line.strip())
                                # 改进key_field推断逻辑，处理复数形式和复合词
                                # 例如：meeting_bookings -> [booking_id, meeting_booking_id, ...]
                                key_candidates = []
                                # 1. 尝试去掉末尾单词的s（meeting_bookings -> meeting_booking -> booking_id）
                                if data_type.endswith('s'):
                                    singular = data_type[:-1]
                                    parts = singular.split('_')
                                    if len(parts) > 1:
                                        # 取最后一个词作为key前缀（meeting_booking -> booking_id）
                                        key_candidates.append(f"{parts[-1]}_id")
                                    key_candidates.append(f"{singular}_id")
                                # 2. 原样加_id
                                key_candidates.append(f"{data_type}_id")
                                # 3. 通用key
                                key_candidates.extend(["id", "uuid"])

                                for key_field in key_candidates:
                                    if key_field in record:
                                        final_state[data_type][record[key_field]] = record
                                        break
                except Exception as e:
                    logging.warning(f"读取{jsonl_file}失败: {e}")

            result_data["final_state"] = final_state

        # 保存结果
        result_file = results_dir / f"{data_id}.json"
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, ensure_ascii=False, indent=2)

        logging.info(f"✅ {data_id}: {result.get('execution_status')}, 耗时 {result_data['execution_time']:.1f}s")

        return {
            "data_id": data_id,
            "status": result.get("execution_status"),
            "time": result_data['execution_time']
        }

    except Exception as e:
        # 记录详细的错误信息和完整traceback
        error_msg = str(e)
        full_traceback = traceback.format_exc()

        # 判断错误类型
        error_category = "未知错误"
        if "HTTPError" in type(e).__name__ or "HTTP" in error_msg:
            if "429" in error_msg or "rate limit" in error_msg.lower():
                error_category = "API限速"
            elif any(code in error_msg for code in ["500", "502", "503", "504"]):
                error_category = "API服务器错误"
            else:
                error_category = "HTTP错误"
        elif "timeout" in error_msg.lower():
            error_category = "请求超时"
        elif "connection" in error_msg.lower():
            error_category = "网络连接错误"

        logging.error(f"❌ {data_id}: 执行失败 ({error_category}) - {error_msg}")
        logging.debug(f"完整异常栈:\n{full_traceback}")

        # 保存错误结果
        execution_time = time.time() - start_time
        result_data = {
            "data_id": data_id,
            "response": f"执行错误 ({error_category}): {error_msg}",
            "conversation_history": [],
            "tool_call_list": [],
            "execution_status": "error",
            "execution_time": execution_time,
            "error": error_msg,
            "error_category": error_category,
            "error_traceback": full_traceback  # 保存完整traceback供调试
        }

        # 包含样本的关键字段（checker需要）
        for key in ["check_list", "environment", "query", "system", "servers"]:
            if key in sample:
                result_data[key] = sample[key]

        result_file = results_dir / f"{data_id}.json"
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, ensure_ascii=False, indent=2)

        return {
            "data_id": data_id,
            "status": "error",
            "error": error_msg,
            "error_category": error_category
        }


def execute_single_sample_wrapper(
    idx: int,
    sample: Dict,
    total_count: int,
    scenario_dir: Path,
    base_env: Path,
    results_dir: Path,
    mcp_servers_config: Dict,
    model: str,
    base_url: Optional[str],
    api_key: Optional[str],
    max_turns: int,
    temperature: float
) -> Dict:
    """
    执行单个样本（线程安全）
    
    Returns:
        {
            "data_id": str,
            "status": "success" | "error",
            "error": str (可选)
        }
    """
    data_id = sample.get("data_id")
    logging.info(f"\n{'='*60}")
    logging.info(f"进度: {idx}/{total_count} - {data_id}")
    logging.info(f"{'='*60}")
    
    # 为每个样本创建独立的MCP客户端和Agent
    mcp_client = None
    sample_cwd = None
    try:
        # 为每个样本创建独立的临时环境目录
        temp_env = tempfile.mkdtemp(prefix=f"env_{data_id}_", dir=results_dir)
        sample_cwd = Path(temp_env)
        
        # 从基础环境目录复制文件到临时目录
        if base_env.exists():
            for item in base_env.iterdir():
                if item.is_file():
                    shutil.copy2(item, sample_cwd / item.name)
                elif item.is_dir():
                    shutil.copytree(item, sample_cwd / item.name)
        
        # 准备样本环境数据（在临时目录中）
        prepare_environment(sample, sample_cwd)
        logging.info(f"已准备环境数据（临时目录: {sample_cwd}）")
        
        # GitHub 场景：如检测到 github_name.txt，则在推理前执行仓库初始化脚本并等待5分钟
        try:
            gh_name_file = sample_cwd / "github_name.txt"
            if gh_name_file.exists():
                logging.info("检测到 github_name.txt，开始执行 GitHub 仓库初始化脚本…")
                
                # 从已部署的环境目录读取脚本
                script_path = sample_cwd / "create_mcp_repo.sh"
                
                if not script_path.exists():
                    logging.warning(f"初始化脚本不存在，跳过：{script_path}")
                else:
                    # 校验必要环境变量
                    env_map = os.environ.copy()
                    token = env_map.get("GITHUB_PERSONAL_ACCESS_TOKEN") or env_map.get("GH_TOKEN")
                    owner = env_map.get("GITHUB_OWNER")
                    if not token or not owner:
                        logging.warning("缺少 GITHUB_PERSONAL_ACCESS_TOKEN/GH_TOKEN 或 GITHUB_OWNER，跳过仓库初始化")
                    else:
                        try:
                            os.chmod(script_path, 0o755)
                        except Exception:
                            pass
                        import subprocess
                        proc = subprocess.run([
                            "sh", str(script_path)
                        ], cwd=str(sample_cwd), env=env_map, capture_output=True, text=True)
                        if proc.returncode != 0:
                            logging.error("GitHub 仓库初始化脚本执行失败，返回码 %s", proc.returncode)
                            stderr_snippet = (proc.stderr or "").splitlines()[-20:]
                            logging.error("stderr 尾部:\n%s", "\n".join(stderr_snippet))
                        else:
                            logging.info("GitHub 仓库初始化完成，等待5分钟以便工作流运行…")
                            time.sleep(300)
            else:
                logging.debug("未检测到 github_name.txt，跳过仓库初始化")
        except Exception as e:
            logging.warning(f"GitHub 仓库初始化阶段出现异常：{e}")
        
        # 从临时目录读取servers.json（prepare_environment可能已修改）
        temp_servers_json = sample_cwd / "servers.json"
        if temp_servers_json.exists():
            with open(temp_servers_json, 'r', encoding='utf-8') as f:
                current_server_config = json.load(f)
            if current_server_config and "mcpServers" in current_server_config:
                current_mcp_servers_config = current_server_config["mcpServers"]
            else:
                current_mcp_servers_config = mcp_servers_config
        else:
            current_mcp_servers_config = mcp_servers_config
        
        # 创建MultiMCPClient并启动所有服务器
        multi_client = MultiMCPClient()
        failed_servers = []
        
        import re
        for server_name, server_info in current_mcp_servers_config.items():
            command = server_info.get("command")
            server_args = server_info.get("args", [])
            
            # 处理环境变量占位符
            env_vars = {}
            resolved_args = []
            for arg in server_args:
                arg_str = str(arg)
                matches = re.findall(r'\$\{([^}]+)\}', arg_str)
                for var_name in matches:
                    if var_name not in env_vars:
                        env_vars[var_name] = str(sample_cwd)
                    arg_str = arg_str.replace(f"${{{var_name}}}", env_vars[var_name])
                resolved_args.append(arg_str)
            
            # 创建并添加客户端
            client = MCPClient(command=command, args=resolved_args, cwd=sample_cwd, env=env_vars)
            if not multi_client.add_client(server_name, client):
                logging.warning(f"启动MCP服务器 {server_name} 失败")
                failed_servers.append(server_name)
            else:
                logging.info(f"成功启动MCP服务器: {server_name}")
        
        # 设置mcp_client供finally清理使用
        mcp_client = multi_client
        
        if len(failed_servers) == len(current_mcp_servers_config):
            # 所有服务器都失败
            logging.error(f"所有MCP服务器启动失败")
            result = {
                "data_id": data_id,
                "status": "error",
                "error": "Failed to start all MCP servers"
            }
        else:
            if failed_servers:
                logging.warning(f"部分服务器启动失败: {', '.join(failed_servers)}")
            
            # 创建Agent
            agent = MCPAgent(
                mcp_client=multi_client,
                model=model,
                base_url=base_url,
                api_key=api_key,
                max_turns=max_turns,
                temperature=temperature
            )
            
            # 执行任务
            result = execute_sample(sample, multi_client, agent, results_dir, sample_cwd)
            
            # 保存执行后的环境数据
            save_final_environment(sample_cwd, results_dir, data_id)
            logging.info(f"已保存执行后环境数据")
        
        return result
    
    except Exception as e:
        logging.error(f"执行样本时发生异常: {e}")
        return {
            "data_id": data_id,
            "status": "error",
            "error": str(e)
        }
    
    finally:
        # 清理资源
        if mcp_client:
            mcp_client.stop()
        
        # 清理临时环境目录
        if sample_cwd and sample_cwd.exists():
            try:
                shutil.rmtree(sample_cwd)
                logging.debug(f"已清理临时环境目录: {sample_cwd}")
            except Exception as e:
                logging.warning(f"清理临时目录失败: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="MCP-Benchmark Agent执行器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 执行office_administration场景
  python executor.py \\
    --scenario release/scenarios/office_administration \\
    --samples release/scenarios/office_administration/samples/eval.jsonl \\
    --results-dir results/office_administration \\
    --model gpt-4 \\
    --api-key sk-xxx

  # Resume模式（跳过已完成）
  python executor.py \\
    --scenario release/scenarios/office_administration \\
    --samples release/scenarios/office_administration/samples/eval.jsonl \\
    --results-dir results/office_administration \\
    --model gpt-4 \\
    --resume
        """
    )

    parser.add_argument("--scenario", required=True, help="场景目录路径")
    parser.add_argument("--samples", required=True, help="样本文件（JSONL）")
    parser.add_argument("--results-dir", required=True, help="结果保存目录")
    parser.add_argument("--model", required=True, help="模型名称（如gpt-4）")
    parser.add_argument("--base-url", help="API基础URL")
    parser.add_argument("--api-key", help="API密钥")
    parser.add_argument("--max-turns", type=int, default=20, help="最大对话轮数（默认20）")
    parser.add_argument("--temperature", type=float, default=0.0, help="采样温度（默认0.0）")
    parser.add_argument("--resume", action="store_true", help="跳过已完成的样本")
    parser.add_argument("--offset", type=int, default=0, help="跳过前N个样本（与--limit配合：第offset+1到offset+limit个）")
    parser.add_argument("--limit", type=int, help="限制执行样本数量（用于测试）")
    parser.add_argument("--max-concurrency", type=int, default=1, help="最大并发执行数（默认1=顺序执行，建议2-4避免rate limit）")
    parser.add_argument("--verbose", action="store_true", help="详细日志")

    args = parser.parse_args()

    setup_logging(args.verbose)

    # 验证路径（使用绝对路径）
    scenario_dir = Path(args.scenario).absolute()
    samples_file = Path(args.samples).absolute()
    results_dir = Path(args.results_dir).absolute()

    if not scenario_dir.exists():
        logging.error(f"场景目录不存在: {scenario_dir}")
        sys.exit(1)
    if not samples_file.exists():
        logging.error(f"样本文件不存在: {samples_file}")
        sys.exit(1)

    results_dir.mkdir(parents=True, exist_ok=True)

    # 加载样本
    logging.info(f"加载样本文件: {samples_file}")
    samples = load_samples(samples_file)
    logging.info(f"共加载 {len(samples)} 个样本")

    # Resume模式
    if args.resume:
        completed = get_completed_samples(results_dir)
        if completed:
            samples = [s for s in samples if s.get("data_id") not in completed]
            logging.info(f"Resume模式：跳过 {len(completed)} 个已完成样本，剩余 {len(samples)} 个")

    # 限制数量（测试用）
    if args.offset or args.limit:
        start = args.offset if args.offset else 0
        end = start + args.limit if args.limit else None
        samples = samples[start:end]
        if args.limit:
            logging.info(f"选择样本：第{start+1}到第{start+len(samples)}个，共{len(samples)}个")
        else:
            logging.info(f"选择样本：从第{start+1}个开始，共{len(samples)}个")

    if not samples:
        logging.info("没有需要执行的样本")
        return

    # 加载MCP服务器配置
    server_config = load_server_config(scenario_dir)
    if not server_config or "mcpServers" not in server_config:
        logging.error("未找到MCP服务器配置（env/servers.json）")
        sys.exit(1)

    # 获取所有MCP服务器配置
    mcp_servers_config = server_config["mcpServers"]
    if not mcp_servers_config:
        logging.error("MCP服务器配置为空")
        sys.exit(1)

    base_env = scenario_dir / "env"  # 基础环境目录（只读）

    logging.info(f"检测到 {len(mcp_servers_config)} 个MCP服务器:")
    for server_name in mcp_servers_config.keys():
        server_info = mcp_servers_config[server_name]
        command = server_info.get("command")
        server_args = server_info.get("args", [])
        logging.info(f"  - {server_name}: {command} {' '.join(str(a) for a in server_args)}")
    logging.info(f"基础环境目录: {base_env}")

    # 执行统计
    stats = {
        "total": len(samples),
        "success": 0,
        "error": 0,
        "results": []
    }

    # 线程安全的统计锁
    stats_lock = Lock()
    
    def execute_and_update_stats(idx_and_sample):
        """包装函数：执行样本并更新统计"""
        idx, sample = idx_and_sample
        
        # 执行单个样本
        result = execute_single_sample_wrapper(
            idx=idx,
            sample=sample,
            total_count=len(samples),
            scenario_dir=scenario_dir,
            base_env=base_env,
            results_dir=results_dir,
            mcp_servers_config=mcp_servers_config,
            model=args.model,
            base_url=args.base_url,
            api_key=args.api_key,
            max_turns=args.max_turns,
            temperature=args.temperature
        )
        
        # 线程安全地更新统计
        with stats_lock:
            if result["status"] == "success":
                stats["success"] += 1
            else:
                stats["error"] += 1
            stats["results"].append(result)
        
        return result
    
    # 根据并发度选择执行方式
    if args.max_concurrency > 1:
        logging.info(f"使用并发执行模式，并发度: {args.max_concurrency}")
        with ThreadPoolExecutor(max_workers=args.max_concurrency) as executor:
            # executor.map保证顺序，但并发执行
            results = list(executor.map(
                execute_and_update_stats,
                enumerate(samples, 1)
            ))
    else:
        logging.info("使用顺序执行模式")
        results = [execute_and_update_stats((idx, sample))
                   for idx, sample in enumerate(samples, 1)]
    
    # 保存执行报告（resume模式需要合并已有报告）
    stats['success_rate'] = stats['success'] / stats['total'] if stats['total'] > 0 else 0.0
    report_file = results_dir / "execution_report.json"

    # Resume模式：合并之前的执行结果
    if args.resume and report_file.exists():
        try:
            with open(report_file, 'r', encoding='utf-8') as f:
                old_report = json.load(f)
                # 合并results（去重）
                existing_ids = {r['data_id'] for r in old_report.get('results', [])}
                merged_results = old_report.get('results', [])
                for r in stats['results']:
                    if r['data_id'] not in existing_ids:
                        merged_results.append(r)
                # 重新计算总统计
                stats['results'] = merged_results
                stats['total'] = len(merged_results)
                stats['success'] = sum(1 for r in merged_results if r['status'] == 'success')
                stats['error'] = sum(1 for r in merged_results if r['status'] == 'error')
                stats['success_rate'] = stats['success'] / stats['total'] if stats['total'] > 0 else 0.0
                logging.info(f"Resume模式：合并已有报告，总计 {stats['total']} 个样本")
        except Exception as e:
            logging.warning(f"合并已有报告失败: {e}，将覆盖旧报告")

    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    # 打印总结
    logging.info(f"\n{'='*60}")
    logging.info("执行完成")
    logging.info(f"总计: {stats['total']}")
    logging.info(f"成功: {stats['success']}")
    logging.info(f"失败: {stats['error']}")
    logging.info(f"成功率: {stats['success']/stats['total']*100:.1f}%")
    logging.info(f"结果保存至: {results_dir}")
    logging.info(f"{'='*60}")


if __name__ == "__main__":
    main()
