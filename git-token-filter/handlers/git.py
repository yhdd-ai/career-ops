"""
git.py - Git 命令输出过滤器
支持：status / diff / log / push / pull / show
"""

import re
from .base import truncate, dedup_lines, estimate_tokens


# ──────────────────────────────────────────────
# git status
# ──────────────────────────────────────────────

def filter_status(raw: str) -> str:
    """
    只保留文件状态行，去掉所有解释性文字。
    原始输出示例：
        On branch main
        Changes not staged for commit:
          (use "git add <file>..." to update what will be committed)
                modified:   src/main.py
        ...
    过滤后：
        branch: main
        M  src/main.py
        ?? untracked.txt
    """
    lines = raw.splitlines()
    result = []
    branch = ""

    for line in lines:
        stripped = line.strip()

        # 提取分支名
        if stripped.startswith("On branch"):
            branch = stripped.replace("On branch", "").strip()
            continue

        # 跳过解释性文字（括号提示、空行、段落标题）
        if not stripped or stripped.startswith("(") or stripped.startswith("no changes"):
            continue
        if stripped in (
            "Changes to be committed:",
            "Changes not staged for commit:",
            "Untracked files:",
            "nothing to commit, working tree clean",
            "nothing added to commit but untracked files present (use \"git add\" to track)",
        ):
            continue

        # 处理文件行：去掉前缀词，保留状态符号
        for prefix in ("modified:", "deleted:", "new file:", "renamed:", "copied:"):
            if prefix in stripped:
                fname = stripped.split(prefix)[-1].strip()
                symbol = {
                    "modified:": "M ",
                    "deleted:": "D ",
                    "new file:": "A ",
                    "renamed:": "R ",
                    "copied:": "C ",
                }.get(prefix, "? ")
                result.append(f"  {symbol} {fname}")
                break
        else:
            # untracked 文件（无前缀词）
            if stripped and not stripped.startswith("-"):
                result.append(f"  ?? {stripped}")

    header = f"branch: {branch}" if branch else ""
    body = '\n'.join(result) if result else "  (clean)"
    output = f"{header}\n{body}" if header else body
    return truncate(output)


# ──────────────────────────────────────────────
# git diff
# ──────────────────────────────────────────────

def filter_diff(raw: str) -> str:
    """
    只保留：
    - diff --git 文件名行
    - @@ 变更位置行
    - + 新增行
    - - 删除行
    去掉大段未修改的上下文行（以空格开头）
    """
    lines = raw.splitlines()
    result = []
    context_skip = 0  # 连续跳过的上下文行计数

    for line in lines:
        # 文件名行
        if line.startswith("diff --git"):
            if context_skip > 0:
                result.append(f"  ... [{context_skip} 行上下文已省略]")
                context_skip = 0
            # 提取简短文件名
            parts = line.split(" b/")
            fname = parts[-1] if len(parts) > 1 else line
            result.append(f"\n📄 {fname}")
            continue

        # 跳过 index / --- / +++ 元数据行
        if line.startswith("index ") or line.startswith("--- ") or line.startswith("+++ "):
            continue

        # 变更位置行 @@
        if line.startswith("@@"):
            if context_skip > 0:
                result.append(f"  ... [{context_skip} 行上下文已省略]")
                context_skip = 0
            # 简化 @@ 行，只保留行号
            m = re.search(r'@@ .+? @@(.*)', line)
            hint = m.group(1).strip() if m else ""
            result.append(f"  @@ {hint}" if hint else "  @@")
            continue

        # 实际变更行
        if line.startswith("+") or line.startswith("-"):
            if context_skip > 0:
                result.append(f"  ... [{context_skip} 行上下文已省略]")
                context_skip = 0
            result.append(f"  {line}")
            continue

        # 未修改的上下文行（以空格开头）——跳过并计数
        if line.startswith(" "):
            context_skip += 1
            continue

    if context_skip > 0:
        result.append(f"  ... [{context_skip} 行上下文已省略]")

    output = '\n'.join(result).strip()
    return truncate(output) if output else "(no diff)"


# ──────────────────────────────────────────────
# git log
# ──────────────────────────────────────────────

def filter_log(raw: str) -> str:
    """
    把多行 commit 块压缩为单行：
      abc1234  Fix login bug  (John, 2 days ago)
    """
    lines = raw.splitlines()
    result = []
    current = {}

    def flush():
        if current:
            sha = current.get("sha", "")[:7]
            msg = current.get("msg", "").strip()
            author = current.get("author", "")
            date = current.get("date", "")
            result.append(f"  {sha}  {msg}  ({author}, {date})")

    for line in lines:
        if line.startswith("commit "):
            flush()
            current = {"sha": line.split()[1]}
        elif line.startswith("Author:"):
            # 只取名字，不要邮箱
            name = re.sub(r'<.*?>', '', line.replace("Author:", "")).strip()
            current["author"] = name
        elif line.startswith("Date:"):
            current["date"] = line.replace("Date:", "").strip()
        elif line.strip() and "msg" not in current:
            current["msg"] = line.strip()

    flush()
    output = '\n'.join(result)
    return truncate(output) if output else "(no commits)"


# ──────────────────────────────────────────────
# git push / pull
# ──────────────────────────────────────────────

def filter_push_pull(raw: str) -> str:
    """
    简化 push/pull 输出：只显示最终结果行。
    成功时输出：ok main -> origin/main
    """
    lines = raw.splitlines()
    result = []
    for line in lines:
        stripped = line.strip()
        # 保留关键结果行
        if any(kw in stripped for kw in [
            "->", "up to date", "fast-forward",
            "error", "rejected", "Everything up-to-date",
            "master", "main",
        ]):
            result.append(stripped)
    output = '\n'.join(result) if result else raw.strip()
    return truncate(output)


# ──────────────────────────────────────────────
# git show
# ──────────────────────────────────────────────

def filter_show(raw: str) -> str:
    """git show 复用 diff 过滤器，但保留 commit 元数据"""
    lines = raw.splitlines()
    header = []
    diff_start = 0
    for i, line in enumerate(lines):
        if line.startswith("diff --git"):
            diff_start = i
            break
        header.append(line)

    # 只保留前 4 行元数据（commit/author/date/message）
    short_header = []
    for line in header[:6]:
        stripped = line.strip()
        if stripped:
            short_header.append(stripped)

    diff_part = filter_diff('\n'.join(lines[diff_start:]))
    return '\n'.join(short_header) + '\n\n' + diff_part


# ──────────────────────────────────────────────
# 路由入口
# ──────────────────────────────────────────────

def handle(subcommand: str, raw: str) -> tuple[str, str]:
    """
    根据 git 子命令选择过滤函数。
    返回 (filtered_output, subcommand_name)
    """
    sub = subcommand.lower()

    if sub == "status":
        return filter_status(raw), "status"
    elif sub == "diff":
        return filter_diff(raw), "diff"
    elif sub in ("log",):
        return filter_log(raw), "log"
    elif sub in ("push", "pull", "fetch"):
        return filter_push_pull(raw), sub
    elif sub == "show":
        return filter_show(raw), "show"
    else:
        # 未知子命令：通用截断+去重
        return truncate(dedup_lines(raw)), sub
