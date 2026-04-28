"""
Job Search Context Engine  —  Harness Engineering 方向一
跨会话上下文引擎：让 Agent 的评估标准在所有会话中保持一致

核心功能：
  1. 历史评估摘要注入   — 将历史评分模式压缩后注入 prompt，防止评分漂移
  2. 动态偏好追踪       — 从用户行为（申请/放弃）中学习偏好信号
  3. 会话状态持久化     — 记录当前批次的进度（支持中断后感知）
  4. 一致性统计报告     — 量化评分稳定性，提供可量化的 benchmark 数据

存储结构（context/ 目录）：
  eval_history_summary.json  — 压缩版历史评分摘要（最近 50 条，不存 full_report）
  session_state.json         — 当前会话进度
  preference_signals.json    — 从用户行为学习到的偏好信号

集成方式：
  evaluator.py  — build_evaluation_prompt() 调用 get_context_block()
  run.py        — cmd_evaluate 后调用 record_evaluation()
                  cmd_update 后调用 record_status_change()
"""
import json
from pathlib import Path
from datetime import datetime
from typing import Optional

BASE_DIR    = Path(__file__).parent.parent
CONTEXT_DIR = BASE_DIR / "context"

# 岗位类型关键词映射（用于按类型统计均分）
_CATEGORY_RULES = [
    (["算法", "大模型", "AI", "LLM", "NLP", "机器学习", "深度学习"], "AI/算法"),
    (["后端", "Java", "Go", "服务端", "开发工程师"],                  "后端开发"),
    (["数据", "分析", "BI", "ETL", "数仓"],                           "数据"),
    (["前端", "React", "Vue", "Android", "iOS"],                      "前端/移动"),
]
_DEFAULT_CATEGORY = "其他"


def _infer_category(title: str) -> str:
    for keywords, cat in _CATEGORY_RULES:
        if any(kw in title for kw in keywords):
            return cat
    return _DEFAULT_CATEGORY


class ContextEngine:
    """
    跨会话求职上下文引擎。

    所有方法设计为幂等且容错：即使存储文件损坏或缺失，也不会抛出异常，
    只会静默降级（返回空字符串 / 跳过写入），不影响主求职流程。
    """

    def __init__(self):
        CONTEXT_DIR.mkdir(exist_ok=True)
        self._history_path = CONTEXT_DIR / "eval_history_summary.json"
        self._session_path = CONTEXT_DIR / "session_state.json"
        self._pref_path    = CONTEXT_DIR / "preference_signals.json"

    # ── I/O 工具 ──────────────────────────────────────────────────────────────

    def _load(self, path: Path, default):
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return default

    def _save(self, path: Path, data) -> None:
        try:
            path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except OSError:
            pass  # 写入失败不阻断主流程

    # ── 核心：生成 prompt 注入块 ──────────────────────────────────────────────

    def get_context_block(self) -> str:
        """
        生成注入评估 prompt 的一致性校准块（约 80-120 tokens）。

        通过向 LLM 展示历史评分基准，防止跨会话的评分漂移（Context Drift）。
        当历史记录少于 2 条时返回空字符串，避免注入意义不大的噪声。
        """
        try:
            from src.tracker import get_all_jobs
            jobs = get_all_jobs()
        except Exception:
            return ""

        scored_jobs = [j for j in jobs if j.get("score", 0) > 0]
        if len(scored_jobs) < 2:
            return ""

        # ① 基础统计
        avg_score = round(sum(j["score"] for j in scored_jobs) / len(scored_jobs), 1)

        grade_dist: dict[str, int] = {}
        for j in scored_jobs:
            g = j.get("grade", "?")
            grade_dist[g] = grade_dist.get(g, 0) + 1
        grade_str = " ".join(
            f"{g}:{n}" for g, n in sorted(grade_dist.items()) if n > 0
        )

        # ② 按岗位类型的均分（帮助 LLM 在不同类型间保持横向一致性）
        role_avgs: dict[str, list] = {}
        for j in scored_jobs:
            cat = _infer_category(j.get("title", ""))
            role_avgs.setdefault(cat, []).append(j["score"])

        role_avg_parts = [
            f"{cat}均分{round(sum(v)/len(v), 1)}"
            for cat, v in sorted(role_avgs.items())
            if len(v) >= 1
        ]
        role_avg_str = "  ".join(role_avg_parts) if role_avg_parts else ""

        # ③ 评分区间
        scores     = [j["score"] for j in scored_jobs]
        score_min  = min(scores)
        score_max  = max(scores)

        # ④ 行为信号（已申请/面试/放弃 的最近样本）
        applied   = [j for j in jobs if j.get("status") in ("已申请", "面试中", "已拿Offer")]
        abandoned = [j for j in jobs if j.get("status") == "已放弃"]

        applied_str   = ""
        abandoned_str = ""

        if applied:
            samples = applied[-3:]
            applied_str = "  已申请：" + "、".join(
                f"{j['company']}·{j['title'][:6]}({j['grade']}{j['score']})"
                for j in samples
            )
        if abandoned:
            samples = abandoned[-2:]
            abandoned_str = "  主动放弃：" + "、".join(
                f"{j['company']}·{j['title'][:6]}({j.get('grade','?')}{j.get('score',0)})"
                for j in samples
            )

        # ⑤ 组装注入块
        lines = [
            f"历史评估背景（共 {len(scored_jobs)} 条，均分 {avg_score}，"
            f"等级分布 {grade_str}）",
            f"  评分区间：{score_min}–{score_max}",
        ]
        if role_avg_str:
            lines.append(f"  分类均分：{role_avg_str}")
        if applied_str:
            lines.append(applied_str)
        if abandoned_str:
            lines.append(abandoned_str)
        lines.append(
            "  ↑ 请参考以上历史基准维持评分一致性，"
            "不要无故拔高或压低新职位的评分。"
        )

        return "\n".join(lines)

    # ── 记录评估结果 ──────────────────────────────────────────────────────────

    def record_evaluation(self, result: dict) -> None:
        """
        评估完成后调用：将精简摘要追加到历史记录。
        只保存关键字段，丢弃 full_report，防止文件无限膨胀。
        最多保留最近 50 条记录（约 10–20 KB）。
        """
        history: list = self._load(self._history_path, [])
        entry = {
            "company":     result.get("company", ""),
            "title":       result.get("title", ""),
            "score":       result.get("score", 0),
            "grade":       result.get("grade", "?"),
            "archetype":   result.get("archetype_label", ""),
            "gate":        result.get("gate_triggered", False),
            "recorded_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        history.append(entry)
        history = history[-50:]           # 只保留最近 50 条
        self._save(self._history_path, history)

        # 同步会话状态
        session: dict = self._load(self._session_path, {})
        if not session.get("started_at"):
            session["started_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        evaluated = session.get("evaluated_this_session", [])
        evaluated.append({
            "company": entry["company"],
            "title":   entry["title"],
            "score":   entry["score"],
            "grade":   entry["grade"],
        })
        session["evaluated_this_session"] = evaluated
        session["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        self._save(self._session_path, session)

    # ── 记录状态变更 ──────────────────────────────────────────────────────────

    def record_status_change(self, job: dict, new_status: str) -> None:
        """
        用户更新申请状态时调用：提取行为偏好信号。

        "已申请" / "面试中" → 正向信号（用户认为该职位值得投入）
        "已放弃"             → 负向信号（主动放弃，即便评分不低）

        这些信号未来可用于校准推荐逻辑和评分标准。
        """
        signals: dict = self._load(self._pref_path, {
            "positive": [], "negative": [], "events": []
        })

        event = {
            "company":     job.get("company", ""),
            "title":       job.get("title", ""),
            "score":       job.get("score", 0),
            "grade":       job.get("grade", "?"),
            "from_status": job.get("status", ""),
            "to_status":   new_status,
            "recorded_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        signals.setdefault("events", []).append(event)

        summary = {
            "company": job["company"],
            "title":   job["title"],
            "score":   job.get("score", 0),
            "grade":   job.get("grade", "?"),
        }
        if new_status in ("已申请", "面试中", "已拿Offer"):
            signals.setdefault("positive", []).append(summary)
        elif new_status == "已放弃":
            signals.setdefault("negative", []).append(summary)

        # 保留最近若干条，防止文件无限增长
        signals["events"]   = signals["events"][-30:]
        signals["positive"] = signals["positive"][-20:]
        signals["negative"] = signals["negative"][-20:]
        self._save(self._pref_path, signals)

    # ── 会话管理 ──────────────────────────────────────────────────────────────

    def reset_session(self) -> None:
        """开始新的 batch 任务时可主动调用，清空当前会话计数。"""
        self._save(self._session_path, {
            "evaluated_this_session": [],
            "started_at":  datetime.now().strftime("%Y-%m-%d %H:%M"),
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        })

    def get_session_summary(self) -> dict:
        return self._load(self._session_path, {})

    # ── 统计报告（用于 `python run.py context` 命令）────────────────────────

    def show_stats(self) -> None:
        """
        在终端输出 Context Engine 完整状态报告。
        包含：记录量、行为信号数、评分一致性分析、当前注入块预览。
        """
        history = self._load(self._history_path, [])
        signals = self._load(self._pref_path, {})
        session = self._load(self._session_path, {})

        print("\n🧠 Context Engine 状态报告")
        print("─" * 50)
        print(f"  压缩历史记录：{len(history)} 条（上限 50 条滚动）")
        print(f"  正向行为信号：{len(signals.get('positive', []))} 条"
              f"（已申请 / 面试 / Offer）")
        print(f"  负向行为信号：{len(signals.get('negative', []))} 条（主动放弃）")

        # 本次会话统计
        sess_list = session.get("evaluated_this_session", [])
        if sess_list:
            started = session.get("started_at", "")
            print(f"\n  本次会话：自 {started} 已评估 {len(sess_list)} 个职位")
            for item in sess_list:
                print(f"    · {item['company']} · {item['title']}"
                      f"  {item['grade']}{item['score']}")

        # 评分一致性分析
        scores = [h["score"] for h in history if h.get("score", 0) > 0]
        if len(scores) >= 3:
            avg      = round(sum(scores) / len(scores), 1)
            variance = round(sum((s - avg) ** 2 for s in scores) / len(scores), 1)
            std_dev  = round(variance ** 0.5, 1)
            print(f"\n  评分一致性：均分 {avg}  标准差 {std_dev}  方差 {variance}")

            # 评级：方差越小，Context Engine 效果越好
            if variance < 80:
                tag = "✓ 评分非常稳定"
            elif variance < 150:
                tag = "✓ 评分稳定"
            elif variance < 250:
                tag = "⚠ 评分略有波动（轻微漂移）"
            else:
                tag = "✗ 评分波动较大（建议检查 profile.yml 权重）"
            print(f"  {tag}")

        # 当前注入块预览
        block = self.get_context_block()
        print(f"\n  当前上下文注入块：")
        if block:
            for line in block.splitlines():
                print(f"    {line}")
        else:
            print("    （历史记录不足 2 条，首次评估后自动激活）")

        print()


# ── 单例工厂 ─────────────────────────────────────────────────────────────────

_engine: Optional[ContextEngine] = None


def get_engine() -> ContextEngine:
    """返回全局单例 ContextEngine，首次调用时初始化。"""
    global _engine
    if _engine is None:
        _engine = ContextEngine()
    return _engine
