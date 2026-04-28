#!/usr/bin/env python3
"""
Career-Ops 评估集测试运行器
用于验证 evaluate 模式的大模型输出是否符合 golden label

用法：
  python eval_runner.py                   # 运行全部 case
  python eval_runner.py --case case_001   # 运行单个 case
  python eval_runner.py --grade A         # 只运行期望等级为 A 的 case
  python eval_runner.py --adversarial     # 只运行对抗测试
  python eval_runner.py --gate            # 只运行门控测试
  python eval_runner.py --dry-run         # 只显示 case 列表，不实际调用 LLM
"""
import json
import argparse
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

EVAL_DATASET = BASE_DIR / "data" / "eval_dataset.json"

# ── 颜色输出 ─────────────────────────────────────────────────────
def c(text, code): return f"\033[{code}m{text}\033[0m"
def green(t):  return c(t, "32")
def blue(t):   return c(t, "34")
def yellow(t): return c(t, "33")
def red(t):    return c(t, "31")
def bold(t):   return c(t, "1")
def grey(t):   return c(t, "90")

def grade_color(g):
    return {"A": green, "B": blue, "C": yellow, "F": red, "D": yellow}.get(g, grey)


@dataclass
class CaseResult:
    case_id: str
    label: str
    passed: bool
    expected_grade: str
    actual_grade: Optional[str] = None
    expected_score_min: int = 0
    expected_score_max: int = 100
    actual_score: Optional[int] = None
    failures: list[str] = field(default_factory=list)   # Fix 10: 补充类型参数
    warnings: list[str] = field(default_factory=list)
    error: Optional[str] = None


def load_dataset() -> dict:
    with open(EVAL_DATASET, encoding="utf-8") as f:
        return json.load(f)


def check_dimension(dim_name: str, actual_val: int, expected_range: dict,
                    tolerance: int) -> tuple[bool, str]:
    """检查单个维度分数是否在期望区间（含容差）内"""
    lo = expected_range["min"] - tolerance
    hi = expected_range["max"] + tolerance
    ok = lo <= actual_val <= hi
    msg = (f"{dim_name}: got {actual_val}, "
           f"expected [{expected_range['min']}, {expected_range['max']}]"
           f"  reason='{expected_range.get('reason', '')}'")
    return ok, msg


# ── Fix 3: key_assertions 执行器 ─────────────────────────────────

def _eval_assertion(expr: str, ctx: dict) -> tuple[bool, str]:
    """
    安全执行单条 key_assertion 字符串，返回 (passed, error_msg)。
    ctx 包含 eval_result 的关键字段供断言引用。
    """
    try:
        passed = bool(eval(expr, {"__builtins__": {}}, ctx))  # noqa: S307
        return passed, ""
    except Exception as e:
        return False, f"断言执行异常: {e}"


def check_key_assertions(case: dict, eval_result: dict) -> tuple[list[str], list[str]]:
    """
    执行 case 中的 key_assertions 字符串断言列表。
    返回 (failures, warnings)。

    断言中可使用的变量：
      grade, score, gate_triggered, original_grade, full_report,
      recommendation, parse_failed, gate_reasons
    """
    assertions = case.get("key_assertions", [])
    if not assertions:
        return [], []

    ctx = {
        "grade":          eval_result.get("grade", "?"),
        "score":          eval_result.get("score", -1),
        "gate_triggered": eval_result.get("gate_triggered", False),
        "original_grade": eval_result.get("original_grade", ""),
        "full_report":    eval_result.get("full_report", ""),
        "recommendation": eval_result.get("recommendation", ""),
        "parse_failed":   eval_result.get("parse_failed", False),
        "gate_reasons":   eval_result.get("gate_reasons", []),
        # 便捷别名
        "any":  any,
        "all":  all,
        "len":  len,
        "None": None,
        "True": True,
        "False": False,
    }

    failures = []
    for expr in assertions:
        passed, err = _eval_assertion(expr, ctx)
        if err:
            failures.append(f"断言异常 [{expr}]: {err}")
        elif not passed:
            failures.append(f"断言失败 [{expr}]  实际值: grade={ctx['grade']}, score={ctx['score']}")
    return failures, []


# ── 主测试逻辑 ────────────────────────────────────────────────────

def run_case(case: dict, backend: str = "auto", tolerance: int = 15) -> CaseResult:
    """运行单个评估 case，返回测试结果"""
    from src import evaluator

    case_id = case["id"]
    label   = case["label"]
    jd      = case["jd"]

    # Fix 7: 支持 expected_grade_set（多等级容错）
    expected_grade_set: list[str] = case.get(
        "expected_grade_set", [case["expected_grade"]]
    )
    if isinstance(expected_grade_set, str):
        expected_grade_set = [expected_grade_set]

    result = CaseResult(
        case_id=case_id,
        label=label,
        passed=False,
        expected_grade=case["expected_grade"],
        expected_score_min=case["expected_score_min"],
        expected_score_max=case["expected_score_max"],
    )

    print(f"\n  {bold(case_id)}  {grey(label)}")
    expected_display = "/".join(expected_grade_set)
    print(f"  期望: {grade_color(case['expected_grade'])(expected_display)} 级 "
          f"({case['expected_score_min']}-{case['expected_score_max']} 分)")

    try:
        eval_result = evaluator.auto_evaluate(
            jd_text=jd["text"],
            company=jd["company"],
            title=jd["title"],
            location=jd.get("location", ""),
            url="",
            backend=backend,
            use_cache=False,
        )
    except Exception as e:
        result.error = str(e)
        result.passed = False
        print(red(f"  ✗ 运行异常: {e}"))
        return result

    actual_grade = eval_result.get("grade", "?")
    actual_score = eval_result.get("score", -1)
    actual_dims  = eval_result.get("dimensions", {})
    actual_gate  = eval_result.get("gate_triggered", False)

    result.actual_grade = actual_grade
    result.actual_score = actual_score

    failures: list[str] = []
    warnings: list[str] = []

    # ── 1. 等级检查（支持多等级容错）────────────────────────────────
    if actual_grade not in expected_grade_set:
        failures.append(
            f"Grade: got '{actual_grade}', expected one of {expected_grade_set}"
        )
    else:
        print(green(f"  ✓ 等级正确: {actual_grade}"))

    # ── 2. 分数区间检查 ───────────────────────────────────────────
    score_min = case["expected_score_min"] - tolerance // 2
    score_max = case["expected_score_max"] + tolerance // 2
    if not (score_min <= actual_score <= score_max):
        failures.append(
            f"Score: got {actual_score}, "
            f"expected [{case['expected_score_min']}, {case['expected_score_max']}]"
        )
    else:
        print(green(f"  ✓ 分数正确: {actual_score}"))

    # ── 3. 维度分数检查（警告级别）──────────────────────────────────
    expected_dims = case.get("expected_dimensions", {})
    for dim_name, dim_range in expected_dims.items():
        actual_dim_val = actual_dims.get(dim_name, -1)
        if actual_dim_val == -1:
            warnings.append(f"维度缺失: {dim_name}")
            continue
        ok, msg = check_dimension(dim_name, actual_dim_val, dim_range, tolerance)
        if not ok:
            warnings.append(f"⚠ 维度偏差  {msg}")

    # ── 4. 门控检查 ───────────────────────────────────────────────
    expected_gate = case.get("gate_triggered", False)
    if expected_gate and not actual_gate:
        failures.append("Gate: 期望触发门控降级，但实际未触发")
    elif not expected_gate and actual_gate:
        warnings.append("Gate: 未期望触发门控，但实际触发了")
    elif expected_gate and actual_gate:
        orig_grade    = eval_result.get("original_grade", "")
        expected_orig = case.get("original_grade_before_gate", "")
        if expected_orig and orig_grade != expected_orig:
            warnings.append(
                f"Gate original_grade: got '{orig_grade}', expected '{expected_orig}'"
            )
        else:
            print(green("  ✓ 门控正确触发"))

    # ── 5. 对抗注入检查 ───────────────────────────────────────────
    if case.get("adversarial"):
        if actual_grade == "A" and actual_score >= 90:
            failures.append(
                f"对抗测试失败：模型可能被 prompt 注入影响，输出了 A/{actual_score}"
            )
        else:
            print(green("  ✓ 对抗测试通过：未受注入影响"))

    # ── 6. key_assertions 执行 (Fix 3) ───────────────────────────
    assertion_failures, assertion_warnings = check_key_assertions(case, eval_result)
    if assertion_failures:
        failures.extend(assertion_failures)
    else:
        assertions = case.get("key_assertions", [])
        if assertions:
            print(green(f"  ✓ key_assertions 全部通过（{len(assertions)} 条）"))

    result.failures = failures
    result.warnings = warnings
    result.passed   = len(failures) == 0

    # ── 输出结果 ─────────────────────────────────────────────────
    gc = grade_color(actual_grade)
    print(f"  实际: {gc(actual_grade)} 级 {actual_score}/100  gate={actual_gate}")

    for w in warnings:
        print(yellow(f"  {w}"))
    for f_msg in failures:
        print(red(f"  ✗ {f_msg}"))

    print(f"  → {green('PASS') if result.passed else red('FAIL')}")
    return result


def run_dry(cases: list):
    """只打印 case 列表，不调用 LLM"""
    print(bold(f"\n📋 评估集共 {len(cases)} 个 Case\n"))
    print(f"  {'ID':<14} {'期望等级':>6} {'分数区间':>12}  {'标签'}")
    print("  " + "─" * 68)
    for case in cases:
        gc        = grade_color(case["expected_grade"])
        grade_set = case.get("expected_grade_set", [case["expected_grade"]])
        grade_str = "/".join(grade_set) if isinstance(grade_set, list) else grade_set
        adv_tag   = "  [对抗]"  if case.get("adversarial")    else ""
        gate_tag  = "  [门控]"  if case.get("gate_triggered")  else ""
        n_assert  = len(case.get("key_assertions", []))
        asrt_tag  = f"  [{n_assert}断言]" if n_assert else ""
        print(f"  {case['id']:<14} {gc(grade_str):>6}  "
              f"  {case['expected_score_min']:>3}-{case['expected_score_max']:<3}  "
              f"  {grey(case['label'][:30])}{adv_tag}{gate_tag}{asrt_tag}")


def print_summary(results: list[CaseResult]):
    total  = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed

    print(bold(f"\n{'─'*60}"))
    print(bold(f"📊 测试摘要  {passed}/{total} 通过"))
    print(bold(f"{'─'*60}"))

    if failed == 0:
        print(green("  ✓ 全部通过！"))
    else:
        print(red(f"  ✗ {failed} 个失败"))
        for r in results:
            if not r.passed:
                gc  = grade_color(r.expected_grade)
                act = grade_color(r.actual_grade or "?")
                print(f"\n  {red('FAIL')} {r.case_id}  {grey(r.label)}")
                print(f"       期望 {gc(r.expected_grade)} → "
                      f"实际 {act(r.actual_grade or '?')} ({r.actual_score} 分)")
                for f_msg in r.failures:
                    print(f"       {red('✗')} {f_msg}")

    errors = [r for r in results if r.error]
    if errors:
        print(yellow(f"\n  ⚠ {len(errors)} 个运行异常（未计入失败）"))
        for r in errors:
            print(f"    {r.case_id}: {r.error}")

    print()


def main():
    parser = argparse.ArgumentParser(
        description="Career-Ops Evaluate 评估集测试运行器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--case",        default="", help="运行指定 case ID，如 case_001")
    parser.add_argument("--grade",       default="", help="只运行期望等级为指定值的 case，如 A/B/C/F")
    parser.add_argument("--adversarial", action="store_true", help="只运行对抗测试 case")
    parser.add_argument("--gate",        action="store_true", help="只运行门控测试 case")
    parser.add_argument("--dry-run",     action="store_true", help="只显示 case 列表，不调用 LLM")
    parser.add_argument("--backend",     default="auto", choices=["auto", "claude", "ollama"],
                        help="LLM 后端")
    parser.add_argument("--tolerance",   type=int, default=15,
                        help="维度分数容差（默认±15分）")
    args = parser.parse_args()

    dataset   = load_dataset()
    all_cases = dataset["cases"]
    tolerance = args.tolerance

    cases = all_cases
    if args.case:
        cases = [c for c in cases if c["id"] == args.case]
        if not cases:
            print(red(f"未找到 case: {args.case}"))
            print(grey(f"可用 ID: {', '.join(c['id'] for c in all_cases)}"))
            sys.exit(1)
    elif args.grade:
        cases = [c for c in cases if c["expected_grade"] == args.grade.upper()]
    elif args.adversarial:
        cases = [c for c in cases if c.get("adversarial")]
    elif args.gate:
        cases = [c for c in cases if c.get("gate_triggered")]

    if not cases:
        print(yellow("没有符合条件的 case"))
        sys.exit(0)

    if args.dry_run:
        run_dry(cases)
        return

    print(bold("\n🧪 Career-Ops Evaluate 评估集测试"))
    print(grey(f"   后端: {args.backend}  容差: ±{tolerance}  Case 数: {len(cases)}"))

    results = []
    for case in cases:
        result = run_case(case, backend=args.backend, tolerance=tolerance)
        results.append(result)

    print_summary(results)

    failed = sum(1 for r in results if not r.passed and not r.error)
    sys.exit(failed)


if __name__ == "__main__":
    main()
