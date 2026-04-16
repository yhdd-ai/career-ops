"""
求职信生成引擎
根据简历和 JD 自动生成针对特定职位的中文求职信。
"""
import os
import yaml
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent.parent


def _load_api_config() -> dict:
    api_path = BASE_DIR / "config" / "api.yml"
    if not api_path.exists():
        return {}
    with open(api_path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _load_cv() -> str:
    cv_path = BASE_DIR / "cv.md"
    if not cv_path.exists():
        raise FileNotFoundError("找不到 cv.md，请先导入简历：python3 run.py import-cv <file>")
    return cv_path.read_text(encoding="utf-8")


def _load_cover_letter_mode() -> str:
    mode_path = BASE_DIR / "modes" / "cover_letter.md"
    if not mode_path.exists():
        raise FileNotFoundError("找不到 modes/cover_letter.md")
    return mode_path.read_text(encoding="utf-8")


def build_cover_letter_prompt(jd_text: str, company: str = "", title: str = "") -> str:
    """构建求职信生成提示词"""
    cv = _load_cv()
    mode = _load_cover_letter_mode()

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


def generate_cover_letter(jd_text: str, company: str = "", title: str = "") -> str:
    """
    调用 Claude API 生成求职信，返回求职信文本。
    """
    try:
        import anthropic
    except ImportError:
        raise ImportError("请先安装：pip install anthropic")

    cfg = _load_api_config()
    api_key = cfg.get("anthropic_api_key", "") or os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key or api_key.startswith("sk-ant-xxx"):
        raise ValueError("请在 config/api.yml 中填入有效的 anthropic_api_key")

    model = cfg.get("model", "claude-opus-4-6")
    max_tokens = cfg.get("max_tokens", 2048)

    prompt = build_cover_letter_prompt(jd_text, company, title)

    client = anthropic.Anthropic(api_key=api_key)
    print(f"  🤖 正在调用 Claude API ({model}) 生成求职信...")
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text


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
