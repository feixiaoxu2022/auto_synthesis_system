# Init Agent Compact Strategy

## 目标和原则

### 核心目标
在Init Agent的长时间工作过程中（分析失败样本、修改设计），Context会不断增长。Compact机制的目标是：
- **控制Context大小**：避免超过API限制（200K tokens）
- **保留关键信息**：确保Agent能继续有效工作
- **按需加载数据**：依赖落盘数据，通过Read工具访问

### 设计原则
1. **落盘优先**：所有详细数据已完整落盘，Context删除≠数据丢失
2. **Summary作为工作状态快照**：压缩后生成assistant消息总结当前进展
3. **时序逻辑正确**：Summary反映"已完成的工作"，而非"未来的计划"
4. **保留最近工作**：最近N步完整保留，支持连续工作

## 触发条件

```python
COMPACT_TRIGGER_THRESHOLD = 150_000  # 150K
API_HARD_LIMIT = 200_000            # 200K (Opus)

if total_tokens > COMPACT_TRIGGER_THRESHOLD:
    trigger_compact()
```

- **模型**: Claude Opus 4.5 (200K context window)
- **阈值**: 150K tokens（使用75%空间时触发）
- **触发时机**: 每次API调用前检查
- **自动执行**: 无需人工干预
- **压缩预期**: 150K → 75-90K，留出110-125K工作空间

**阈值设计考虑**：
1. **充分利用空间**：使用75%空间才触发，适合Init Agent的深度分析任务
2. **压缩后足够工作**：剩余110-125K可继续分析5-10个失败样本
3. **减少压缩频率**：避免频繁生成Summary影响工作连续性
4. **安全边际合理**：距离200K限制仍有50K缓冲空间

## Compact执行流程

### 第一步：Mock user消息触发Summary生成

**Mock消息内容**：
```python
compact_prompt = {
    "role": "user",
    "content": """请对当前工作进行总结，保留以下关键信息：
- 当前场景设计的核心要点
- Execute Agent反馈的主要问题
- 已完成的分析结论
- 待办事项清单
- 关键路径（execution_output_dir等）

总结格式使用JSON，确保信息完整但简洁。"""
}
```

**为什么要Mock？**
- Claude API要求messages以user消息开头，user/assistant必须交替
- Mock一条user消息，让LLM生成Summary作为assistant回复
- 格式天然正确，时序逻辑清晰

### 第二步：调用LLM生成Summary

```python
# 将compact_prompt追加到当前messages
messages_for_compact = current_messages + [compact_prompt]

# 调用Claude API生成Summary
response = client.messages.create(
    model="claude-opus-4.5",
    system=system_prompt,
    messages=messages_for_compact,
    max_tokens=4000
)

summary_message = {
    "role": "assistant",
    "content": response.content[0].text
}
```

### 第三步：构建压缩后的messages

```python
# 保留最近N步的完整对话
recent_messages = current_messages[-N*2:]  # N个user-assistant对

# 构建压缩后的messages
compressed_messages = [
    compact_prompt,      # Mock的user消息
    summary_message,     # LLM生成的Summary (assistant)
    *recent_messages     # 最近N步完整对话
]
```

**压缩效果**：
- 删除：从ExecuteToInitContext到触发点之前的所有中间对话
- 保留：Mock消息 + Summary + 最近N步
- 格式：完全符合API协议（user → assistant交替）

### 第四步：保留最近N步完整对话

```python
# 保留最近N步的完整对话
recent_messages = current_messages[-N*2:]  # N个user-assistant对
```

- **N值**: 可配置参数，默认值为3（推荐值，参考Anthropic和Wenning实践）
- **配置示例**: `KEEP_RECENT_STEPS = 3`（可根据场景需求调整为5、7等）
- **运行时行为**: N值在Compact过程中保持不变（不递减）
- **内容**: 完整保留user + assistant + tool_result

**为什么N值保持不变而不递减？**
- 每次Compact应该使用相同策略，确保稳定性
- N=3是常见的平衡点（足够上下文 + 有效压缩），但可根据实际需求调整
- 避免边界问题和复杂的动态调整逻辑

### 第五步（可选）：压缩超长Tool Result

**背景说明**：
- Messages拼装阶段已经删除了History中的所有tool result
- Compact时只有"最近N步"包含tool result
- 这部分本来就会完整保留，通常不需要额外压缩

**何时需要**：
- 最近N步中存在超长tool result（如读取了大型trace文件，>5K tokens）
- 可以截断为 `前1K + ... + 后1K`，保留关键信息

**实现示例**：
```python
def compress_long_tool_results(messages: List[Dict], max_length: int = 5000) -> List[Dict]:
    """可选：压缩超长tool result"""
    for msg in messages:
        if msg.get('role') == 'tool':
            content = msg.get('content', '')
            if len(content) > max_length:
                # 保留前后各1000字符
                prefix = content[:1000]
                suffix = content[-1000:]
                msg['content'] = f"{prefix}\n\n[... {len(content)-2000} chars omitted ...]\n\n{suffix}"
    return messages
```

**注意**：这是额外优化，不是必需步骤。

## Compact前后对比示例

### Compact前（假设当前第10轮，total_tokens=155K）

```python
messages = [
    {"role": "user", "content": "<execute_to_init_context>...</execute_to_init_context>"},
    {"role": "assistant", "content": "收到反馈，开始分析..."},
    {"role": "user", "content": "调用Read工具读取trace"},
    {"role": "tool_result", "content": "...trace内容..."},
    {"role": "assistant", "content": "发现问题1..."},
    {"role": "user", "content": "继续读取下一个trace"},
    {"role": "tool_result", "content": "...trace内容..."},
    {"role": "assistant", "content": "发现问题2..."},
    {"role": "user", "content": "读取BusinessRules"},
    {"role": "tool_result", "content": "..."},
    {"role": "assistant", "content": "当前正在修改设计..."}
]
# total_tokens = 155K，触发Compact
```

### Compact后（N=3保留最近3步，total_tokens≈70K）

```python
messages = [
    # Mock消息触发Summary
    {
        "role": "user",
        "content": "请对当前工作进行总结，保留以下关键信息：当前场景设计核心要点、Execute反馈的主要问题、已完成分析结论、待办事项、关键路径..."
    },
    # LLM生成的Summary
    {
        "role": "assistant",
        "content": """基于Execute Agent的反馈，我完成了以下分析工作：

<compact_summary>
{
  "current_design": "Leave Application场景，包含3类假期...",
  "execute_feedback": {
    "execution_output_dir": "scenarios/leave_application/execution_outputs/iteration_5",
    "total_failures": 15,
    "main_problems": ["余额扣减时机不明确", "checker阈值过严"]
  },
  "analysis_done": [
    "已分析LA_001, LA_005, LA_012三个样本",
    "发现余额扣减规则未明确要求"
  ],
  "pending_tasks": [
    "修改BusinessRules.md添加余额扣减规则",
    "调整checker容忍度到0.01"
  ]
}
</compact_summary>"""
    },
    # 以下是最近3步的完整保留
    {"role": "user", "content": "继续读取下一个trace"},
    {"role": "tool_result", "content": "...trace内容..."},
    {"role": "assistant", "content": "发现问题2..."},
    {"role": "user", "content": "读取BusinessRules"},
    {"role": "tool_result", "content": "..."},
    {"role": "assistant", "content": "当前正在修改设计..."}
]
# total_tokens ≈ 70K，剩余130K可用空间
```

**关键变化**：
- 删除了ExecuteToInitContext和前面7轮对话
- 用Mock消息 + Summary替代（约10-15K tokens）
- 保留最近3步完整对话（约60K tokens）
- Summary中包含关键路径，需要时可以通过Read工具访问落盘数据

## 实现注意事项

### 1. Summary生成质量控制

**Mock消息的设计要点**：
- 明确要求保留的信息类型（设计要点、反馈问题、分析结论、待办事项）
- 要求使用JSON格式，方便结构化
- 强调"完整但简洁"，避免冗余

**生成参数建议**：
```python
response = client.messages.create(
    model="claude-opus-4.5",
    system=system_prompt,
    messages=messages_for_compact,
    max_tokens=4000,        # 给Summary生成足够空间
    temperature=0.0         # 降低随机性，保持一致性
)
```

**质量验证**：
```python
def validate_summary(summary_content: str) -> bool:
    # 检查是否包含关键信息
    required_keywords = ["current_design", "execute_feedback",
                        "analysis", "pending", "execution_output_dir"]
    return any(kw in summary_content.lower() for kw in required_keywords)
```

### 2. 边界条件处理

**情况1：刚收到ExecuteToInitContext就触发Compact**
- 如果还没开始实质工作，LLM生成的Summary会反映："已收到反馈，准备开始分析"
- ExecuteToInitContext的关键信息会被包含在Summary中

**情况2：连续多次触发Compact**
- 每次生成新的Mock消息和Summary
- 新的Summary会基于之前的Summary + 最近N步工作生成
- N值保持不变（配置值，不递减）

**情况3：最近N步仍然超过150K（极端情况）**
- Mock消息 + Summary + 最近N步仍然很大
- 可能原因：最近N步包含大量超长tool_result
- 解决方案：使用第五步的tool result压缩
- 如果还不够：可以考虑增大压缩阈值或人工介入

### 3. 与Execute Agent的一致性

**Execute Agent的Compact策略**：
- Execute Agent也有类似的Compact机制
- Summary内容和结构可以不同（根据各自工作特点）
- 核心原则一致：落盘优先、Summary作为工作状态快照

### 4. 调试和监控

**日志记录**：
```python
logger.info(f"Compact triggered: total_tokens={total_tokens}, KEEP_RECENT_STEPS={N}")
logger.info(f"Summary generated: {len(summary_content)} tokens")
logger.info(f"Messages before: {len(messages_before)}, after: {len(messages_after)}")
```

**质量监控**：
- 监控Compact后Agent的工作质量
- 如果发现Summary信息不足导致工作受阻，调整Summary生成逻辑
- 收集人工反馈，持续优化Summary内容

## 与其他组件的协同

### 与System Prompt的关系
- **System Prompt**: 静态角色定义和协议规范
- **Summary**: 动态工作状态快照
- **时序关系**: System Prompt（静态背景） → ExecuteToInitContext（T0输入） → 工作过程（T0-T1） → Summary（T1总结）

### 与Read工具的配合
- Summary中保留关键路径
- Agent需要详细信息时，通过Read工具访问落盘文件
- 例如：`Read(f"{execution_output_dir}/samples/{sample_id}.json")`

### 与HITL的配合
- Compact不影响HITL审核流程
- 修改设计后仍需HITL-1批准
- Summary中应包含待人工审核的决策点

## 总结

Init Agent的Compact策略核心思想：
1. **Mock user消息触发Summary生成**（符合API协议）
2. **LLM生成Summary**（assistant回复，包含关键信息和路径）
3. **保留最近N步完整对话**（支持连续工作）
4. **依赖落盘数据按需访问**（符合落盘优先原则）

这个设计确保了：
- ✅ 格式正确：user → assistant交替，完全符合Claude API协议
- ✅ 时序逻辑清晰：Mock消息触发，LLM总结已完成的工作
- ✅ Summary质量高：LLM生成的总结比手动拼接更灵活准确
- ✅ Context大小可控：155K → 70K，剩余130K工作空间
- ✅ 工作状态完整：Summary + 最近N步保留足够上下文
- ✅ 符合Agentic Loop的自主决策理念：Agent可通过Read工具按需访问落盘数据
