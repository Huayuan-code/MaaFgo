#!/usr/bin/env python3
"""在 APK 的 Python 环境验收 Chaldea 数据与本地库存；不连接控制器或操作游戏。

在 PI 根运行，或通过 --pi-root 指定。默认禁止联网、禁止写文件；
--allow-download 仅允许真实 Chaldea 客户端首次下载并写入队伍缓存。
标准输出始终是一份 JSON，失败退出码为 1。可用 --section 分别验收。
"""

from __future__ import annotations

import argparse
from contextlib import ExitStack, redirect_stdout
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch
import urllib.request


DEFAULT_SOURCE = "https://link.chaldea.center/laplace/share?id=72098"


class CapturedOutput(io.StringIO):
    # mfaalog 在导入时会配置 stdout 编码；StringIO 本身没有该方法。
    def reconfigure(self, **_kwargs):
        pass


def resolved(root: Path, value: str) -> Path:
    path = Path(value)
    return (path if path.is_absolute() else root / path).resolve()


def fingerprint(data) -> str:
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def file_info(path: Path) -> dict:
    raw = path.read_bytes()
    return {"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def offline_client(stack: ExitStack, chaldea):
    """阻断业务入口的网络函数；保留真实解码、缓存和转换实现。"""
    message = "本次检查禁止网络函数调用"
    return [stack.enter_context(patch.object(chaldea, name, side_effect=AssertionError(message)))
            for name in ("fetch_team_by_id", "fetch_teams_by_quest")]


def check_chaldea(args, root: Path) -> dict:
    import chaldea
    from battle.data.chaldea_converter import convert_chaldea_actions_to_battle_plan
    from chaldea.chaldea_client import parse_import_source
    from chaldea.servant_aliases import build_servant_lookup
    from chaldea.support_criteria import build_support_criteria

    cache_dir = resolved(root, args.cache_dir)
    before = {str(p): file_info(p)["sha256"] for p in cache_dir.glob("*.json")}
    with patch.object(chaldea, "CACHE_DIR", str(cache_dir)):
        with ExitStack() as stack:
            if not args.allow_download:
                offline_client(stack, chaldea)
                stack.enter_context(patch.object(chaldea, "_save_cache", side_effect=AssertionError(
                    "只读检查不能写队伍缓存")))
            share, quest_id, team_id = chaldea.fetch_share_data(args.source)
        require(isinstance(share, dict), "来源获取/解码失败；只读模式需要已有缓存")
        require(str((share.get("quest") or {}).get("id")) == str(args.quest_id), "队伍关卡 ID 不匹配")
        _, source_team_id, _ = parse_import_source(args.source)
        require(source_team_id is not None, "此验收脚本的 source 必须为在线队伍链接或队伍 ID")
        cache = chaldea._find_cache_file(None, source_team_id)
        require(cache is not None, "下载后未找到队伍缓存")
        cache = Path(cache).resolve()
        require(cache.name.endswith(f"_{source_team_id}_{args.quest_id}.json"), "未使用新版队伍缓存文件名")
        expected = fingerprint(share)

        # 所有后续调用均阻断联网，验证各输入确实由缓存/本地 JSON 提供。
        inputs = {"share_link": args.source, "quest_id": str(args.quest_id),
                  "cache_filename": cache.name, "absolute_path": str(cache)}
        offline = {}
        with ExitStack() as stack:
            network = offline_client(stack, chaldea)
            stack.enter_context(patch.object(chaldea, "_save_cache", side_effect=AssertionError(
                "离线缓存检查不能写文件")))
            for name, source in inputs.items():
                data, local_quest, local_team = chaldea.fetch_share_data(source)
                require(isinstance(data, dict) and fingerprint(data) == expected,
                        f"离线 {name} 读取结果与首次获取不一致")
                offline[name] = {"ok": True, "quest_id": local_quest, "team_id": local_team}
            require(all(mock.call_count == 0 for mock in network), "离线阶段尝试了网络调用")

    team = share.get("team") or {}
    mystic_code = (team.get("mysticCode") or {}).get("mysticCodeId")
    if mystic_code is None:
        mystic_code = (share.get("mysticCode") or {}).get("id")
    plan = convert_chaldea_actions_to_battle_plan(
        share.get("actions"), delegate=share.get("delegate"), mystic_code_id=mystic_code)
    if source_team_id == 72098:
        require(len(plan.turns) == 1 and plan.turns[0].np_order == (3, 2)
                and len(plan.turns[0].servant_skills) == 9
                and len(plan.turns[0].master_skills) == 1,
                "72098 原生计划与已确认的 9 从者技能/1 御主技能/宝具 3→2 不一致")
    catalog_path = resolved(root, args.servant_catalog)
    catalog = json.loads(catalog_path.read_text(encoding="utf-8-sig"))["servants"]
    criteria = build_support_criteria(share, build_servant_lookup(catalog))
    face_root = root / "resource/base/image/servant_face"
    ce_root = root / "resource/base/image/lizhuang"
    if not face_root.is_dir():
        face_root = root / "assets/resource/base/image/servant_face"
        ce_root = root / "assets/resource/base/image/lizhuang"
    templates = {
        "servant_face_count": sum((face_root / name).is_file() for name in criteria["images"]),
        "craft_essences": [{"name": spec["name"], "status": spec["status"],
                            "exists": (ce_root / spec["status"] / spec["name"]).is_file()}
                           for spec in criteria["ce_specs"]],
    }
    require(templates["servant_face_count"] > 0, "助战从者缺少全部头像模板")
    require(all(item["exists"] for item in templates["craft_essences"]), "助战礼装模板缺失")
    after = {str(p): file_info(p)["sha256"] for p in cache_dir.glob("*.json")}
    if not args.allow_download:
        require(before == after, "只读模式的队伍缓存发生变化")
    face_cards = [attack for action in share.get("actions") or [] if isinstance(action, dict)
                  and action.get("type") == "attack" for attack in action.get("attacks") or []
                  if isinstance(attack, dict) and not attack.get("isTD", False)]
    return {
        "ok": True, "source": args.source, "quest_id": quest_id, "team_id": team_id,
        "share_sha256": expected, "cache": file_info(cache),
        "cache_files_added": sorted(set(after) - set(before)),
        "cache_files_changed": sorted(p for p in set(before) & set(after) if before[p] != after[p]),
        "offline": offline, "offline_network_calls": 0,
        "native_plan": asdict(plan), "support_criteria": criteria, "templates": templates,
        "limitations": {"explicit_face_cards_in_source": len(face_cards),
                        "explicit_face_card_order_replayed": False,
                        "note": "当前转换器仅保留技能、宝具顺序和换人；指定面卡由原生策略重新选择。"},
    }


def check_inventory(args, root: Path) -> dict:
    from bond_completion_action import CompleteBondFormation

    result = {}
    for kind, value, expected_hash in (
        ("servants", args.servants_file, args.servants_sha256),
        ("equips", args.equips_file, args.equips_sha256),
    ):
        path = resolved(root, value)
        info = file_info(path)
        if expected_hash:
            require(info["sha256"] == expected_hash.lower(), f"{kind} SHA256 不匹配")
        # 调用羁绊补齐实际消费函数，验证 schema/kind/scan_complete/ID/count。
        ids, document = CompleteBondFormation._read_player_inventory(str(path), kind, kind)
        require(type(document.get("catalog_complete")) is bool, f"{kind} 缺少 catalog_complete 布尔标志")
        missing = document.get("missing_template_ids")
        require(isinstance(missing, list), f"{kind} 缺少 missing_template_ids 数组")
        require(document["catalog_complete"] == (not missing), f"{kind} 模板完整标志与缺失列表矛盾")
        scan = document.get("scan") or {}
        require(isinstance(scan, dict) and scan.get("bottom_confirmed") is True,
                f"{kind} 未确认扫描到底")
        require(scan.get("bottom_detection") == "scrollbar", f"{kind} 缺少滚动条到底证据")
        require(scan.get("recognition_valid") is True, f"{kind} 识别结果无效")
        require(file_info(path)["sha256"] == info["sha256"], f"{kind} 消费读取后文件发生变化")
        result[kind] = {
            "ok": True, **info, "schema_version": document["schema_version"],
            "scan_complete": document["scan_complete"], "catalog_complete": document["catalog_complete"],
            "count": document["count"], "consumer_loaded_ids": len(ids),
            "generated_at": document.get("generated_at"), "scan": scan,
            "missing_template_count": len(missing), "sha256_unchanged": True,
            "consumer": "CompleteBondFormation._read_player_inventory",
        }
    return {"ok": True, **result}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pi-root", default=os.getcwd())
    parser.add_argument("--section", choices=("all", "chaldea", "inventory"), default="all")
    parser.add_argument("--allow-download", action="store_true")
    parser.add_argument("--source", default=DEFAULT_SOURCE)
    parser.add_argument("--quest-id", type=int, default=94146537)
    parser.add_argument("--cache-dir", default="config/Battle")
    parser.add_argument("--servant-catalog", default="agent/custom/servant_list.json")
    parser.add_argument("--servants-file", default="config/Inventory/player_servants.json")
    parser.add_argument("--equips-file", default="config/Inventory/player_equips.json")
    parser.add_argument("--servants-sha256")
    parser.add_argument("--equips-sha256")
    args = parser.parse_args(argv)
    root = Path(args.pi_root).resolve()
    sys.path[:0] = [str(root / "agent/custom"), str(root / "agent")]
    result = {"ok": True, "pi_root": str(root), "allow_download": args.allow_download,
              "checked_at_utc": datetime.now(timezone.utc).isoformat(), "sections": {}}
    captured = CapturedOutput()
    with redirect_stdout(captured), ExitStack() as stack:
        if not args.allow_download:
            stack.enter_context(patch.object(urllib.request, "urlopen", side_effect=AssertionError(
                "只读模式禁止所有 HTTP 请求")))
        for name, check in (("chaldea", check_chaldea), ("inventory", check_inventory)):
            if args.section not in ("all", name):
                continue
            try:
                os.chdir(root)
                result["sections"][name] = check(args, root)
            except Exception as exc:
                result["ok"] = False
                result["sections"][name] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    result["diagnostics"] = captured.getvalue().splitlines()[-100:]
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
