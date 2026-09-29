"""步骤 0 验收脚本（判据 1–4 的载体）。

用法：python check_step0.py       退出码 0 = 全部通过
"""
import os
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
R = Path(__file__).resolve().parent

# 子进程强制 UTF-8，否则 Windows 下按 GBK 输出，父进程解码乱码
ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}


def run_selftest():
    r = subprocess.run([sys.executable, "-m", "lib.schema"],
                       capture_output=True, cwd=R, env=ENV)
    out = (r.stdout or b"").decode("utf-8", "replace")
    err = (r.stderr or b"").decode("utf-8", "replace")
    return r.returncode, out, err


rc, out, err = run_selftest()
print("=" * 74)
print("步骤 0 验收")
print("=" * 74)
print(f"lib.schema 自测 exit = {rc}")
if err.strip():
    print("--- stderr ---")
    print(err.strip()[:2000])

fails = [l.strip() for l in out.splitlines() if "[FAIL]" in l]
result = [l.strip() for l in out.splitlines() if "结果：" in l]
print(f"FAIL 行数 = {len(fails)}")
for l in fails:
    print("   " + l)
print(result[0] if result else "(未找到结果行 —— 自测可能崩溃)")
print()

# ---- 判据 4：Config frozen ----
print("=" * 74)
print("附加验收")
print("=" * 74)
import config
from lib.exceptions import ConfigViolation

try:
    config.CONFIG.K = 30
    print("[FAIL] Config 可被修改")
except Exception as e:
    print(f"[PASS] Config frozen（{type(e).__name__}）")

cases = [("2026-10-31", True), ("2026-10-15", False), ("2026-02-28", True),
         ("2026-02-29", False), ("notadate", False), ("2020-01-31", False),
         ("", False)]
print("\nvalidate_sample_end：")
allok = True
for s, should_pass in cases:
    try:
        config.validate_sample_end(s)
        got = True
    except ConfigViolation:
        got = False
    mark = "PASS" if got == should_pass else "FAIL"
    if got != should_pass:
        allok = False
    shown = s if s else "(空)"
    print(f"  [{mark}] {shown:12s} 期望{'通过' if should_pass else '拒绝'}，"
          f"实际{'通过' if got else '拒绝'}")

# ---- 判据 1：import ----
print()
from lib import paths, formatting, schema, exceptions  # noqa
print("[PASS] config / lib.{paths,exceptions,schema,formatting} 全部导入成功")
print(f"[INFO] 项目根 = {paths.ROOT}")

# ---- 汇总 ----
ok = (rc == 0 and not fails and allok)
print()
print("=" * 74)
print("步骤 0 验收：" + ("全部通过 ✓" if ok else "存在失败 ✗"))
print("=" * 74)
sys.exit(0 if ok else 1)
