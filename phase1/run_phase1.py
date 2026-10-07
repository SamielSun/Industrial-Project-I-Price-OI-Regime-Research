#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
run_phase1 —— 一条命令跑完 Phase 1 的六个处理步骤

它在 Phase 1 中的位置：驱动器，不是第七个处理步骤。**不做任何数据计算。**

做什么
------
  按顺序把六个脚本跑一遍，`--out-root` 与 `--sample-end` 原样透传给每一个：

      1  Step 0-2  build_candidate_pool.py   枚举归档 → 硬过滤 → 逐月排名 → 候选池
      2  Step 3    fetch_market_data.py      下载候选池五个源的原始数据
      3  Step 4    build_layer2.py           建第 2 层 4 张规范 1h 表
      4  Step 5    build_features.py         建 19 列密集面板 features_1h
      5  Step 6a   build_universe.py         四条资格闸 → PIT 成员集
      6  Step 6b   build_deliverables.py     质量证明 + 字典 + 复现 + 校验和

  核验（`build_deliverables.py --verify`）**不包含在内** —— 它是独立动作，
  自己跑：

      python phase1/build_deliverables.py --out-root data --sample-end 2026-08-31 --verify

用法
----
  # 全流程（约 45 分钟；Step 0-3 需要 VPN）
  python phase1/run_phase1.py --out-root data --sample-end 2026-08-31

  # 看要跑哪些步骤，不执行
  python phase1/run_phase1.py --out-root data --sample-end 2026-08-31 --dry-run

任一一步失败即停在该步，不会继续往下跑。要单跑某一步，直接调那个脚本 ——
六个脚本的命令见 phase1/REPRODUCE.md 的「The same thing, step by step」。

三条设计约束（改这个文件时不要破坏）
------------------------------------
1. **子进程 stdio 继承，不走管道。** Step 3 要跑近半小时，进度必须实时可见；
   管道还会引入缓冲与 Windows 上的坑。
2. **不吞 KeyboardInterrupt。** Step 3 自己会捕获 Ctrl-C、落盘并写
   `raw_written_at`（fetch_market_data.py 的收尾分支）。本脚本收到中断后必须
   **继续等子进程收尾**，不能抢先杀掉它 —— 否则那批已下好的数据会失去进度戳，
   下次重跑要重下几十万个文件。
3. **不引入第二个参数真相。** 本脚本只透传 `--out-root` / `--sample-end`，
   不解释、不重写、不代填任何旗标。单步特有的旗标（`--subset` `--keep-cache`
   `--skip-download` 等）一律直接对着那个脚本用。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))                                # 项目根
import config as cfg_mod                                     # noqa: E402

# (Step 标签, 脚本名, 一句话说明)
STEPS: list[tuple[str, str, str]] = [
    ("0-2", "build_candidate_pool.py", "枚举归档 → 硬过滤 → 逐月排名 → 候选池"),
    ("3",   "fetch_market_data.py",    "下载候选池五个源的原始数据"),
    ("4",   "build_layer2.py",         "建第 2 层 4 张规范 1h 表"),
    ("5",   "build_features.py",       "建 19 列密集面板 features_1h"),
    ("6a",  "build_universe.py",       "四条资格闸 → PIT 成员集"),
    ("6b",  "build_deliverables.py",   "质量证明 + 字典 + 复现 + 校验和"),
]
T_START = time.time()


def log(msg: str = "") -> None:
    el = time.time() - T_START
    print(f"[{int(el)//60:02d}:{int(el)%60:02d}] {msg}", flush=True)


def run_step(script: str, out_root: str,
             sample_end: str) -> tuple[int, float]:
    """跑一个步骤，stdio 继承。返回 (退出码, 耗时秒数)。

    中断处理见文件头约束 2：收到 Ctrl-C 后继续等子进程收尾，再原样返回它的退出码。
    """
    path = HERE / script
    if not path.exists():
        log(f"  ✗ 找不到 {path}")
        return 127, 0.0
    cmd = [sys.executable, str(path),
           "--out-root", out_root, "--sample-end", sample_end]
    log(f"  $ {' '.join(cmd[1:])}")
    t0 = time.time()
    proc = subprocess.Popen(cmd, cwd=str(ROOT))       # stdio 继承，不 capture
    try:
        code = proc.wait()
    except KeyboardInterrupt:
        log("")
        log("  ! 收到 Ctrl-C —— 等这一步自己收尾（它会 flush 并把进度戳落盘）…")
        try:
            code = proc.wait()
        except KeyboardInterrupt:                     # 又按了一次：这次强制终止
            log("  ! 再次中断 —— 强制终止子进程")
            proc.terminate()
            code = proc.wait()
    return code, time.time() - t0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Phase 1 驱动器 —— 一条命令跑完六个处理步骤")
    ap.add_argument("--out-root", required=True,
                    help="产出根目录（必填，与六个脚本的 --out-root 同义）")
    ap.add_argument("--sample-end", required=True, help="样本截止日，必须是月末")
    ap.add_argument("--dry-run", action="store_true", help="只打印要跑哪些步骤，不执行")
    args = ap.parse_args()

    # 复用 config 里唯一的校验实现，不另写一套。日期敲错时立刻失败，
    # 而不是等 Step 0-2 枚举完归档才报。
    try:
        cfg_mod.validate_sample_end(args.sample_end)
    except cfg_mod.ConfigViolation as e:
        print(f"\n参数校验失败：\n{e}", file=sys.stderr)
        return 2

    todo = STEPS

    log("=" * 78)
    log(f"run_phase1   sample_end={args.sample_end}")
    log(f"  产出根目录 : {Path(args.out_root).resolve()}")
    log(f"  本次步骤   : {len(todo)} / {len(STEPS)}")
    log("=" * 78)
    for i, (label, script, desc) in enumerate(todo, 1):
        log(f"  {i}. Step {label:<4} {script:<24} {desc}")
    log("")
    if args.dry_run:
        log("--dry-run：到此为止，未执行任何步骤。")
        return 0

    results: list[tuple[str, str, int, float]] = []
    for i, (label, script, desc) in enumerate(todo, 1):
        log("")
        log("=" * 78)
        log(f"[{i}/{len(todo)}] Step {label}  {script}  —— {desc}")
        log("=" * 78)
        code, secs = run_step(script, args.out_root, args.sample_end)
        results.append((label, script, code, secs))
        if code != 0:
            log("")
            log("=" * 78)
            log(f"✗ Step {label}（{script}）失败，退出码 {code} —— 后续步骤不再执行。")
            log(f"  修好之后单跑这一步：")
            log(f"    python phase1/{script} --out-root {args.out_root} "
                f"--sample-end {args.sample_end}")
            log(f"  或者整条重跑（已完成的步骤会自己跳过/自愈）。")
            log("=" * 78)
            break

    log("")
    log("=" * 78)
    log("运行摘要")
    log("=" * 78)
    for label, script, code, secs in results:
        mark = "ok  " if code == 0 else f"FAIL({code})"
        log(f"  Step {label:<4} {script:<24} {mark:<9} {secs:>7.0f}s")
    ran = len(results)
    if ran < len(todo):
        log(f"  —— 在 {ran}/{len(todo)} 步中止")
    log(f"  总耗时 {time.time()-T_START:.0f}s")
    log("=" * 78)
    if results and results[-1][2] != 0:
        return results[-1][2]
    log("")
    log("核验（不在本脚本范围内）：")
    log(f"  python phase1/build_deliverables.py --out-root {args.out_root} "
        f"--sample-end {args.sample_end} --verify")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        # 子进程的中断已在 run_step 里处理完毕；这里只负责干净退出。
        print("\n已中断。", file=sys.stderr)
        raise SystemExit(130)
