#!/usr/bin/env python3
"""
Career-Ops 本地调试版（Ollama）
使用本地模型运行，无需 Claude API Key

用法：
  python3 run_local.py evaluate --url "招聘链接"
  python3 run_local.py evaluate --jd "JD文本" --company "字节" --title "后端实习"
  python3 run_local.py recommend --direction "大模型算法"
  python3 run_local.py list
  python3 run_local.py update <id> <状态>
  python3 run_local.py dashboard
  python3 run_local.py models         查看本地已安装模型

前置条件：
  1. 安装 Ollama：https://ollama.com
  2. 启动服务：ollama serve
  3. 拉取模型：ollama pull qwen2.5:7b
"""
import sys
import os
import argparse
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

from src import tracker, evaluator, recommender, pdf_gen, dashboard_gen
from src.cv_importer import import_cv
from src.ollama_client import chat, list_models, load_local_config
from src import cv_tailor, cover_letter as cl


# ── 颜色 ────────────────────────────────────────────────────────
def c(text, code): return f"\033[{code}m{text}\033[0m"
green  = lambda t: c(t, "32")
yellow = lambda t: c(t, "33")
red    = lambda t: c(t, "31")
bold   = lambda t: c(t, "1")
grey   = lambda t: c(t, "90")

def grade_color(grade):
    return {"A": lambda t: c(t,"32"), "B": lambda t: c(t,"34"),
            "C": yellow, "F": red}.get(grade, grey)


# ── Ollama 版评估 ────────────────────────────────────────────────
def ollama_evaluate(jd_text: str, company: str, title: str,
                    location: str = "", url: str = "") -> dict:
    cfg    = load_local_config()
    model  = cfg.get("model", "qwen2.5:7b")
    prompt = evaluator.build_evaluation_prompt(jd_text)

    print(f"  🦙 正在调用本地模型 ({model})...")
    raw = chat(prompt, cfg)
    return evaluator.parse_evaluation_result(raw, company, title, location, url)


# ── Ollama 版推荐 ────────────────────────────────────────────────
def ollama_recommend(direction: str) -> str:
    cfg   = load_local_config()
    model = cfg.get("model", "qwen2.5:7b")
    prompt = recommender.build_recommend_prompt(direction)

    print(f"  🦙 正在调用本地模型 ({model})...")
    return chat(prompt, cfg)


# ── evaluate 命令 ────────────────────────────────────────────────
def cmd_evaluate(args):
    from src.scraper import scrape_job

    url      = args.url or ""
    company  = args.company or ""
    title    = args.title or ""
    location = args.location or ""
    jd_text  = ""

    if url.startswith("http"):
        print(f"  🌐 正在爬取：{url}")
        try:
            info     = scrape_job(url, headless=not args.visible)
            jd_text  = info.jd_text
            company  = company  or info.company
            title    = title    or info.title
            location = location or info.location
            print(green(f"  ✓ 爬取成功：{title} @ {company}"))
        except ImportError:
            print(yellow("  ⚠ 未安装 Playwright，跳过自动爬取"))
        except Exception as e:
            print(yellow(f"  ⚠ 爬取失败（{e}）"))

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

    company  = company  or input("  公司名称：").strip()
    title    = title    or input("  职位名称：").strip()
    location = location or input("  工作地点（回车跳过）：").strip()

    try:
        result = ollama_evaluate(jd_text, company, title, location, url)
    except (ConnectionError, TimeoutError) as e:
        print(red(f"✗ {e}"))
        sys.exit(1)

    job      = tracker.add_job(**{k: result[k] for k in
               ["company","title","location","url","score","grade",
                "dimensions","recommendation","full_report"]})
    rpt_path = evaluator.save_report_to_file(result)
    pdf_path = pdf_gen.generate_pdf(job)
    dashboard_gen.generate_dashboard()

    gc = grade_color(job["grade"])
    print(f"\n{gc(bold(' ' + str(job['grade']) + ' 级 ' + str(job['score']) + '/100'))} · {company} · {title}")
    print(green(f"  ✓ ID={job['id']}  报告：{rpt_path.name}  PDF：{pdf_path.name}"))
    print(green(f"  ✓ 看板已更新"))


# ── recommend 命令 ───────────────────────────────────────────────
def cmd_recommend(args):
    direction = args.direction or input("  求职方向：").strip()
    if not direction:
        print(red("方向不能为空"))
        sys.exit(1)

    print(f"\n  🔍 正在为「{direction}」生成推荐...")
    try:
        report = ollama_recommend(direction)
    except (ConnectionError, TimeoutError) as e:
        print(red(f"✗ {e}"))
        sys.exit(1)

    print("\n" + report)
    path = recommender.save_recommend_report(direction, report)
    print(green(f"\n  ✓ 推荐报告已保存：{path.name}"))


# ── models 命令 ──────────────────────────────────────────────────
def cmd_models(args):
    cfg  = load_local_config()
    base = cfg.get("ollama_base_url", "http://localhost:11434")
    models = list_models(base)
    if not models:
        print(yellow("未找到已安装模型，或 Ollama 未启动"))
        print(grey("  启动：ollama serve"))
        print(grey("  安装模型：ollama pull qwen2.5:7b"))
        return
    print(bold(f"\n已安装模型（共 {len(models)} 个）："))
    for m in models:
        cur = cfg.get("model", "")
        tag = green(" ← 当前使用") if m == cur else ""
        print(f"  • {m}{tag}")
    print(grey(f"\n修改模型：编辑 config/api_local.yml 中的 model 字段"))


# ── Ollama 版 tailor-cv ──────────────────────────────────────────
def cmd_tailor_cv(args):
    from src.scraper import scrape_job
    cfg = load_local_config()

    url, company, title, jd_text = args.url or "", args.company or "", args.title or "", ""

    if url.startswith("http"):
        print(f"  🌐 正在爬取：{url}")
        try:
            info = scrape_job(url, headless=True)
            jd_text = info.jd_text
            company = company or info.company
            title   = title   or info.title
            print(green(f"  ✓ 爬取成功：{title} @ {company}"))
        except Exception as e:
            print(yellow(f"  ⚠ 爬取失败（{e}）"))

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

    prompt = cv_tailor.build_tailor_prompt(jd_text, company, title)
    model  = cfg.get("model", "qwen2.5:latest")
    print(f"  🦙 正在调用本地模型 ({model}) 裁剪简历...")
    result = chat(prompt, cfg)

    path = cv_tailor.save_tailored_cv(result, company, title)
    print(green(f"\n  ✓ 定向简历已生成：reports/tailored_cvs/{path.name}"))


# ── Ollama 版 cover-letter ────────────────────────────────────────
def cmd_cover_letter(args):
    from src.scraper import scrape_job
    cfg = load_local_config()

    url, company, title, jd_text = args.url or "", args.company or "", args.title or "", ""

    if url.startswith("http"):
        print(f"  🌐 正在爬取：{url}")
        try:
            info = scrape_job(url, headless=True)
            jd_text = info.jd_text
            company = company or info.company
            title   = title   or info.title
            print(green(f"  ✓ 爬取成功：{title} @ {company}"))
        except Exception as e:
            print(yellow(f"  ⚠ 爬取失败（{e}）"))

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

    prompt = cl.build_cover_letter_prompt(jd_text, company, title)
    model  = cfg.get("model", "qwen2.5:latest")
    print(f"  🦙 正在调用本地模型 ({model}) 生成求职信...")
    letter = chat(prompt, cfg)

    path = cl.save_cover_letter(letter, company, title)
    print(f"\n{bold('──── 求职信预览 ────')}")
    print(letter)
    print(green(f"\n  ✓ 求职信已保存：reports/cover_letters/{path.name}"))


# ── 其他命令复用原版 ─────────────────────────────────────────────
def cmd_list(args):
    jobs = tracker.get_all_jobs()
    print(bold(f"\n📋 职位列表（共 {len(jobs)} 条）\n"))
    tracker.print_jobs_table(jobs)

def cmd_update(args):
    job = tracker.update_status(args.id, args.status)
    if job:
        print(green(f"✓ #{args.id} → {args.status}"))
        dashboard_gen.generate_dashboard()
    else:
        print(red(f"找不到 ID={args.id}"))

def cmd_dashboard(args):
    path = dashboard_gen.generate_dashboard()
    print(green(f"✓ 看板已生成：{path}"))
    if sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)


def cmd_import_cv(args):
    try:
        path = import_cv(args.file, overwrite=args.overwrite)
        print(green(f"✓ 简历已导入：{path}"))
    except Exception as e:
        print(red(f"✗ 导入失败：{e}"))


# ── 主程序 ───────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Career-Ops 本地调试版（Ollama）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    sub = parser.add_subparsers(dest="command")

    p_ev = sub.add_parser("evaluate", help="爬取+本地模型评估职位")
    p_ev.add_argument("--url", default="")
    p_ev.add_argument("--jd", default="")
    p_ev.add_argument("--jd-file", default="")
    p_ev.add_argument("--company", default="")
    p_ev.add_argument("--title", default="")
    p_ev.add_argument("--location", default="")
    p_ev.add_argument("--visible", action="store_true")

    p_rec = sub.add_parser("recommend", help="本地模型推荐职位")
    p_rec.add_argument("--direction", default="")

    p_tailor = sub.add_parser("tailor-cv", help="根据 JD 裁剪简历，生成定向版 Markdown")
    p_tailor.add_argument("--url", default="")
    p_tailor.add_argument("--jd", default="")
    p_tailor.add_argument("--jd-file", default="")
    p_tailor.add_argument("--company", default="")
    p_tailor.add_argument("--title", default="")

    p_cl = sub.add_parser("cover-letter", help="根据 JD 生成求职信")
    p_cl.add_argument("--url", default="")
    p_cl.add_argument("--jd", default="")
    p_cl.add_argument("--jd-file", default="")
    p_cl.add_argument("--company", default="")
    p_cl.add_argument("--title", default="")

    sub.add_parser("models", help="查看已安装的 Ollama 模型")

    p_cv = sub.add_parser("import-cv", help="导入简历文件（PDF/TXT/MD）")
    p_cv.add_argument("file", help="简历路径，如 ~/Downloads/resume.pdf")
    p_cv.add_argument("--overwrite", action="store_true")

    p_list = sub.add_parser("list", help="列出所有职位")
    p_upd  = sub.add_parser("update", help="更新申请状态")
    p_upd.add_argument("id", type=int)
    p_upd.add_argument("status")
    sub.add_parser("dashboard", help="打开看板")

    args = parser.parse_args()
    cmds = {
        "import-cv":    cmd_import_cv,
        "evaluate":     cmd_evaluate,
        "recommend":    cmd_recommend,
        "tailor-cv":    cmd_tailor_cv,
        "cover-letter": cmd_cover_letter,
        "models":       cmd_models,
        "list":         cmd_list,
        "update":       cmd_update,
        "dashboard":    cmd_dashboard,
    }

    if args.command in cmds:
        cmds[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
