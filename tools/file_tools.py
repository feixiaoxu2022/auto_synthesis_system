"""
文件操作工具集 - 基于Wenning实现适配

包含：file_reader, file_writer, file_editor
"""
import json
import csv
import mimetypes
from pathlib import Path
from typing import Dict, Any, Optional, List
import difflib


class FileReader:
    """文件读取工具 - 支持多种格式"""

    name = "file_reader"
    description = "读取文件内容，支持Text、JSON、CSV、Excel、PDF等格式，自动识别类型"

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir

    def _safe_path(self, filename: str) -> Path:
        """安全路径检查：支持相对路径和绝对路径"""
        p = Path(filename)

        # 绝对路径直接使用
        if p.is_absolute():
            return p

        # 检查路径穿越
        if ".." in p.parts:
            raise ValueError("不允许使用'..'进行路径穿越")

        return self.base_dir / filename

    def _infer_mode(self, filename: str) -> str:
        """自动推断文件类型"""
        ext = Path(filename).suffix.lower()
        if ext in [".txt", ".md", ".log", ".jsonl", ".yaml", ".yml", ".py"]:
            return "text"
        if ext == ".json":
            return "json"
        if ext in [".csv", ".tsv"]:
            return "csv"
        if ext in [".xls", ".xlsx"]:
            return "excel"
        if ext == ".pdf":
            return "pdf"
        if ext in [".png", ".jpg", ".jpeg", ".gif"]:
            return "binary"
        return "text"  # 默认文本

    def _read_text(self, path: Path, encoding: str, max_bytes: int, max_lines: int) -> Dict[str, Any]:
        """读取文本文件"""
        data = path.open("rb").read(max_bytes)
        text = data.decode(encoding, errors="replace")
        lines = text.splitlines()
        truncated = path.stat().st_size > len(data) or len(lines) > max_lines
        if len(lines) > max_lines:
            lines = lines[:max_lines]
        return {"content": "\n".join(lines), "truncated": truncated}

    def _read_json(self, path: Path, encoding: str, max_bytes: int) -> Dict[str, Any]:
        """读取JSON文件"""
        size = path.stat().st_size
        if size <= max_bytes:
            try:
                with path.open("r", encoding=encoding, errors="replace") as f:
                    content = json.load(f)
                return {"content": content, "truncated": False}
            except Exception as e:
                return {"error": f"JSON解析失败: {e}", "truncated": False}
        else:
            with path.open("r", encoding=encoding, errors="replace") as f:
                head = f.read(max_bytes)
            return {"content": head, "truncated": True}

    def _read_csv(self, path: Path, encoding: str, rows: int) -> Dict[str, Any]:
        """读取CSV文件"""
        out_rows: List[List[str]] = []
        headers: Optional[List[str]] = None
        try:
            with path.open("r", encoding=encoding, errors="replace", newline="") as f:
                sample = f.read(2048)
                f.seek(0)
                try:
                    dialect = csv.Sniffer().sniff(sample)
                except Exception:
                    dialect = csv.excel
                reader = csv.reader(f, dialect)
                for i, row in enumerate(reader):
                    if i == 0:
                        headers = row
                    else:
                        out_rows.append(row)
                    if i >= rows:
                        break
        except Exception as e:
            return {"error": f"CSV读取失败: {e}"}
        return {"headers": headers, "rows": out_rows, "truncated": True}

    def _read_binary(self, path: Path) -> Dict[str, Any]:
        """读取二进制文件元信息"""
        size = path.stat().st_size
        mime, _ = mimetypes.guess_type(path.name)
        meta = {"size": size, "mime": mime or "application/octet-stream"}
        return {"meta": meta}

    def execute(self, filename: str, max_lines: int = 1000, max_bytes: int = 200000,
                encoding: str = "utf-8", mode: str = "auto") -> Dict[str, Any]:
        """执行文件读取"""
        path = self._safe_path(filename)
        if not path.exists():
            return {"error": f"文件不存在: {filename}"}

        file_mode = mode if mode != "auto" else self._infer_mode(filename)
        data: Dict[str, Any] = {"filename": filename, "type": file_mode, "path": str(path)}

        if file_mode == "text":
            data.update(self._read_text(path, encoding, max_bytes, max_lines))
        elif file_mode == "json":
            data.update(self._read_json(path, encoding, max_bytes))
        elif file_mode == "csv":
            data.update(self._read_csv(path, encoding, max_lines))
        elif file_mode == "binary":
            data.update(self._read_binary(path))
        else:
            data.update(self._read_text(path, encoding, max_bytes, max_lines))

        return data


class FileWriter:
    """文件写入工具"""

    name = "file_writer"
    description = "创建新文件或覆盖已有文件"

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir

    def _safe_path(self, filename: str) -> Path:
        """安全路径检查"""
        p = Path(filename)
        if p.is_absolute() or ".." in p.parts:
            raise ValueError("仅允许相对路径，不允许绝对路径或'..'")
        return self.base_dir / filename

    def execute(self, filename: str, content: str, encoding: str = "utf-8",
                overwrite: bool = True) -> Dict[str, Any]:
        """执行文件写入"""
        path = self._safe_path(filename)

        # 检查是否已存在
        existed = path.exists()
        if existed and not overwrite:
            return {"error": f"文件已存在: {filename}，设置overwrite=true可覆盖"}

        # 确保目录存在
        path.parent.mkdir(parents=True, exist_ok=True)

        # 写入文件
        path.write_text(content, encoding=encoding)

        return {
            "success": True,
            "filename": filename,
            "path": str(path),
            "file_size": path.stat().st_size,
            "lines": content.count('\n') + 1 if content else 0,
            "action": "overwritten" if existed else "created"
        }


class FileEditor:
    """文件编辑工具 - 支持字符串替换和行范围编辑"""

    name = "file_editor"
    description = "编辑已有文件，支持精确字符串替换和行范围编辑两种模式"

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir

    def _safe_path(self, filename: str) -> Path:
        """安全路径检查"""
        p = Path(filename)
        if p.is_absolute() or ".." in p.parts:
            raise ValueError("仅允许相对路径")
        return self.base_dir / filename

    def execute_replace(self, filename: str, old_string: str, new_string: str,
                       replace_all: bool = False, encoding: str = "utf-8") -> Dict[str, Any]:
        """模式1：精确字符串替换"""
        path = self._safe_path(filename)
        if not path.exists():
            return {"error": f"文件不存在: {filename}"}

        content = path.read_text(encoding=encoding)

        if old_string not in content:
            return {"error": f"未找到要替换的字符串: {old_string[:100]}..."}

        # 检查唯一性
        if not replace_all and content.count(old_string) > 1:
            return {"error": f"找到多个匹配项（{content.count(old_string)}个），请提供更具体的old_string或设置replace_all=true"}

        # 执行替换
        if replace_all:
            new_content = content.replace(old_string, new_string)
            count = content.count(old_string)
        else:
            new_content = content.replace(old_string, new_string, 1)
            count = 1

        path.write_text(new_content, encoding=encoding)

        return {
            "success": True,
            "mode": "string_replace",
            "filename": filename,
            "path": str(path),
            "replacements": count
        }

    def execute_line_range(self, filename: str, start_line: int, end_line: int,
                          new_content: str, verify_context: str = None,
                          encoding: str = "utf-8") -> Dict[str, Any]:
        """模式2：行范围编辑"""
        path = self._safe_path(filename)
        if not path.exists():
            return {"error": f"文件不存在: {filename}"}

        lines = path.read_text(encoding=encoding).splitlines(keepends=True)
        total_lines = len(lines)

        # 验证行号
        if start_line < 1 or end_line < 1:
            return {"error": f"行号必须从1开始"}
        if start_line > total_lines or end_line > total_lines:
            return {"error": f"行号超出范围，文件共{total_lines}行"}
        if start_line > end_line:
            return {"error": f"start_line不能大于end_line"}

        # 可选：验证上下文
        if verify_context:
            context_lines = ''.join(lines[start_line-1:end_line])
            if verify_context not in context_lines:
                return {"error": f"上下文验证失败：在第{start_line}-{end_line}行未找到指定内容"}

        # 保存原始内容用于diff
        old_content = ''.join(lines[start_line-1:end_line])

        # 执行替换
        new_lines = []
        new_lines.extend(lines[:start_line-1])
        if new_content and not new_content.endswith('\n') and lines and lines[-1].endswith('\n'):
            new_content = new_content + '\n'
        new_lines.append(new_content)
        new_lines.extend(lines[end_line:])

        path.write_text(''.join(new_lines), encoding=encoding)

        # 生成diff
        diff = list(difflib.unified_diff(
            old_content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=f"{filename} (lines {start_line}-{end_line})",
            tofile=f"{filename} (new)",
            lineterm=''
        ))

        return {
            "success": True,
            "mode": "line_range",
            "filename": filename,
            "path": str(path),
            "lines_replaced": end_line - start_line + 1,
            "diff": '\n'.join(diff[:20]) if diff else "(no visible changes)"
        }
