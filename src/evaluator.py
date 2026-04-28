"""
职位评估引擎
读取简历和配置，通过统一 LLM 接口评估 JD，并解析结构化结果。

输出可靠性：
  使用 chat_structured() + JSON Schema 约束，LLM 直接返回 typed dict，
  消除正则解析失败的隐患。解析层退化为直接读取 dict 字段，无需 re.search。
  若结构化调用异常，回退到文本解析并设置 parse_failed=True 标记。
"""
import re
from pathlib import Path
from datetime import datetime
from src.utils import load_cv, load_mode, load_profile
from src.schemas import EVALUATION_TOOL_NAME, EVALUATION_SCHEMA

BASE_DIR = Path(__file__).parent.parent


def auto_evaluate(jd_text: str, company: str = "", title: str = "",
                  location: str = "", url: str = "",
                  backend: str = "auto", use_cache: bool = True) -> dict:
    """
    两阶段评估 Pipeline：
      Stage 1 — Archetype 分类（关键词规则优先，置信度低时回退 LLM）
      Stage 2 — 带 Archetype 权重的 JD 评估（chat_structured，JSON Schema 强制约束）

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

    # ③ Stage 2：带 Archetype 权重的评估（结构化输出）
    from src.llm_client import get_client
    from src.archetype import apply_gate_pass
    from src.context_engine import get_engine

    client = get_client(backend)

    # 从 Context Engine 获取历史校准块（历史不足 2 条时返回空字符串，不注入）
    context_block = get_engine().get_context_block()
    if context_block:
        print("  🧠 Context Engine 已激活（历史基准注入）")

    prompt = build_evaluation_prompt(
        jd_text, archetype=archetype, context_block=context_block
    )
    result = _call_structured(client, prompt, company, title, location, url)

    # ④ 门控评分：对 LLM 输出施加业务规则约束
    result = apply_gate_pass(result, archetype)
    if result["gate_triggered"]:
        for g in result["gate_reasons"]:
            dim_label = {
                "role_match": "岗位匹配度", "experience_match": "经验要求匹配",
                "company_quality": "公司质量",
            }.get(g["dim"], g["dim"])
            print(f"  ⚠  门控触发：{dim_label} {g['score']} < {g['threshold']}"
                  f"  →  等级 {result['original_grade']} 压至 {result['grade']}")

    # 记录 Archetype 信息，方便后续分析
    result["archetype_id"]    = archetype.id
    result["archetype_label"] = archetype.label
    result["archetype_method"]= method

    # ⑤ 写入缓存
    eval_cache.put(url, jd_text, result)

    return result


def _call_structured(client, prompt: str, company: str, title: str,
                     location: str, url: str) -> dict:
    """
    调用 chat_structured() 并将结果转换为标准 result dict。
    若结构化调用失败，回退到 chat() + parse_evaluation_result()，
    并在结果中设置 parse_failed=True 以供下游识别。
    """
    try:
        data = client.chat_structured(prompt, EVALUATION_TOOL_NAME, EVALUATION_SCHEMA)
        result = _build_result_from_schema(data, company, title, location, url)
        result["parse_failed"] = False
        return result

    except Exception as e:
        # 结构化调用失败：回退到文本解析（兼容性保障）
        print(f"  ⚠  结构化输出失败（{type(e).__name__}: {e}），回退文本解析")
        try:
            raw = client.chat(prompt)
        except Exception as fallback_err:
            # LLM 完全不可用，返回空结果
            return _empty_result(company, title, location, url,
                                 error=str(fallback_err))

        result = parse_evaluation_result(raw, company, title, location, url)
        # 只有分数和等级同时缺失才算真正解析失败；
        # 合法的低分岗位（score==0）不应被误标为 parse_failed
        result["parse_failed"] = (result["score"] == 0 and result["grade"] == "?")
        return result


def _build_result_from_schema(data: dict, company: str, title: str,
                               location: str, url: str) -> dict:
    """
    将 chat_structured 返回的 dict 转换为标准 result 格式。
    data 已经是 typed dict，直接读取字段，无需正则解析。
    """
    return {
        "company":        company,
        "title":          title,
        "location":       location,
        "url":            url,
        "score":          int(data["score"]),
        "grade":          str(data["grade"]),
        "dimensions":     {k: int(v) for k, v in data["dimensions"].items()},
        "recommendation": str(data.get("recommendation", "")),
        "full_report":    str(data.get("full_report", "")),
        "evaluated_at":   datetime.now().strftime("%Y-%m-%d %H:%M"),
        "status":         "待申请",
        "notes":          "",
    }


def _empty_result(company: str, title: str, location: str, url: str,
                  error: str = "") -> dict:
    """LLM 完全不可用时的兜底空结果"""
    return {
        "company": company, "title": title, "location": location, "url": url,
        "score": 0, "grade": "?",
        "dimensions": {k: 0 for k in [
            "role_match", "growth_potential", "company_quality",
            "location_fit", "compensation", "experience_match", "workload_culture"
        ]},
        "recommendation": "", "full_report": "",
        "evaluated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "status": "待申请", "notes": "",
        "parse_failed": True,
        "parse_error": error,
    }


def build_evaluation_prompt(jd_text: str, use_summary: bool = True,
                            archetype=None, context_block: str = "") -> str:
    """
    生成评估提示词。
    use_summary=True（默认）：使用 CV 压缩摘要，节省约 300 tokens。
    use_summary=False：使用完整 CV，适合需要精确匹配细节的场景。
    archetype：Archetype 对象，用于注入岗位类型专属权重；None 则使用默认权重。
    context_block：由 ContextEngine.get_context_block() 生成的历史评分基准块；
                   非空时注入 prompt，帮助 LLM 防止跨会话评分漂移（Context Drift）。
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

    # ── Context Engine 注入块（仅历史记录足够时出现）────────────────────────
    context_section = ""
    if context_block:
        context_section = f"""
═══════════════════════════════════════════
历史评分基准（一致性校准 · Context Engine）
═══════════════════════════════════════════
{context_block}

"""

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
{context_section}
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
将完整的 Markdown 报告正文放入 full_report 字段，同时在其他字段中填入精确的数值结果。
"""
    check_prompt_size(prompt, "evaluate prompt")
    return prompt


def parse_evaluation_result(raw_result: str, company: str, title: str,
                             location: str = "", url: str = "") -> dict:
    """
    【兼容性保留】基于正则的文本解析，仅在结构化输出失败时作为回退使用。
    新代码应优先使用 _call_structured() + chat_structured()。
    """
    # 提取综合评分
    score_match = re.search(r'综合评分[：:]\s*(\d+)', raw_result)
    score = int(score_match.group(1)) if score_match else 0

    # 提取等级
    grade_match = re.search(r'等级[：:]\s*([A-F])', raw_result)
    grade = grade_match.group(1) if grade_match else "?"

    # 提取各维度分数
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

    recommend_match = re.search(r'最终推荐.*?\n\s*(.*?)(?:\n|$)', raw_result)
    recommendation = recommend_match.group(1).strip() if recommend_match else ""

    return {
        "company": company, "title": title, "location": location, "url": url,
        "score": score, "grade": grade,
        "dimensions": dimensions,
        "recommendation": recommendation,
        "full_report": raw_result,
        "evaluated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "status": "待申请", "notes": "",
    }


def _clean_report(text: str) -> str:
    """清理模型输出：去掉代码块包裹、多余空行"""
    text = re.sub(r"^```[^\n]*\n", "", text.strip())
    text = re.sub(r"\n```$", "", text.strip())
    text = text.strip()
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

    # 如果门控触发，在报告头部注明
    gate_note = ""
    if evaluation.get("gate_triggered"):
        reasons = "；".join(r["reason"] for r in evaluation.get("gate_reasons", []))
        orig = evaluation.get("original_grade", "")
        curr = evaluation.get("grade", "")
        gate_note = f"> ⚠️ **门控触发**：等级由 {orig} 压至 {curr}。{reasons}\n\n"

    content = f"# 职位评估报告 · {evaluation['company']} · {evaluation['title']}\n\n"
    if meta_block:
        content += f"{meta_block}\n\n---\n\n"
    content += gate_note
    content += clean_body + "\n"

    filepath.write_text(content, encoding="utf-8")
    return filepath
