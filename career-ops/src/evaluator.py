"""
职位评估引擎
读取简历和配置，自动调用 Claude API 评估 JD，并解析结构化结果。
"""
import os
import json
import yaml
from pathlib import Path
from datetime import datetime


def load_api_config() -> dict:
    api_path = BASE_DIR / "config" / "api.yml"
    if not api_path.exists():
        return {}
    with open(api_path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def auto_evaluate(jd_text: str, company: str = "", title: str = "",
                  location: str = "", url: str = "") -> dict:
    """
    全自动评估：调用 Claude API，返回解析后的职位评估字典。
    需要 config/api.yml 中配置 anthropic_api_key。
    """
    try:
        import anthropic
    except ImportError:
        raise ImportError("请先安装：pip install anthropic")

    cfg = load_api_config()
    api_key = cfg.get("anthropic_api_key", "") or os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key or api_key.startswith("sk-ant-xxx"):
        raise ValueError("请在 config/api.yml 中填入有效的 anthropic_api_key")

    model = cfg.get("model", "claude-opus-4-6")
    max_tokens = cfg.get("max_tokens", 4096)

    prompt = build_evaluation_prompt(jd_text)

    client = anthropic.Anthropic(api_key=api_key)
    print(f"  🤖 正在调用 Claude API ({model})...")
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}]
    )

    raw_result = response.content[0].text
    return parse_evaluation_result(raw_result, company, title, location, url)

BASE_DIR = Path(__file__).parent.parent


def load_cv() -> str:
    cv_path = BASE_DIR / "cv.md"
    if not cv_path.exists():
        raise FileNotFoundError("找不到 cv.md，请先完善您的简历")
    return cv_path.read_text(encoding="utf-8")


def load_profile() -> dict:
    profile_path = BASE_DIR / "config" / "profile.yml"
    if not profile_path.exists():
        raise FileNotFoundError("找不到 config/profile.yml")
    with open(profile_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_evaluate_mode() -> str:
    mode_path = BASE_DIR / "modes" / "evaluate.md"
    if not mode_path.exists():
        raise FileNotFoundError("找不到 modes/evaluate.md")
    return mode_path.read_text(encoding="utf-8")


def build_evaluation_prompt(jd_text: str) -> str:
    """生成完整评估提示词，可粘贴到任何 AI 对话中使用"""
    cv = load_cv()
    profile = load_profile()
    mode = load_evaluate_mode()

    preferred_locations = "、".join(profile.get("preferred_locations", []))
    target_roles = "、".join(profile.get("target_roles", []))
    preferred_industries = "、".join(profile.get("preferred_industries", []))
    min_daily = profile.get("compensation", {}).get("min_daily", 0)
    preferred_daily = profile.get("compensation", {}).get("preferred_daily", 200)

    prompt = f"""你是一个专业的实习求职顾问。请根据以下候选人信息和评估规则，对给定的职位进行详细评估。

═══════════════════════════════════════════
候选人简历
═══════════════════════════════════════════
{cv}

═══════════════════════════════════════════
候选人求职偏好
═══════════════════════════════════════════
目标岗位：{target_roles}
偏好城市：{preferred_locations}
目标行业：{preferred_industries}
期望日薪：{preferred_daily}元（最低：{min_daily}元）

═══════════════════════════════════════════
评估规则（请严格按照此框架评分）
═══════════════════════════════════════════
{mode}

═══════════════════════════════════════════
待评估职位 JD
═══════════════════════════════════════════
{jd_text}

请按照评估规则中的输出格式，给出完整的职位评估报告。
"""
    return prompt


def parse_evaluation_result(raw_result: str, company: str, title: str,
                             location: str = "", url: str = "") -> dict:
    """
    解析评估报告文本，提取关键信息并生成结构化数据。
    raw_result: Claude 返回的评估报告文本
    """
    import re

    # 提取综合评分
    score_match = re.search(r'综合评分[：:]\s*(\d+)', raw_result)
    score = int(score_match.group(1)) if score_match else 0

    # 提取等级
    grade_match = re.search(r'等级[：:]\s*([A-F])', raw_result)
    grade = grade_match.group(1) if grade_match else "?"

    # 提取各维度分数
    dimensions = {}
    dim_patterns = {
        "role_match": r'岗位匹配度\s+(\d+)',
        "growth_potential": r'成长空间\s+(\d+)',
        "company_quality": r'公司质量\s+(\d+)',
        "location_fit": r'地点匹配\s+(\d+)',
        "compensation": r'薪资水平\s+(\d+)',
        "experience_match": r'经验要求匹配\s+(\d+)',
        "workload_culture": r'工作强度与文化\s+(\d+)',
    }
    for key, pattern in dim_patterns.items():
        m = re.search(pattern, raw_result)
        dimensions[key] = int(m.group(1)) if m else 0

    # 提取最终推荐
    recommend_match = re.search(r'最终推荐.*?\n\s*(.*?)(?:\n|$)', raw_result)
    recommendation = recommend_match.group(1).strip() if recommend_match else ""

    return {
        "company": company,
        "title": title,
        "location": location,
        "url": url,
        "score": score,
        "grade": grade,
        "dimensions": dimensions,
        "recommendation": recommendation,
        "full_report": raw_result,
        "evaluated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "status": "待申请",
        "notes": "",
    }


def save_report_to_file(evaluation: dict) -> Path:
    """将评估报告保存为 Markdown 文件"""
    reports_dir = BASE_DIR / "reports"
    reports_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_company = evaluation["company"].replace("/", "-").replace(" ", "_")
    filename = f"{timestamp}_{safe_company}_{evaluation['grade']}{evaluation['score']}.md"
    filepath = reports_dir / filename

    content = f"""# 职位评估报告

**公司**：{evaluation['company']}
**职位**：{evaluation['title']}
**地点**：{evaluation['location']}
**评分**：{evaluation['score']}/100（{evaluation['grade']} 级）
**评估时间**：{evaluation['evaluated_at']}
**链接**：{evaluation['url']}

---

{evaluation['full_report']}
"""
    filepath.write_text(content, encoding="utf-8")
    return filepath
