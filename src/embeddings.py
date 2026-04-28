"""
Embedding 客户端抽象层

为语义缓存提供向量化能力，屏蔽不同 embedding 模型的差异。
采用与 LLMClient 相同的 ABC + 工厂函数模式，保持代码风格一致。

支持的后端：
  SentenceTransformerClient — 本地离线，支持中英双语，推荐首选
    模型：paraphrase-multilingual-MiniLM-L12-v2（384维，约500MB，一次性下载）

安装：
  pip install sentence-transformers

不可用时：
  get_embedding_client() 返回 None，语义缓存自动退化为精确匹配，
  不影响系统其他功能，无异常抛出。
"""

from __future__ import annotations
from abc import ABC, abstractmethod


# ── 抽象基类 ──────────────────────────────────────────────────────────────────

class EmbeddingClient(ABC):
    """所有 Embedding 客户端的统一接口"""

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """
        将文本编码为归一化的 embedding 向量。
        返回值已 L2 归一化，cosine similarity 可直接用点积计算。
        """
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """当前使用的模型标识"""
        ...

    @property
    @abstractmethod
    def dim(self) -> int:
        """向量维度"""
        ...


# ── SentenceTransformer 实现 ──────────────────────────────────────────────────

class SentenceTransformerClient(EmbeddingClient):
    """
    基于 sentence-transformers 的本地 embedding 客户端。

    使用 paraphrase-multilingual-MiniLM-L12-v2：
      - 维度：384
      - 语言：50+ 语言，含简体/繁体中文
      - 首次使用自动下载模型权重（~500MB）
      - 适合 JD 文本语义匹配（句子级别相似度）
    """

    DEFAULT_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

    def __init__(self, model: str = DEFAULT_MODEL):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise ImportError(
                "请先安装：pip install sentence-transformers\n"
                "语义缓存需要此依赖；不安装时系统自动降级到精确匹配。"
            )
        self._model_name = model
        self._model = SentenceTransformer(model)
        self._dim = self._model.get_sentence_embedding_dimension()

    def embed(self, text: str) -> list[float]:
        """
        编码文本，返回 L2 归一化向量。
        normalize_embeddings=True 使后续 cosine similarity = 点积，计算更快。
        """
        vec = self._model.encode(text, normalize_embeddings=True)
        return vec.tolist()

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dim(self) -> int:
        return self._dim


# ── 工厂函数 ──────────────────────────────────────────────────────────────────

# 模块级单例，避免每次都重新加载模型权重（约 1-2s 的冷启动开销）
_cached_client: EmbeddingClient | None = None
_init_attempted: bool = False


def get_embedding_client() -> EmbeddingClient | None:
    """
    获取 Embedding 客户端单例。

    sentence-transformers 未安装或模型加载失败时返回 None，
    调用方应将 None 视为"语义缓存不可用"并降级到精确匹配，
    不应抛出异常影响主流程。
    """
    global _cached_client, _init_attempted
    if _init_attempted:
        return _cached_client

    _init_attempted = True
    try:
        _cached_client = SentenceTransformerClient()
    except ImportError:
        # sentence-transformers 未安装，静默降级
        _cached_client = None
    except Exception:
        # 模型下载失败、磁盘空间不足等，静默降级
        _cached_client = None

    return _cached_client


def is_available() -> bool:
    """快速检查语义缓存能力是否可用"""
    return get_embedding_client() is not None
