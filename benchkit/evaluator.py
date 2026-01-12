#!/usr/bin/env python3
import argparse
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock
from typing import Dict, Iterable, List, Optional

# 兼容包内/脚本执行两种方式
try:
    from .check_runner import CheckRunner
    from .server_launcher import ServerLauncher
except Exception:
    import sys
    from pathlib import Path as _Path
    _HERE = _Path(__file__).resolve().parent
    sys.path.insert(0, str(_HERE))
    from check_runner import CheckRunner  # type: ignore
    from server_launcher import ServerLauncher  # type: ignore


def setup_logging(verbose: bool = False):
    """设置日志配置"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )


def iter_jsonl(path: Path) -> Iterable[Dict]:
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)


def find_default_samples_file(scenario_dir: Path) -> Optional[Path]:
    # 源仓库：scenarios/<name>/samples_for_open_benchmark
    # 发布包：<scenario>/samples 或 <scenario>/samples_for_open_benchmark
    # 优先标准文件名，提高确定性
    preferred = [
        scenario_dir / "samples" / "eval.jsonl",
        scenario_dir / "samples_for_open_benchmark" / "eval.jsonl",
    ]
    for p in preferred:
        if p.exists():
            return p
    for sub in ("samples", "samples_for_open_benchmark"):
        d = scenario_dir / sub
        if not d.exists():
            continue
        files = list(d.glob("*.jsonl"))
        if files:
            return files[0]
    return None


def default_result_path(results_dir: Path, data_id) -> Path:
    return results_dir / f"{data_id}.json"


def get_completed_checks(output_dir: Path) -> set:
    """获取已完成评测的样本ID"""
    completed = set()
    per_case_dir = output_dir / "cases"
    if not per_case_dir.exists():
        return completed
    for check_file in per_case_dir.glob("check_*.json"):
        try:
            with open(check_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                data_id = data.get("data_id")
                if data_id:
                    completed.add(data_id)
        except Exception:
            pass
    return completed


def standardize_check_result(res: Dict) -> Dict:
    """
    统一checker输出格式：将list格式的check_details转换为dict格式

    标准格式（dict）：
    {
        "check_details": {
            "检查项1": {"检查结论": "不合格", "原因": "...", "详情": "..."}
        },
        "check_list_count": 4,
        "completion_status": "completed",
        "completion_reason": "检查完成",
        "error_reason": "失败项: 检查项1, 检查项3"
    }

    非标准格式（list）：
    {
        "check_details": [
            {"check_item": {...}, "passed": false, "details": "..."}
        ],
        "required_check_count": 4,
        "required_check_passed_count": 2
    }
    """
    check_details = res.get("check_details")

    # 如果已经是dict格式，只需删除不需要的字段
    if isinstance(check_details, dict):
        # 移除不需要的字段
        res.pop("check_version", None)
        res.pop("task_id", None)
        res.pop("result_file_info", None)
        return res

    # 如果是list格式，转换为dict格式
    if isinstance(check_details, list):
        new_check_details = {}
        failed_items = []

        for idx, item in enumerate(check_details, 1):
            if not isinstance(item, dict):
                continue

            # 解析list格式字段
            check_item = item.get("check_item", {})
            passed = item.get("passed", False)
            details = item.get("details", "")

            # 生成检查项名称
            check_name = check_item.get("name") or check_item.get("description") or f"检查项{idx}"

            # 转换为标准dict格式
            new_check_details[check_name] = {
                "检查结论": "合格" if passed else "不合格",
                "原因": check_item.get("description", ""),
                "详情": details
            }

            # 记录失败项
            if not passed:
                failed_items.append(check_name)

        # 更新check_details为dict格式
        res["check_details"] = new_check_details

        # 添加check_list_count字段
        res["check_list_count"] = len(new_check_details)

        # 添加completion_status和completion_reason（如果原始结果中没有）
        if "completion_status" not in res:
            overall_result = res.get("overall_result", "")
            if overall_result in ("Success", "Failure"):
                res["completion_status"] = "completed"
            elif overall_result == "Error":
                res["completion_status"] = "failed"
            else:
                res["completion_status"] = "completed"

        if "completion_reason" not in res:
            passed_count = len(new_check_details) - len(failed_items)
            res["completion_reason"] = f"检查完成，共{len(new_check_details)}项检查，{passed_count}项通过"

        # 更新error_reason：列出失败的检查项（如果原始结果中已有且非空，保留原值）
        if not res.get("error_reason"):
            if failed_items:
                res["error_reason"] = f"失败项: {', '.join(failed_items)}"
            else:
                res["error_reason"] = ""

        # 移除list格式特有的统计字段
        res.pop("required_check_count", None)
        res.pop("required_check_passed_count", None)
        res.pop("required_check_pass_rate", None)

    # 移除不需要的字段
    res.pop("check_version", None)
    res.pop("task_id", None)
    res.pop("result_file_info", None)

    return res


def check_single_sample(
    item: Dict,
    runner: 'CheckRunner',
    tmp_bench_dir: Path,
    results_dir: Path,
    per_case_dir: Path,
    index: int,
    total: int,
    max_retries: int = 0
) -> Dict:
    """
    检查单个样本

    Args:
        item: 样本数据
        runner: CheckRunner实例
        tmp_bench_dir: 临时bench文件目录
        results_dir: 执行结果目录
        per_case_dir: 检查结果输出目录
        index: 当前索引（用于日志）
        total: 总样本数（用于日志）
        max_retries: 最大重试次数

    Returns:
        检查结果
    """
    data_id = item.get("data_id")

    bench_path = tmp_bench_dir / f"bench_{data_id}.json"
    with open(bench_path, "w", encoding="utf-8") as f:
        json.dump(item, f, ensure_ascii=False)

    result_path = default_result_path(results_dir, data_id)
    out_path = per_case_dir / f"check_{data_id}.json"

    logging.info(f"[{index}/{total}] 开始检查样本: {data_id}")
    check_start_time = time.time()

    # 读取执行结果获取execution_status
    execution_status = None
    try:
        with open(result_path, 'r', encoding='utf-8') as f:
            exec_result = json.load(f)
            execution_status = exec_result.get("execution_status")
    except Exception:
        pass

    # 如果执行阶段失败，跳过checker调用，直接生成跳过结果
    if execution_status == "error":
        res = {
            "data_id": data_id,
            "overall_result": "Skipped",
            "execution_status": "error",
            "check_details": {},
            "completion_status": "skipped",
            "completion_reason": "执行阶段失败，跳过检查阶段以节省成本"
        }
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=2)
        logging.info(f"[{index}/{total}] {data_id} - Skipped (执行阶段失败)")
        return res

    # 执行成功，正常调用checker（带智能重试：仅对LLM API限速错误重试）
    last_error = None
    base_delay = 1.0  # 初始延迟1秒

    for attempt in range(max_retries + 1):
        try:
            res = runner.run(bench_file=bench_path, result_file=result_path, output_file=out_path)
            # 统一格式：将list格式转换为dict格式
            res = standardize_check_result(res)
            # 添加data_id（确保文件中包含data_id，用于resume功能）
            res["data_id"] = data_id
            # 添加execution_status到check结果
            res["execution_status"] = execution_status
            # 重新写入统一格式后的结果
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(res, f, ensure_ascii=False, indent=2)

            # 记录检查结果
            check_time = time.time() - check_start_time
            overall_result = res.get("overall_result", "Unknown")

            # 统计检查详情
            check_details = res.get("check_details", {})
            if isinstance(check_details, dict):
                passed_count = sum(1 for v in check_details.values()
                                 if isinstance(v, dict) and v.get("检查结论") == "合格")
                total_checks = len(check_details)
                detail_summary = f"{passed_count}/{total_checks} checks passed"
            else:
                detail_summary = "no details"

            retry_info = f" (重试 {attempt}/{max_retries})" if attempt > 0 else ""
            logging.info(f"[{index}/{total}] {data_id} - {overall_result} ({check_time:.2f}s, {detail_summary}){retry_info}")

            return res
        except Exception as e:
            last_error = e
            error_msg = str(e).lower()

            # 判断是否是可重试的错误（LLM API限速或服务器错误）
            is_retryable = any([
                '429' in error_msg,  # Too Many Requests
                'rate limit' in error_msg,
                'too many requests' in error_msg,
                '500' in error_msg,  # Internal Server Error
                '502' in error_msg,  # Bad Gateway
                '503' in error_msg,  # Service Unavailable
                '504' in error_msg,  # Gateway Timeout
            ])

            if is_retryable and attempt < max_retries:
                # 使用指数退避策略
                delay = base_delay * (2 ** attempt)
                logging.warning(f"[{index}/{total}] {data_id} - 检查失败（LLM API限速/服务器错误），{delay:.1f}秒后重试 (第{attempt + 1}/{max_retries}次): {e}")
                time.sleep(delay)
                continue
            elif not is_retryable:
                # 非可重试错误，直接失败
                logging.error(f"[{index}/{total}] {data_id} - 检查失败（不可重试的错误）: {e}")
                break
            else:
                # 已达最大重试次数
                logging.error(f"[{index}/{total}] {data_id} - 检查失败（已重试{max_retries}次）: {e}")
                break

    # 所有重试都失败，生成错误结果
    res = {
        "data_id": data_id,
        "overall_result": "Error",
        "execution_status": execution_status,
        "check_details": {},
        "completion_status": "failed",
        "completion_reason": f"检查失败: {last_error}",
        "error_reason": str(last_error)
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    return res


def aggregate_summary(case_results: List[Dict]) -> Dict:
    total = len(case_results)

    # 执行阶段统计
    execution_error = sum(1 for r in case_results if r.get("execution_status") == "error")
    valid_count = total - execution_error

    # 检查阶段统计（只针对执行成功的样本）
    executed_cases = [r for r in case_results if r.get("execution_status") != "error"]
    check_success = sum(1 for r in executed_cases if r.get("overall_result") == "Success")
    check_partial = sum(1 for r in executed_cases if r.get("overall_result") == "Partial")
    check_failure = sum(1 for r in executed_cases if r.get("overall_result") == "Failure")
    check_error = sum(1 for r in executed_cases if r.get("overall_result") == "Error")

    evaluable_count = check_success + check_partial + check_failure

    return {
        "total": total,

        # 执行阶段
        "execution_stage": {
            "execution_error": execution_error,
            "valid_execution": valid_count,
            "valid_execution_rate": (valid_count / total) if total else 0.0,
        },

        # 检查阶段
        "check_stage": {
            "check_success": check_success,
            "check_partial": check_partial,
            "check_failure": check_failure,
            "check_error": check_error,
            "task_completion_rate": (check_success / evaluable_count) if evaluable_count else 0.0,
        }
    }


def run_scenario(
    scenario_dir: Path,
    samples_file: Path,
    results_dir: Path,
    output_dir: Path,
    start_servers: bool,
    model: Optional[str],
    base_url: Optional[str],
    api_key: Optional[str],
    resume: bool = False,
    max_concurrency: int = 1,
    max_retries: int = 0,
) -> Dict:
    # 支持三种checker位置：
    # 1) env/checker.py
    # 2) env/check.py
    # 3) checker.py（场景根目录）
    platform_dir = None
    check_script = None
    candidate3 = scenario_dir / "env" / "checker.py"
    candidate4 = scenario_dir / "env" / "check.py"
    candidate2 = scenario_dir / "checker.py"

    if candidate3.exists():
        check_script = candidate3
        platform_dir = candidate3.parent
    elif candidate4.exists():
        check_script = candidate4
        platform_dir = candidate4.parent
    elif candidate2.exists():
        check_script = candidate2
        platform_dir = scenario_dir
    else:
        raise FileNotFoundError(
            f"未发现 checker：尝试过 {candidate3}, {candidate4}, {candidate2}"
        )

    ensure_dir(output_dir)
    tmp_bench_dir = output_dir / "benches"
    ensure_dir(tmp_bench_dir)
    per_case_dir = output_dir / "cases"
    ensure_dir(per_case_dir)

    # 可选启动MCP服务（通常Agent执行阶段需要，checker多为纯校验）
    launcher = None
    if start_servers:
        launcher = ServerLauncher(scenario_dir)
        launcher.start()

    try:
        runner = CheckRunner(
            check_script=check_script,
            work_dir=str(platform_dir),
            model=model,
            base_url=base_url,
            api_key=api_key,
        )

        # 收集需要评测的样本（先扫描一遍找出已执行的）
        samples_to_check = []
        for item in iter_jsonl(samples_file):
            data_id = item.get("data_id")
            if data_id is None:
                continue
            result_path = default_result_path(results_dir, data_id)
            if result_path.exists():
                samples_to_check.append(item)

        # Resume模式：跳过已完成的检查
        if resume:
            completed = get_completed_checks(output_dir)
            if completed:
                samples_to_check = [s for s in samples_to_check if s.get("data_id") not in completed]
                logging.info(f"Resume模式：跳过 {len(completed)} 个已完成检查，剩余 {len(samples_to_check)} 个")

        total_to_check = len(samples_to_check)
        logging.info(f"开始评测，共 {total_to_check} 个样本")

        if total_to_check == 0:
            logging.info("没有需要检查的样本")
            return {"summary": {}, "cases": [], "output": str(output_dir)}

        # 线程安全的结果收集
        case_results: List[Dict] = []
        results_lock = Lock()

        def check_and_collect(idx_and_item):
            """包装函数：检查样本并收集结果"""
            idx, item = idx_and_item
            res = check_single_sample(
                item=item,
                runner=runner,
                tmp_bench_dir=tmp_bench_dir,
                results_dir=results_dir,
                per_case_dir=per_case_dir,
                index=idx,
                total=total_to_check,
                max_retries=max_retries
            )
            with results_lock:
                case_results.append(res)
            return res

        # 根据并发度选择执行方式
        if max_concurrency > 1:
            logging.info(f"使用并发检查模式，并发度: {max_concurrency}")
            with ThreadPoolExecutor(max_workers=max_concurrency) as executor:
                list(executor.map(
                    check_and_collect,
                    enumerate(samples_to_check, 1)
                ))
        else:
            logging.info("使用顺序检查模式")
            for idx, item in enumerate(samples_to_check, 1):
                check_and_collect((idx, item))

        summary = aggregate_summary(case_results)
        summary_path = output_dir / "summary.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump({"summary": summary, "cases": case_results}, f, ensure_ascii=False, indent=2)

        return {"summary": summary, "cases": case_results, "output": str(output_dir)}
    finally:
        if launcher:
            launcher.stop()


def main():
    ap = argparse.ArgumentParser(description="MCP-Benchmark 开放评测Runner（按场景）")
    ap.add_argument("--scenario", required=True, help="场景目录，例如 scenarios/trip")
    ap.add_argument("--samples", help="样本文件（JSONL）。缺省自动从 samples_for_open_benchmark/ 取首个文件")
    ap.add_argument("--results-dir", required=True, help="Agent结果目录，期望包含 {data_id}.json")
    ap.add_argument("--output-dir", required=True, help="评测输出目录")
    ap.add_argument("--start-servers", action="store_true", help="在评测前启动MCP服务（多数仅Agent执行阶段需要）")
    ap.add_argument("--judge-model", help="LLM Judge模型名，可用环境变量 BENCH_CHECK_MODEL 兜底")
    ap.add_argument("--base-url", help="LLM Judge Base URL，可用环境变量 BENCH_CHECK_BASE_URL 兜底")
    ap.add_argument("--api-key", help="LLM Judge API Key，可用环境变量 BENCH_CHECK_API_KEY 兜底")
    ap.add_argument("--skip-env-check", action="store_true", help="跳过MCP工具枚举健康检查（仅用于演示/离线校验）")
    ap.add_argument("--resume", action="store_true", help="跳过已完成的检查（断点恢复）")
    ap.add_argument("--max-concurrency", type=int, default=1, help="并发检查数（默认1，顺序执行）")
    ap.add_argument("--max-retries", type=int, default=2, help="失败重试次数（默认2）")
    ap.add_argument("--verbose", action="store_true", help="启用详细日志输出")
    args = ap.parse_args()

    setup_logging(verbose=args.verbose)

    scenario_dir = Path(args.scenario).resolve()
    if not scenario_dir.exists():
        raise SystemExit(f"场景目录不存在: {scenario_dir}")

    samples_file = Path(args.samples).resolve() if args.samples else find_default_samples_file(scenario_dir)
    if not samples_file or not samples_file.exists():
        raise SystemExit("未找到样本文件，请通过 --samples 指定或检查 samples_for_open_benchmark 目录")

    results_dir = Path(args.results_dir).resolve()
    output_dir = Path(args.output_dir).resolve()

    model = args.judge_model or os.getenv("BENCH_CHECK_MODEL")
    base_url = args.base_url or os.getenv("BENCH_CHECK_BASE_URL")
    api_key = args.api_key or os.getenv("BENCH_CHECK_API_KEY")

    # 优先从样本读取 environment.servers 进行环境就绪检查
    first_sample = None
    for rec in iter_jsonl(samples_file):
        first_sample = rec
        break
    servers_override = None
    if isinstance(first_sample, dict):
        environment = first_sample.get("environment", [])
        if isinstance(environment, list):
            for item in environment:
                if isinstance(item, dict) and "servers.json" in item.get("path", ""):
                    content = item.get("content")
                    if isinstance(content, str):
                        try:
                            servers_override = json.loads(content)
                        except json.JSONDecodeError:
                            pass
                    elif isinstance(content, dict):
                        servers_override = content
                    break

    # 运行时工具发现（严格）作为环境就绪检查（优先样本环境）
    if not args.skip_env_check:
        try:
            try:
                from .tools_discovery import discover_tools
            except Exception:
                from tools_discovery import discover_tools  # type: ignore
            # set debug dir for tools_discovery
            os.environ["BENCHKIT_DEBUG_DIR"] = str(output_dir)
            tools, aliases = discover_tools(
                scenario_dir,
                runtime_strict=True,
                allow_fallback=False,
                override_servers=servers_override,
            )
            if not tools:
                raise SystemExit(
                    "环境初始化失败：未能通过 MCP 运行时枚举获取工具清单。\n"
                    "请检查样本中的 environment.servers 或场景目录 env/servers.json 是否可用、依赖是否安装、必要的环境变量是否设置。"
                )
            ensure_dir(output_dir)
            with open(output_dir / "tools.json", "w", encoding="utf-8") as f:
                import json as _json
                _json.dump({"tools": tools}, f, ensure_ascii=False, indent=2)
        except SystemExit:
            raise
        except Exception as e:
            raise SystemExit(f"环境初始化异常：{e}")

    eval_start_time = time.time()
    logging.info(f"开始评测场景: {scenario_dir.name}")

    report = run_scenario(
        scenario_dir=scenario_dir,
        samples_file=samples_file,
        results_dir=results_dir,
        output_dir=output_dir,
        start_servers=args.start_servers,
        model=model,
        base_url=base_url,
        api_key=api_key,
        resume=args.resume,
        max_concurrency=args.max_concurrency,
        max_retries=args.max_retries,
    )

    eval_time = time.time() - eval_start_time
    summary = report["summary"]

    logging.info("=" * 60)
    logging.info("评测完成")
    logging.info(f"总耗时: {eval_time:.2f}s")
    logging.info(f"总样本数: {summary['total']}")
    logging.info(f"执行成功: {summary['execution_stage']['valid_execution']}/{summary['total']} ({summary['execution_stage']['valid_execution_rate']:.1%})")
    logging.info(f"检查通过: {summary['check_stage']['check_success']}/{summary['total']} ({summary['check_stage']['task_completion_rate']:.1%})")
    logging.info(f"检查失败: {summary['check_stage']['check_failure']}")
    logging.info(f"检查错误: {summary['check_stage']['check_error']}")
    logging.info(f"结果已保存至: {report['output']}")
    logging.info("=" * 60)

    print(json.dumps(report["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
