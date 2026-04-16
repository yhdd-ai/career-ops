#!/usr/bin/env python3
"""
Career-Ops 主入口
实习求职 AI 助手 · 命令行界面

用法：
  python run.py evaluate --jd "JD文本"         【全自动】调用 Claude API 评估，生成 PDF + 更新看板
  python run.py evaluate --jd-file jd.txt      从文件读取 JD 全自动评估
  python run.py list                            列出所有职位
  python run.py update <id> <状态>              更新申请状态
  python run.py pdf <id>                        为指定职位生成 PDF 报告
  python run.py dashboard                       生成并打开 HTML 看板
  python run.py stats                           显示统计摘要
"""
import sys
import os
import argparse
import json
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

from src import tracker, evaluator, pdf_gen, dashboard_gen, recommender
from src.cv_importer import import_cv
from src import cv_tailor, cover_letter as cl


# ── 颜色输出 ────────────────────────────────────────────────────
def c(text, code): return f"\033[{code}m{text}\033[0m"
def green(t): return c(t, "32")
def blue(t): return c(t, "34")
def yellow(t): return c(t, "33")
def red(t): return c(t, "31")
def bold(t): return c(t, "1")
def grey(t): return c(t, "90")


def grade_color(grade):
    return {"A": green, "B": blue, "C": yellow, "D": lambda t: c(t, "33"),
            "F": red}.get(grade, grey)


# ── evaluate 命令（全自动）────────────────────────────────────────
def cmd_evaluate(args):
    """全自动：URL 传入 → 爬取 JD → Claude API 评估 → PDF + 看板"""
    from src.scraper import scrape_job

    url = args.url or ""
    company  = args.company  or ""
    title    = args.title    or ""
    location = args.location or ""
    jd_text  = ""

    # ① 优先从 URL 自动爬取
    if url and url.startswith("http"):
        print(f"  🌐 正在爬取：{url}")
        try:
            info = scrape_job(url, headless=not args.visible)
            jd_text  = info.jd_text
            company  = company  or info.company
            title    = title    or info.title
            location = location or info.location
            print(green(f"  ✓ 爬取成功：{title} @ {company}"))
        except ImportError:
            print(yellow("  ⚠ 未安装 Playwright，跳过自动爬取"))
            print(yellow("    pip install playwright && playwright install chromium"))
        except Exception as e:
            print(yellow(f"  ⚠ 爬取失败（{e}），请手动提供 JD"))

    # ② 爬取失败 / 无 URL → 读文件或手动输入
    if not jd_text:
        if args.jd_file:
            jd_text = Path(args.jd_file).read_text(encoding="utf-8")
        elif args.jd:
            jd_text = args.jd
        else:
            print(bold("请粘贴 JD 内容（Ctrl+D 结束）："))
            lines = []
            try:
                while True:
                    lines.append(input())
            except EOFError:
                pass
            jd_text = "\n".join(lines)

    if not jd_text.strip():
        print(red("错误：JD 内容为空"))
        sys.exit(1)

    company  = company  or input("  公司名称：").strip()
    title    = title    or input("  职位名称：").strip()
    location = location or input("  工作地点（可回车跳过）：").strip()

    # 调用 LLM（统一接口，自动选 Claude/Ollama）
    try:
        result = evaluator.auto_evaluate(jd_text, company, title, location, url, backend="claude")
    except (ImportError, ValueError) as e:
        print(red(f"✗ {e}"))
        sys.exit(1)

    # 保存职位
    job = tracker.add_job(**{k: result[k] for k in
          ["company","title","location","url","score","grade",
           "dimensions","recommendation","full_report"]})

    # 保存 MD 报告
    rpt_path = evaluator.save_report_to_file(result)

    # 生成 PDF
    pdf_path = pdf_gen.generate_pdf(job)

    # 更新看板
    dashboard_gen.generate_dashboard()

    gc = grade_color(job["grade"])
    print(f"\n{gc(bold(' ' + str(job['grade']) + ' 级 ' + str(job['score']) + '/100'))} · {company} · {title}")
    print(green(f"  ✓ ID={job['id']}  报告：{rpt_path.name}  PDF：{pdf_path.name}"))
    print(green(f"  ✓ 看板已更新"))


# ── list 命令 ────────────────────────────────────────────────────
def cmd_list(args):
    jobs = tracker.get_all_jobs()
    if args.grade:
        jobs = [j for j in jobs if j.get("grade") == args.grade.upper()]
    if args.status:
        jobs = [j for j in jobs if j.get("status") == args.status]

    print(bold(f"\n📋 职位列表（共 {len(jobs)} 条）\n"))
    tracker.print_jobs_table(jobs)

    stats = tracker.get_stats()
    print(f"\n{grey('统计：')} 平均分 {bold(str(stats['avg_score']))}  "
          f"已申请 {bold(str(stats['applied']))}  "
          f"Offer {bold(str(stats['offers']))}")


# ── update 命令 ──────────────────────────────────────────────────
def cmd_update(args):
    valid = tracker.VALID_STATUSES
    if args.status not in valid:
        print(red(f"无效状态。可选：{', '.join(valid)}"))
        sys.exit(1)
    job = tracker.update_status(args.id, args.status)
    if job:
        print(green(f"✓ #{args.id} {job['company']} · {job['title']} → {args.status}"))
        dashboard_gen.generate_dashboard()
    else:
        print(red(f"找不到 ID={args.id} 的职位"))


# ── recommend 命令 ───────────────────────────────────────────────
def cmd_recommend(args):
    """根据方向，AI 推荐匹配的公司和职位"""
    direction = args.direction or input("  请输入求职方向（如：大模型算法、Java后端、数据分析）：").strip()
    if not direction:
        print(red("方向不能为空"))
        sys.exit(1)

    print(f"\n  🔍 正在为「{direction}」生成推荐...")
    try:
        report = recommender.auto_recommend(direction, backend="claude")
    except (ImportError, ValueError) as e:
        print(red(f"✗ {e}"))
        sys.exit(1)

    # 打印报告
    print("\n" + report)

    # 保存到文件
    path = recommender.save_recommend_report(direction, report)
    print(green(f"\n  ✓ 推荐报告已保存：{path.name}"))

    # 询问是否批量评估推荐的职位
    if input(bold("\n  是否对推荐的职位逐一评估？(y/N) ")).strip().lower() == "y":
        print(yellow("  请将招聘链接逐一传入：python3 run.py evaluate --url \"链接\""))


# ── pdf 命令 ─────────────────────────────────────────────────────
def cmd_pdf(args):
    job = tracker.get_job_by_id(args.id)
    if not job:
        print(red(f"找不到 ID={args.id} 的职位"))
        sys.exit(1)
    _generate_pdf_for_job(job)


def _generate_pdf_for_job(job):
    try:
        path = pdf_gen.generate_pdf(job)
        print(green(f"✓ PDF 已生成：{path}"))
        # macOS 自动打开
        if sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
    except Exception as e:
        print(red(f"PDF 生成失败：{e}"))


# ── dashboard 命令 ───────────────────────────────────────────────
def cmd_dashboard(args):
    path = dashboard_gen.generate_dashboard()
    print(green(f"✓ 看板已生成：{path}"))
    # 自动打开
    if sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    elif sys.platform.startswith("linux"):
        subprocess.run(["xdg-open", str(path)], check=False)
    else:
        print(blue(f"请在浏览器中打开：file://{path}"))


# ── import-cv 命令 ──────────────────────────────────────────────
def cmd_import_cv(args):
    try:
        path = import_cv(args.file, overwrite=args.overwrite)
        print(green(f"✓ 简历已导入：{path}"))
        print(grey("  可以开始评估职位了：python3 run.py evaluate --url \"...\""))
    except Exception as e:
        print(red(f"✗ 导入失败：{e}"))


# ── tailor-cv 命令 ───────────────────────────────────────────────
def cmd_tailor_cv(args):
    """根据 JD 裁剪简历，生成定向版 Markdown"""
    from src.scraper import scrape_job

    url      = args.url or ""
    company  = args.company or ""
    title    = args.title or ""
    jd_text  = ""

    if url.startswith("http"):
        print(f"  🌐 正在爬取：{url}")
        try:
            info     = scrape_job(url, headless=True)
            jd_text  = info.jd_text
            company  = company or info.company
            title    = title   or info.title
            print(green(f"  ✓ 爬取成功：{title} @ {company}"))
        except Exception as e:
            print(yellow(f"  ⚠ 爬取失败（{e}），请手动提供 JD"))

    if not jd_text:
        if args.jd_file:
            jd_text = Path(args.jd_file).read_text(encoding="utf-8")
        elif args.jd:
            jd_text = args.jd
        else:
            print(bold("请粘贴 JD 内容（Ctrl+D 结束）："))
            lines = []
            try:
                while True: lines.append(input())
            except EOFError: pass
            jd_text = "\n".join(lines)

    if not jd_text.strip():
        print(red("错误：JD 内容为空"))
        sys.exit(1)

    company = company or input("  公司名称：").strip()
    title   = title   or input("  职位名称：").strip()

    try:
        result = cv_tailor.tailor_cv(jd_text, company, title, backend="claude")
    except (ImportError, ValueError) as e:
        print(red(f"✗ {e}"))
        sys.exit(1)

    path = cv_tailor.save_tailored_cv(result, company, title)
    print(green(f"\n  ✓ 定向简历已生成：reports/tailored_cvs/{path.name}"))
    print(grey("  提示：可直接复制到 Word/LaTeX 排版后发送"))


# ── cover-letter 命令 ─────────────────────────────────────────────
def cmd_cover_letter(args):
    """根据 JD 生成求职信"""
    from src.scraper import scrape_job

    url      = args.url or ""
    company  = args.company or ""
    title    = args.title or ""
    jd_text  = ""

    if url.startswith("http"):
        print(f"  🌐 正在爬取：{url}")
        try:
            info     = scrape_job(url, headless=True)
            jd_text  = info.jd_text
            company  = company or info.company
            title    = title   or info.title
            print(green(f"  ✓ 爬取成功：{title} @ {company}"))
        except Exception as e:
            print(yellow(f"  ⚠ 爬取失败（{e}），请手动提供 JD"))

    if not jd_text:
        if args.jd_file:
            jd_text = Path(args.jd_file).read_text(encoding="utf-8")
        elif args.jd:
            jd_text = args.jd
        else:
            print(bold("请粘贴 JD 内容（Ctrl+D 结束）："))
            lines = []
            try:
                while True: lines.append(input())
            except EOFError: pass
            jd_text = "\n".join(lines)

    if not jd_text.strip():
        print(red("错误：JD 内容为空"))
        sys.exit(1)

    company = company or input("  公司名称：").strip()
    title   = title   or input("  职位名称：").strip()

    try:
        letter = cl.generate_cover_letter(jd_text, company, title, backend="claude")
    except (ImportError, ValueError) as e:
        print(red(f"✗ {e}"))
        sys.exit(1)

    path = cl.save_cover_letter(letter, company, title)
    print(f"\n{bold('──── 求职信预览 ────')}")
    print(letter)
    print(green(f"\n  ✓ 求职信已保存：reports/cover_letters/{path.name}"))


# ── gen-cv-summary 命令 ──────────────────────────────────────────
def cmd_gen_cv_summary(args):
    """重建 CV 压缩摘要缓存（cv.md 更新后使用）"""
    from src.token_optimizer import rebuild_cv_summary, estimate_tokens
    summary = rebuild_cv_summary()
    tokens_saved = estimate_tokens(Path("cv.md").read_text(encoding="utf-8")) - estimate_tokens(summary)
    print(green(f"✓ CV 摘要已重建：config/cv_summary.md"))
    print(grey(f"  摘要长度：{len(summary)} 字符 ≈ {estimate_tokens(summary)} tokens"))
    print(grey(f"  每次评估节省约 {tokens_saved} tokens"))
    print(bold("\n摘要预览："))
    print(summary)


# ── stats 命令 ───────────────────────────────────────────────────
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
        if n:
            print(grade_color(g)(f"{g}:{n}"), end="  ")
    print()
    print(f"\n  申请状态：")
    for s, n in stats["statuses"].items():
        if n:
            print(f"    {s:<10} {n}")


# ── 主程序 ───────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Career-Ops 实习求职助手",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    sub = parser.add_subparsers(dest="command")

    # import-cv
    p_cv = sub.add_parser("import-cv", help="导入简历文件（PDF/TXT/MD）到 cv.md")
    p_cv.add_argument("file", help="简历文件路径，如 ~/Downloads/resume.pdf")
    p_cv.add_argument("--overwrite", action="store_true", help="覆盖时不备份")

    # recommend
    p_rec = sub.add_parser("recommend", help="AI 根据方向推荐匹配职位")
    p_rec.add_argument("--direction", default="", help="求职方向，如：大模型算法、Java后端")

    # evaluate（全自动）
    p_eval = sub.add_parser("evaluate", help="【全自动】URL → 爬取 → Claude 评估 → PDF")
    p_eval.add_argument("--url", default="", help="职位页面 URL（自动爬取 JD）")
    p_eval.add_argument("--jd", default="", help="手动提供 JD 文本")
    p_eval.add_argument("--jd-file", default="", help="JD 文本文件路径")
    p_eval.add_argument("--company", default="", help="公司名称")
    p_eval.add_argument("--title", default="", help="职位名称")
    p_eval.add_argument("--location", default="", help="工作地点")
    p_eval.add_argument("--visible", action="store_true", help="显示浏览器窗口（调试用）")

    # list
    p_list = sub.add_parser("list", help="列出所有职位")
    p_list.add_argument("--grade", help="按等级筛选 (A/B/C/D/F)")
    p_list.add_argument("--status", help="按状态筛选")

    # update
    p_update = sub.add_parser("update", help="更新申请状态")
    p_update.add_argument("id", type=int, help="职位 ID")
    p_update.add_argument("status", help=f"新状态：{' / '.join(tracker.VALID_STATUSES)}")

    # pdf
    p_pdf = sub.add_parser("pdf", help="生成 PDF 报告")
    p_pdf.add_argument("id", type=int, help="职位 ID")

    # tailor-cv
    p_tailor = sub.add_parser("tailor-cv", help="根据 JD 裁剪简历，生成定向版 Markdown")
    p_tailor.add_argument("--url", default="", help="职位 URL（自动爬取 JD）")
    p_tailor.add_argument("--jd", default="", help="手动提供 JD 文本")
    p_tailor.add_argument("--jd-file", default="", help="JD 文本文件路径")
    p_tailor.add_argument("--company", default="", help="公司名称")
    p_tailor.add_argument("--title", default="", help="职位名称")

    # cover-letter
    p_cl = sub.add_parser("cover-letter", help="根据 JD 生成求职信")
    p_cl.add_argument("--url", default="", help="职位 URL（自动爬取 JD）")
    p_cl.add_argument("--jd", default="", help="手动提供 JD 文本")
    p_cl.add_argument("--jd-file", default="", help="JD 文本文件路径")
    p_cl.add_argument("--company", default="", help="公司名称")
    p_cl.add_argument("--title", default="", help="职位名称")

    # gen-cv-summary
    sub.add_parser("gen-cv-summary", help="重建 CV 压缩摘要缓存（cv.md 更新后使用）")

    # dashboard
    sub.add_parser("dashboard", help="生成并打开 HTML 看板")

    # stats
    sub.add_parser("stats", help="显示统计摘要")

    args = parser.parse_args()

    cmds = {
        "import-cv":      cmd_import_cv,
        "gen-cv-summary": cmd_gen_cv_summary,
        "evaluate":       cmd_evaluate,
        "recommend":    cmd_recommend,
        "tailor-cv":    cmd_tailor_cv,
        "cover-letter": cmd_cover_letter,
        "list":         cmd_list,
        "update":       cmd_update,
        "pdf":          cmd_pdf,
        "dashboard":    cmd_dashboard,
        "stats":        cmd_stats,
    }

    if args.command in cmds:
        cmds[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
