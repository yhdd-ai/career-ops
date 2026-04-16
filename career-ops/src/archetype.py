"""
岗位 Archetype 分类模块

两阶段 Pipeline 的第一阶段：在正式评估前，先把 JD 归类到岗位类型，
再用 Archetype 特定的维度权重进行打分，使评估结果更贴近不同岗位的实际判断标准。

分类策略（混合方案，面试亮点）：
  Stage 1 — 规则分类：基于关键词快速匹配，零 LLM 消耗，覆盖 80% 明确 JD
  Stage 2 — LLM 分类：关键词置信度低时回退，处理模糊或跨领域 JD

支持的 Archetype：
  大模型/NLP   机器学习/算法   后端工程   数据分析/科学   前端/全栈   产品/运营   通用
"""

from __future__ import annotations
from dataclasses import dataclass, field


# ── Archetype 定义 ────────────────────────────────────────────────────────────

@dataclass
class Archetype:
    id:       str
    label:    str
    keywords: list[str]
    weights:  dict[str, float]    # 7 个维度的权重，合计必须 = 1.0
    tip:      str = ""            # 面向候选人的评估重点提示


# 规则：维度 key 与 evaluate.md / parse_evaluation_result 保持一致
_W_DEFAULT = dict(
    role_match=0.25, growth_potential=0.20, company_quality=0.15,
    location_fit=0.10, compensation=0.10, experience_match=0.10,
    workload_culture=0.10,
)

ARCHETYPES: dict[str, Archetype] = {

    "llm_nlp": Archetype(
        id="llm_nlp",
        label="大模型 / NLP / AIGC",
        keywords=[
            "大模型", "LLM", "NLP", "AIGC", "Transformer", "GPT", "RAG",
            "prompt", "预训练", "微调", "fine-tune", "生成式", "多模态",
            "向量数据库", "Agent", "langchain", "llamaindex",
        ],
        weights=dict(
            role_match=0.30,        # 技术方向契合最关键
            growth_potential=0.25,  # 大模型方向成长价值高
            company_quality=0.20,   # 平台背书对未来求职影响大
            location_fit=0.08,
            compensation=0.07,
            experience_match=0.05,  # 该方向实习生门槛相对宽松
            workload_culture=0.05,
        ),
        tip="重点关注：模型架构理论基础、有无真实训练/推理经验、导师资源",
    ),

    "ml_algo": Archetype(
        id="ml_algo",
        label="机器学习 / 推荐 / 计算机视觉",
        keywords=[
            "机器学习", "深度学习", "推荐系统", "计算机视觉", "CV", "图像",
            "目标检测", "强化学习", "特征工程", "XGBoost", "神经网络",
            "PyTorch", "TensorFlow", "算法工程师",
        ],
        weights=dict(
            role_match=0.28,
            growth_potential=0.22,
            company_quality=0.18,
            location_fit=0.10,
            compensation=0.10,
            experience_match=0.07,
            workload_culture=0.05,
        ),
        tip="重点关注：竞赛背景、论文发表、实际项目落地经验",
    ),

    "backend": Archetype(
        id="backend",
        label="后端工程 / 服务端 / 分布式",
        keywords=[
            "后端", "Java", "Go", "Golang", "Spring", "分布式", "微服务",
            "数据库", "MySQL", "Redis", "Kafka", "服务端", "RPC",
            "高并发", "中间件", "云原生", "Kubernetes",
        ],
        weights=dict(
            role_match=0.25,
            growth_potential=0.15,
            company_quality=0.20,  # 大厂后端更注重平台规模
            location_fit=0.10,
            compensation=0.13,     # 后端薪资差异较大，值得关注
            experience_match=0.12, # 后端门槛相对明确
            workload_culture=0.05,
        ),
        tip="重点关注：技术栈匹配度、业务规模（QPS/DAU）、是否接触核心链路",
    ),

    "data": Archetype(
        id="data",
        label="数据分析 / 数据科学 / BI",
        keywords=[
            "数据分析", "数据科学", "BI", "SQL", "数据挖掘", "Tableau",
            "Power BI", "数据可视化", "商业分析", "A/B测试", "数据仓库",
            "ETL", "Hive", "Spark", "统计分析",
        ],
        weights=dict(
            role_match=0.25,
            growth_potential=0.18,
            company_quality=0.17,
            location_fit=0.10,
            compensation=0.12,
            experience_match=0.10,
            workload_culture=0.08,
        ),
        tip="重点关注：业务场景丰富度、是否有真实决策影响力、工具栈是否现代",
    ),

    "frontend": Archetype(
        id="frontend",
        label="前端 / 全栈 / 移动端",
        keywords=[
            "前端", "React", "Vue", "JavaScript", "TypeScript", "全栈",
            "Node.js", "小程序", "iOS", "Android", "Flutter", "WebGL",
            "前端工程化", "移动端",
        ],
        weights=dict(
            role_match=0.25,
            growth_potential=0.18,
            company_quality=0.18,
            location_fit=0.10,
            compensation=0.12,
            experience_match=0.10,
            workload_culture=0.07,
        ),
        tip="重点关注：项目复杂度、是否涉及性能优化、跨端经验",
    ),

    "product": Archetype(
        id="product",
        label="产品 / 运营 / 增长",
        keywords=[
            "产品经理", "产品运营", "增长", "用户研究", "PRD", "原型",
            "运营", "内容运营", "社区运营", "增长黑客", "用户增长",
            "商业分析", "市场",
        ],
        weights=dict(
            role_match=0.22,
            growth_potential=0.20,
            company_quality=0.23,  # 品牌背书对产品岗影响最大
            location_fit=0.10,
            compensation=0.10,
            experience_match=0.08,
            workload_culture=0.07,
        ),
        tip="重点关注：产品方向与个人兴趣契合度、是否接触核心产品决策、品牌价值",
    ),

    "general": Archetype(
        id="general",
        label="通用 / 其他",
        keywords=[],
        weights=_W_DEFAULT,
        tip="",
    ),
}

# 默认 fallback
DEFAULT_ARCHETYPE = ARCHETYPES["general"]

# 置信度阈值：关键词命中数达到此值时，直接使用规则分类，不调 LLM
KEYWORD_THRESHOLD = 2


# ── 混合分类器 ────────────────────────────────────────────────────────────────

def classify(jd_text: str, backend: str = "auto") -> tuple[Archetype, str]:
    """
    对 JD 进行 Archetype 分类，返回 (Archetype, method)。
    method: "rule"（关键词规则）| "llm"（LLM 分类）| "default"（兜底）

    策略：
      1. 规则扫描：统计各 Archetype 的关键词命中数
      2. 命中数 >= KEYWORD_THRESHOLD：直接返回，零 LLM 消耗
      3. 否则：调 LLM 做语义分类（仅此一次，约 200 tokens）
    """
    archetype, score = _rule_classify(jd_text)
    if score >= KEYWORD_THRESHOLD:
        return archetype, "rule"

    # 关键词命中不足，回退到 LLM 分类
    try:
        archetype = _llm_classify(jd_text, backend)
        return archetype, "llm"
    except Exception:
        return DEFAULT_ARCHETYPE, "default"


def _rule_classify(jd_text: str) -> tuple[Archetype, int]:
    """关键词扫描，返回 (最高命中 Archetype, 命中数)"""
    text = jd_text.lower()
    best_archetype = DEFAULT_ARCHETYPE
    best_score     = 0

    for arc in ARCHETYPES.values():
        if not arc.keywords:
            continue
        hits = sum(1 for kw in arc.keywords if kw.lower() in text)
        if hits > best_score:
            best_score     = hits
            best_archetype = arc

    return best_archetype, best_score


def _llm_classify(jd_text: str, backend: str = "auto") -> Archetype:
    """调用 LLM 语义分类，返回对应 Archetype"""
    from src.llm_client import get_client
    from src.utils import load_mode
    from src.token_optimizer import truncate_jd

    client     = get_client(backend)
    mode       = load_mode("archetype")
    jd_preview = truncate_jd(jd_text, max_chars=800)   # 分类只需要 JD 摘要

    ids_desc = "\n".join(
        f"  {arc.id}: {arc.label}"
        for arc in ARCHETYPES.values()
        if arc.id != "general"
    )

    prompt = f"""{mode}

可选 Archetype ID 列表：
{ids_desc}
  general: 通用 / 其他

待分类 JD（摘要）：
{jd_preview}

请只输出一个 Archetype ID，不加任何解释。"""

    raw = client.chat(prompt, max_tokens=32).strip().lower()

    # 解析 LLM 返回的 ID
    for aid in ARCHETYPES:
        if aid in raw:
            return ARCHETYPES[aid]

    return DEFAULT_ARCHETYPE


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def format_weights_block(archetype: Archetype) -> str:
    """将 Archetype 权重格式化为注入 Prompt 的文本块"""
    dim_labels = {
        "role_match":       "岗位匹配度",
        "growth_potential": "成长空间",
        "company_quality":  "公司质量",
        "location_fit":     "地点匹配",
        "compensation":     "薪资水平",
        "experience_match": "经验要求匹配",
        "workload_culture": "工作强度与文化",
    }
    lines = [
        f"【岗位类型：{archetype.label}】",
        "本次评估请使用以下权重（针对该岗位类型调整）：",
    ]
    for key, pct in archetype.weights.items():
        label = dim_labels.get(key, key)
        lines.append(f"  · {label}：{int(pct * 100)}%")
    if archetype.tip:
        lines.append(f"评估重点：{archetype.tip}")
    return "\n".join(lines)


def get_archetype_by_id(aid: str) -> Archetype:
    return ARCHETYPES.get(aid, DEFAULT_ARCHETYPE)
