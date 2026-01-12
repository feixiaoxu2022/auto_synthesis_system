# 图标资源库

## 📂 目录结构

```
assets/icons/
├── README.md           # 本文档
├── user-cog.svg        # Human-in-the-Loop (HITL) 图标
└── (未来会持续添加)
```

---

## 🎨 图标清单

### 1. user-cog.svg
**用途**: Human-in-the-Loop (HITL) / 人工介入点标识

**来源**: Tabler Icons (icon-tabler-user-cog)

**描述**:
- 结合人形剪影和齿轮元素
- 表示人工参与系统流程/人机协作
- 适用于标注需要人工Review、确认、决策的环节

**使用场景**:
- ✅ Checkpoint标注（架构图中的4个人工介入点）
- ✅ 审批流程图
- ✅ 人工校验环节
- ✅ 用户配置/设置界面

**尺寸建议**:
- 大型标注: 30x30px (主要Checkpoint)
- 小型标注: 20x20px (次要说明)
- 按钮/UI: 24x24px (标准尺寸)

**颜色方案**:
- 当前使用: `#ff8c00` (橙色，匹配human-box背景)
- 建议配色: `stroke="currentColor"` 可灵活适配主题

**SVG代码示例**:
```svg
<!-- 在defs中定义为可复用symbol -->
<symbol id="hitl-icon" viewBox="0 0 24 24">
  <path stroke="none" d="M0 0h24v24H0z" fill="none"/>
  <path d="M8 7a4 4 0 1 0 8 0a4 4 0 0 0 -8 0" stroke="#ff8c00" stroke-width="2"/>
  <!-- ... 其他路径 -->
</symbol>

<!-- 使用时 -->
<use href="#hitl-icon" x="100" y="100" width="30" height="30"/>
```

**已应用位置**:
- `docs/productization/architecture_agentic_loop.svg`
  - Checkpoint 1: Layer 1人工Review (x=1310, y=450, 30x30)
  - Checkpoint 2: Layer 2测试失败 (x=1070, y=772, 20x20)
  - Checkpoint 3: Layer 4归因校验 (x=1070, y=1092, 20x20)
  - Checkpoint 4: Layer 1问题 (x=760, y=1530, 30x30)

---

## 📋 待添加图标清单

以下是未来可能需要的图标类型：

### Agent相关
- [ ] `robot.svg` - AI Agent / 自动化流程
- [ ] `brain.svg` - LLM推理 / 智能决策
- [ ] `terminal.svg` - 命令行 / 脚本执行

### 流程控制
- [ ] `git-branch.svg` - 分支决策 / 路由
- [ ] `refresh-cw.svg` - 迭代循环 / 重试
- [ ] `check-circle.svg` - 验证通过 / 质量达标
- [ ] `alert-circle.svg` - 异常 / 需要注意
- [ ] `x-circle.svg` - 失败 / 错误

### 数据流
- [ ] `database.svg` - 数据存储 / checkpoint
- [ ] `file-text.svg` - 文档 / 配置文件
- [ ] `code.svg` - 代码生成 / 工具
- [ ] `package.svg` - 组件 / 模块

### 评测相关
- [ ] `target.svg` - 目标 / Ground Truth
- [ ] `bar-chart.svg` - 评测报告 / 统计
- [ ] `search.svg` - 归因分析 / 问题定位
- [ ] `layers.svg` - 分层架构

### 知识库
- [ ] `book-open.svg` - Skills知识库
- [ ] `lightbulb.svg` - 最佳实践 / 经验
- [ ] `bookmark.svg` - 参考样本

---

## 🔧 使用规范

### 文件命名
- 使用小写字母和连字符：`icon-name.svg`
- 名称要清晰表达用途：`user-cog` 而非 `icon1`

### SVG规范
- viewBox统一为 `0 0 24 24`（24x24基准）
- 使用 `stroke="currentColor"` 便于动态配色
- 保持路径简洁，避免过度复杂的图形
- 包含必要的无障碍属性（title、desc）

### 版权说明
- 所有图标应注明来源
- 优先使用开源图标库：
  - [Tabler Icons](https://tabler-icons.io/) (MIT License)
  - [Lucide](https://lucide.dev/) (ISC License)
  - [Heroicons](https://heroicons.com/) (MIT License)
  - [Feather Icons](https://feathericons.com/) (MIT License)

---

## 📚 参考资源

- **Tabler Icons**: https://tabler-icons.io/
- **SVG优化工具**: https://jakearchibald.github.io/svgomg/
- **SVG使用指南**: https://developer.mozilla.org/en-US/docs/Web/SVG

---

**维护者**: Universal Scenario Framework Team
**最后更新**: 2025-12-31
**版本**: v1.0
