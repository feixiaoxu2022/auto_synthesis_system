"""
MCP-Benchmark Open Evaluation Framework (skeleton)

提供：
- ServerLauncher：按场景解析 mcpservers.json(.l) 并启动/关闭MCP服务
- CheckRunner：统一调用各场景 env/check.py
- Runner：批量遍历样本，对给定 results 目录进行检查与汇总

注意：本框架不包含“待测Agent”的实现，仅提供评测侧设施。
"""

