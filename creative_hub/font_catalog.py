from __future__ import annotations

from pathlib import Path


FONT_SUFFIXES = {".otf", ".ttf"}
FONT_DIR = Path(__file__).resolve().parent / "assets" / "fonts"


def discover_font_names(folder: Path = FONT_DIR) -> list[str]:
    if not folder.is_dir():
        return []
    names = {
        _font_full_name(path)
        for path in folder.iterdir()
        if path.is_file()
        and path.suffix.lower() in FONT_SUFFIXES
        and not path.name.startswith("AppleColorEmoji-")
    }
    return sorted(name for name in names if name)


def _font_full_name(path: Path) -> str:
    try:
        data = path.read_bytes()
        table_offset = _name_table_offset(data)
        if table_offset is None:
            return path.stem.replace("-", " ")
        count = int.from_bytes(data[table_offset + 2 : table_offset + 4], "big")
        strings_offset = table_offset + int.from_bytes(data[table_offset + 4 : table_offset + 6], "big")
        candidates: dict[int, list[str]] = {}
        for index in range(count):
            record = table_offset + 6 + index * 12
            platform = int.from_bytes(data[record : record + 2], "big")
            name_id = int.from_bytes(data[record + 6 : record + 8], "big")
            length = int.from_bytes(data[record + 8 : record + 10], "big")
            offset = int.from_bytes(data[record + 10 : record + 12], "big")
            raw = data[strings_offset + offset : strings_offset + offset + length]
            if len(raw) != length:
                continue
            encoding = "utf-16-be" if platform in {0, 3} else "mac_roman"
            try:
                value = raw.decode(encoding).strip()
            except UnicodeDecodeError:
                continue
            if value:
                candidates.setdefault(name_id, []).append(value)
        for name_id in (4, 16, 1):
            if candidates.get(name_id):
                return candidates[name_id][0]
    except OSError:
        pass
    return path.stem.replace("-", " ")


def _name_table_offset(data: bytes) -> int | None:
    if len(data) < 12:
        return None
    table_count = int.from_bytes(data[4:6], "big")
    for index in range(table_count):
        record = 12 + index * 16
        if record + 16 > len(data):
            return None
        if data[record : record + 4] == b"name":
            return int.from_bytes(data[record + 8 : record + 12], "big")
    return None
