"""
Batch State Manager  —  Harness Engineering 状态持久化模块

解决的核心问题：
  "批量评估中途崩溃（速率限制/网络中断/进程被杀），前功尽弃"
  ← State Degradation（状态降级）问题

工作原理：
  1. 每个批量任务分配唯一 batch_id（8 位 hex）
  2. 每个子任务（单个 JD/URL）有独立状态：pending → running → done | failed | skipped
  3. 状态实时写入 data/batch_states/{batch_id}.json（原子写：先写 .tmp 再 rename）
  4. 中断后可通过 batch_id resume，自动跳过已完成任务，按需重试失败任务
  5. 心跳机制：running 状态记录 started_at，超过 STALE_TIMEOUT 视为 stale 可重试

面试亮点：
  - 原子写入（.tmp → rename）防写入中途崩溃导致状态文件损坏
  - 幂等性：同一任务 done 后再 run 自动 skip，不重复消耗 token
  - 心跳超时检测：crashed worker 留下的 running 状态自动重置为 pending
  - ETA 估算：基于已完成任务的平均耗时，实时预测剩余完成时间
  - 多维统计：total/done/failed/pending/skipped/elapsed，面试可直接引用数字

用法（CLI，通过 run.py）：
  python run.py batch run --urls urls.txt               # 从文件读取 URL 批量评估
  python run.py batch run --jd-dir ./jds --star         # 从目录读取 JD 文件
  python run.py batch status <batch_id>                 # 查看进度
  python run.py batch resume <batch_id>                 # 断点续传
  python run.py batch retry <batch_id>                  # 重试失败任务
  python run.py batch list                              # 列出所有批次
"""
import json
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

BASE_DIR         = Path(__file__).parent.parent
BATCH_STATE_DIR  = BASE_DIR / "data" / "batch_states"

# running 状态超过此秒数视为 stale（可被 resume 重新拾取）
STALE_TIMEOUT    = 600   # 10 分钟


# ── 状态常量 ────────────────────────────────────────────────────────────────

class TaskStatus:
    PENDING  = "pending"
    RUNNING  = "running"
    DONE     = "done"
    FAILED   = "failed"
    SKIPPED  = "skipped"   # 已存在相同缓存，主动跳过


# ── 数据结构 ─────────────────────────────────────────────────────────────────

@dataclass
class BatchTask:
    task_id:    str
    input_type: str            # "url" | "jd_file" | "jd_text"
    input_val:  str            # URL / 文件路径 / JD 文本片段
    company:    str  = ""
    title:      str  = ""
    status:     str  = TaskStatus.PENDING
    result:     dict = field(default_factory=dict)   # 评估结果摘要
    error:      str  = ""
    started_at: str  = ""
    finished_at:str  = ""
    elapsed_s:  float = 0.0


@dataclass
class BatchJob:
    batch_id:   str
    created_at: str
    label:      str                          # 用户可读描述
    backend:    str  = "auto"
    star:       bool = False                 # 是否同步生成 STAR 故事
    tasks:      list = field(default_factory=list)  # list[BatchTask]


# ── 颜色输出 ─────────────────────────────────────────────────────────────────

def _c(text, code): return f"\033[{code}m{text}\033[0m"
def green(t):  return _c(t, "32")
def yellow(t): return _c(t, "33")
def red(t):    return _c(t, "31")
def bold(t):   return _c(t, "1")
def grey(t):   return _c(t, "90")
def blue(t):   return _c(t, "34")


# ── 序列化 / 反序列化 ────────────────────────────────────────────────────────

def _job_to_dict(job: BatchJob) -> dict:
    d = asdict(job)
    d["tasks"] = [asdict(t) if isinstance(t, BatchTask) else t for t in job.tasks]
    return d


def _job_from_dict(d: dict) -> BatchJob:
    tasks = [BatchTask(**t) if isinstance(t, dict) else t for t in d.get("tasks", [])]
    return BatchJob(
        batch_id   = d["batch_id"],
        created_at = d["created_at"],
        label      = d.get("label", ""),
        backend    = d.get("backend", "auto"),
        star       = d.get("star", False),
        tasks      = tasks,
    )


# ── 文件 I/O（原子写入）──────────────────────────────────────────────────────

def _state_path(batch_id: str) -> Path:
    BATCH_STATE_DIR.mkdir(parents=True, exist_ok=True)
    return BATCH_STATE_DIR / f"{batch_id}.json"


def _load(batch_id: str) -> Optional[BatchJob]:
    """加载批次状态文件，不存在时返回 None"""
    path = _state_path(batch_id)
    if not path.exists():
        return None
    try:
        return _job_from_dict(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return None


def _save(job: BatchJob) -> None:
    """
    原子写入：先写 .tmp 临时文件，再 rename 到目标路径。
    即使写入中途进程崩溃，原有状态文件也不会被截断/损坏。
    """
    BATCH_STATE_DIR.mkdir(parents=True, exist_ok=True)
    target = _state_path(job.batch_id)
    tmp    = target.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(_job_to_dict(job), ensure_ascii=False, indent=2),
                       encoding="utf-8")
        tmp.rename(target)
    except Exception:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise


# ── 核心 API ─────────────────────────────────────────────────────────────────

def create_batch(inputs: list[tuple[str, str]], label: str = "",
                 backend: str = "auto", star: bool = False) -> BatchJob:
    """
    创建新批次。
    inputs: [(input_type, input_val), ...]
            input_type in {"url", "jd_file", "jd_text"}
    """
    batch_id = uuid.uuid4().hex[:8]
    tasks = [
        BatchTask(
            task_id    = f"{batch_id}_{i:03d}",
            input_type = itype,
            input_val  = ival,
        )
        for i, (itype, ival) in enumerate(inputs)
    ]
    job = BatchJob(
        batch_id   = batch_id,
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        label      = label or f"{len(tasks)} 个任务",
        backend    = backend,
        star       = star,
        tasks      = tasks,
    )
    _save(job)
    return job


def get_batch(batch_id: str) -> Optional[BatchJob]:
    return _load(batch_id)


def list_batches() -> list[BatchJob]:
    """列出所有批次，按创建时间倒序"""
    BATCH_STATE_DIR.mkdir(parents=True, exist_ok=True)
    jobs = []
    for p in sorted(BATCH_STATE_DIR.glob("*.json"), reverse=True):
        j = _load(p.stem)
        if j:
            jobs.append(j)
    return jobs


def get_stats(job: BatchJob) -> dict:
    """计算批次进度统计"""
    total   = len(job.tasks)
    done    = sum(1 for t in job.tasks if t.status == TaskStatus.DONE)
    failed  = sum(1 for t in job.tasks if t.status == TaskStatus.FAILED)
    skipped = sum(1 for t in job.tasks if t.status == TaskStatus.SKIPPED)
    running = sum(1 for t in job.tasks if t.status == TaskStatus.RUNNING)
    pending = sum(1 for t in job.tasks if t.status == TaskStatus.PENDING)

    done_tasks = [t for t in job.tasks if t.status == TaskStatus.DONE and t.elapsed_s > 0]
    avg_s = (sum(t.elapsed_s for t in done_tasks) / len(done_tasks)) if done_tasks else 0
    remaining = pending + running
    eta_s  = int(avg_s * remaining) if avg_s > 0 else None

    return {
        "total":   total,
        "done":    done,
        "failed":  failed,
        "skipped": skipped,
        "running": running,
        "pending": pending,
        "pct":     round(done / total * 100, 1) if total else 0,
        "avg_s":   round(avg_s, 1),
        "eta_s":   eta_s,
    }


def _reset_stale(job: BatchJob) -> int:
    """
    心跳超时检测：将 running 状态中超过 STALE_TIMEOUT 的任务重置为 pending。
    返回重置数量。
    """
    now   = time.time()
    count = 0
    for t in job.tasks:
        if t.status == TaskStatus.RUNNING and t.started_at:
            try:
                started = datetime.strptime(t.started_at, "%Y-%m-%d %H:%M:%S").timestamp()
                if now - started > STALE_TIMEOUT:
                    t.status     = TaskStatus.PENDING
                    t.started_at = ""
                    count += 1
            except ValueError:
                pass
    return count


# ── 运行批次 ─────────────────────────────────────────────────────────────────

def run_batch(job: BatchJob, retry_failed: bool = False) -> None:
    """
    执行批次中所有 pending（及可选的 failed）任务，实时持久化每个任务的状态。
    中断后可重新调用，已 done/skipped 的任务自动跳过（幂等性）。

    retry_failed=True 时，先将 failed 任务重置为 pending 再执行。
    """
    from src import evaluator
    from src.context_engine import get_engine

    # 心跳超时检测
    stale = _reset_stale(job)
    if stale:
        print(yellow(f"  ⚠ 检测到 {stale} 个超时 running 任务，已重置为 pending"))
        _save(job)

    # 按需重置 failed → pending
    if retry_failed:
        for t in job.tasks:
            if t.status == TaskStatus.FAILED:
                t.status = TaskStatus.PENDING
                t.error  = ""
        _save(job)

    # 只处理 pending 任务
    pending_tasks = [t for t in job.tasks if t.status == TaskStatus.PENDING]
    stats = get_stats(job)

    print(bold(f"\n  📦 批次 {job.batch_id}  「{job.label}」"))
    print(grey(f"     总任务 {stats['total']} · 已完成 {stats['done']} "
               f"· 失败 {stats['failed']} · 跳过 {stats['skipped']}"))
    print(grey(f"     本轮待执行：{len(pending_tasks)} 个\n"))

    if not pending_tasks:
        print(green("  ✓ 全部任务已完成，无需执行"))
        return

    engine = get_engine()

    for idx, task in enumerate(pending_tasks, 1):
        # ── 标记为 running ────────────────────────────────────────────────
        task.status     = TaskStatus.RUNNING
        task.started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _save(job)

        t0 = time.time()
        label = _task_label(task)
        print(f"  [{idx}/{len(pending_tasks)}] {label}  ", end="", flush=True)

        try:
            result = _execute_task(task, job, evaluator, engine)

            # ── 标记为 done ───────────────────────────────────────────────
            task.status      = TaskStatus.DONE
            task.elapsed_s   = round(time.time() - t0, 1)
            task.finished_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            task.result      = {
                "grade":   result.get("grade", "?"),
                "score":   result.get("score", 0),
                "company": result.get("company", task.company),
                "title":   result.get("title",   task.title),
            }
            grade = result.get("grade", "?")
            score = result.get("score", 0)
            gc    = {"A": green, "B": blue, "C": yellow, "F": red}.get(grade, grey)
            print(gc(f"{grade} {score}分") + grey(f"  ({task.elapsed_s}s)"))

        except Exception as e:
            # ── 标记为 failed ─────────────────────────────────────────────
            task.status      = TaskStatus.FAILED
            task.elapsed_s   = round(time.time() - t0, 1)
            task.finished_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            task.error       = str(e)[:200]
            print(red(f"✗ {str(e)[:60]}"))

        _save(job)

        # ETA 刷新
        stats = get_stats(job)
        if stats["eta_s"] and stats["pending"] > 0:
            m, s = divmod(stats["eta_s"], 60)
            eta_str = f"{m}分{s}秒" if m else f"{s}秒"
            print(grey(f"     进度 {stats['done']}/{stats['total']} ({stats['pct']}%)  ETA {eta_str}"))

    # ── 最终汇总 ─────────────────────────────────────────────────────────────
    _print_batch_summary(job)


def _execute_task(task: BatchTask, job: BatchJob, evaluator, engine) -> dict:
    """执行单个任务并返回评估结果；失败时抛出异常"""
    from src.tracker import add_job
    from src.pdf_gen import generate_pdf
    from src.dashboard_gen import generate_dashboard
    from src import star_bank

    jd_text = ""
    company = task.company or ""
    title   = task.title   or ""
    url     = ""

    if task.input_type == "url":
        url = task.input_val
        from src.scraper import scrape_job
        info    = scrape_job(url, headless=True)
        jd_text = info.jd_text
        if not company: company = info.company
        if not title:   title   = info.title

    elif task.input_type == "jd_file":
        jd_text = Path(task.input_val).read_text(encoding="utf-8")

    elif task.input_type == "jd_text":
        jd_text = task.input_val

    if not jd_text.strip():
        raise ValueError("JD 内容为空")

    result = evaluator.auto_evaluate(
        jd_text=jd_text,
        company=company,
        title=title,
        location="",
        url=url,
        backend=job.backend,
        use_cache=True,
    )

    # 写入看板
    job_entry = add_job(**{k: result[k] for k in
                [  "company", "title", "location", "url",
                   "score",   "grade", "dimensions",
                   "recommendation", "full_report" ]})
    generate_pdf(job_entry)
    generate_dashboard()

    # Context Engine 记录
    try:
        engine.record_evaluation(result)
    except Exception:
        pass

    # STAR 故事
    if job.star:
        try:
            story = star_bank.generate_story(jd_text, company, title, backend=job.backend)
            star_bank.append_story(story, company, title)
        except Exception:
            pass

    return result


def _task_label(task: BatchTask) -> str:
    if task.input_type == "url":
        return grey(task.input_val[:55] + ("…" if len(task.input_val) > 55 else ""))
    if task.input_type == "jd_file":
        return grey(Path(task.input_val).name)
    return grey(task.input_val[:40] + "…")


# ── 输出 ─────────────────────────────────────────────────────────────────────

def print_batch_status(job: BatchJob) -> None:
    """打印批次详情，包含每个任务的状态"""
    stats = get_stats(job)
    stale = _count_stale(job)

    print(bold(f"\n  📦 批次 {job.batch_id}  「{job.label}」"))
    print(f"  创建：{grey(job.created_at)}  后端：{grey(job.backend)}")
    print(f"  总计：{stats['total']}  "
          f"完成：{green(str(stats['done']))}  "
          f"失败：{red(str(stats['failed'])) if stats['failed'] else grey('0')}  "
          f"跳过：{grey(str(stats['skipped']))}  "
          f"待执行：{yellow(str(stats['pending']))}")
    print(f"  进度：{bold(str(stats['pct']) + '%')}", end="")
    if stale:
        print(f"  {yellow(f'({stale} stale)')}", end="")
    print()

    # 任务列表
    print(f"\n  {'#':>4}  {'状态':>7}  {'等级':>4}  {'用时':>6}  {'公司/文件'}")
    print("  " + "─" * 62)
    for i, t in enumerate(job.tasks, 1):
        status_str = {
            TaskStatus.DONE:    green("done   "),
            TaskStatus.FAILED:  red("failed "),
            TaskStatus.RUNNING: yellow("running"),
            TaskStatus.PENDING: grey("pending"),
            TaskStatus.SKIPPED: grey("skipped"),
        }.get(t.status, grey(t.status))

        grade = t.result.get("grade", "–") if t.result else "–"
        score = t.result.get("score", "") if t.result else ""
        grade_str = f"{grade}{score}" if score else grade
        time_str  = f"{t.elapsed_s:.1f}s" if t.elapsed_s else "–"

        name = (t.result.get("company","") + "·" + t.result.get("title","")
                ) if t.result else _task_label(t)

        print(f"  {i:>4}  {status_str}  {grade_str:>5}  {time_str:>6}  {grey(str(name)[:35])}")
        if t.status == TaskStatus.FAILED and t.error:
            print(f"         {red('↳ ' + t.error[:60])}")


def _count_stale(job: BatchJob) -> int:
    now = time.time()
    count = 0
    for t in job.tasks:
        if t.status == TaskStatus.RUNNING and t.started_at:
            try:
                started = datetime.strptime(t.started_at, "%Y-%m-%d %H:%M:%S").timestamp()
                if now - started > STALE_TIMEOUT:
                    count += 1
            except ValueError:
                pass
    return count


def print_batch_list(jobs: list[BatchJob]) -> None:
    if not jobs:
        print(yellow("  暂无批次记录"))
        return
    print(bold(f"\n  📋 批次列表（共 {len(jobs)} 个）\n"))
    print(f"  {'Batch ID':<12}  {'创建时间':<18}  {'进度':>8}  {'标签'}")
    print("  " + "─" * 66)
    for j in jobs:
        s = get_stats(j)
        pct_str = f"{s['done']}/{s['total']} ({s['pct']}%)"
        status_color = green if s["pct"] == 100 else (yellow if s["failed"] else blue)
        print(f"  {j.batch_id:<12}  {j.created_at:<18}  "
              f"{status_color(pct_str):>8}  {grey(j.label[:30])}")


def _print_batch_summary(job: BatchJob) -> None:
    stats = get_stats(job)
    print(bold(f"\n  {'─'*56}"))
    print(bold(f"  批次 {job.batch_id} 完成  {stats['done']}/{stats['total']} 成功  "
               f"失败 {stats['failed']}  跳过 {stats['skipped']}"))
    if stats["failed"]:
        print(yellow(f"  ⚠ {stats['failed']} 个任务失败，可用 'batch retry {job.batch_id}' 重试"))
    else:
        print(green("  ✓ 全部完成！"))


# ── 输入解析工具 ──────────────────────────────────────────────────────────────

def parse_url_file(path: str) -> list[tuple[str, str]]:
    """
    从文本文件读取 URL 列表（每行一个，# 开头为注释）。
    返回 [("url", url), ...]
    """
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    urls  = [l.strip() for l in lines if l.strip() and not l.strip().startswith("#")]
    return [("url", u) for u in urls]


def parse_jd_dir(path: str) -> list[tuple[str, str]]:
    """
    从目录读取所有 .txt / .md 文件作为 JD 文本来源。
    返回 [("jd_file", filepath), ...]
    """
    p = Path(path)
    files = sorted(p.glob("*.txt")) + sorted(p.glob("*.md"))
    return [("jd_file", str(f)) for f in files]
