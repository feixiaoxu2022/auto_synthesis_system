"""
Auto Synthesis System - CLI入口

Agent自动样本合成系统的命令行界面
"""
import argparse
import sys
from pathlib import Path

from orchestrator import Orchestrator
from agents import ScenarioBuilderAgent


def main():
    parser = argparse.ArgumentParser(
        description="Agent自动样本合成系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py "为会议室预订场景合成评测样本"
  python main.py "为请假审批场景生成样本并执行评测" --work-dir ./my_work
        """
    )

    parser.add_argument(
        "requirement",
        nargs="?",
        help="用户需求描述"
    )

    parser.add_argument(
        "--work-dir",
        default="work",
        help="工作目录 (默认: work)"
    )

    parser.add_argument(
        "--skills-dir",
        default=".claude/skills",
        help="Skills目录 (默认: .claude/skills)"
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

    parser.add_argument(
        "--resume",
        action="store_true",
        help="从最近的checkpoint恢复"
    )

    parser.add_argument(
        "--checkpoint-dir",
        default="checkpoints",
        help="Checkpoint目录 (默认: checkpoints)"
    )

    args = parser.parse_args()

    if not args.requirement and not args.test and not args.resume:
        parser.print_help()
        sys.exit(1)

    # 确保工作目录存在
    work_dir = Path(args.work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    if args.test:
        # 使用Mock Agent测试
        from orchestrator.orchestrator import MockAgent
        print("\n" + "="*60)
        print("测试模式：使用Mock Agent")
        print("="*60)

        orchestrator = Orchestrator(
            agent=MockAgent(should_succeed=True),
            work_dir=str(work_dir),
            checkpoint_dir=args.checkpoint_dir
        )

        result = orchestrator.run("测试需求：合成评测样本")

    elif args.resume:
        # 从checkpoint恢复
        print("\n" + "="*60)
        print("Resume模式：从checkpoint恢复")
        print("="*60)

        # 创建Agent实例
        agent = ScenarioBuilderAgent(
            skills_dir=args.skills_dir,
            model=args.model
        )

        # 恢复orchestrator
        orchestrator = Orchestrator.resume(
            agent=agent,
            work_dir=str(work_dir),
            checkpoint_dir=args.checkpoint_dir
        )

        if orchestrator is None:
            print("错误：没有找到可用的checkpoint")
            sys.exit(1)

        # 如果提供了新的需求，继续执行
        if args.requirement:
            result = orchestrator.continue_with_input(args.requirement)
        else:
            # 只显示状态
            print("\nCheckpoint已恢复，可以使用 continue_with_input() 继续")
            result = orchestrator._build_final_result()

    else:
        # 使用真实Agent
        print("\n" + "="*60)
        print("自动样本合成系统启动")
        print("="*60)
        print(f"用户需求: {args.requirement}")
        print(f"工作目录: {work_dir}")
        print(f"模型: {args.model}")
        print("="*60 + "\n")

        agent = ScenarioBuilderAgent(
            skills_dir=args.skills_dir,
            model=args.model
        )

        orchestrator = Orchestrator(
            agent=agent,
            work_dir=str(work_dir),
            checkpoint_dir=args.checkpoint_dir
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
