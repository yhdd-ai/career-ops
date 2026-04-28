"""
职位追踪模块
管理 data/jobs.json 中的职位记录（增删改查）
"""
import json
from pathlib import Path
from datetime import datetime
from typing import Optional

BASE_DIR = Path(__file__).parent.parent
JOBS_FILE = BASE_DIR / "data" / "jobs.json"

VALID_STATUSES = ["待申请", "已申请", "笔试/测评", "面试中", "已拿Offer", "已拒绝", "已放弃"]
VALID_GRADES = ["A", "B", "C", "D", "F"]


def _load_jobs() -> list:
    JOBS_FILE.parent.mkdir(exist_ok=True)
    if not JOBS_FILE.exists():
        return []
    with open(JOBS_FILE, encoding="utf-8") as f:
        return json.load(f)


def _save_jobs(jobs: list):
    with open(JOBS_FILE, "w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False, indent=2)


def _next_id(jobs: list) -> int:
    if not jobs:
        return 1
    return max(j.get("id", 0) for j in jobs) + 1


def add_job(company: str, title: str, score: int, grade: str,
            location: str = "", url: str = "", status: str = "待申请",
            notes: str = "", dimensions: dict = None,
            recommendation: str = "", full_report: str = "") -> dict:
    """添加一条职位记录"""
    jobs = _load_jobs()
    job = {
        "id": _next_id(jobs),
        "company": company,
        "title": title,
        "location": location,
        "score": score,
        "grade": grade,
        "status": status,
        "url": url,
        "notes": notes,
        "dimensions": dimensions or {},
        "recommendation": recommendation,
        "full_report": full_report,
        "evaluated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "applied_at": None,
    }
    jobs.append(job)
    _save_jobs(jobs)
    return job


def get_all_jobs() -> list:
    return _load_jobs()


def get_job_by_id(job_id: int) -> Optional[dict]:
    jobs = _load_jobs()
    for job in jobs:
        if job.get("id") == job_id:
            return job
    return None


def update_status(job_id: int, new_status: str) -> Optional[dict]:
    """更新职位申请状态"""
    if new_status not in VALID_STATUSES:
        raise ValueError(f"无效状态，可选：{', '.join(VALID_STATUSES)}")
    jobs = _load_jobs()
    for job in jobs:
        if job.get("id") == job_id:
            job["status"] = new_status
            if new_status == "已申请" and not job.get("applied_at"):
                job["applied_at"] = datetime.now().strftime("%Y-%m-%d")
            _save_jobs(jobs)
            return job
    return None


def update_notes(job_id: int, notes: str) -> Optional[dict]:
    jobs = _load_jobs()
    for job in jobs:
        if job.get("id") == job_id:
            job["notes"] = notes
            _save_jobs(jobs)
            return job
    return None


def delete_job(job_id: int) -> bool:
    jobs = _load_jobs()
    new_jobs = [j for j in jobs if j.get("id") != job_id]
    if len(new_jobs) == len(jobs):
        return False
    _save_jobs(new_jobs)
    return True


def get_stats() -> dict:
    """统计概览"""
    jobs = _load_jobs()
    if not jobs:
        return {"total": 0}

    grades = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
    statuses = {s: 0 for s in VALID_STATUSES}
    total_score = 0

    for job in jobs:
        g = job.get("grade", "?")
        if g in grades:
            grades[g] += 1
        s = job.get("status", "待申请")
        if s in statuses:
            statuses[s] += 1
        total_score += job.get("score", 0)

    return {
        "total": len(jobs),
        "avg_score": round(total_score / len(jobs), 1) if jobs else 0,
        "grades": grades,
        "statuses": statuses,
        "applied": statuses.get("已申请", 0) + statuses.get("笔试/测评", 0) +
                   statuses.get("面试中", 0) + statuses.get("已拿Offer", 0),
        "offers": statuses.get("已拿Offer", 0),
    }


def print_jobs_table(jobs: list = None):
    """在终端打印职位列表"""
    if jobs is None:
        jobs = _load_jobs()
    if not jobs:
        print("暂无记录")
        return

    header = f"{'ID':>3}  {'公司':<12}  {'职位':<18}  {'分数':>4}  {'等级':>4}  {'状态':<8}  {'地点':<6}  {'评估时间':<16}"
    print(header)
    print("─" * len(header))
    for job in sorted(jobs, key=lambda x: -x.get("score", 0)):
        grade_icon = {"A": "★", "B": "◆", "C": "●", "D": "▲", "F": "✗"}.get(job.get("grade"), "?")
        print(
            f"{job['id']:>3}  "
            f"{job['company']:<12}  "
            f"{job['title']:<18}  "
            f"{job.get('score', 0):>4}  "
            f"{grade_icon} {job.get('grade', '?'):>2}  "
            f"{job.get('status', ''):<8}  "
            f"{job.get('location', ''):<6}  "
            f"{job.get('evaluated_at', ''):<16}"
        )
