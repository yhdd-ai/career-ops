"""
语义相似度缓存模块

在精确 key（URL / MD5）命中失败后，用 JD 文本的 embedding 向量做
cosine similarity 近邻搜索：相似度 >= 阈值时复用历史评估结果，
避免对"措辞不同但内容相同"的 JD 重复调用 LLM。

典型场景：
  - 同公司同岗位换了推广链接（URL 不同，JD 文本高度重合）
  - 两家不同公司发布了几乎一致的通用实习 JD
  - 同一 JD 被候选人稍作修改后重新输入

存储：data/semantic_cache.json
结构：
  {
    "version": 1,
    "model": "paraphrase-multilingual-MiniLM-L12-v2",
    "entries": [
      {
        "id": "sem_0001",
        "jd_hash": "<MD5>",
        "jd_preview": "<前100字>",
        "embedding": [0.1, 0.2, ...],   // 384 floats，~3KB/条
        "company": "字节跳动",
        "title": "算法实习",
        "grade": "B",
        "score": 82,
        "result": {...完整评估结果...},
        "cached_at": "2026-04-17 10:00",
        "hit_count": 0,
        "last_similarity": 0.9456
      }
    ]
  }
"""

from __future__ import annotations

import json
import math
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional

BASE_DIR             = Path(__file__).parent.parent
SEMANTIC_CACHE_FILE  = BASE_DIR / "data" / "semantic_cache.json"

# cosine similarity 阈值：>= 此值认为语义等价
# 0.92 经验值：同岗位换链接约 0.97+，不同公司相似岗位约 0.85-0.92
SIMILARITY_THRESHOLD = 0.92

# 每次 embed 的 JD 截断长度（tokens 估算约 1500，足以覆盖核心内容）
JD_MAX_CHARS = 2000


# ── 相似度计算 ────────────────────────────────────────────────────────────────

def cosine_similarity(a: list[float], b: list[float]) -> float:
    """
    计算两个向量的 cosine similarity。
    若向量已 L2 归一化（SentenceTransformerClient 默认），等价于点积，更快。
    使用纯 Python 避免强依赖 numpy，兼容所有环境。
    """
    if len(a) != len(b):
        return 0.0
    dot    = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a < 1e-9 or norm_b < 1e-9:
        return 0.0
    return dot / (norm_a * norm_b)


# ── 存储 I/O ─────────────────────────────────────────────────────────────────

def _load() -> dict:
    if not SEMANTIC_CACHE_FILE.exists():
        return {"version": 1, "model": "", "entries": []}
    try:
        return json.loads(SEMANTIC_CACHE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"version": 1, "model": "", "entries": []}


def _save(data: dict) -> None:
    SEMANTIC_CACHE_FILE.parent.mkdir(exist_ok=True)
    # separators 去掉多余空格，embedding 数组紧凑存储
    SEMANTIC_CACHE_FILE.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8"
    )


# ── 公开 API ──────────────────────────────────────────────────────────────────

def get(jd_text: str) -> Optional[tuple[dict, float]]:
    """
    语义近邻查找。

    1. 对查询 JD 计算 embedding（截断至 JD_MAX_CHARS）
    2. 与缓存中所有向量计算 cosine similarity
    3. 取最高相似度；>= SIMILARITY_THRESHOLD 则命中

    Returns:
        (result_dict, similarity) 命中时
        None                      未命中或 embedding 不可用
    """
    from src.embeddings import get_embedding_client

    emb_client = get_embedding_client()
    if emb_client is None:
        return None

    data    = _load()
    entries = data.get("entries", [])
    if not entries:
        return None

    # Fix 6: 模型名称不匹配时跳过语义缓存，避免不同 embedding 模型之间互相误命中
    if data.get("model") and data["model"] != emb_client.model_name:
        return None

    query_vec = emb_client.embed(jd_text[:JD_MAX_CHARS])

    best_sim   = 0.0
    best_idx   = -1
    for i, entry in enumerate(entries):
        stored_vec = entry.get("embedding")
        if not stored_vec:
            continue
        sim = cosine_similarity(query_vec, stored_vec)
        if sim > best_sim:
            best_sim = sim
            best_idx = i

    if best_sim >= SIMILARITY_THRESHOLD and best_idx >= 0:
        entry = entries[best_idx]
        entry["hit_count"]       = entry.get("hit_count", 0) + 1
        entry["last_hit"]        = datetime.now().strftime("%Y-%m-%d %H:%M")
        entry["last_similarity"] = round(best_sim, 4)
        data["entries"][best_idx] = entry
        _save(data)
        return entry["result"], round(best_sim, 4)

    return None


def put(jd_text: str, result: dict) -> bool:
    """
    将 JD 的 embedding 和评估结果存入语义缓存。

    - 相同 jd_hash 的条目不重复写入
    - embedding 不可用时静默跳过，返回 False
    - 返回 True 表示成功写入

    Note：embedding 计算在后台进行，首次调用会触发模型加载（约 1-2s）。
    """
    from src.embeddings import get_embedding_client

    emb_client = get_embedding_client()
    if emb_client is None:
        return False

    jd_hash = hashlib.md5(jd_text.strip().encode("utf-8")).hexdigest()
    data    = _load()
    entries = data.get("entries", [])

    # 防重：相同 hash 已存在则跳过
    for entry in entries:
        if entry.get("jd_hash") == jd_hash:
            return False

    embedding = emb_client.embed(jd_text[:JD_MAX_CHARS])

    new_entry = {
        "id":          f"sem_{len(entries) + 1:04d}",
        "jd_hash":     jd_hash,
        "jd_preview":  jd_text[:120].replace("\n", " "),
        "embedding":   embedding,
        "company":     result.get("company", ""),
        "title":       result.get("title", ""),
        "grade":       result.get("grade", "?"),
        "score":       result.get("score", 0),
        "result":      result,
        "cached_at":   datetime.now().strftime("%Y-%m-%d %H:%M"),
        "hit_count":   0,
        "last_similarity": None,
    }
    entries.append(new_entry)
    data["entries"] = entries
    data["model"]   = emb_client.model_name
    _save(data)
    return True


# ── 统计 & 管理 ───────────────────────────────────────────────────────────────

def stats() -> dict:
    """返回语义缓存统计（含可用性信息）"""
    from src.embeddings import is_available

    enabled = is_available()
    data    = _load()
    entries = data.get("entries", [])

    return {
        "enabled":    enabled,
        "model":      data.get("model", "未知"),
        "threshold":  SIMILARITY_THRESHOLD,
        "entries":    len(entries),
        "total_hits": sum(e.get("hit_count", 0) for e in entries),
        "items": [
            {
                "id":         e.get("id", ""),
                "company":    e.get("company", ""),
                "title":      e.get("title", ""),
                "grade":      e.get("grade", "?"),
                "score":      e.get("score", 0),
                "cached_at":  e.get("cached_at", ""),
                "hit_count":  e.get("hit_count", 0),
                "last_sim":   e.get("last_similarity"),
            }
            for e in entries
        ],
    }


def clear() -> int:
    """清空语义缓存，返回删除条目数"""
    data  = _load()
    count = len(data.get("entries", []))
    _save({"version": 1, "model": "", "entries": []})
    return count


def find_similar(jd_text: str, top_k: int = 3) -> list[dict]:
    """
    调试 / 分析用：返回最相似的 top_k 条缓存记录（含相似度）。
    不更新 hit_count。
    """
    from src.embeddings import get_embedding_client

    emb_client = get_embedding_client()
    if emb_client is None:
        return []

    data    = _load()
    entries = data.get("entries", [])
    if not entries:
        return []

    query_vec = emb_client.embed(jd_text[:JD_MAX_CHARS])
    scored = []
    for entry in entries:
        stored_vec = entry.get("embedding")
        if not stored_vec:
            continue
        sim = cosine_similarity(query_vec, stored_vec)
        scored.append({
            "id":        entry.get("id"),
            "company":   entry.get("company"),
            "title":     entry.get("title"),
            "grade":     entry.get("grade"),
            "score":     entry.get("score"),
            "similarity": round(sim, 4),
            "preview":   entry.get("jd_preview", "")[:60],
        })

    scored.sort(key=lambda x: x["similarity"], reverse=True)
    return scored[:top_k]
