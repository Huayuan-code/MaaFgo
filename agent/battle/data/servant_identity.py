"""Local servant identities and names for battle rosters and logs."""
from functools import lru_cache
import json
from pathlib import Path


@lru_cache(maxsize=1)
def _catalog():
    path = Path(__file__).resolve().parents[2] / "custom" / "servant_list.json"
    with path.open(encoding="utf-8-sig") as stream:
        return json.load(stream)["servants"]


@lru_cache(maxsize=1)
def _servant_lookup():
    from chaldea.servant_aliases import build_servant_lookup

    return build_servant_lookup(_catalog())


def canonical_servant_id(servant_id: object) -> str | None:
    """归一有效从者 ID；目录外的正数 ID 保留，未知身份返回 None。"""
    if isinstance(servant_id, bool):
        return None
    if isinstance(servant_id, str):
        servant_id = servant_id.strip()
        if not servant_id.isdecimal():
            return None
        servant_id = int(servant_id)
    if not isinstance(servant_id, int) or servant_id <= 0:
        return None
    sid = str(servant_id)
    servant = _servant_lookup().get(sid)
    return str(servant["id"]) if servant is not None else sid


def servant_name(servant_id):
    return next((item["name"] for item in _catalog()
                 if str(item["id"]) == servant_id), servant_id or "未知")
