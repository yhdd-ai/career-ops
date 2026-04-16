"""
职位评估引擎
读取简历和配置，通过统一 LLM 接口评估 JD，并解析结构化结果。
"""
import re
from pathlib import Path
from datetime import datetime
from src.utils import load_cv, load_mode, load_profile


def auto_evaluate(jd_text: str, company: str = "", title: str = "",
                  location: str = "", url: str = "",
                  backend: str = "auto", use_cache: bool = True) -> dict:
    """
    两阶段评估 Pipeline：
      Stage 1 — Archetype 分类（关键词规则优先，置信度低时回退 LLM）
      Stage 2 — 带 Archetype 权重的 JD 评估

    backend:   "auto" | "claude" | "ollama"
    use_cache: True 时先查缓存，命中则直接返回；False 时强制重新评估
    """
    from src import cache as eval_cache
    from src.archetype import classify

    # ① 查缓存
    if use_cache:
        cached = eval_cache.get(url, jd_text)
        if cached:
            print("  ✦ 命中缓存，跳过 LLM 调用")
            return cached

    # ② Stage 1：Archetype 分类
    archetype, method = classify(jd_text, backend=backend)
    method_label = {"rule": "关键词规则", "llm": "LLM语义", "default": "默认"}.get(method, method)
    print(f"  🏷  岗位类型：{archetype.label}（{method_label}分类）")

    # ③ Stage 2：带 Archetype 权重的评估
    from src.llm_client import get_client
    client     = get_client(backend)
    prompt     = build_evaluation_prompt(jd_text, archetype=archetype)
    raw_result = client.chat(prompt)
    result     = parse_evaluation_result(raw_result, company, title, location, url)

    # 记录 Archetype 信息，方便后续分析
    result["archetype_id"]    = archetype.id
    result["archetype_label"] = archetype.label
    result["archetype_method"]= method

    # ④ 写入缓存
    eval_cache.put(url, jd_text, result)

    return result

BASE_DIR = Path(__file__).parent.parent


def build_evaluation_prompt(jd_text: str, use_summary: bool = True,
                            archetype=None) -> str:
    """
    生成评估提示词。
    use_summary=True（默认）：使用 CV 压缩摘要，节省约 300 tokens。
    use_summary=False：使用完整 CV，适合需要精确匹配细节的场景。
    archetype：Archetype 对象，用于注入岗位类型专属权重；None 则使用默认权重。
    """
    from src.token_optimizer import get_cv_summary, truncate_jd, check_prompt_size
    from src.archetype import format_weights_block, DEFAULT_ARCHETYPE

    cv      = get_cv_summary() if use_summary else load_cv()
    jd_text = truncate_jd(jd_text)
    profile = load_profile()
    mode    = load_mode("evaluate")

    arc = archetype if archetype is not None else DEFAULT_ARCHETYPE
    weights_block = format_weights_block(arc)

    preferred_locations  = "、".join(profile.get("preferred_locations", []))
    target_roles         = "、".join(profile.get("target_roles", []))
    preferred_industries = "、".join(profile.get("preferred_industries", []))
    min_daily            = profile.get("compensation", {}).get("min_daily", 0)
    preferred_daily      = profile.get("compensation", {}).get("preferred_daily", 200)

    prompt = f"""你是一个专业的实习求职顾问。请根据以下候选人信息和评估规则，对给定的职位进行详细评估。

═══════════════════════════════════════════
候选人简历摘要
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
岗位类型权重（覆盖默认权重，请严格遵守）
═══════════════════════════════════════════
{weights_block}

═══════════════════════════════════════════
评估规则（输出格式与评分细则）
═══════════════════════════════════════════
{mode}

═══════════════════════════════════════════
待评估职位 JD
═══════════════════════════════════════════
{jd_text}

请按照评估规则中的输出格式，给出完整的职位评估报告。权重以【岗位类型权重】部分为准。
"""
    check_prompt_size(prompt, "evaluate prompt")
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

    # 提取各维度分数（兼容表格格式 "| 岗位匹配度 | 85/100 |" 和纯文本 "岗位匹配度 85"）
    dimensions = {}
    dim_patterns = {
        "role_match":       r'岗位匹配度[^\d]*(\d+)',
        "growth_potential": r'成长空间[^\d]*(\d+)',
        "company_quality":  r'公司质量[^\d]*(\d+)',
        "location_fit":     r'地点匹配[^\d]*(\d+)',
        "compensation":     r'薪资水平[^\d]*(\d+)',
        "experience_match": r'经验要求匹配[^\d]*(\d+)',
        "workload_culture": r'工作强度与文化[^\d]*(\d+)',
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


def _clean_report(text: str) -> str:
    """清理模型输出：去掉代码块包裹、多余空行"""
    import re
    # 去掉开头和结尾的 ``` 代码块
    text = re.sub(r"^```[^\n]*\n", "", text.strip())
    text = re.sub(r"\n```$", "", text.strip())
    text = text.strip()
    # 压缩连续空行（最多保留 1 个）
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def save_report_to_file(evaluation: dict) -> Path:
    """将评估报告保存为干净的 Markdown 文件"""
    reports_dir = BASE_DIR / "reports"
    reports_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_company = evaluation["company"].replace("/", "-").replace(" ", "_")
    filename = f"{timestamp}_{safe_company}_{evaluation['grade']}{evaluation['score']}.md"
    filepath = reports_dir / filename

    clean_body = _clean_report(evaluation.get("full_report", ""))

    meta = []
    if evaluation.get("url"):
        meta.append(f"**链接**：{evaluation['url']}")
    if evaluation.get("evaluated_at"):
        meta.append(f"**评估时间**：{evaluation['evaluated_at']}")
    meta_block = "  ·  ".join(meta)

    content = f"# 职位评估报告 · {evaluation['company']} · {evaluation['title']}\n\n"
    if meta_block:
        content += f"{meta_block}\n\n---\n\n"
    content += clean_body + "\n"

    filepath.write_text(content, encoding="utf-8")
    return filepath
