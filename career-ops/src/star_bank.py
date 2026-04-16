"""
STAR 故事库模块

每次评估 JD 后，自动从候选人简历中提取最相关经历并生成 STAR 结构的面试故事，
追加到 reports/story_bank.md，随时间积累成一个面试素材库。

STAR = Situation（情境）/ Task（任务）/ Action（行动）/ Result（结果）

使用方式：
    from src.star_bank import generate_story, append_story, list_stories
    story = generate_story(jd_text, company, title, backend)
    append_story(story, company, title)
"""

import re
from pathlib import Path
from datetime import datetime
from src.utils import load_cv, load_mode

BASE_DIR  = Path(__file__).parent.parent
BANK_FILE = BASE_DIR / "reports" / "story_bank.md"

# ── 生成 ──────────────────────────────────────────────────────────────────────

def build_star_prompt(jd_text: str, company: str, title: str) -> str:
    """构建 STAR 故事生成提示词（使用完整 CV，不压缩）"""
    cv   = load_cv()
    mode = load_mode("star_story")

    return f"""你是一位面试教练。请根据以下候选人简历和目标职位，生成一条 STAR 结构的面试故事。

═══════════════════════════════════════════
生成规则
═══════════════════════════════════════════
{mode}

═══════════════════════════════════════════
候选人简历
═══════════════════════════════════════════
{cv}

═══════════════════════════════════════════
目标职位
═══════════════════════════════════════════
公司：{company or "（未知公司）"}
岗位：{title or "（未知岗位）"}

{jd_text}

请直接输出 STAR 故事，严格遵守输出格式，不加任何前言。
"""


def generate_story(jd_text: str, company: str = "", title: str = "",
                   backend: str = "auto") -> str:
    """调用 LLM 生成 STAR 故事文本"""
    from src.llm_client import get_client
    client = get_client(backend)
    print("  ⭐ 正在生成 STAR 面试故事...")
    return client.chat(build_star_prompt(jd_text, company, title), max_tokens=1024)


# ── 存储 ──────────────────────────────────────────────────────────────────────

def append_story(story_text: str, company: str = "", title: str = "") -> Path:
    """
    将 STAR 故事追加到 story_bank.md。
    文件头部为索引，故事块用分隔线隔开，支持持续积累。
    """
    BANK_FILE.parent.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry_id  = _next_id()

    # 首次创建时写文件头
    if not BANK_FILE.exists():
        BANK_FILE.write_text(
            "# STAR 故事库\n\n"
            "> 每次评估职位后自动积累，面试前快速复习。\n\n"
            "---\n\n",
            encoding="utf-8"
        )

    block = (
        f"## #{entry_id} · {company} · {title}\n"
        f"*生成时间：{timestamp}*\n\n"
        f"{story_text.strip()}\n\n"
        f"---\n\n"
    )

    with open(BANK_FILE, "a", encoding="utf-8") as f:
        f.write(block)

    return BANK_FILE


# ── 查询 ──────────────────────────────────────────────────────────────────────

def list_stories() -> list[dict]:
    """
    解析 story_bank.md，返回所有故事的元信息列表。
    每条：{id, company, title, timestamp, preview}
    """
    if not BANK_FILE.exists():
        return []

    content = BANK_FILE.read_text(encoding="utf-8")
    # 匹配 ## #N · company · title 块
    pattern = re.compile(
        r"## #(\d+) · (.+?) · (.+?)\n\*生成时间：(.+?)\*\n\n(.*?)(?=\n## #|\Z)",
        re.DOTALL
    )
    stories = []
    for m in pattern.finditer(content):
        body    = m.group(5).strip()
        preview = body[:80].replace("\n", " ") + ("..." if len(body) > 80 else "")
        stories.append({
            "id":        int(m.group(1)),
            "company":   m.group(2),
            "title":     m.group(3),
            "timestamp": m.group(4),
            "preview":   preview,
        })
    return stories


def search_stories(keyword: str) -> list[dict]:
    """
    在故事库中搜索包含关键词的条目（简单文本匹配，不区分大小写）。
    返回匹配的元信息列表。
    """
    keyword = keyword.lower()
    return [s for s in list_stories()
            if keyword in s["company"].lower()
            or keyword in s["title"].lower()
            or keyword in s["preview"].lower()]


def get_story_count() -> int:
    return len(list_stories())


# ── 内部 ──────────────────────────────────────────────────────────────────────

def _next_id() -> int:
    stories = list_stories()
    return (stories[-1]["id"] + 1) if stories else 1
