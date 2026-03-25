import os
from pathlib import Path
from db import fetch_all

LIBRARY_DIR = Path(os.getenv("LIBRARY_DIR", "/data/library"))
SUPPORTED_EXT = {".pdf", ".txt", ".md", ".docx"}

def scan_library_tree() -> list[dict]:
    """扫描 LIBRARY_DIR，返回嵌套目录树，标注已索引状态"""
    indexed = {}
    rows = fetch_all("SELECT file_path, id, title FROM books")
    for r in rows:
        indexed[r["file_path"]] = {"book_id": r["id"], "title": r["title"]}

    def _scan(path: Path) -> list[dict]:
        items = []
        try:
            entries = sorted(path.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        except PermissionError:
            return items
        for entry in entries:
            if entry.name.startswith("."):
                continue
            if entry.is_dir():
                children = _scan(entry)
                if children:  # 仅包含有内容的目录
                    items.append({
                        "name": entry.name,
                        "path": str(entry),
                        "type": "dir",
                        "children": children,
                    })
            elif entry.suffix.lower() in SUPPORTED_EXT:
                info = indexed.get(str(entry), {})
                items.append({
                    "name": entry.name,
                    "path": str(entry),
                    "type": "file",
                    "indexed": bool(info),
                    "book_id": info.get("book_id"),
                    "title": info.get("title"),
                })
        return items

    if not LIBRARY_DIR.exists():
        return []
    return _scan(LIBRARY_DIR)
