import json
import os
import subprocess
from pathlib import Path
from typing import Dict, Optional, Union


class CheckRunner:
    """
    统一封装各场景 env/check.py 的调用方式。

    约定：
    - check.py 支持 --bench 与 --result 两个参数
    - 可能需要 --model/--base-url/--api-key（若包含 LLM Judge）
    - 默认输出 check_result.json（也允许 --output 覆写）
    """

    def __init__(
        self,
        check_script: Union[str, Path],
        work_dir: Optional[Union[str, Path]] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        self.check_script = str(check_script)
        self.work_dir = str(work_dir) if work_dir else None
        # 统一模型配置加载（model + provider）
        self.model = model
        self.base_url = base_url
        self.api_key = api_key

    def run(
        self,
        bench_file: Union[str, Path],
        result_file: Union[str, Path],
        output_file: Optional[Union[str, Path]] = None,
    ) -> Dict:
        # 若未显式提供，加载 benchkit 模型配置
        if not (self.model and (self.base_url or os.getenv("BENCH_CHECK_PROVIDER"))):
            try:
                # 兼容包/脚本两种导入
                try:
                    from .model_config import load_model_config
                except Exception:
                    from model_config import load_model_config  # type: ignore
                mc = load_model_config(kind="judge")
                self.model = self.model or mc.model
                # 对于多数 checker，优先 base_url + api_key；provider 仅用于少数需要
                self.base_url = self.base_url or mc.base_url
                self.api_key = self.api_key or mc.api_key
            except Exception:
                pass

        # 读取result.json获取env_dir（支持选项2：在result中指定环境路径）
        env_dir = None
        try:
            with open(result_file, 'r', encoding='utf-8') as f:
                result_data = json.load(f)
                env_dir = result_data.get("env_dir")
        except Exception:
            pass

        # 使用绝对路径避免cwd导致的路径问题
        check_script_abs = Path(self.check_script).absolute()
        cmd = [
            "python",
            str(check_script_abs),
            "--bench",
            str(Path(bench_file).absolute()),
            "--result",
            str(Path(result_file).absolute()),
        ]
        if self.model:
            cmd += ["--model", self.model]
        if self.base_url:
            cmd += ["--base-url", self.base_url]
        if self.api_key:
            cmd += ["--api-key", self.api_key]
        # 支持env_dir：传递给checker的--work-dir参数（使用绝对路径）
        if env_dir:
            env_path = Path(env_dir).absolute()
            if env_path.exists():
                cmd += ["--work-dir", str(env_path)]
        # 注：若某些场景的 checker 还要求 provider，可在此补充 --provider 传入（当前通用checker未要求）
        # provider = os.getenv("BENCH_CHECK_PROVIDER")
        # if provider:
        #     cmd += ["--provider", provider]
        if output_file:
            cmd += ["--output", str(Path(output_file).absolute())]

        # 不设置cwd，避免在某些环境下os.getcwd()失败（litellm导入时会调用）
        # 所有路径都已转换为绝对路径，不需要依赖工作目录
        # 传递环境变量给子进程（GitHub场景需要GITHUB_PERSONAL_ACCESS_TOKEN等）
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', env=os.environ.copy())
        if proc.returncode != 0:
            raise RuntimeError(f"check脚本执行失败: {proc.returncode}\nSTDOUT:{proc.stdout}\nSTDERR:{proc.stderr}")

        # 优先读显式 output_file，否则默认文件名
        out_path = Path(output_file) if output_file else Path(self.work_dir or ".") / "check_result.json"
        if not out_path.exists():
            # 某些场景直接在stdout打印JSON结果，尝试解析
            try:
                return json.loads(proc.stdout.strip())
            except Exception:
                pass
            raise FileNotFoundError(f"未发现检查结果文件: {out_path}")

        with open(out_path, "r", encoding="utf-8") as f:
            return json.load(f)


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="批量运行Checker评测")
    parser.add_argument("--scenario", required=True, help="场景目录路径")
    parser.add_argument("--results-dir", required=True, help="Agent执行结果目录")
    parser.add_argument("--output-dir", required=True, help="Checker结果输出目录")
    parser.add_argument("--limit", type=int, help="限制评测数量")
    parser.add_argument("--model", help="LLM Judge模型名称")
    parser.add_argument("--base-url", help="LLM Judge API URL")
    parser.add_argument("--api-key", help="LLM Judge API密钥")

    args = parser.parse_args()

    scenario_dir = Path(args.scenario)
    results_dir = Path(args.results_dir)
    output_dir = Path(args.output_dir)

    # 查找checker脚本
    checker_script = scenario_dir / "checker.py"
    if not checker_script.exists():
        print(f"错误：未找到checker脚本 {checker_script}")
        sys.exit(1)

    # 查找样本文件
    samples_file = scenario_dir / "samples" / "eval.jsonl"
    if not samples_file.exists():
        print(f"错误：未找到样本文件 {samples_file}")
        sys.exit(1)

    # 创建输出目录
    cases_dir = output_dir / "cases"
    cases_dir.mkdir(parents=True, exist_ok=True)

    # 加载样本
    samples = []
    with open(samples_file, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                samples.append(json.loads(line))

    if args.limit:
        samples = samples[:args.limit]

    # 创建CheckRunner
    runner = CheckRunner(
        check_script=checker_script,
        work_dir=scenario_dir,
        model=args.model,
        base_url=args.base_url,
        api_key=args.api_key
    )

    # 批量评测
    success_count = 0
    error_count = 0
    import tempfile

    for sample in samples:
        data_id = sample.get("data_id")
        result_file = results_dir / f"{data_id}.json"

        if not result_file.exists():
            print(f"跳过 {data_id}: 结果文件不存在")
            continue

        output_file = cases_dir / f"check_{data_id}.json"

        # 为每个样本创建临时bench.json文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as tmp:
            json.dump(sample, tmp, ensure_ascii=False, indent=2)
            tmp_bench_file = tmp.name

        try:
            print(f"评测 {data_id}...")
            check_result = runner.run(
                bench_file=tmp_bench_file,
                result_file=result_file,
                output_file=output_file
            )
            success_count += 1
            overall_result = check_result.get("overall_result", "Unknown")
            print(f"  ✓ {data_id}: {overall_result}")
        except Exception as e:
            error_count += 1
            print(f"  ✗ {data_id}: {e}")
        finally:
            # 清理临时文件
            try:
                Path(tmp_bench_file).unlink()
            except Exception:
                pass

    print(f"\n评测完成: 成功 {success_count}, 失败 {error_count}")
