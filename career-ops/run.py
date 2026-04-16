#!/usr/bin/env python3
"""
Career-Ops 实习求职 AI 助手

用法：
  python run.py [--backend auto|claude|ollama] <命令> [参数]

后端选项：
  --backend auto    自动选择：有 Claude API Key 则用 Claude，否则用 Ollama（默认）
  --backend claude  强制使用 Claude API（需配置 config/api.yml）
  --backend ollama  强制使用本地 Ollama（需先运行 ollama serve）

常用命令：
  evaluate      URL → 爬取 JD → AI 评估 → PDF + 看板
  tailor-cv     根据 JD 定向裁剪简历
  cover-letter  根据 JD 生成求职信
  recommend     AI 推荐匹配职位
  list          查看所有已评估职位
  stats         统计概览
  dashboard     打开可视化看板
"""
import sys
import argparse
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

from src import tracker, evaluator, pdf_gen, dashboard_gen, recommender
from src.cv_importer import import_cv
from src import cv_tailor, cover_letter as cl
from src import ab_test as ab
from src import star_bank


# ── 颜色输出 ─────────────────────────────────────────────────────
def c(text, code): return f"\033[{code}m{text}\033[0m"
def green(t):  return c(t, "32")
def blue(t):   return c(t, "34")
def yellow(t): return c(t, "33")
def red(t):    return c(t, "31")
def bold(t):   return c(t, "1")
def grey(t):   return c(t, "90")

def grade_color(grade):
    return {"A": green, "B": blue, "C": yellow, "F": red}.get(grade, grey)


# ── 公共工具 ─────────────────────────────────────────────────────
def _read_jd(args) -> str:
    """从 URL / 文件 / 参数 / 标准输入中读取 JD 文本"""
    from src.scraper import scrape_job

    url     = getattr(args, "url", "") or ""
    jd_text = ""

    if url.startswith("http"):
        print(f"  🌐 正在爬取：{url}")
        try:
            headless = not getattr(args, "visible", False)
            info     = scrape_job(url, headless=headless)
            jd_text  = info.jd_text
            # 回写爬取到的信息（如果 args 里是空的）
            if not args.company: args.company = info.company
            if not args.title:   args.title   = info.title
            if hasattr(args, "location") and not args.location:
                args.location = info.location
            print(green(f"  ✓ 爬取成功：{args.title} @ {args.company}"))
        except ImportError:
            print(yellow("  ⚠ 未安装 Playwright，跳过自动爬取"))
            print(yellow("    pip install playwright && playwright install webkit"))
        except Exception as e:
            print(yellow(f"  ⚠ 爬取失败（{e}），请手动提供 JD"))

    if not jd_text:
        jd_file = getattr(args, "jd_file", "") or ""
        jd_arg  = getattr(args, "jd", "") or ""
        if jd_file:
            jd_text = Path(jd_file).read_text(encoding="utf-8")
        elif jd_arg:
            jd_text = jd_arg
        else:
            print(bold("请粘贴 JD 内容（Ctrl+D 结束）："))
            lines = []
            try:
                while True: lines.append(input())
            except EOFError: pass
            jd_text = "\n".join(lines)

    return jd_text


def _ensure_company_title(args):
    """确保 company 和 title 不为空（交互式补充）"""
    if not args.company: args.company = input("  公司名称：").strip()
    if not args.title:   args.title   = input("  职位名称：").strip()


# ── evaluate ─────────────────────────────────────────────────────
def cmd_evaluate(args):
    jd_text = _read_jd(args)
    if not jd_text.strip():
        print(red("错误：JD 内容为空"))
        sys.exit(1)

    location = getattr(args, "location", "") or ""
    if not args.company: args.company = input("  公司名称：").strip()
    if not args.title:   args.title   = input("  职位名称：").strip()
    if not location:     location     = input("  工作地点（可回车跳过）：").strip()

    try:
        result = evaluator.auto_evaluate(
            jd_text, args.company, args.title, location,
            getattr(args, "url", ""),
            backend=args.backend,
            use_cache=not args.no_cache,
        )
    except (ImportError, ValueError) as e:
        print(red(f"✗ {e}"))
        sys.exit(1)

    job      = tracker.add_job(**{k: result[k] for k in
               ["company","title","location","url","score","grade",
                "dimensions","recommendation","full_report"]})
    rpt_path = evaluator.save_report_to_file(result)
    pdf_path = pdf_gen.generate_pdf(job)
    dashboard_gen.generate_dashboard()

    gc = grade_color(job["grade"])
    grade_str = f' {job["grade"]} 级 {job["score"]}/100'
    print(f"\n{gc(bold(grade_str))} · {args.company} · {args.title}")
    print(green(f"  ✓ ID={job['id']}  报告：{rpt_path.name}  PDF：{pdf_path.name}"))
    print(green(f"  ✓ 看板已更新"))

    # ── 可选：生成 STAR 故事并追加到故事库 ──
    if getattr(args, "star", False):
        try:
            story = star_bank.generate_story(
                jd_text, args.company, args.title, backend=args.backend)
            star_bank.append_story(story, args.company, args.title)
            count = star_bank.get_story_count()
            print(green(f"  ✓ STAR 故事已追加（故事库共 {count} 条）：reports/story_bank.md"))
        except Exception as e:
            print(yellow(f"  ⚠ STAR 故事生成失败（不影响评估结果）：{e}"))


# ── recommend ────────────────────────────────────────────────────
def cmd_recommend(args):
    direction = args.direction or input("  求职方向（如：大模型算法、Java后端）：").strip()
    if not direction:
        print(red("方向不能为空"))
        sys.exit(1)

    print(f"\n  🔍 正在为「{direction}」生成推荐...")
    try:
        report = recommender.auto_recommend(direction, backend=args.backend)
    except (ImportError, ValueError) as e:
        print(red(f"✗ {e}"))
        sys.exit(1)

    print("\n" + report)
    path = recommender.save_recommend_report(direction, report)
    print(green(f"\n  ✓ 推荐报告已保存：{path.name}"))

    if input(bold("\n  是否对推荐的职位逐一评估？(y/N) ")).strip().lower() == "y":
        print(yellow(f"  请将招聘链接逐一传入：python3 run.py evaluate --url \"链接\""))


# ── tailor-cv ────────────────────────────────────────────────────
def cmd_tailor_cv(args):
    jd_text = _read_jd(args)
    if not jd_text.strip():
        print(red("错误：JD 内容为空"))
        sys.exit(1)

    _ensure_company_title(args)

    try:
        result = cv_tailor.tailor_cv(jd_text, args.company, args.title, backend=args.backend)
    except (ImportError, ValueError) as e:
        print(red(f"✗ {e}"))
        sys.exit(1)

    path = cv_tailor.save_tailored_cv(result, args.company, args.title)
    print(green(f"\n  ✓ 定向简历已生成：reports/tailored_cvs/{path.name}"))
    print(grey("  提示：可直接复制到 Word/LaTeX 排版后发送"))


# ── cover-letter ─────────────────────────────────────────────────
def cmd_cover_letter(args):
    jd_text = _read_jd(args)
    if not jd_text.strip():
        print(red("错误：JD 内容为空"))
        sys.exit(1)

    _ensure_company_title(args)

    try:
        letter = cl.generate_cover_letter(jd_text, args.company, args.title, backend=args.backend)
    except (ImportError, ValueError) as e:
        print(red(f"✗ {e}"))
        sys.exit(1)

    path = cl.save_cover_letter(letter, args.company, args.title)
    print(f"\n{bold('──── 求职信预览 ────')}")
    print(letter)
    print(green(f"\n  ✓ 求职信已保存：reports/cover_letters/{path.name}"))


# ── cache ────────────────────────────────────────────────────────
def cmd_cache(args):
    from src import cache as eval_cache

    if args.cache_action == "stats" or not args.cache_action:
        s = eval_cache.stats()
        if s["entries"] == 0:
            print(yellow("缓存为空"))
            return
        print(bold(f"\n🗄 评估缓存（共 {s['entries']} 条，累计命中 {s['total_hits']} 次）\n"))
        print(f"  {'公司':<12} {'职位':<18} {'评级':>4} {'分数':>5} {'命中':>4}  {'缓存时间'}")
        print("  " + "─" * 62)
        for item in sorted(s["items"], key=lambda x: x["cached_at"], reverse=True):
            tag = "URL" if item["type"] == "url" else "JD "
            gc  = grade_color(item["grade"])
            print(f"  {item['company']:<12} {item['title']:<18} "
                  f"{gc(item['grade']):>4} {item['score']:>5}  "
                  f"{item['hit_count']:>3}次  {item['cached_at']}  [{tag}]")

    elif args.cache_action == "clear":
        n = eval_cache.clear()
        print(green(f"✓ 已清空 {n} 条缓存"))

    elif args.cache_action == "remove":
        if not args.url:
            print(red("请用 --url 指定要删除的缓存条目"))
            sys.exit(1)
        ok = eval_cache.remove(args.url)
        print(green(f"✓ 已删除缓存：{args.url}") if ok else yellow("未找到该缓存条目"))


# ── models ───────────────────────────────────────────────────────
def cmd_models(args):
    from src.llm_client import OllamaClient, _load_yaml
    cfg    = _load_yaml("config/api_local.yml")
    client = OllamaClient(
        base_url=cfg.get("ollama_base_url", "http://127.0.0.1:11434"),
        model=cfg.get("model", "qwen2.5:latest")
    )
    models = client.list_models()
    if not models:
        print(yellow("未找到已安装模型，或 Ollama 未启动"))
        print(grey("  启动：ollama serve"))
        print(grey("  安装模型：ollama pull qwen2.5:7b"))
        return
    print(bold(f"\n已安装模型（共 {len(models)} 个）："))
    for m in models:
        tag = green(" ← 当前使用") if m == client.model_name else ""
        print(f"  • {m}{tag}")
    print(grey("\n修改模型：编辑 config/api_local.yml 中的 model 字段"))


# ── list ─────────────────────────────────────────────────────────
def cmd_list(args):
    jobs = tracker.get_all_jobs()
    if getattr(args, "grade", None):
        jobs = [j for j in jobs if j.get("grade") == args.grade.upper()]
    if getattr(args, "status", None):
        jobs = [j for j in jobs if j.get("status") == args.status]

    print(bold(f"\n📋 职位列表（共 {len(jobs)} 条）\n"))
    tracker.print_jobs_table(jobs)

    stats = tracker.get_stats()
    print(f"\n{grey('统计：')} 平均分 {bold(str(stats['avg_score']))}  "
          f"已申请 {bold(str(stats['applied']))}  "
          f"Offer {bold(str(stats['offers']))}")


# ── update ───────────────────────────────────────────────────────
def cmd_update(args):
    if args.status not in tracker.VALID_STATUSES:
        print(red(f"无效状态。可选：{', '.join(tracker.VALID_STATUSES)}"))
        sys.exit(1)
    job = tracker.update_status(args.id, args.status)
    if job:
        print(green(f"✓ #{args.id} {job['company']} · {job['title']} → {args.status}"))
        dashboard_gen.generate_dashboard()
    else:
        print(red(f"找不到 ID={args.id} 的职位"))


# ── pdf ──────────────────────────────────────────────────────────
def cmd_pdf(args):
    job = tracker.get_job_by_id(args.id)
    if not job:
        print(red(f"找不到 ID={args.id} 的职位"))
        sys.exit(1)
    try:
        path = pdf_gen.generate_pdf(job)
        print(green(f"✓ PDF 已生成：{path}"))
        if sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
    except Exception as e:
        print(red(f"PDF 生成失败：{e}"))


# ── dashboard ────────────────────────────────────────────────────
def cmd_dashboard(args):
    path = dashboard_gen.generate_dashboard()
    print(green(f"✓ 看板已生成：{path}"))
    if sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    elif sys.platform.startswith("linux"):
        subprocess.run(["xdg-open", str(path)], check=False)
    else:
        print(blue(f"请在浏览器中打开：file://{path}"))


# ── import-cv ────────────────────────────────────────────────────
def cmd_import_cv(args):
    try:
        path = import_cv(args.file, overwrite=args.overwrite)
        print(green(f"✓ 简历已导入：{path}"))
        print(grey("  建议重新生成摘要：python3 run.py gen-cv-summary"))
    except Exception as e:
        print(red(f"✗ 导入失败：{e}"))


# ── gen-cv-summary ───────────────────────────────────────────────
def cmd_gen_cv_summary(args):
    from src.token_optimizer import rebuild_cv_summary, estimate_tokens
    summary      = rebuild_cv_summary()
    cv_tokens    = estimate_tokens(Path("cv.md").read_text(encoding="utf-8"))
    sum_tokens   = estimate_tokens(summary)
    print(green(f"✓ CV 摘要已重建：config/cv_summary.md"))
    print(grey(f"  {cv_tokens} tokens → {sum_tokens} tokens，节省 {cv_tokens - sum_tokens} tokens"))
    print(bold("\n摘要预览："))
    print(summary)


# ── stories ──────────────────────────────────────────────────────
def cmd_stories(args):
    action = args.stories_action

    if action == "list" or not action:
        stories = star_bank.list_stories()
        if not stories:
            print(yellow("故事库为空。评估职位时加 --star 自动生成："))
            print(grey("  python run.py evaluate --url <url> --star"))
            return
        print(bold(f"\n⭐ STAR 故事库（共 {len(stories)} 条）\n"))
        print(f"  {'#':>3}  {'公司':<14} {'职位':<18} {'时间':<17} 预览")
        print("  " + "─" * 70)
        for s in stories:
            print(f"  {s['id']:>3}  {s['company']:<14} {s['title']:<18} "
                  f"{s['timestamp']:<17} {grey(s['preview'][:28])}")
        print(grey(f"\n  完整故事库：reports/story_bank.md"))

    elif action == "search":
        if not args.keyword:
            print(red("请用 --keyword 指定搜索关键词"))
            sys.exit(1)
        results = star_bank.search_stories(args.keyword)
        if not results:
            print(yellow(f"未找到包含「{args.keyword}」的故事"))
            return
        print(bold(f"\n搜索「{args.keyword}」，命中 {len(results)} 条：\n"))
        for s in results:
            print(f"  #{s['id']} {s['company']} · {s['title']}  ({s['timestamp']})")
            print(f"     {grey(s['preview'])}\n")

    elif action == "gen":
        jd_text = _read_jd(args)
        if not jd_text.strip():
            print(red("错误：JD 内容为空"))
            sys.exit(1)
        _ensure_company_title(args)
        try:
            story = star_bank.generate_story(
                jd_text, args.company, args.title, backend=args.backend)
            path  = star_bank.append_story(story, args.company, args.title)
            count = star_bank.get_story_count()
            print(f"\n{bold('──── STAR 故事预览 ────')}")
            print(story)
            print(green(f"\n  ✓ 已追加到故事库（共 {count} 条）：{path.name}"))
        except Exception as e:
            print(red(f"✗ {e}"))
            sys.exit(1)


# ── ab-test ──────────────────────────────────────────────────────
def cmd_ab_test(args):
    jd_text = _read_jd(args)
    if not jd_text.strip():
        print(red("错误：JD 内容为空"))
        sys.exit(1)

    _ensure_company_title(args)

    rounds = args.rounds
    print(bold(f"\n🧪 A/B 测试：{args.company} · {args.title}（每 Variant {rounds} 轮）"))
    print(grey(f"   Variant A：全文CV + 完整JD（基准）"))
    print(grey(f"   Variant B：摘要CV + 截断JD（优化方案）"))

    try:
        report = ab.run_ab_test(
            jd_text, args.company, args.title,
            rounds=rounds, backend=args.backend,
        )
    except (ImportError, ValueError) as e:
        print(red(f"✗ {e}"))
        sys.exit(1)

    ab.print_report(report)

    if not args.no_save:
        path = ab.save_report(report)
        print(green(f"  ✓ 报告已保存：reports/ab_tests/{path.name}"))


# ── stats ────────────────────────────────────────────────────────
def cmd_stats(args):
    stats = tracker.get_stats()
    if stats["total"] == 0:
        print(yellow("暂无数据"))
        return
    print(bold("\n📊 求职统计摘要"))
    print(f"  已评估：{bold(str(stats['total']))} 个职位")
    print(f"  平均分：{bold(str(stats['avg_score']))}")
    print(f"  已申请：{bold(str(stats['applied']))}")
    print(f"  已拿 Offer：{green(bold(str(stats['offers'])))}")
    print(f"\n  等级分布：", end="")
    for g, n in stats["grades"].items():
        if n: print(grade_color(g)(f"{g}:{n}"), end="  ")
    print()
    print(f"\n  申请状态：")
    for s, n in stats["statuses"].items():
        if n: print(f"    {s:<10} {n}")


# ── 主程序 ───────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Career-Ops 实习求职助手",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    # 全局参数
    parser.add_argument(
        "--backend", default="auto", choices=["auto", "claude", "ollama"],
        help="LLM 后端：auto（自动选择）| claude（Claude API）| ollama（本地模型）"
    )
    sub = parser.add_subparsers(dest="command")

    # import-cv
    p_cv = sub.add_parser("import-cv", help="导入简历文件（PDF/TXT/MD）")
    p_cv.add_argument("file", help="简历路径，如 ~/Downloads/resume.pdf")
    p_cv.add_argument("--overwrite", action="store_true", help="覆盖时不备份")

    # gen-cv-summary
    sub.add_parser("gen-cv-summary", help="重建 CV 压缩摘要缓存（cv.md 更新后使用）")

    # evaluate
    p_eval = sub.add_parser("evaluate", help="URL → 爬取 JD → AI 评估 → PDF + 看板")
    p_eval.add_argument("--url",      default="", help="职位页面 URL（自动爬取 JD）")
    p_eval.add_argument("--jd",       default="", help="手动提供 JD 文本")
    p_eval.add_argument("--jd-file",  default="", help="JD 文本文件路径")
    p_eval.add_argument("--company",  default="", help="公司名称")
    p_eval.add_argument("--title",    default="", help="职位名称")
    p_eval.add_argument("--location", default="", help="工作地点")
    p_eval.add_argument("--visible",   action="store_true", help="显示浏览器窗口（调试用）")
    p_eval.add_argument("--no-cache",  action="store_true", help="忽略缓存，强制重新评估")
    p_eval.add_argument("--star",      action="store_true", help="评估后自动生成 STAR 面试故事并追加到故事库")

    # recommend
    p_rec = sub.add_parser("recommend", help="AI 根据方向推荐匹配职位")
    p_rec.add_argument("--direction", default="", help="求职方向，如：大模型算法、Java后端")

    # tailor-cv
    p_tailor = sub.add_parser("tailor-cv", help="根据 JD 裁剪简历，生成定向版 Markdown")
    p_tailor.add_argument("--url",     default="", help="职位 URL（自动爬取 JD）")
    p_tailor.add_argument("--jd",      default="", help="手动提供 JD 文本")
    p_tailor.add_argument("--jd-file", default="", help="JD 文本文件路径")
    p_tailor.add_argument("--company", default="", help="公司名称")
    p_tailor.add_argument("--title",   default="", help="职位名称")
    p_tailor.add_argument("--visible", action="store_true", help="显示浏览器窗口（调试用）")

    # cover-letter
    p_cl = sub.add_parser("cover-letter", help="根据 JD 生成求职信")
    p_cl.add_argument("--url",     default="", help="职位 URL（自动爬取 JD）")
    p_cl.add_argument("--jd",      default="", help="手动提供 JD 文本")
    p_cl.add_argument("--jd-file", default="", help="JD 文本文件路径")
    p_cl.add_argument("--company", default="", help="公司名称")
    p_cl.add_argument("--title",   default="", help="职位名称")
    p_cl.add_argument("--visible", action="store_true", help="显示浏览器窗口（调试用）")

    # stories
    p_stories = sub.add_parser("stories", help="管理 STAR 面试故事库")
    p_stories.add_argument("stories_action", nargs="?", default="list",
                           choices=["list", "search", "gen"],
                           help="list（查看，默认）| search（搜索）| gen（手动生成）")
    p_stories.add_argument("--keyword", default="", help="配合 search 使用，搜索关键词")
    p_stories.add_argument("--url",     default="", help="配合 gen 使用，职位 URL")
    p_stories.add_argument("--jd",      default="", help="配合 gen 使用，JD 文本")
    p_stories.add_argument("--jd-file", default="", help="配合 gen 使用，JD 文件路径")
    p_stories.add_argument("--company", default="", help="公司名称")
    p_stories.add_argument("--title",   default="", help="职位名称")
    p_stories.add_argument("--visible", action="store_true", help="显示浏览器窗口")

    # ab-test
    p_ab = sub.add_parser("ab-test",
        help="A/B 测试：量化摘要CV+截断JD（优化版）vs 全文（基准版）的质量代价")
    p_ab.add_argument("--url",      default="", help="职位 URL（自动爬取 JD）")
    p_ab.add_argument("--jd",       default="", help="手动提供 JD 文本")
    p_ab.add_argument("--jd-file",  default="", help="JD 文本文件路径")
    p_ab.add_argument("--company",  default="", help="公司名称")
    p_ab.add_argument("--title",    default="", help="职位名称")
    p_ab.add_argument("--visible",  action="store_true", help="显示浏览器窗口（调试用）")
    p_ab.add_argument("--rounds",   type=int, default=3,
                      help="每个 Variant 的重复轮次（默认 3，越多结果越稳定）")
    p_ab.add_argument("--no-save",  action="store_true", help="不保存 JSON 报告")

    # cache
    p_cache = sub.add_parser("cache", help="管理评估结果缓存")
    p_cache.add_argument("cache_action", nargs="?", default="stats",
                         choices=["stats", "clear", "remove"],
                         help="stats（查看，默认）| clear（清空）| remove（删除单条）")
    p_cache.add_argument("--url", default="", help="配合 remove 使用，指定要删除的 URL")

    # models（仅 Ollama 有意义）
    sub.add_parser("models", help="查看本地已安装的 Ollama 模型")

    # list
    p_list = sub.add_parser("list", help="列出所有职位")
    p_list.add_argument("--grade",  help="按等级筛选 (A/B/C/D/F)")
    p_list.add_argument("--status", help="按状态筛选")

    # update
    p_upd = sub.add_parser("update", help="更新申请状态")
    p_upd.add_argument("id",     type=int, help="职位 ID")
    p_upd.add_argument("status", help=f"新状态：{' / '.join(tracker.VALID_STATUSES)}")

    # pdf
    p_pdf = sub.add_parser("pdf", help="生成 PDF 报告")
    p_pdf.add_argument("id", type=int, help="职位 ID")

    # dashboard / stats
    sub.add_parser("dashboard", help="生成并打开 HTML 看板")
    sub.add_parser("stats",     help="显示统计摘要")

    args = parser.parse_args()

    cmds = {
        "import-cv":      cmd_import_cv,
        "gen-cv-summary": cmd_gen_cv_summary,
        "evaluate":       cmd_evaluate,
        "recommend":      cmd_recommend,
        "tailor-cv":      cmd_tailor_cv,
        "cover-letter":   cmd_cover_letter,
        "stories":        cmd_stories,
        "ab-test":        cmd_ab_test,
        "cache":          cmd_cache,
        "models":         cmd_models,
        "list":           cmd_list,
        "update":         cmd_update,
        "pdf":            cmd_pdf,
        "dashboard":      cmd_dashboard,
        "stats":          cmd_stats,
    }

    if args.command in cmds:
        cmds[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
