import json
import subprocess
import sys
from pathlib import Path

GUARD = str(Path(__file__).resolve().parent / "secret_guard.py")

# (이 파일 내용에는 .env / secret / credentials 텍스트가 일부러 들어있다 —
#  정밀화된 가드가 '문서 내용'은 막지 않고 '실제 경로/명령'만 막는지 확인하기 위함.)
cases = [
    ("Bash description만 .env 언급", {"tool_name": "Bash", "tool_input": {"command": "ls -la", "description": "work with the .env file"}}, 0),
    ("Bash cat 실제 .env",         {"tool_name": "Bash", "tool_input": {"command": "cat app/.env"}}, 2),
    ("Write 문서에 .env 텍스트",    {"tool_name": "Write", "tool_input": {"file_path": "docs/chat-log.md", "content": "today we wired the .env guard and secret stuff"}}, 0),
    ("Read 실제 .env",             {"tool_name": "Read", "tool_input": {"file_path": "app/.env"}}, 2),
    ("Grep path=.env",            {"tool_name": "Grep", "tool_input": {"pattern": "KEY", "path": "app/.env"}}, 2),
    ("Grep pattern=process.env",  {"tool_name": "Grep", "tool_input": {"pattern": "process.env", "path": "src"}}, 0),
    ("Edit 코드에 .env 텍스트",     {"tool_name": "Edit", "tool_input": {"file_path": "x.py", "old_string": "a", "new_string": "DOTENV='.env'"}}, 0),
    ("Read credentials.json",     {"tool_name": "Read", "tool_input": {"file_path": "app/credentials.json"}}, 2),
    ("Read id_rsa",               {"tool_name": "Read", "tool_input": {"file_path": "/home/u/.ssh/id_rsa"}}, 2),
    ("Read 정상 .py",             {"tool_name": "Read", "tool_input": {"file_path": "core/security/secret_guard.py"}}, 0),
]

ok = 0
for name, payload, expect in cases:
    p = subprocess.run([sys.executable, GUARD], input=json.dumps(payload), capture_output=True, text=True)
    got = p.returncode
    mark = "OK" if got == expect else "FAIL"
    if got == expect:
        ok += 1
    print(f"[{mark}] {name}: exit={got} (expect {expect})")

print(f"\n{ok}/{len(cases)} passed")
sys.exit(0 if ok == len(cases) else 1)

