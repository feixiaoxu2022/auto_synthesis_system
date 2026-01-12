#!/usr/bin/env python3
"""
样本格式验证工具

验证生成的样本是否符合 sample_format_spec.json 规范
"""
import json
import sys
from pathlib import Path


def validate_sample(sample: dict) -> tuple[bool, list[str]]:
    """
    验证单个样本格式
    
    Returns:
        (is_valid, errors)
    """
    errors = []
    
    # 必需字段检查
    required_fields = ["data_id", "query", "system", "servers", "environment", "check_list"]
    for field in required_fields:
        if field not in sample:
            errors.append(f"❌ 缺少必需字段: {field}")
    
    # 字段类型检查
    if "data_id" in sample and not isinstance(sample["data_id"], str):
        errors.append(f"❌ data_id 必须是字符串")
    
    if "query" in sample and not isinstance(sample["query"], str):
        errors.append(f"❌ query 必须是字符串")
    
    if "system" in sample and not isinstance(sample["system"], str):
        errors.append(f"❌ system 必须是字符串")
    
    if "servers" in sample:
        if not isinstance(sample["servers"], list):
            errors.append(f"❌ servers 必须是列表")
        elif len(sample["servers"]) == 0:
            errors.append(f"❌ servers 不能为空")
    
    if "environment" in sample:
        if not isinstance(sample["environment"], list):
            errors.append(f"❌ environment 必须是列表")
        else:
            for i, env_item in enumerate(sample["environment"]):
                if not isinstance(env_item, dict):
                    errors.append(f"❌ environment[{i}] 必须是对象")
                    continue
                if "path" not in env_item:
                    errors.append(f"❌ environment[{i}] 缺少 path 字段")
                if "type" not in env_item:
                    errors.append(f"❌ environment[{i}] 缺少 type 字段")
                if "content" not in env_item:
                    errors.append(f"❌ environment[{i}] 缺少 content 字段")
    
    if "check_list" in sample:
        if not isinstance(sample["check_list"], list):
            errors.append(f"❌ check_list 必须是列表")
        elif len(sample["check_list"]) == 0:
            errors.append(f"❌ check_list 不能为空")
        else:
            for i, check_item in enumerate(sample["check_list"]):
                if not isinstance(check_item, dict):
                    errors.append(f"❌ check_list[{i}] 必须是对象")
                    continue
                if "check_type" not in check_item:
                    errors.append(f"❌ check_list[{i}] 缺少 check_type")
                if "params" not in check_item:
                    errors.append(f"❌ check_list[{i}] 缺少 params")
    
    # 检查是否有不应该存在的字段
    invalid_fields = ["sample_id", "template_id", "complexity", "description", 
                      "user_need", "initial_state", "metadata"]
    for field in invalid_fields:
        if field in sample:
            errors.append(f"⚠️  使用了错误的字段名: {field} (应该使用规范中的字段)")
    
    return len(errors) == 0, errors


def validate_jsonl_file(filepath: Path) -> dict:
    """
    验证JSONL样本文件

    Args:
        filepath: JSONL文件路径

    Returns:
        {
            "valid": bool,
            "total_samples": int,
            "valid_samples": int,
            "errors": list[str],  # 所有错误列表
            "error_summary": str  # 错误摘要
        }
    """
    if not filepath.exists():
        return {
            "valid": False,
            "total_samples": 0,
            "valid_samples": 0,
            "errors": [f"文件不存在: {filepath}"],
            "error_summary": "文件不存在"
        }

    total_samples = 0
    valid_samples = 0
    all_errors = []

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                if not line.strip():
                    continue

                try:
                    sample = json.loads(line)
                    total_samples += 1

                    is_valid, errors = validate_sample(sample)

                    if is_valid:
                        valid_samples += 1
                    else:
                        # 添加样本标识到错误信息
                        sample_id = sample.get('data_id') or sample.get('sample_id', f'Line {line_num}')
                        for error in errors:
                            all_errors.append(f"[{sample_id}] {error}")

                except json.JSONDecodeError as e:
                    all_errors.append(f"[Line {line_num}] JSON解析失败: {e}")

        # 构建结果
        is_valid = len(all_errors) == 0

        if is_valid:
            error_summary = ""
        else:
            error_count = len(all_errors)
            invalid_count = total_samples - valid_samples
            error_summary = f"发现 {error_count} 个格式问题 (影响 {invalid_count}/{total_samples} 个样本)"

        return {
            "valid": is_valid,
            "total_samples": total_samples,
            "valid_samples": valid_samples,
            "errors": all_errors,
            "error_summary": error_summary
        }

    except Exception as e:
        return {
            "valid": False,
            "total_samples": 0,
            "valid_samples": 0,
            "errors": [f"读取文件失败: {str(e)}"],
            "error_summary": "读取文件失败"
        }


def main():
    if len(sys.argv) < 2:
        print("用法: python validate_sample_format.py <samples.jsonl>")
        sys.exit(1)

    samples_file = Path(sys.argv[1])
    print(f"验证样本文件: {samples_file}\n")

    result = validate_jsonl_file(samples_file)

    print("="*60)
    print(f"总样本数: {result['total_samples']}")
    print(f"✅ 格式正确: {result['valid_samples']}")
    print(f"❌ 格式错误: {result['total_samples'] - result['valid_samples']}")

    if not result['valid']:
        print(f"\n{result['error_summary']}")
        print("\n详细错误:")
        for error in result['errors']:
            print(f"  - {error}")
        sys.exit(1)
    else:
        print("\n✅ 所有样本格式正确")
        sys.exit(0)


if __name__ == "__main__":
    main()
