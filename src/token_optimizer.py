"""
Token 用量优化模块

三项优化：
1. CV 压缩摘要：evaluate/recommend 用 ~150 token 摘要替代 ~470 token 原文
2. JD 截断：超过 MAX_JD_CHARS 的 JD 自动截断，保留关键段落
3. 用量预警：prompt 超过阈值时打印警告

CV 摘要生成后缓存到 config/cv_summary.md，只在 cv.md 变动时重新生成。
"""
import hashlib
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent

# ── 阈值配置 ────────────────────────────────────────────────────────────────
MAX_JD_CHARS   = 1500   # JD 超过此长度时截断（约 375 tokens）
WARN_TOKENS    = 3000   # prompt 超过此 token 数时预警
CV_SUMMARY_LEN = 600    # CV 摘要目标长度（chars，约 150 tokens）


# ── Token 估算（中英文混合修正：中文字符约 1 char = 1 token）──────────────
def estimate_tokens(text: str) -> int:
    """
    估算文本 token 数。
    修正：英文 4 char ≈ 1 token；中文 1 字符 ≈ 1 token。
    混合文本分别统计，避免纯英文公式对中文严重低估。
    """
    chinese = sum(1 for ch in text if '\u4e00' <= ch <= '\u9fff')
    other   = len(text) - chinese
    return chinese + other // 4


def check_prompt_size(prompt: str, label: str = "prompt") -> None:
    """超过阈值时打印预警，不阻断流程"""
    tokens = estimate_tokens(prompt)
    if tokens > WARN_TOKENS:
        print(f"  ⚠ {label} 较大（约 {tokens} tokens），响应可能较慢或费用较高")


# ── JD 截断 ─────────────────────────────────────────────────────────────────
def truncate_jd(jd_text: str, max_chars: int = MAX_JD_CHARS) -> str:
    """
    截断过长的 JD，优先保留前半部分（通常含职责和要求），
    超出部分用提示语替代。
    """
    if len(jd_text) <= max_chars:
        return jd_text

    truncated = jd_text[:max_chars]
    # 尽量在句子/段落边界截断
    for sep in ["\n\n", "\n", "。", "；"]:
        idx = truncated.rfind(sep)
        if idx > max_chars * 0.7:
            truncated = truncated[:idx]
            break

    original_len = len(jd_text)
    return truncated + f"\n\n[JD 已截断，原文 {original_len} 字，保留前 {len(truncated)} 字]"


# ── CV 摘要缓存 ──────────────────────────────────────────────────────────────
def _cv_hash() -> str:
    cv_path = BASE_DIR / "cv.md"
    return hashlib.md5(cv_path.read_bytes()).hexdigest()[:8] if cv_path.exists() else ""


def _summary_path() -> Path:
    return BASE_DIR / "config" / "cv_summary.md"


def _is_summary_fresh() -> bool:
    """检查 cv_summary.md 是否与当前 cv.md 一致（通过 hash 注释）"""
    sp = _summary_path()
    if not sp.exists():
        return False
    first_line = sp.read_text(encoding="utf-8").splitlines()[0]
    return first_line.strip() == f"<!-- cv_hash:{_cv_hash()} -->"


def get_cv_summary(force_rebuild: bool = False) -> str:
    """
    返回 CV 压缩摘要。首次调用时从 cv.md 提取关键信息生成摘要并缓存；
    cv.md 变动后自动重建缓存。
    """
    if not force_rebuild and _is_summary_fresh():
        lines = _summary_path().read_text(encoding="utf-8").splitlines()
        return "\n".join(lines[1:]).strip()  # 跳过 hash 注释行

    return _build_summary_from_cv()


def _build_summary_from_cv() -> str:
    """从 cv.md 提取关键信息，生成紧凑摘要并缓存"""
    cv_path = BASE_DIR / "cv.md"
    if not cv_path.exists():
        raise FileNotFoundError("找不到 cv.md")

    cv_text = cv_path.read_text(encoding="utf-8")
    summary = _extract_cv_key_info(cv_text)

    # 写入缓存（首行为 hash 注释）
    sp = _summary_path()
    sp.parent.mkdir(exist_ok=True)
    sp.write_text(f"<!-- cv_hash:{_cv_hash()} -->\n{summary}", encoding="utf-8")

    return summary


def _extract_cv_key_info(cv_text: str) -> str:
    """
    从简历文本中提取关键信息：
    - 姓名 + 学历（学校、专业、时间）
    - 工作/实习经历（公司、职位、核心成果，每段 ≤ 2 行）
    - 核心技能（一行）
    使用规则提取，不依赖 LLM，零 token 消耗。
    """
    import re
    lines = cv_text.splitlines()
    sections: dict[str, list[str]] = {}
    current = "header"
    sections[current] = []

    section_keywords = {
        "教育": "education",
        "工作": "experience",
        "实习": "experience",
        "项目": "projects",
        "科研": "projects",
        "技能": "skills",
        "荣誉": "honors",
    }

    for line in lines:
        matched = False
        for kw, key in section_keywords.items():
            if kw in line and len(line) < 30:
                current = key
                sections.setdefault(current, [])
                matched = True
                break
        if not matched:
            sections.setdefault(current, []).append(line)

    parts = []

    # 姓名
    header_lines = [l for l in sections.get("header", []) if l.strip()]
    if header_lines:
        parts.append(header_lines[0].strip())  # 姓名
        for l in header_lines[1:3]:
            if l.strip():
                parts.append(l.strip())

    # 教育（最多 3 行）
    edu = [l for l in sections.get("education", []) if l.strip()]
    if edu:
        parts.append("【教育】" + "；".join(edu[:3]))

    # 工作/实习经历（每段取前 2 行）
    exp_lines = [l for l in sections.get("experience", []) if l.strip()]
    if exp_lines:
        # 找公司名行（通常是粗体或较短的行）
        condensed = []
        for i, l in enumerate(exp_lines[:12]):
            stripped = l.lstrip()
            # 跳过纯项目符号行但保留有实质内容的
            if stripped.startswith("参与") or stripped.startswith("设计") or stripped.startswith("实习成效"):
                if i < 6:
                    condensed.append(stripped[:60])
            else:
                condensed.append(stripped[:60])
        parts.append("【经历】" + "；".join(condensed[:5]))

    # 技能（取前 100 字）
    skill_lines = [l.strip() for l in sections.get("skills", []) if l.strip()]
    if skill_lines:
        skill_text = " ".join(skill_lines)[:120]
        parts.append("【技能】" + skill_text)

    summary = "\n".join(parts)

    # 超出目标长度时截断
    if len(summary) > CV_SUMMARY_LEN:
        summary = summary[:CV_SUMMARY_LEN] + "..."

    return summary


def rebuild_cv_summary() -> str:
    """强制重建 CV 摘要缓存，返回新摘要"""
    return _build_summary_from_cv()
