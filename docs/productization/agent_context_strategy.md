# Agent Context Management Strategy

本文档定义Init Agent和Execute Agent的Context管理策略。两个Agent使用**相同的核心机制**，仅在配置参数上有差异。

---

## 配置参数对比

| 参数 | Init Agent | Execute Agent | 说明 |
|------|-----------|--------------|------|
| **模型** | Claude Opus 4.5 | Claude Sonnet 4.5 | Init需要更强推理，Execute注重执行 |
| **Context Window** | 200K | 1M | Opus 200K, Sonnet 1M |
| **Compact触发阈值** | 150K (75%) | 700K (70%) | 充分利用各自的context window |
| **保留最近N步** | 3 (默认) | 5 (默认) | Execute工作量大，需要更多上下文 |

---

## Context构成（Claude API标准）

### 1. System Prompt
- **Init Agent**: ~2K tokens（角色、职责、约束、Context协议）
- **Execute Agent**: ~2K tokens（角色、职责、约束、Context协议）
- **内容**: 详见各自的system_prompt.md

### 2. Tool Lists
- **共同**: ~1K tokens（Read, Write等文件操作工具）
- **固定**: 不随对话增长

### 3. Messages: List[Dict]
- **格式**: `{"role": "user"/"assistant"/"tool", "content": "...", "tool_calls": [...], "tool_result": {...}}`
- **动态增长**: 核心管理对象

---

## Messages拼装策略

Messages拼装分为两个部分：**History（历史会话）** + **当前会话（最近N步）**

### History（历史会话）

**处理规则**：
- 保留每轮的最后一条 user message 和 assistant message
- **删除所有 tool result**（降低token消耗）

**示例**：
```python
# 原始对话
[
    {"role": "user", "content": "读取文件A"},
    {"role": "tool", "content": "...10K tokens..."},
    {"role": "assistant", "content": "分析结果..."}
]

# History处理后
[
    {"role": "user", "content": "读取文件A"},
    {"role": "assistant", "content": "分析结果..."}
]
```

### 当前会话（最近N步）

**处理规则**：
- **完整保留** user + assistant + tool_result
- **N值可配置**：
  - Init Agent: 默认N=3
  - Execute Agent: 默认N=5

**示例**：
```python
# 最近N步完整保留
recent_messages = current_messages[-(N*2):]
```

### 配置参数

```python
# Init Agent
KEEP_RECENT_STEPS = 3  # 可配置

# Execute Agent
KEEP_RECENT_STEPS = 5  # 可配置
```

---

## Compact压缩策略

当Context使用率超过阈值时，自动触发压缩。

### 触发条件

```python
# Init Agent (Opus 200K)
COMPACT_TRIGGER_THRESHOLD = 150_000  # 150K (75%)
API_HARD_LIMIT = 200_000

# Execute Agent (Sonnet 1M)
COMPACT_TRIGGER_THRESHOLD = 700_000  # 700K (70%)
API_HARD_LIMIT = 1_000_000

if total_tokens > COMPACT_TRIGGER_THRESHOLD:
    trigger_compact()
```

**阈值设计考虑**：
- **Init Agent**: 75%触发，适合深度分析任务，留出足够缓冲
- **Execute Agent**: 70%触发，充分利用Sonnet的1M空间，减少压缩频率

### Compact执行流程

#### 第一步：Mock user消息触发Summary生成

**Mock消息内容**：
```python
compact_prompt = {
    "role": "user",
    "content": """请对当前工作进行总结，保留以下关键信息：
- 当前场景设计/生成组件的核心要点
- Execute Agent反馈的主要问题/评测进度
- 已完成的分析结论/已识别的问题
- 待办事项清单
- 关键路径（execution_output_dir等）

总结格式使用JSON，确保信息完整但简洁。"""
}
```

**为什么要Mock？**
- Claude API要求messages以user消息开头，user/assistant必须交替
- Mock一条user消息，让LLM生成Summary作为assistant回复
- 格式天然正确，时序逻辑清晰

#### 第二步：调用LLM生成Summary

```python
# 将compact_prompt追加到当前messages
messages_for_compact = current_messages + [compact_prompt]

# 调用Claude API生成Summary
response = client.messages.create(
    model="claude-opus-4.5",  # 或 claude-sonnet-4.5
    system=system_prompt,
    messages=messages_for_compact,
    max_tokens=4000,
    temperature=0.0
)

summary_message = {
    "role": "assistant",
    "content": response.content[0].text
}
```

#### 第三步：构建压缩后的messages

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
- 删除：从起始点到触发点之前的所有中间对话
- 保留：Mock消息 + Summary + 最近N步
- 格式：完全符合API协议（user → assistant交替）

#### 第四步：保留最近N步完整对话

```python
# 保留最近N步的完整对话
recent_messages = current_messages[-N*2:]  # N个user-assistant对
```

- **N值**: 可配置参数
  - Init Agent: 默认N=3
  - Execute Agent: 默认N=5
- **运行时行为**: N值在Compact过程中保持不变（不递减）
- **内容**: 完整保留user + assistant + tool_result

**为什么N值保持不变而不递减？**
- 每次Compact应该使用相同策略，确保稳定性
- 避免边界问题和复杂的动态调整逻辑

#### 第五步（可选）：压缩超长Tool Result

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

---

## Summary内容差异

虽然生成机制相同，但两个Agent的Summary侧重点不同：

### Init Agent Summary

```json
{
  "current_design_summary": {
    "unified_scenario_design": "场景设计的核心要点摘要",
    "business_rules_key_points": ["关键业务规则1", "关键业务规则2"],
    "format_specifications": "格式规范摘要"
  },
  "execute_feedback_summary": {
    "execution_output_dir": "scenarios/.../execution_outputs/iteration_12",
    "total_failure_samples": 15,
    "layer1_problems_summary": ["问题类型1：描述", "问题类型2：描述"]
  },
  "analysis_conclusions": [
    "已分析的样本ID和主要发现",
    "识别的设计缺陷和根本原因",
    "已确认需要修改的设计部分"
  ],
  "pending_actions": [
    "需要继续分析的样本",
    "待修改的具体设计内容",
    "需要人工审核的决策点"
  ],
  "key_paths": {
    "execution_output_dir": "...",
    "layer1_problems_report": "..."
  }
}
```

### Execute Agent Summary

```json
{
  "generated_components": {
    "tools": ["tool1.py: 功能描述", "tool2.py: 功能描述"],
    "checkers": ["checker1.py: 检查逻辑", "checker2.py: 检查逻辑"],
    "samples": "已生成15个样本，覆盖3类场景"
  },
  "evaluation_progress": {
    "current_iteration": 5,
    "success_rate": "12/15 (80%)",
    "layer_status": "Layer 3完成，Layer 4进行中"
  },
  "identified_issues": {
    "layer2_problems": ["Tool A返回格式不一致"],
    "layer3_problems": ["Checker B阈值过严"],
    "fix_attempts": ["已修复Tool A，待验证"]
  },
  "pending_work": [
    "继续修复Checker B",
    "重新评测失败样本",
    "如成功率<85%，继续迭代"
  ],
  "key_paths": {
    "execution_output_dir": "scenarios/.../execution_outputs/iteration_5"
  }
}
```

---

## Compact前后对比示例

### Init Agent示例

**Compact前（total_tokens=155K）**：
```python
messages = [
    {"role": "user", "content": "<execute_to_init_context>...</execute_to_init_context>"},
    {"role": "assistant", "content": "收到反馈，开始分析..."},
    {"role": "user", "content": "调用Read工具读取trace"},
    {"role": "tool", "content": "...trace内容..."},
    {"role": "assistant", "content": "发现问题1..."},
    # ... 共10轮对话
]
```

**Compact后（total_tokens≈70K）**：
```python
messages = [
    {"role": "user", "content": "请对当前工作进行总结..."},
    {"role": "assistant", "content": "基于Execute Agent的反馈，我完成了以下分析...\n<compact_summary>{...}</compact_summary>"},
    # 最近3步完整保留（6条消息）
]
```

### Execute Agent示例

**Compact前（total_tokens=720K）**：
```python
messages = [
    {"role": "user", "content": "<init_to_execute_context>...</init_to_execute_context>"},
    {"role": "assistant", "content": "开始生成tools..."},
    # ... 大量生成、评测、修复对话，共100轮
]
```

**Compact后（total_tokens≈200K）**：
```python
messages = [
    {"role": "user", "content": "请对当前工作进行总结..."},
    {"role": "assistant", "content": "我已完成以下工作...\n<compact_summary>{...}</compact_summary>"},
    # 最近5步完整保留（10条消息）
]
```

**关键变化**：
- Execute Agent因为context更大，可以工作更久才触发Compact
- 压缩比更高（720K → 200K），但仍保留足够上下文

---

## 实现注意事项

### 1. Summary生成质量控制

**Mock消息的设计要点**：
- 明确要求保留的信息类型
- 要求使用JSON格式，方便结构化
- 强调"完整但简洁"，避免冗余

**生成参数建议**：
```python
response = client.messages.create(
    model=model_name,  # opus或sonnet
    system=system_prompt,
    messages=messages_for_compact,
    max_tokens=4000,
    temperature=0.0  # 降低随机性
)
```

**质量验证**：
```python
def validate_summary(summary_content: str) -> bool:
    required_keywords = ["current", "progress", "pending", "execution_output_dir"]
    return any(kw in summary_content.lower() for kw in required_keywords)
```

### 2. 边界条件处理

**情况1：刚收到初始Context就触发Compact**
- LLM生成的Summary会反映："已收到输入，准备开始工作"
- 初始Context的关键信息会被包含在Summary中

**情况2：连续多次触发Compact**
- 每次生成新的Mock消息和Summary
- 新的Summary会基于之前的Summary + 最近N步工作生成
- N值保持不变（配置值，不递减）

**情况3：最近N步仍然超过阈值（极端情况）**
- Mock消息 + Summary + 最近N步仍然很大
- 可能原因：最近N步包含大量超长tool_result
- 解决方案：使用第五步的tool result压缩
- 如果还不够：可以考虑增大压缩阈值或人工介入

### 3. 与Read工具的配合

- Summary中保留关键路径
- Agent需要详细信息时，通过Read工具访问落盘文件
- 例如：`Read(f"{execution_output_dir}/samples/{sample_id}.json")`

### 4. 与HITL的配合

**Init Agent**:
- Compact不影响HITL审核流程
- 修改设计后仍需HITL-1批准
- Summary中应包含待人工审核的决策点

**Execute Agent**:
- Compact不影响迭代决策
- 仍需判断何时停止/何时返回Init/何时继续
- Summary中应包含评测进度和决策依据

---

## 总结

两个Agent的Context管理策略核心思想：
1. **Mock user消息触发Summary生成**（符合API协议）
2. **LLM生成Summary**（assistant回复，包含关键信息和路径）
3. **保留最近N步完整对话**（支持连续工作）
4. **依赖落盘数据按需访问**（符合落盘优先原则）

这个设计确保了：
- ✅ 格式正确：user → assistant交替，完全符合Claude API协议
- ✅ 时序逻辑清晰：Mock消息触发，LLM总结已完成的工作
- ✅ Summary质量高：LLM生成的总结比手动拼接更灵活准确
- ✅ Context大小可控：根据各自的context window合理设置阈值
- ✅ 工作状态完整：Summary + 最近N步保留足够上下文
- ✅ 符合Agentic Loop的自主决策理念：Agent可通过Read工具按需访问落盘数据

**两个Agent的差异仅在配置参数，核心机制完全相同，便于维护和理解。**
