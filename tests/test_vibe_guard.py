"""vibe-guard：每轮提醒走流程；这一轮改了代码，结束前必须核对关卡、更新台账。"""
import json
import os
import re
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

GUARD = Path(__file__).resolve().parent.parent / "vibe-workflow" / "assets" / "vibe-guard.py"
LEDGER = "docs/开发进度跟踪.md"


class GuardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.state = root / "state"
        self.repo = root / "项目"
        (self.repo / "docs").mkdir(parents=True)
        (self.repo / "app.py").write_text("a = 1\n", encoding="utf-8")
        (self.repo / LEDGER).write_text("# 台账\n", encoding="utf-8")
        for cmd in (["init", "-q"], ["add", "."],
                    ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init"]):
            subprocess.run(["git", *cmd], cwd=self.repo, check=True)

    def tearDown(self):
        self.tmp.cleanup()

    def run_guard(self, mode, cwd=None, active=False, background=None):
        payload = {"session_id": "s1", "cwd": str(cwd or self.repo), "stop_hook_active": active}
        if background:
            payload["background_tasks"] = background
        proc = subprocess.run(["python3", str(GUARD), mode], input=json.dumps(payload), text=True,
                              capture_output=True, env=dict(os.environ, VIBE_GUARD_STATE=str(self.state)))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout) if proc.stdout.strip() else {}

    def start_turn(self):
        out = self.run_guard("prompt")
        time.sleep(0.05)
        return out

    def edit(self, name="app.py"):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"a = {time.time()}\n", encoding="utf-8")

    def test_prompt_reminds_inside_a_git_project(self):
        text = self.start_turn()["hookSpecificOutput"]["additionalContext"]
        self.assertIn("vibe-workflow", text)
        self.assertIn("只是提问", text)

    def test_prompt_stays_quiet_outside_git(self):
        self.assertEqual(self.run_guard("prompt", cwd=self.tmp.name), {})

    def test_plain_chat_turn_is_not_blocked(self):
        self.start_turn()
        self.assertEqual(self.run_guard("stop"), {})

    def test_changes_from_before_this_turn_do_not_count(self):
        self.edit()
        time.sleep(0.05)
        self.start_turn()
        self.assertEqual(self.run_guard("stop"), {})

    def test_code_change_without_ledger_is_blocked(self):
        self.start_turn()
        self.edit()
        out = self.run_guard("stop")
        self.assertEqual(out["decision"], "block")
        self.assertIn("台账", out["reason"])
        self.assertIn("app.py", out["reason"])

    def test_new_untracked_code_file_counts(self):
        self.start_turn()
        self.edit("新目录/新文件.py")
        self.assertEqual(self.run_guard("stop")["decision"], "block")

    def test_code_change_with_ledger_still_asks_for_gate_list_once(self):
        self.start_turn()
        self.edit()
        self.edit(LEDGER)
        out = self.run_guard("stop")
        self.assertEqual(out["decision"], "block")
        self.assertIn("关卡清单", out["reason"])
        self.assertNotIn("还没更新", out["reason"])
        self.assertEqual(self.run_guard("stop", active=True), {})

    def test_docs_only_turn_is_not_blocked(self):
        self.start_turn()
        self.edit("docs/说明.md")
        self.assertEqual(self.run_guard("stop"), {})

    def test_second_pass_never_loops_and_warns_the_user(self):
        self.start_turn()
        self.edit()
        out = self.run_guard("stop", active=True)
        self.assertNotIn("decision", out)
        self.assertIn("台账", out["systemMessage"])

    def test_background_report_does_not_hide_earlier_changes(self):
        self.start_turn()
        self.edit()
        self.run_guard("prompt")  # 后台代理汇报回来，也算一次新消息
        self.assertEqual(self.run_guard("stop")["decision"], "block")

    def test_work_done_by_a_background_agent_is_checked_when_it_reports(self):
        self.start_turn()
        self.assertEqual(self.run_guard("stop", background=[{"type": "subagent"}]), {})  # 主线先停下等后台
        time.sleep(0.05)
        self.edit()
        self.run_guard("prompt")
        self.assertEqual(self.run_guard("stop")["decision"], "block")

    def test_background_work_after_a_checked_pass_is_still_checked(self):
        self.start_turn()
        self.edit()
        self.edit(LEDGER)
        self.run_guard("stop", background=[{"type": "subagent"}])
        self.run_guard("stop", active=True, background=[{"type": "subagent"}])
        self.edit("后台改的.py")
        self.run_guard("prompt")
        self.assertIn("后台改的.py", self.run_guard("stop")["reason"])

    def test_long_running_background_shell_does_not_block_every_chat(self):
        server = [{"type": "shell"}]
        self.start_turn()
        self.edit()
        self.edit(LEDGER)
        self.run_guard("stop", background=server)
        self.run_guard("stop", active=True, background=server)
        time.sleep(0.05)
        self.start_turn()
        self.assertEqual(self.run_guard("stop", background=server), {})

    def test_interrupted_chat_turn_leaves_nothing_behind(self):
        self.start_turn()         # 闲聊时被打断，这一轮没有结束检查
        time.sleep(0.05)
        self.start_turn()         # 没有待核对的改动，计时重新开始
        self.assertEqual(self.run_guard("stop"), {})

    def test_turn_outside_git_does_not_leave_a_stale_start_time(self):
        self.run_guard("prompt", cwd=self.tmp.name)
        self.run_guard("stop", cwd=self.tmp.name)
        time.sleep(0.05)
        self.edit()
        time.sleep(0.05)
        self.start_turn()
        self.assertEqual(self.run_guard("stop"), {})

    def test_tracked_files_in_build_folders_are_code(self):
        self.edit("build/webpack.config.js")
        self.edit("app.log")
        subprocess.run(["git", "add", "."], cwd=self.repo, check=True)
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "加"],
                       cwd=self.repo, check=True)
        time.sleep(1.2)
        self.start_turn()
        self.edit("build/webpack.config.js")
        self.edit("app.log")
        reason = self.run_guard("stop")["reason"]
        self.assertIn("build/webpack.config.js", reason)
        self.assertIn("app.log", reason)

    def test_interrupted_turn_is_still_checked_next_time(self):
        self.start_turn()
        self.edit()               # 用户按 Esc 打断，这一轮没有结束检查
        time.sleep(0.05)
        self.start_turn()
        self.assertEqual(self.run_guard("stop")["decision"], "block")

    def test_finished_turn_does_not_carry_over(self):
        self.start_turn()
        self.edit()
        self.edit(LEDGER)
        self.run_guard("stop")
        self.run_guard("stop", active=True)
        time.sleep(0.05)
        self.start_turn()
        self.assertEqual(self.run_guard("stop"), {})

    def test_change_committed_in_the_same_turn_counts(self):
        self.start_turn()
        self.edit()
        time.sleep(1.2)  # 提交时间只到秒
        subprocess.run(["git", "add", "."], cwd=self.repo, check=True)
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "改"],
                       cwd=self.repo, check=True)
        self.assertEqual(self.run_guard("stop")["decision"], "block")

    def test_generated_files_are_not_code(self):
        self.start_turn()
        self.edit("__pycache__/m.cpython-39.pyc")
        self.edit(".DS_Store")
        self.edit("node_modules/x/index.js")
        self.assertEqual(self.run_guard("stop"), {})

    def test_non_utf8_locale_still_catches_chinese_file_names(self):
        self.start_turn()
        self.edit("中文.py")
        payload = json.dumps({"session_id": "s1", "cwd": str(self.repo)})
        proc = subprocess.run(["python3", str(GUARD), "stop"], input=payload.encode(), capture_output=True,
                              env=dict(os.environ, VIBE_GUARD_STATE=str(self.state), LC_ALL="C", PYTHONUTF8="0",
                                       PYTHONCOERCECLOCALE="0"))
        self.assertEqual(json.loads(proc.stdout.decode("utf-8"))["decision"], "block")

    def test_documented_command_never_blocks_when_the_script_is_gone(self):
        guide = (GUARD.parent.parent / "references" / "换机器搬家清单.md").read_text(encoding="utf-8")
        snippet = guide[guide.index('"hooks": {'):]
        commands = re.findall(r'"command": ("(?:[^"\\]|\\.)*")', snippet[:snippet.index("```")])
        self.assertEqual(len(commands), 2)
        for event, raw in zip(("UserPromptSubmit", "Stop"), commands):
            command = json.loads(raw)
            self.assertIn("vibe-guard.py", command)
            broken = command.replace("vibe-guard.py", "不存在.py")
            proc = subprocess.run(["sh", "-c", broken], input="{}", text=True, capture_output=True)
            self.assertEqual(proc.returncode, 0, event)

    def test_missing_turn_marker_or_bad_input_does_nothing(self):
        self.assertEqual(self.run_guard("stop"), {})
        proc = subprocess.run(["python3", str(GUARD), "stop"], input="不是 JSON", text=True, capture_output=True,
                              env=dict(os.environ, VIBE_GUARD_STATE=str(self.state)))
        self.assertEqual((proc.returncode, proc.stdout), (0, ""))


if __name__ == "__main__":
    unittest.main()
