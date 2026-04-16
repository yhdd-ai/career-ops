"""
求职信生成引擎
根据简历和 JD 自动生成针对特定职位的中文求职信。
"""
from pathlib import Path
from datetime import datetime
from src.utils import load_cv, load_mode

BASE_DIR = Path(__file__).parent.parent


def build_cover_letter_prompt(jd_text: str, company: str = "", title: str = "") -> str:
    """构建求职信生成提示词"""
    cv   = load_cv()
    mode = load_mode("cover_letter")

    prompt = f"""你是一位资深 HR 顾问，请根据以下候选人简历和目标职位信息，生成一封专业的求职信。

═══════════════════════════════════════════
写作规则
═══════════════════════════════════════════
{mode}

═══════════════════════════════════════════
候选人简历
═══════════════════════════════════════════
{cv}

═══════════════════════════════════════════
目标职位
═══════════════════════════════════════════
目标公司：{company or "（公司名）"}
目标岗位：{title or "（岗位名）"}

{jd_text}

请直接输出求职信正文，不加任何说明前言。
"""
    return prompt


def generate_cover_letter(jd_text: str, company: str = "", title: str = "",
                          backend: str = "auto") -> str:
    """通过统一 LLM 接口生成求职信"""
    from src.llm_client import get_client
    client = get_client(backend)
    return client.chat(build_cover_letter_prompt(jd_text, company, title), max_tokens=2048)


def save_cover_letter(letter_text: str, company: str, title: str) -> Path:
    """将求职信保存为 Markdown 文件"""
    out_dir = BASE_DIR / "reports" / "cover_letters"
    out_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_company = (company or "未知公司").replace("/", "-").replace(" ", "_")
    safe_title   = (title   or "未知岗位").replace("/", "-").replace(" ", "_")
    filename = f"{timestamp}_{safe_company}_{safe_title}_cover_letter.md"
    filepath = out_dir / filename

    header = f"# 求职信 · {company} · {title}\n\n"
    header += f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n---\n\n"

    filepath.write_text(header + letter_text.strip() + "\n", encoding="utf-8")
    return filepath
