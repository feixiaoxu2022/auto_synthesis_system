"""
Auto Synthesis System - CLI入口

双Agent自动样本合成系统的命令行界面
"""
import argparse
import sys
from pathlib import Path

from orchestrator import Orchestrator
from agents import InitAgent, ExecuteAgent


def main():
    parser = argparse.ArgumentParser(
        description="双Agent自动样本合成系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py "设计一个会议室预订场景"
  python main.py "设计一个请假审批场景" --output-dir ./my_outputs
        """
    )

    parser.add_argument(
        "requirement",
        nargs="?",
        help="用户需求描述"
    )

    parser.add_argument(
        "--output-dir",
        default="outputs",
        help="输出目录 (默认: outputs)"
    )

    parser.add_argument(
        "--skills-dir",
        default="skills",
        help="Skills目录 (默认: skills)"
    )

    parser.add_argument(
        "--model",
        default="claude-sonnet-4-5-20250929",
        help="使用的模型 (默认: claude-sonnet-4-5-20250929)"
    )

    parser.add_argument(
        "--test",
        action="store_true",
        help="使用Mock Agent进行测试"
    )

    args = parser.parse_args()

    if not args.requirement and not args.test:
        parser.print_help()
        sys.exit(1)

    # 确保输出目录存在
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.test:
        # 使用Mock Agent测试
        from orchestrator.orchestrator import MockInitAgent, MockExecuteAgent
        print("\n" + "="*60)
        print("测试模式：使用Mock Agent")
        print("="*60)

        orchestrator = Orchestrator(
            init_agent=MockInitAgent(should_succeed=True),
            execute_agent=MockExecuteAgent(result_sequence=["completed"]),
            output_dir=str(output_dir)
        )

        result = orchestrator.run("测试需求：设计一个简单场景")

    else:
        # 使用真实Agent
        print("\n" + "="*60)
        print("自动样本合成系统启动")
        print("="*60)
        print(f"用户需求: {args.requirement}")
        print(f"输出目录: {output_dir}")
        print(f"模型: {args.model}")
        print("="*60 + "\n")

        init_agent = InitAgent(
            output_dir=str(output_dir),
            skills_dir=args.skills_dir,
            model=args.model
        )

        execute_agent = ExecuteAgent(
            skills_dir=args.skills_dir,
            model=args.model
        )

        orchestrator = Orchestrator(
            init_agent=init_agent,
            execute_agent=execute_agent,
            output_dir=str(output_dir)
        )

        result = orchestrator.run(args.requirement)

    # 输出结果
    print("\n" + "="*60)
    print("执行结果")
    print("="*60)
    import json
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
