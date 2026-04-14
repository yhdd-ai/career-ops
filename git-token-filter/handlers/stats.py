"""
stats.py - Token 节省统计
记录每次调用的 原始/过滤后 token 数，累计展示节省情况
"""

import json
import os
from datetime import datetime

STATS_FILE = os.path.expanduser("~/.gtf_stats.json")


def _load() -> dict:
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"total_raw": 0, "total_filtered": 0, "calls": []}


def _save(data: dict):
    try:
        with open(STATS_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def record(subcommand: str, raw_tokens: int, filtered_tokens: int):
    """记录一次调用的 token 统计"""
    data = _load()
    data["total_raw"] += raw_tokens
    data["total_filtered"] += filtered_tokens
    data["calls"].append({
        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "cmd": subcommand,
        "raw": raw_tokens,
        "filtered": filtered_tokens,
        "saved": raw_tokens - filtered_tokens,
    })
    # 只保留最近 100 条记录
    data["calls"] = data["calls"][-100:]
    _save(data)


def show():
    """打印累计节省统计"""
    data = _load()
    total_raw = data["total_raw"]
    total_filtered = data["total_filtered"]
    total_saved = total_raw - total_filtered
    calls = data["calls"]

    if total_raw == 0:
        print("暂无统计数据，先运行几条 git 命令吧！")
        return

    pct = round(total_saved / total_raw * 100) if total_raw > 0 else 0

    print("=" * 45)
    print("  GTF Token 节省统计")
    print("=" * 45)
    print(f"  累计原始 tokens :  {total_raw:,}")
    print(f"  累计过滤 tokens :  {total_filtered:,}")
    print(f"  累计节省 tokens :  {total_saved:,}  (-{pct}%)")
    print(f"  总调用次数      :  {len(calls)}")
    print()

    if calls:
        print("  最近 5 次调用：")
        for c in calls[-5:][::-1]:
            saved_pct = round(c['saved'] / c['raw'] * 100) if c['raw'] > 0 else 0
            print(f"    {c['time']}  git {c['cmd']:<10}"
                  f"  {c['raw']:>5} → {c['filtered']:>4} tokens  (-{saved_pct}%)")
    print("=" * 45)


def reset():
    """清空统计数据"""
    _save({"total_raw": 0, "total_filtered": 0, "calls": []})
    print("统计数据已清空。")
