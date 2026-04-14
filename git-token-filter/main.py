#!/usr/bin/env python3
"""
GTF - Git Token Filter
用法：
  python main.py git status
  python main.py git diff
  python main.py git log -n 10
  python main.py git push
  python main.py gain           # 查看节省统计
  python main.py gain --reset   # 清空统计
"""

import sys
import subprocess

from handlers import git as git_handler
from handlers.base import estimate_tokens
from handlers import stats


def run_git(args: list[str]) -> str:
    """运行真实的 git 命令，返回原始输出"""
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
        )
        # stderr 也合并进来（push/pull 的输出在 stderr）
        output = result.stdout
        if result.stderr:
            output = output + result.stderr if output else result.stderr
        return output
    except FileNotFoundError:
        print("错误：找不到 git 命令，请确保 git 已安装。", file=sys.stderr)
        sys.exit(1)


def main():
    args = sys.argv[1:]

    # ── gain 统计命令 ──────────────────────────────
    if not args or args[0] == "gain":
        if "--reset" in args:
            stats.reset()
        else:
            stats.show()
        return

    # ── git 命令 ──────────────────────────────────
    if args[0] == "git":
        git_args = args[1:]  # 去掉 "git"
    else:
        # 兼容直接写子命令：python main.py status
        git_args = args

    if not git_args:
        print("用法: python main.py git <subcommand> [args...]")
        return

    subcommand = git_args[0]

    # 运行真实 git 命令
    raw = run_git(git_args)

    if not raw.strip():
        print("(无输出)")
        return

    # 过滤输出
    filtered, sub = git_handler.handle(subcommand, raw)

    # 统计 token 节省
    raw_tokens = estimate_tokens(raw)
    filtered_tokens = estimate_tokens(filtered)
    stats.record(sub, raw_tokens, filtered_tokens)

    # 打印过滤后结果
    print(filtered)

    # 右下角显示本次节省摘要（类似 RTK 风格）
    saved = raw_tokens - filtered_tokens
    if saved > 0:
        pct = round(saved / raw_tokens * 100)
        print(f"\n  💡 {raw_tokens} → {filtered_tokens} tokens  (-{pct}%)", flush=True)


if __name__ == "__main__":
    main()
