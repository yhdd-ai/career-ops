"""
A/B 测试模块：量化评估 Token 优化方案的质量代价

实验设计：
  Variant A（基准）：完整 CV + 完整 JD  → 精度上限
  Variant B（优化）：摘要 CV + 截断 JD  → 生产方案

每个 Variant 独立运行 N 轮，收集：
  - 综合评分 & 各维度分数（衡量准确性）
  - 估算 token 数（衡量成本）
  - 响应耗时（衡量速度）
  - 解析成功率（衡量稳定性）

结论指标：
  score_delta  = mean(B.score) - mean(A.score)   接近 0 说明优化无损
  token_saving = (A.tokens - B.tokens) / A.tokens  压缩比
  time_saving  = (A.time  - B.time)  / A.time     加速比
"""

import time
import json
import statistics
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent

# ── Variant 定义 ────────────────────────────────────────────────────────────

VARIANTS: dict[str, dict] = {
    "A_baseline": {
        "label":       "基准版（全文CV + 完整JD）",
        "use_summary": False,
        "truncate_jd": False,
    },
    "B_optimized": {
        "label":       "优化版（摘要CV + 截断JD）",
        "use_summary": True,
        "truncate_jd": True,
    },
}

# ── 核心运行函数 ─────────────────────────────────────────────────────────────

def _run_single(jd_text: str, use_summary: bool, truncate_jd_flag: bool,
                client) -> dict:
    """
    运行一次评估，返回 {score, dimensions, tokens, elapsed, parse_ok}。
    不写缓存，不写 tracker，纯粹测量。

    使用 chat_structured() 直接获取结构化结果，parse_ok 由 parse_failed
    标记决定，不再依赖 score > 0 的隐式判断（0 分是合理的低分，不等于解析失败）。
    """
    from src.evaluator import build_evaluation_prompt, _call_structured
    from src.token_optimizer import estimate_tokens, truncate_jd

    jd_input = truncate_jd(jd_text) if truncate_jd_flag else jd_text
    prompt   = build_evaluation_prompt(jd_input, use_summary=use_summary)
    tokens   = estimate_tokens(prompt)

    t0 = time.time()
    try:
        result = _call_structured(client, prompt, "", "", "", "")
    except Exception as e:
        return {"score": 0, "dimensions": {}, "tokens": tokens,
                "elapsed": round(time.time() - t0, 2), "parse_ok": False,
                "error": str(e)}
    elapsed = round(time.time() - t0, 2)

    # parse_failed=True 表示结构化 + 文本解析都失败，才算解析失败
    parse_ok = not result.get("parse_failed", False)

    return {
        "score":      result["score"],
        "dimensions": result["dimensions"],
        "tokens":     tokens,
        "elapsed":    elapsed,
        "parse_ok":   parse_ok,
    }


def run_ab_test(jd_text: str,
                company: str = "",
                title:   str = "",
                rounds:  int = 3,
                backend: str = "auto") -> dict:
    """
    主入口：对同一 JD 分别用 A/B 两个 Variant 各跑 rounds 轮，返回汇总报告。

    Args:
        jd_text:  JD 正文
        company:  公司（仅用于报告元信息）
        title:    职位（仅用于报告元信息）
        rounds:   每个 Variant 的重复次数（默认 3，至少 1）
        backend:  LLM 后端选择

    Returns:
        {
          "meta": {...},
          "variants": {
            "A_baseline": {"runs": [...], "summary": {...}},
            "B_optimized": {"runs": [...], "summary": {...}},
          },
          "comparison": {
            "score_delta": float,        # B.mean - A.mean（越接近 0 越好）
            "token_saving_pct": float,   # token 节省百分比
            "time_saving_pct": float,    # 响应时间节省百分比
            "parse_success_A": float,    # A 解析成功率
            "parse_success_B": float,    # B 解析成功率
            "verdict": str,              # 结论文字
          }
        }
    """
    from src.llm_client import get_client

    rounds  = max(1, rounds)
    client  = get_client(backend)
    results = {}

    for vid, vcfg in VARIANTS.items():
        print(f"\n  ▶ Variant {vid}：{vcfg['label']}（{rounds} 轮）")
        runs = []
        for r in range(1, rounds + 1):
            print(f"    轮次 {r}/{rounds}...", end=" ", flush=True)
            run = _run_single(
                jd_text,
                use_summary    = vcfg["use_summary"],
                truncate_jd_flag = vcfg["truncate_jd"],
                client         = client,
            )
            runs.append(run)
            status = "✓" if run["parse_ok"] else "✗(解析失败)"
            print(f"分数={run['score']}  tokens={run['tokens']}  "
                  f"耗时={run['elapsed']}s  {status}")

        results[vid] = {"config": vcfg, "runs": runs, "summary": _summarize(runs)}

    comparison = _compare(results["A_baseline"]["summary"],
                          results["B_optimized"]["summary"])

    report = {
        "meta": {
            "company":    company,
            "title":      title,
            "model":      client.model_name,
            "backend":    backend,
            "rounds":     rounds,
            "tested_at":  datetime.now().strftime("%Y-%m-%d %H:%M"),
            "jd_preview": jd_text[:120].replace("\n", " ") + "...",
        },
        "variants":   results,
        "comparison": comparison,
    }

    return report


# ── 统计汇总 ─────────────────────────────────────────────────────────────────

def _summarize(runs: list[dict]) -> dict:
    """对多轮运行结果做均值 / 标准差汇总"""
    scores   = [r["score"]   for r in runs if r["parse_ok"]]
    tokens   = [r["tokens"]  for r in runs]
    elapsed  = [r["elapsed"] for r in runs]
    parse_ok = [r["parse_ok"] for r in runs]

    # 各维度均值
    dim_keys = set()
    for r in runs:
        dim_keys.update(r["dimensions"].keys())
    dim_means = {}
    for k in dim_keys:
        vals = [r["dimensions"].get(k, 0) for r in runs if r["parse_ok"]]
        dim_means[k] = round(statistics.mean(vals), 1) if vals else 0

    return {
        "score_mean":    round(statistics.mean(scores), 1)   if scores  else 0,
        "score_std":     round(statistics.stdev(scores), 2)  if len(scores) > 1 else 0,
        "score_min":     min(scores)  if scores else 0,
        "score_max":     max(scores)  if scores else 0,
        "token_mean":    round(statistics.mean(tokens), 0),
        "elapsed_mean":  round(statistics.mean(elapsed), 2),
        "parse_success": round(sum(parse_ok) / len(parse_ok) * 100, 1),
        "dim_means":     dim_means,
    }


def _compare(sa: dict, sb: dict) -> dict:
    """计算 A vs B 的对比指标，生成结论"""
    score_delta = round(sb["score_mean"] - sa["score_mean"], 1)
    tok_a, tok_b = sa["token_mean"], sb["token_mean"]
    token_saving_pct = round((tok_a - tok_b) / tok_a * 100, 1) if tok_a else 0
    time_a, time_b   = sa["elapsed_mean"], sb["elapsed_mean"]
    time_saving_pct  = round((time_a - time_b) / time_a * 100, 1) if time_a else 0

    # 结论判定
    if abs(score_delta) <= 3:
        quality = "评分差异极小（≤3分），优化方案质量近似无损"
    elif score_delta > 3:
        quality = f"优化版评分高出基准 {score_delta} 分（摘要聚焦关键信息，可能减少噪音）"
    else:
        quality = f"优化版评分低于基准 {abs(score_delta)} 分（信息压缩有轻微质量代价）"

    if token_saving_pct > 0:
        cost_str = f"token 节省 {token_saving_pct}%"
    else:
        cost_str = f"token 增加 {abs(token_saving_pct)}%"

    verdict = f"{quality}；{cost_str}，响应加速 {time_saving_pct}%。"

    return {
        "score_delta":      score_delta,
        "token_saving_pct": token_saving_pct,
        "time_saving_pct":  time_saving_pct,
        "parse_success_A":  sa["parse_success"],
        "parse_success_B":  sb["parse_success"],
        "verdict":          verdict,
    }


# ── 报告输出 ─────────────────────────────────────────────────────────────────

def print_report(report: dict) -> None:
    """在终端打印可读的 A/B 测试报告"""
    meta = report["meta"]
    comp = report["comparison"]

    BOLD  = "\033[1m"
    GREEN = "\033[32m"
    YELLOW= "\033[33m"
    RED   = "\033[31m"
    BLUE  = "\033[34m"
    RESET = "\033[0m"

    print(f"\n{BOLD}{'═'*60}{RESET}")
    print(f"{BOLD}  A/B 测试报告{RESET}")
    print(f"{'═'*60}")
    print(f"  公司 / 职位：{meta['company']} · {meta['title']}")
    print(f"  模型：{meta['model']}（{meta['backend']}）  轮次：{meta['rounds']}")
    print(f"  测试时间：{meta['tested_at']}")
    print(f"  JD 预览：{meta['jd_preview'][:60]}...")
    print(f"\n{'─'*60}")
    print(f"  {'指标':<20} {'A 基准':>10} {'B 优化':>10} {'差值':>8}")
    print(f"{'─'*60}")

    sa = report["variants"]["A_baseline"]["summary"]
    sb = report["variants"]["B_optimized"]["summary"]

    def delta_color(v, invert=False):
        if abs(v) < 0.5: return f"{BLUE}{v:+.1f}{RESET}"
        good = v > 0 if not invert else v < 0
        return f"{GREEN}{v:+.1f}{RESET}" if good else f"{RED}{v:+.1f}{RESET}"

    score_d = comp["score_delta"]
    tok_d   = sb["token_mean"] - sa["token_mean"]
    time_d  = sb["elapsed_mean"] - sa["elapsed_mean"]

    print(f"  {'综合评分（均值）':<20} {sa['score_mean']:>10.1f} {sb['score_mean']:>10.1f} "
          f"  {delta_color(score_d)}")
    print(f"  {'评分标准差':<20} {sa['score_std']:>10.2f} {sb['score_std']:>10.2f}")
    print(f"  {'评分区间':<20} "
          f"  [{sa['score_min']}-{sa['score_max']}]  [{sb['score_min']}-{sb['score_max']}]")
    print(f"  {'解析成功率 (%)':<20} {sa['parse_success']:>10.1f} {sb['parse_success']:>10.1f}")
    print(f"  {'Token 估算':<20} {sa['token_mean']:>10.0f} {sb['token_mean']:>10.0f} "
          f"  {delta_color(tok_d, invert=True)}")
    print(f"  {'平均耗时 (s)':<20} {sa['elapsed_mean']:>10.2f} {sb['elapsed_mean']:>10.2f} "
          f"  {delta_color(time_d, invert=True)}")

    # 维度对比
    all_dims = set(sa["dim_means"]) | set(sb["dim_means"])
    if all_dims:
        print(f"\n{'─'*60}")
        print(f"  {BOLD}维度评分对比{RESET}")
        dim_labels = {
            "role_match": "岗位匹配度",
            "growth_potential": "成长空间",
            "company_quality": "公司质量",
            "location_fit": "地点匹配",
            "compensation": "薪资水平",
            "experience_match": "经验匹配",
            "workload_culture": "工作强度文化",
        }
        for k in sorted(all_dims):
            va = sa["dim_means"].get(k, 0)
            vb = sb["dim_means"].get(k, 0)
            label = dim_labels.get(k, k)
            d = round(vb - va, 1)
            print(f"  {label:<18} {va:>8.1f} {vb:>10.1f}  {delta_color(d)}")

    print(f"\n{'─'*60}")
    print(f"  {BOLD}结论：{RESET}{comp['verdict']}")
    print(f"  Token 节省：{GREEN}{comp['token_saving_pct']}%{RESET}   "
          f"响应加速：{GREEN}{comp['time_saving_pct']}%{RESET}   "
          f"评分偏差：{delta_color(comp['score_delta'])}")
    print(f"{'═'*60}\n")


def save_report(report: dict) -> Path:
    """保存 JSON 报告到 reports/ab_tests/"""
    out_dir = BASE_DIR / "reports" / "ab_tests"
    out_dir.mkdir(parents=True, exist_ok=True)

    ts      = datetime.now().strftime("%Y%m%d_%H%M%S")
    company = report["meta"].get("company", "unknown").replace("/", "-").replace(" ", "_")
    path    = out_dir / f"{ts}_ab_{company}.json"

    # 保存时去掉 raw 字段（节省空间）
    slim = json.loads(json.dumps(report))
    for vid in slim.get("variants", {}).values():
        for run in vid.get("runs", []):
            run.pop("raw", None)

    path.write_text(json.dumps(slim, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
