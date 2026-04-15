"""
AI 职位推荐模块
根据用户指定方向，调用 Claude API 推荐匹配的公司和职位
"""
import re
import yaml
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent.parent


def _load_file(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def build_recommend_prompt(direction: str) -> str:
    cv      = _load_file(BASE_DIR / "cv.md")
    profile = _load_file(BASE_DIR / "config" / "profile.yml")
    mode    = _load_file(BASE_DIR / "modes" / "recommend.md")

    return f"""你是一个专业的实习求职顾问。请根据以下候选人信息，为其推荐匹配的实习职位。

═══════════════════════════════════════
候选人简历
═══════════════════════════════════════
{cv}

═══════════════════════════════════════
候选人偏好配置
═══════════════════════════════════════
{profile}

═══════════════════════════════════════
推荐规则
═══════════════════════════════════════
{mode}

═══════════════════════════════════════
用户指定求职方向
═══════════════════════════════════════
{direction}

请按照推荐规则中的输出格式，给出完整的职位推荐报告。
"""


def auto_recommend(direction: str) -> str:
    """调用 Claude API，返回推荐报告文本"""
    try:
        import anthropic
    except ImportError:
        raise ImportError("请先安装：pip install anthropic")

    cfg_path = BASE_DIR / "config" / "api.yml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}

    import os
    api_key = cfg.get("anthropic_api_key", "") or os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key or "xxx" in api_key:
        raise ValueError("请在 config/api.yml 中填入有效的 anthropic_api_key")

    model      = cfg.get("model", "claude-opus-4-6")
    max_tokens = cfg.get("max_tokens", 4096)
    prompt     = build_recommend_prompt(direction)

    client = anthropic.Anthropic(api_key=api_key)
    print(f"  🤖 正在调用 Claude API ({model})...")

    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text


def save_recommend_report(direction: str, report: str) -> Path:
    """保存推荐报告到 reports/"""
    reports_dir = BASE_DIR / "reports"
    reports_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_dir  = direction.replace(" ", "_").replace("/", "-")[:20]
    path = reports_dir / f"{timestamp}_推荐_{safe_dir}.md"
    path.write_text(f"# 职位推荐报告\n\n**方向**：{direction}\n\n---\n\n{report}", encoding="utf-8")
    return path
