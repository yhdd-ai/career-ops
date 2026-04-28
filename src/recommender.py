"""
AI 职位推荐模块
根据用户指定方向，调用 Claude API 推荐匹配的公司和职位
"""
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent.parent


def _load_file(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def build_recommend_prompt(direction: str) -> str:
    from src.token_optimizer import get_cv_summary, check_prompt_size
    cv      = get_cv_summary()
    profile = _load_file(BASE_DIR / "config" / "profile.yml")
    mode    = _load_file(BASE_DIR / "modes" / "recommend.md")

    prompt = f"""你是一个专业的实习求职顾问。请根据以下候选人信息，为其推荐匹配的实习职位。

═══════════════════════════════════════
候选人简历摘要
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
    check_prompt_size(prompt, "recommend prompt")
    return prompt


def auto_recommend(direction: str, backend: str = "auto") -> str:
    """通过统一 LLM 接口返回推荐报告文本"""
    from src.llm_client import get_client
    client = get_client(backend)
    return client.chat(build_recommend_prompt(direction))


def save_recommend_report(direction: str, report: str) -> Path:
    """保存推荐报告到 reports/"""
    reports_dir = BASE_DIR / "reports"
    reports_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_dir  = direction.replace(" ", "_").replace("/", "-")[:20]
    path = reports_dir / f"{timestamp}_推荐_{safe_dir}.md"
    path.write_text(f"# 职位推荐报告\n\n**方向**：{direction}\n\n---\n\n{report}", encoding="utf-8")
    return path
