"""
CV 定向裁剪引擎
根据 JD 自动生成针对特定职位的简历裁剪版本。
"""
import os
import re
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


def _load_tailor_mode() -> str:
    mode_path = BASE_DIR / "modes" / "tailor_cv.md"
    if not mode_path.exists():
        raise FileNotFoundError("找不到 modes/tailor_cv.md")
    return mode_path.read_text(encoding="utf-8")


def build_tailor_prompt(jd_text: str, company: str = "", title: str = "") -> str:
    """构建 CV 裁剪提示词"""
    cv = _load_cv()
    mode = _load_tailor_mode()

    target_info = ""
    if company or title:
        target_info = f"\n目标公司：{company}\n目标岗位：{title}\n"

    prompt = f"""你是一位专业的求职顾问。请根据以下候选人简历和目标职位 JD，生成一份定向裁剪版简历。

═══════════════════════════════════════════
裁剪规则
═══════════════════════════════════════════
{mode}

═══════════════════════════════════════════
候选人原始简历
═══════════════════════════════════════════
{cv}

═══════════════════════════════════════════
目标职位信息
═══════════════════════════════════════════{target_info}
{jd_text}

请按照裁剪规则，输出定向裁剪后的简历（Markdown 格式），结尾附上裁剪说明。
"""
    return prompt


def tailor_cv(jd_text: str, company: str = "", title: str = "") -> str:
    """
    调用 Claude API 生成裁剪版简历，返回裁剪后的文本。
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
    max_tokens = cfg.get("max_tokens", 4096)

    prompt = build_tailor_prompt(jd_text, company, title)

    client = anthropic.Anthropic(api_key=api_key)
    print(f"  🤖 正在调用 Claude API ({model}) 裁剪简历...")
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text


def save_tailored_cv(tailored_text: str, company: str, title: str) -> Path:
    """将裁剪版简历保存为 Markdown 文件"""
    out_dir = BASE_DIR / "reports" / "tailored_cvs"
    out_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_company = (company or "未知公司").replace("/", "-").replace(" ", "_")
    safe_title   = (title   or "未知岗位").replace("/", "-").replace(" ", "_")
    filename = f"{timestamp}_{safe_company}_{safe_title}_tailored.md"
    filepath = out_dir / filename

    # 提取裁剪说明（最后一行 **裁剪说明**:...）
    note_match = re.search(r'\*\*裁剪说明\*\*[：:](.*?)$', tailored_text, re.MULTILINE)
    note = note_match.group(1).strip() if note_match else ""

    header = f"# 定向简历 · {company} · {title}\n\n"
    header += f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}"
    if note:
        header += f"  |  裁剪策略：{note}"
    header += "\n\n---\n\n"

    # 去掉裁剪说明行，只保留简历主体
    body = re.sub(r'\n\*\*裁剪说明\*\*[：:].*$', '', tailored_text, flags=re.MULTILINE).strip()

    filepath.write_text(header + body + "\n", encoding="utf-8")
    return filepath
