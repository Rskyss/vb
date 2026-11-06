#!/usr/bin/env python3
"""vibe-guard：让 AI 不靠自觉走 vibe-workflow。给 Claude Code 的 hook 用。

prompt：用户每发一条消息，提醒走流程。上一轮核对完、或没有待核对的改动，才开始新一轮计时，
        所以后台汇报回来、用户中途打断，都不会冲掉没核对的改动。
stop：  这一轮改了代码（含已提交的），就拦一次，要求核对关卡；台账没更新要先更新。
        后台子代理还在跑时不结束这一轮，等它汇报后再核对。
        这一轮开始之前留下的改动不算；同一时间别的工具改的文件分不出来，会算进去。
只拦一次、绝不循环；第二次仍没更新台账，就直接告诉用户。
任何异常都放行：守卫坏了不能挡住工作。脚本文件不在时，由 settings.json 里的命令兜底放行。
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

LEDGER = "docs/开发进度跟踪.md"
KEEP_SECONDS = 7 * 24 * 3600
GENERATED_DIRS = {"__pycache__", "node_modules", ".pytest_cache", ".venv", "dist", "build"}
GENERATED_NAMES = {".DS_Store"}
GENERATED_ENDINGS = (".pyc", ".log")
REMINDER = (
    "【vibe-workflow】本轮如果涉及开发、修 bug、改功能或处理用户反馈，动手前必须："
    "1）调用 vibe-workflow 技能（这段对话加载过可跳过），并读 docs/开发进度跟踪.md；"
    "2）重新判断大小：需求是否已变大（跨模块、超半天），变大就走规划流程；"
    "3）用户反馈改变了已批准的方案，先改《方案》并等批准，再改代码；"
    "4）用户只是提问时先回答，不擅自改代码。"
    "说“做完了”之前，按关卡列清单：测试、真实环境走查、独立复查、台账、文档同步，没做的写“未做”。"
)


def state_dir() -> Path:
    return Path(os.environ.get("VIBE_GUARD_STATE") or Path.home() / ".claude" / "vibe-guard")


def turn_marker(session: str) -> Path:
    return state_dir() / f"{Path(session).name or 'unknown'}.turn"


def repo_root(cwd: str):
    top = git(cwd, "rev-parse", "--show-toplevel").strip()
    return Path(top) if top else None


def git(root, *args) -> str:
    proc = subprocess.run(["git", "-c", "core.quotepath=off", *args], cwd=root, capture_output=True,
                          encoding="utf-8", errors="replace", timeout=10)
    return proc.stdout if proc.returncode == 0 else ""


def counts(name: str, tracked: bool) -> bool:
    """算不算改代码：docs/ 下的文档不算；还没纳入版本管理的生成文件不算。"""
    parts = name.split("/")
    if not name or parts[0] == "docs":
        return False
    return tracked or not (GENERATED_DIRS.intersection(parts[:-1]) or parts[-1] in GENERATED_NAMES
                           or name.endswith(GENERATED_ENDINGS))


def changed_since(root: Path, since: float) -> list:
    """这一轮改过的文件，包括已经提交的。没提交的删除、改名看不到新时间，不算。"""
    files = []
    for entry in git(root, "status", "--porcelain", "-z", "-uall", "--no-renames").split("\0"):
        name = entry[3:]
        try:
            if counts(name, entry[:2] != "??") and (root / name).stat().st_mtime > since:
                files.append(name)
        except OSError:
            pass
    committed = git(root, "log", f"--since={int(since) + 1}", "--name-only", "--pretty=format:", "-z")
    for name in committed.replace("\n", "\0").split("\0"):
        if counts(name, True) and name not in files:
            files.append(name)
    return files


def on_prompt(data: dict) -> dict:
    folder = state_dir()
    folder.mkdir(parents=True, exist_ok=True)
    now = time.time()
    for old in folder.glob("*.turn"):
        if now - old.stat().st_mtime > KEEP_SECONDS:
            old.unlink()
    marker = turn_marker(data.get("session_id", ""))
    root = repo_root(data.get("cwd") or ".")
    if not marker.exists() or root is None or not changed_since(root, marker.stat().st_mtime):
        marker.touch()
    if root is None:
        return {}
    return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": REMINDER}}


def on_stop(data: dict) -> dict:
    marker = turn_marker(data.get("session_id", ""))
    if not marker.exists():
        return {}
    # 子代理还在干活时这一轮没结束；开发服务器这类长期任务不算，否则每轮闲聊都会被拦
    waiting = any(isinstance(task, dict) and task.get("type") == "subagent"
                  for task in data.get("background_tasks") or [])

    def finish() -> None:
        if not waiting:
            marker.unlink()

    root = repo_root(data.get("cwd") or ".")
    if root is None:
        finish()
        return {}
    since = marker.stat().st_mtime
    files = changed_since(root, since)
    if not files:
        finish()
        return {}
    ledger = root / LEDGER
    ledger_done = ledger.exists() and ledger.stat().st_mtime > since
    if data.get("stop_hook_active"):
        finish()
        if ledger_done:
            return {}
        return {"systemMessage": f"⚠️ 这一轮改了代码，但台账 {LEDGER} 没有更新。"}
    shown = "、".join(files[:5]) + (f" 等 {len(files)} 个文件" if len(files) > 5 else "")
    todo = "" if ledger_done else f"台账 {LEDGER} 这一轮还没更新，先更新（没有就新建）。"
    return {"decision": "block", "reason": (
        f"这一轮改了代码：{shown}。{todo}结束前按 vibe-workflow 核对，并在汇报末尾列“关卡清单”："
        "测试、真实环境走查、独立复查、台账、文档同步，逐项写已做或未做。有未做项不许说“做完了”。")}


def main() -> None:
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        result = {"prompt": on_prompt, "stop": on_stop}[sys.argv[1]](data)
        if result:
            sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False).encode("utf-8") + b"\n")
    except Exception:
        return


if __name__ == "__main__":
    main()
