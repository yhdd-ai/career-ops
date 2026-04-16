"""
评估结果缓存模块

缓存策略：
- Key：URL（精确匹配）或 JD 文本的 MD5 hash（手动输入场景）
- 存储：data/eval_cache.json
- 命中：相同 URL/JD 直接返回历史评估，跳过 LLM 调用
- 失效：--no-cache 强制重新评估；cache clear 手动清空

缓存条目结构：
{
  "key": "https://...",
  "type": "url" | "jd_hash",
  "cached_at": "2026-04-16 10:00",
  "hit_count": 3,
  "result": { ...完整评估结果... }
}
"""
import json
import hashlib
from pathlib import Path
from datetime import datetime

BASE_DIR   = Path(__file__).parent.parent
CACHE_FILE = BASE_DIR / "data" / "eval_cache.json"


# ── 读写底层 ─────────────────────────────────────────────────────
def _load() -> dict:
    if not CACHE_FILE.exists():
        return {}
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save(data: dict) -> None:
    CACHE_FILE.parent.mkdir(exist_ok=True)
    CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ── Key 生成 ─────────────────────────────────────────────────────
def _make_key(url: str, jd_text: str) -> tuple[str, str]:
    """
    返回 (key, type)。
    有 URL 时以 URL 为 key（去掉尾部斜杠和 utm 参数）；
    无 URL 时以 JD 文本 MD5 为 key。
    """
    if url and url.startswith("http"):
        # 去掉常见追踪参数
        from urllib.parse import urlparse, urlencode, parse_qs
        parsed = urlparse(url)
        keep = {k: v for k, v in parse_qs(parsed.query).items()
                if k not in ("utm_source", "utm_medium", "utm_campaign", "ref")}
        clean = parsed._replace(query=urlencode(keep, doseq=True)).geturl().rstrip("/")
        return clean, "url"
    else:
        digest = hashlib.md5(jd_text.strip().encode("utf-8")).hexdigest()
        return digest, "jd_hash"


# ── 公开 API ─────────────────────────────────────────────────────
def get(url: str, jd_text: str) -> dict | None:
    """
    查找缓存。命中则更新 hit_count 并返回 result，否则返回 None。
    """
    key, _ = _make_key(url, jd_text)
    data   = _load()
    entry  = data.get(key)
    if not entry:
        return None

    # 更新命中计数
    entry["hit_count"] = entry.get("hit_count", 0) + 1
    entry["last_hit"]  = datetime.now().strftime("%Y-%m-%d %H:%M")
    data[key] = entry
    _save(data)
    return entry["result"]


def put(url: str, jd_text: str, result: dict) -> None:
    """将评估结果写入缓存"""
    key, key_type = _make_key(url, jd_text)
    data = _load()
    data[key] = {
        "key":       key,
        "type":      key_type,
        "cached_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "hit_count": 0,
        "company":   result.get("company", ""),
        "title":     result.get("title", ""),
        "score":     result.get("score", 0),
        "grade":     result.get("grade", "?"),
        "result":    result,
    }
    _save(data)


def stats() -> dict:
    """返回缓存统计信息"""
    data       = _load()
    total_hits = sum(e.get("hit_count", 0) for e in data.values())
    return {
        "entries":    len(data),
        "total_hits": total_hits,
        "items": [
            {
                "key":       e.get("key", k)[:60],
                "type":      e.get("type", ""),
                "company":   e.get("company", ""),
                "title":     e.get("title", ""),
                "grade":     e.get("grade", "?"),
                "score":     e.get("score", 0),
                "cached_at": e.get("cached_at", ""),
                "hit_count": e.get("hit_count", 0),
            }
            for k, e in data.items()
        ],
    }


def clear() -> int:
    """清空全部缓存，返回删除条目数"""
    data  = _load()
    count = len(data)
    _save({})
    return count


def remove(url: str, jd_text: str = "") -> bool:
    """删除单条缓存，返回是否删除成功"""
    key, _ = _make_key(url, jd_text)
    data   = _load()
    if key in data:
        del data[key]
        _save(data)
        return True
    return False
