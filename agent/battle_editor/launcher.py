"""Shared, short-lived launcher for the CMD and Maa Custom Action entries."""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser


DEFAULT_PORT = 18765
PROTOCOL_VERSION = 1
SERVICE_NAME = "maafgo-battle-editor"


class EditorLaunchError(RuntimeError):
    """A startup failure that can be reported in the Maa task log."""


@dataclass(frozen=True)
class LaunchResult:
    url: str
    pid: int
    project_root: str
    mode: str
    reused: bool = False
    browser_opened: bool = False
    log_path: str = ""


def _root(value: str | Path | None = None) -> Path:
    return Path(value).resolve() if value is not None else Path(__file__).resolve().parents[2]


def _url(port: int) -> str:
    if type(port) is not int or not 1 <= port <= 65535:
        raise EditorLaunchError("编辑器端口必须是 1–65535 的整数")
    return f"http://127.0.0.1:{port}"


def _request(url: str, *, token: str | None = None, body: dict | None = None) -> dict:
    headers = {"Accept": "application/json"}
    if token is not None:
        headers["X-Editor-Token"] = token
    payload = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        payload = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=payload, headers=headers)
    # A desktop proxy setting must not send local control requests off the machine.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=1.5) as response:
        value = json.load(response)
    if not isinstance(value, dict):
        raise ValueError("响应不是 JSON 对象")
    return value


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as stream:
        stream.settimeout(0.3)
        return stream.connect_ex(("127.0.0.1", port)) == 0


def service_status(project_root: str | Path | None = None, port: int = DEFAULT_PORT) -> dict | None:
    """Return this installation's health, or reject an occupied foreign service."""
    root = _root(project_root)
    base = _url(port)
    try:
        health = _request(base + "/health")
    except (OSError, ValueError, urllib.error.URLError) as exc:
        if _port_in_use(port):
            raise EditorLaunchError(
                f"端口 {port} 已被其他程序占用，或编辑器尚未就绪；不会打开其他服务。"
            ) from exc
        return None
    if health.get("service") != SERVICE_NAME or health.get("protocolVersion") != PROTOCOL_VERSION:
        raise EditorLaunchError(f"端口 {port} 的服务不是兼容的 MaaFGO 编队编辑器")
    actual_root = health.get("projectRoot")
    if not isinstance(actual_root, str) or os.path.normcase(str(_root(actual_root))) != os.path.normcase(str(root)):
        raise EditorLaunchError(
            f"端口 {port} 正在服务另一份 MaaFGO：{actual_root}；请先停止那份编辑服务。"
        )
    if type(health.get("pid")) is not int or health["pid"] <= 0:
        raise EditorLaunchError("编辑器返回了无效的进程身份")
    return health


def _open_browser(url: str) -> bool:
    try:
        return bool(webbrowser.open(url, new=2))
    except (OSError, webbrowser.Error):
        return False


def open_editor(
    project_root: str | Path | None = None,
    *,
    port: int = DEFAULT_PORT,
    open_browser: bool = True,
    owner_pid: int | None = None,
    owner_created: float | None = None,
    idle_timeout: int = 3600,
    timeout: float = 20.0,
) -> LaunchResult:
    """Start or reuse the detached server, confirm readiness, then open its UI."""
    root = _root(project_root)
    base = _url(port)
    log_path = root / "config" / "BattleEditor" / "service.log"
    health = service_status(root, port)
    reused = health is not None
    if health is None:
        entry = root / "agent" / "battle_editor" / "main.py"
        if not entry.is_file():
            raise EditorLaunchError(f"编辑器服务文件缺失：{entry}")
        # Fail before launching a daemon if the player received an incomplete build.
        static_roots = (root / "assets" / "web" / "battle-editor", root / "web" / "battle-editor")
        if not any((path / "index.html").is_file() and not (path / "src").is_dir() for path in static_roots):
            raise EditorLaunchError("编辑器页面未构建或缺失，请在开发目录运行 npm --prefix web/battle-editor run build")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        args = [sys.executable, "-X", "utf8", str(entry), "--project-root", str(root), "--port", str(port),
                "--idle-timeout", str(idle_timeout)]
        if owner_pid is not None:
            args += ["--owner-pid", str(owner_pid)]
        if owner_created is not None:
            args += ["--owner-created", str(owner_created)]
        environment = dict(os.environ, PYTHONUTF8="1", PYTHONUNBUFFERED="1")
        flags = 0
        if os.name == "nt":
            flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        try:
            with log_path.open("ab", buffering=0) as log_stream:
                child = subprocess.Popen(
                    args, cwd=root, env=environment, stdin=subprocess.DEVNULL,
                    stdout=log_stream, stderr=log_stream, close_fds=True,
                    creationflags=flags,
                )
            # Keep the process handle alive and reap it when it exits, without
            # retaining the launcher or coupling the daemon to a Maa task.
            threading.Thread(target=child.wait, name="battle-editor-child", daemon=True).start()
        except OSError as exc:
            raise EditorLaunchError(f"启动编辑器失败：{exc}；日志：{log_path}") from exc
        deadline = time.monotonic() + timeout
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                health = service_status(root, port)
            except EditorLaunchError as exc:
                # A listener can become reachable before its first health response.
                last_error = exc
                health = None
            if health is not None:
                reused = int(health["pid"]) != child.pid
                break
            if child.poll() is not None:
                # Another simultaneous launcher might have won the bind race.
                time.sleep(0.15)
                try:
                    health = service_status(root, port)
                except EditorLaunchError as exc:
                    last_error = exc
                if health is not None:
                    reused = True
                    break
                raise EditorLaunchError(
                    f"编辑器服务提前退出（{child.returncode}）。{last_error or ''} 日志：{log_path}"
                )
            time.sleep(0.1)
        if health is None:
            # Only stop the process created by this launcher; never kill a port owner.
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=3)
            raise EditorLaunchError(f"编辑器启动超时。{last_error or ''} 日志：{log_path}")
    url = base + "/"
    return LaunchResult(
        url=url, pid=int(health["pid"]), project_root=str(root),
        mode=str(health.get("mode", "standalone")), reused=reused,
        browser_opened=_open_browser(url) if open_browser else False, log_path=str(log_path),
    )


def stop_editor(project_root: str | Path | None = None, *, port: int = DEFAULT_PORT) -> bool:
    root = _root(project_root)
    if service_status(root, port) is None:
        return False
    base = _url(port)
    try:
        session = _request(base + "/api/session")
        _request(base + "/api/shutdown", token=session["token"], body={})
    except (OSError, ValueError, KeyError, urllib.error.URLError) as exc:
        raise EditorLaunchError(f"停止服务失败：{exc}") from exc
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if not _port_in_use(port):
            return True
        time.sleep(0.1)
    raise EditorLaunchError("服务尚未完成停止，请查看编辑器日志")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="打开 MaaFGO 编队与战斗编辑器")
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--owner-pid", type=int)
    parser.add_argument("--owner-created", type=float)
    parser.add_argument("--idle-timeout", type=int, default=3600)
    args = parser.parse_args(argv)
    try:
        if args.stop:
            value = {"stopped": stop_editor(args.project_root, port=args.port)}
        elif args.status:
            value = {"health": service_status(args.project_root, args.port)}
        else:
            value = asdict(open_editor(
                args.project_root, port=args.port, open_browser=not args.no_browser,
                owner_pid=args.owner_pid, owner_created=args.owner_created, idle_timeout=args.idle_timeout,
            ))
        if sys.stdout is not None:
            print(json.dumps(value, ensure_ascii=False))
        return 0
    except (EditorLaunchError, OSError) as exc:
        if sys.stderr is not None:
            print(f"[编队编辑器] {exc}", file=sys.stderr)
        elif os.name == "nt":
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, str(exc), "MaaFGO 编队编辑器", 0x10)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
