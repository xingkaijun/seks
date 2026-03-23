from db import fetch_all
from schemas import ScopeFileOption, ScopeOptionsResponse


def _folder_from_path(file_path: str) -> str:
    cleaned = file_path.strip().rstrip("/")
    if not cleaned:
        return ""
    if "/" not in cleaned:
        return "."
    folder = cleaned.rsplit("/", 1)[0]
    return folder or "/"


def list_scope_options() -> ScopeOptionsResponse:
    rows = fetch_all("SELECT id, title, file_path FROM books ORDER BY title ASC, id ASC")
    files: list[ScopeFileOption] = []
    folders: set[str] = set()

    for row in rows:
        file_path = (row.get("file_path") or "").strip()
        if not file_path:
            continue
        files.append(
            ScopeFileOption(
                book_id=row["id"],
                title=row.get("title") or "未命名",
                file_path=file_path,
            )
        )
        folder = _folder_from_path(file_path)
        if folder:
            folders.add(folder)

    return ScopeOptionsResponse(folders=sorted(folders), files=files)
