"""
LLM 结构化输出 Schema 定义

用于 chat_structured() 的工具定义，强制 LLM 按照 JSON Schema 约束输出结构体，
消除基于正则的文本解析脆弱性。

包含：
  EVALUATION_TOOL_NAME / EVALUATION_SCHEMA  — 职位评估结果
  ARCHETYPE_TOOL_NAME  / ARCHETYPE_SCHEMA   — 岗位 Archetype 分类结果
"""


# ── 职位评估 Schema ──────────────────────────────────────────────────────────

EVALUATION_TOOL_NAME = "submit_evaluation"

EVALUATION_SCHEMA: dict = {
    "type": "object",
    "description": "职位评估结果，包含综合评分、维度分数和完整报告",
    "properties": {
        "score": {
            "type": "integer",
            "minimum": 0,
            "maximum": 100,
            "description": "综合评分 0-100，由各维度加权计算"
        },
        "grade": {
            "type": "string",
            "enum": ["A", "B", "C", "D", "F"],
            "description": "综合等级：A=强烈推荐(85+), B=推荐(70-84), C=可尝试(55-69), D=不推荐(40-54), F=跳过(<40)"
        },
        "dimensions": {
            "type": "object",
            "description": "7个评估维度各自的原始分数（0-100）",
            "properties": {
                "role_match":        {"type": "integer", "minimum": 0, "maximum": 100, "description": "岗位匹配度"},
                "growth_potential":  {"type": "integer", "minimum": 0, "maximum": 100, "description": "成长空间"},
                "company_quality":   {"type": "integer", "minimum": 0, "maximum": 100, "description": "公司质量"},
                "location_fit":      {"type": "integer", "minimum": 0, "maximum": 100, "description": "地点匹配"},
                "compensation":      {"type": "integer", "minimum": 0, "maximum": 100, "description": "薪资水平"},
                "experience_match":  {"type": "integer", "minimum": 0, "maximum": 100, "description": "经验要求匹配"},
                "workload_culture":  {"type": "integer", "minimum": 0, "maximum": 100, "description": "工作强度与文化"},
            },
            "required": [
                "role_match", "growth_potential", "company_quality",
                "location_fit", "compensation", "experience_match", "workload_culture"
            ]
        },
        "recommendation": {
            "type": "string",
            "description": "最终推荐意见，2-3句话，指出最值得关注的优缺点和是否建议申请"
        },
        "full_report": {
            "type": "string",
            "description": "完整的 Markdown 格式评估报告正文，包含各维度分析、总结等"
        },
    },
    "required": ["score", "grade", "dimensions", "recommendation", "full_report"]
}


# ── Archetype 分类 Schema ────────────────────────────────────────────────────

ARCHETYPE_TOOL_NAME = "submit_archetype"

ARCHETYPE_SCHEMA: dict = {
    "type": "object",
    "description": "岗位 Archetype 分类结果",
    "properties": {
        "archetype_id": {
            "type": "string",
            "enum": ["llm_nlp", "ml_algo", "backend", "data", "frontend", "product", "general"],
            "description": (
                "岗位类型 ID："
                "llm_nlp=大模型/NLP/AIGC, "
                "ml_algo=机器学习/推荐/算法, "
                "backend=后端/服务端工程, "
                "data=数据分析/数据科学, "
                "frontend=前端/全栈, "
                "product=产品/运营, "
                "general=通用/其他"
            )
        }
    },
    "required": ["archetype_id"]
}
