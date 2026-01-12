# 快速开始 - 图标使用指南

## 📂 目录位置
```
docs/productization/assets/icons/
```

## 🚀 查看所有图标

### 方法1: 浏览器预览（推荐）
在浏览器中打开 `gallery.html` 文件，可以看到：
- ✅ 所有可用图标的实时预览
- ✅ 不同尺寸演示（20px、24px、30px）
- ✅ 不同配色演示（橙色、绿色、蓝色）
- ✅ 待添加图标的占位提示

```bash
# macOS打开
open docs/productization/assets/icons/gallery.html

# 或直接拖到浏览器中
```

### 方法2: 查看README
```bash
cat docs/productization/assets/icons/README.md
```

---

## 💡 使用示例

### 1. 在SVG架构图中使用

**步骤1**: 在 `<defs>` 中定义图标
```svg
<defs>
  <!-- 定义可复用的图标 -->
  <symbol id="hitl-icon" viewBox="0 0 24 24">
    <path stroke="none" d="M0 0h24v24H0z" fill="none"/>
    <path d="M8 7a4 4 0 1 0 8 0a4 4 0 0 0 -8 0" stroke="#ff8c00" stroke-width="2"/>
    <!-- ... user-cog.svg的其他路径 -->
  </symbol>
</defs>
```

**步骤2**: 在需要的位置使用
```svg
<!-- 大尺寸（主要标注） -->
<use href="#hitl-icon" x="100" y="100" width="30" height="30"/>

<!-- 小尺寸（次要说明） -->
<use href="#hitl-icon" x="200" y="200" width="20" height="20"/>
```

### 2. 在HTML文档中使用

**方式A**: 直接内嵌SVG
```html
<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#ff8c00">
  <!-- 复制 user-cog.svg 的路径内容 -->
</svg>
```

**方式B**: 使用 `<img>` 标签
```html
<img src="assets/icons/user-cog.svg" width="24" height="24" alt="HITL">
```

**方式C**: CSS背景图
```css
.hitl-icon {
  width: 24px;
  height: 24px;
  background: url('assets/icons/user-cog.svg') no-repeat center;
  background-size: contain;
}
```

---

## 🎨 配色指南

### 当前使用的配色方案
- **橙色 `#ff8c00`**: Human-in-the-Loop（与human-box背景匹配）
- **绿色 `#52c41a`**: Execute Phase / 成功状态
- **蓝色 `#1890ff`**: Init Phase / 信息状态
- **紫色 `#722ed1`**: Skills知识库
- **粉色 `#eb2f96`**: 决策层 / 反馈路径

### 灵活配色
使用 `stroke="currentColor"` 可以继承父元素的文字颜色：
```svg
<svg stroke="currentColor">
  <!-- 图标会自动匹配周围文字颜色 -->
</svg>
```

---

## 📝 添加新图标的流程

1. **找到合适的图标**
   - 推荐网站：https://tabler-icons.io/
   - 确保是开源许可（MIT/ISC）

2. **保存SVG文件**
   ```bash
   # 保存到icons目录
   vi docs/productization/assets/icons/new-icon.svg
   ```

3. **更新README.md**
   - 在"图标清单"中添加新图标说明
   - 包括：用途、来源、使用场景、尺寸建议

4. **更新gallery.html**
   - 添加新的图标预览卡片
   - 展示不同尺寸和配色

5. **在架构图中使用**（可选）
   - 在 `architecture_agentic_loop.svg` 的 `<defs>` 中定义
   - 在需要的位置用 `<use>` 引用

---

## 🔍 常见问题

### Q1: 图标显示不全或变形？
A: 确保 `viewBox="0 0 24 24"` 设置正确，这是24x24的基准尺寸。

### Q2: 如何修改图标颜色？
A: 修改 `stroke` 属性：
```svg
<path stroke="#ff0000" />  <!-- 红色 -->
```

### Q3: 图标太小/太大？
A: 调整 `width` 和 `height`：
- 小型标注: 20x20px
- 标准尺寸: 24x24px
- 大型标注: 30x30px
- 超大展示: 48x48px

### Q4: 在不同背景下如何保证可见性？
A: 使用对比色或添加背景：
```svg
<!-- 添加白色背景圆圈 -->
<circle cx="12" cy="12" r="11" fill="white"/>
<use href="#hitl-icon" x="0" y="0" width="24" height="24"/>
```

---

## 📚 参考资源

- **Tabler Icons官网**: https://tabler-icons.io/
- **SVG优化工具**: https://jakearchibald.github.io/svgomg/
- **MDN SVG教程**: https://developer.mozilla.org/en-US/docs/Web/SVG
- **当前项目架构图**: `docs/productization/architecture_agentic_loop.svg`

---

**提示**: 每次添加新图标后，记得在 `gallery.html` 中更新预览，方便团队成员快速查看！
