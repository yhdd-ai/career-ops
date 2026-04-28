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


# ── 门控规则 ──────────────────────────────────────────────────────────────────

# 等级排序（用于门控比较）：数字越大等级越高
GRADE_RANK: dict[str, int] = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1, "?": 0}

@dataclass
class Gate:
    """
    门控规则：当某维度得分低于阈值时，强制将最终等级压低至 max_grade。
    体现"关键维度一票否决"的业务逻辑，防止低匹配岗位因其他维度高分而被高估。
    """
    dim:       str    # 被监控的维度 key（与 parse_evaluation_result 一致）
    threshold: int    # 触发阈值（dim 得分 < threshold 时触发）
    max_grade: str    # 触发后等级上限（A/B/C/D/F）
    reason:    str    # 人类可读的触发原因，显示在报告中


# ── 全局门控（所有 Archetype 共用）────────────────────────────────────────────

GLOBAL_GATES: list[Gate] = [
    Gate(
        dim="role_match", threshold=35, max_grade="C",
        reason="岗位方向与候选人背景不匹配（岗位匹配度<35），即使其他维度得分高，整体不建议申请",
    ),
    Gate(
        dim="experience_match", threshold=20, max_grade="D",
        reason="岗位明确要求有工作经验（经验匹配度<20），实习生申请成功率极低",
    ),
]


# ── Archetype 定义 ────────────────────────────────────────────────────────────

@dataclass
class Archetype:
    id:       str
    label:    str
    keywords: list[str]
    weights:  dict[str, float]    # 7 个维度的权重，合计必须 = 1.0
    tip:      str = ""            # 面向候选人的评估重点提示
    gates:    list[Gate] = field(default_factory=list)  # 该类型专属门控规则


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
            role_match=0.30,
            growth_potential=0.25,
            company_quality=0.20,
            location_fit=0.08,
            compensation=0.07,
            experience_match=0.05,
            workload_culture=0.05,
        ),
        tip="重点关注：模型架构理论基础、有无真实训练/推理经验、导师资源",
        gates=[
            Gate(
                dim="role_match", threshold=50, max_grade="B",
                reason="大模型/NLP 岗位专业壁垒高，方向契合度不足（<50）时价值有限",
            ),
        ],
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
        gates=[
            Gate(
                dim="role_match", threshold=45, max_grade="B",
                reason="算法岗技术专项要求明确，方向契合度不足（<45）时建议优先考虑其他岗位",
            ),
        ],
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
            company_quality=0.20,
            location_fit=0.10,
            compensation=0.13,
            experience_match=0.12,
            workload_culture=0.05,
        ),
        tip="重点关注：技术栈匹配度、业务规模（QPS/DAU）、是否接触核心链路",
        gates=[
            Gate(
                dim="experience_match", threshold=30, max_grade="C",
                reason="后端岗位技术门槛明确，经验匹配度不足（<30）时面试通过率偏低",
            ),
        ],
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
        # 数据分析岗跨界相对容易，仅使用全局门控
        gates=[],
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
        gates=[],
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
            company_quality=0.23,
            location_fit=0.10,
            compensation=0.10,
            experience_match=0.08,
            workload_culture=0.07,
        ),
        tip="重点关注：产品方向与个人兴趣契合度、是否接触核心产品决策、品牌价值",
        gates=[
            Gate(
                dim="company_quality", threshold=40, max_grade="C",
                reason="产品/运营岗品牌背书关键，公司质量过低（<40）会显著削弱简历价值",
            ),
        ],
    ),

    "general": Archetype(
        id="general",
        label="通用 / 其他",
        keywords=[],
        weights=_W_DEFAULT,
        tip="",
        gates=[],
    ),
}

# 权重完整性断言：所有 Archetype 的权重之和必须严格等于 1.0
# 在模块加载时检查，配置错误立即暴露，不等到运行时
for _arc in ARCHETYPES.values():
    _total = round(sum(_arc.weights.values()), 10)
    assert _total == 1.0, (
        f"Archetype '{_arc.id}' 维度权重合计 {_total} ≠ 1.0，"
        f"请检查 archetype.py 中该类型的 weights 配置"
    )

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
    """
    调用 LLM 语义分类，返回对应 Archetype。

    使用 chat_structured() + ARCHETYPE_SCHEMA 强制输出 JSON，
    直接读取 archetype_id 字段，无需正则解析 LLM 文本。
    max_tokens 设为 128（tool_use block 需要足够空间包裹 JSON）。
    """
    from src.llm_client import get_client
    from src.utils import load_mode
    from src.token_optimizer import truncate_jd
    from src.schemas import ARCHETYPE_TOOL_NAME, ARCHETYPE_SCHEMA

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

请选择最匹配的 Archetype ID，填入 archetype_id 字段。"""

    # chat_structured 直接返回 {"archetype_id": "llm_nlp"} 等 dict，
    # 无需正则解析，LLM 不可能输出 enum 之外的值
    data = client.chat_structured(prompt, ARCHETYPE_TOOL_NAME, ARCHETYPE_SCHEMA,
                                  max_tokens=128)
    aid = data.get("archetype_id", "general")
    return ARCHETYPES.get(aid, DEFAULT_ARCHETYPE)


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


# ── 门控评分 ──────────────────────────────────────────────────────────────────

def apply_gate_pass(result: dict, archetype: Archetype) -> dict:
    """
    对 LLM 评估结果施加门控规则：
      1. 先检查全局门控（GLOBAL_GATES）
      2. 再检查 Archetype 专属门控（archetype.gates）
      3. 所有触发的门控中，取最严格的等级上限

    result 中新增字段：
      gate_triggered  bool   是否有门控被触发
      gate_reasons    list   所有触发门控的 reason
      original_grade  str    门控前的原始等级（未触发时与 grade 相同）
    """
    dims       = result.get("dimensions", {})
    cur_grade  = result.get("grade", "?")
    cur_rank   = GRADE_RANK.get(cur_grade, 0)

    all_gates      = GLOBAL_GATES + archetype.gates
    triggered      = []
    effective_rank = cur_rank   # 从当前等级开始向下压

    for gate in all_gates:
        dim_score = dims.get(gate.dim, 100)   # 不存在的维度不触发
        if dim_score < gate.threshold:
            gate_max_rank = GRADE_RANK.get(gate.max_grade, 0)
            if cur_rank > gate_max_rank:       # 当前等级比上限还高才需要压
                effective_rank = min(effective_rank, gate_max_rank)
                triggered.append({
                    "dim":       gate.dim,
                    "score":     dim_score,
                    "threshold": gate.threshold,
                    "max_grade": gate.max_grade,
                    "reason":    gate.reason,
                })

    # 将 effective_rank 还原为等级字符串
    rank_to_grade = {v: k for k, v in GRADE_RANK.items()}
    final_grade   = rank_to_grade.get(effective_rank, cur_grade)

    result["original_grade"]  = cur_grade
    result["gate_triggered"]  = bool(triggered)
    result["gate_reasons"]    = triggered
    result["grade"]           = final_grade   # 覆盖原始等级

    return result
