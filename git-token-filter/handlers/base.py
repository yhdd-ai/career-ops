"""
base.py - 通用过滤工具：截断、去重、token 估算
"""

MAX_CHARS = 3000  # 默认输出上限（约 750 tokens）


def truncate(text: str, max_chars: int = MAX_CHARS) -> str:
    """截断超长输出，并注明隐藏了多少行"""
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    hidden_lines = text[max_chars:].count('\n')
    return truncated + f"\n... [已截断，隐藏 {hidden_lines} 行]"


def dedup_lines(text: str) -> str:
    """合并连续重复行，并显示重复次数"""
    lines = text.splitlines()
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        count = 1
        while i + count < len(lines) and lines[i + count] == line:
            count += 1
        if count > 1:
            result.append(f"{line}  [x{count}]")
        else:
            result.append(line)
        i += count
    return '\n'.join(result)


def estimate_tokens(text: str) -> int:
    """粗略估算 token 数（1 token ≈ 4 字符）"""
    return len(text) // 4


def filter_empty_lines(text: str) -> str:
    """去掉多余的空行（连续空行合并为一行）"""
    import re
    return re.sub(r'\n{3,}', '\n\n', text).strip()
