"""Hot-reloaded skill directions; editing JSON never requires editing Python."""
from functools import lru_cache
import json
from .config import dictionary_path


@lru_cache(maxsize=8)
def _read(path: str, stamp: int, size: int) -> dict:
    payload = json.loads(open(path, encoding="utf-8").read())
    if not isinstance(payload.get("directions"), dict):
        raise ValueError("skills dictionary requires directions")
    result = {}
    for skills in payload["directions"].values():
        for canonical, aliases in skills.items():
            if not isinstance(canonical, str) or not isinstance(aliases, list):
                raise ValueError("invalid dictionary entry")
            result[canonical] = list(dict.fromkeys([canonical, *aliases]))
    return result


def entries() -> dict:
    path = dictionary_path()
    stat = path.stat()
    return _read(str(path), stat.st_mtime_ns, stat.st_size)


def signature() -> tuple:
    path = dictionary_path()
    stat = path.stat()
    return str(path), stat.st_mtime_ns, stat.st_size


def canonical(name: str) -> str:
    low = name.casefold().strip()
    for key, aliases in entries().items():
        if any(low == alias.casefold() for alias in aliases):
            return key
    return name
