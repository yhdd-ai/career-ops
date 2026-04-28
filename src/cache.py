"""
三级评估结果缓存模块

缓存层级（按优先级从高到低）：
  Level 1 — URL 精确匹配      有效 HTTP URL → 规范化后做 key
  Level 2 — JD MD5 精确匹配  手动粘贴场景 → JD 文本 MD5 做 key
  Level 3 — 语义相似度匹配    前两级未命中 → embedding cosine similarity

Level 1/2 存储：data/eval_cache.json（精确 key → 条目）
Level 3 存储：  data/semantic_cache.json（embedding 向量 + 结果）

Level 3 依赖 sentence-transformers；未安装时自动跳过，不影响前两级。
相似度阈值：0.92（在 semantic_cache.py 中定义，可调整）。
"""
import json
import hashlib
from pathlib import Path
from datetime import datetime

BASE_DIR   = Path(__file__).parent.parent
CACHE_FILE = BASE_DIR / "data" / "eval_cache.json"


# ── 存储 I/O ──────────────────────────────────────────────────────────────────

def _load() -> dict:
    if not CACHE_FILE.exists():
        return {}
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save(data: dict) -> None:
    CACHE_FILE.parent.mkdir(exist_ok=True)
    CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                          encoding="utf-8")


# ── Key 生成 ──────────────────────────────────────────────────────────────────

def _make_key(url: str, jd_text: str) -> tuple[str, str]:
    """
    返回 (key, type)。
    有 URL 时以 URL 为 key（去掉尾部斜杠和 utm 参数）；
    无 URL 时以 JD 文本 MD5 为 key。
    """
    if url and url.startswith("http"):
        from urllib.parse import urlparse, urlencode, parse_qs
        parsed = urlparse(url)
        keep   = {k: v for k, v in parse_qs(parsed.query).items()
                  if k not in ("utm_source", "utm_medium", "utm_campaign", "ref")}
        clean  = parsed._replace(query=urlencode(keep, doseq=True)).geturl().rstrip("/")
        return clean, "url"
    else:
        digest = hashlib.md5(jd_text.strip().encode("utf-8")).hexdigest()
        return digest, "jd_hash"


# ── 公开 API ──────────────────────────────────────────────────────────────────

def get(url: str, jd_text: str) -> dict | None:
    """
    三级缓存查找。命中则更新 hit_count 并返回 result dict，未命中返回 None。

    Level 1/2：精确匹配（零耗时）
    Level 3  ：语义相似度匹配（需 sentence-transformers；未安装则跳过）
    """
    # ── Level 1 & 2：精确 key 匹配 ────────────────────────────────────────────
    key, _ = _make_key(url, jd_text)
    data   = _load()
    entry  = data.get(key)
    if entry:
        entry["hit_count"] = entry.get("hit_count", 0) + 1
        entry["last_hit"]  = datetime.now().strftime("%Y-%m-%d %H:%M")
        data[key] = entry
        _save(data)
        return entry["result"]

    # ── Level 3：语义相似度匹配 ────────────────────────────────────────────────
    try:
        from src import semantic_cache
        hit = semantic_cache.get(jd_text)
        if hit is not None:
            result, similarity = hit
            print(f"  ✦ 语义缓存命中（cosine={similarity:.3f}，相似 JD 已评估）")
            return result
    except Exception:
        pass  # 任何异常都不能阻断主流程

    return None


def put(url: str, jd_text: str, result: dict) -> None:
    """
    写入精确缓存（Level 1/2）并同步写入语义缓存（Level 3）。
    语义写入失败时静默跳过，不影响精确缓存。
    """
    # ── Level 1 & 2：写精确缓存 ───────────────────────────────────────────────
    key, key_type = _make_key(url, jd_text)
    data          = _load()
    data[key]     = {
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

    # ── Level 3：写语义缓存 ────────────────────────────────────────────────────
    try:
        from src import semantic_cache
        semantic_cache.put(jd_text, result)
    except Exception:
        pass  # 语义写入失败不影响主流程


def stats() -> dict:
    """返回精确缓存统计信息（语义缓存统计由 semantic_cache.stats() 提供）"""
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
    """清空精确缓存，返回删除条目数"""
    data  = _load()
    count = len(data)
    _save({})
    return count


def remove(url: str, jd_text: str = "") -> bool:
    """删除单条精确缓存，返回是否删除成功"""
    key, _ = _make_key(url, jd_text)
    data   = _load()
    if key in data:
        del data[key]
        _save(data)
        return True
    return False
