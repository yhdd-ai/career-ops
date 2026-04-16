"""
LLM 统一客户端接口
支持 Claude API 和 Ollama 本地模型，通过工厂函数按配置自动选择。

使用方式：
    from src.llm_client import get_client
    client = get_client()          # 自动读取 config/api.yml
    client = get_client("ollama")  # 强制使用 Ollama
    response = client.chat(prompt)
"""
import os
import yaml
from abc import ABC, abstractmethod
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent


# ── 抽象基类 ────────────────────────────────────────────────────────────────

class LLMClient(ABC):
    """所有 LLM 客户端的统一接口"""

    @abstractmethod
    def chat(self, prompt: str, max_tokens: int = 4096) -> str:
        """发送 prompt，返回模型回复文本"""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """当前使用的模型名称"""
        ...


# ── Claude API 实现 ─────────────────────────────────────────────────────────

class ClaudeClient(LLMClient):
    """Anthropic Claude API 客户端"""

    def __init__(self, api_key: str, model: str = "claude-opus-4-6"):
        try:
            import anthropic
        except ImportError:
            raise ImportError("请先安装：pip install anthropic")
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def chat(self, prompt: str, max_tokens: int = 4096) -> str:
        print(f"  🤖 Claude API ({self._model})...")
        response = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text

    @property
    def model_name(self) -> str:
        return self._model


# ── Ollama 实现 ─────────────────────────────────────────────────────────────

class OllamaClient(LLMClient):
    """Ollama 本地模型客户端"""

    def __init__(self, base_url: str = "http://127.0.0.1:11434",
                 model: str = "qwen2.5:latest", timeout: int = 300):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    def chat(self, prompt: str, max_tokens: int = 4096) -> str:
        import requests
        print(f"  🦙 Ollama ({self._model})...")
        resp = requests.post(
            f"{self._base_url}/api/chat",
            json={
                "model": self._model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"num_predict": max_tokens}
            },
            timeout=self._timeout
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]

    def list_models(self) -> list[str]:
        import requests
        try:
            resp = requests.get(f"{self._base_url}/api/tags", timeout=10)
            resp.raise_for_status()
            return [m["name"] for m in resp.json().get("models", [])]
        except Exception:
            return []

    @property
    def model_name(self) -> str:
        return self._model


# ── 工厂函数 ────────────────────────────────────────────────────────────────

def get_client(backend: str = "auto") -> LLMClient:
    """
    根据 backend 参数返回对应的 LLM 客户端实例。

    backend:
        "auto"   - 读取 config/api.yml，有 api_key 则用 Claude，否则用 Ollama
        "claude" - 强制使用 Claude API（读 config/api.yml）
        "ollama" - 强制使用 Ollama（读 config/api_local.yml）
    """
    if backend in ("claude", "auto"):
        cfg = _load_yaml("config/api.yml")
        api_key = cfg.get("anthropic_api_key", "") or os.environ.get("ANTHROPIC_API_KEY", "")
        if api_key and not api_key.startswith("sk-ant-xxx"):
            try:
                return ClaudeClient(
                    api_key=api_key,
                    model=cfg.get("model", "claude-opus-4-6")
                )
            except ImportError:
                if backend == "claude":
                    raise ImportError("请先安装：pip install anthropic")
                # auto 模式：anthropic 未安装时自动降级到 Ollama
                print("  ⚠ anthropic 未安装，自动降级到 Ollama 本地模型")
        elif backend == "claude":
            raise ValueError("请在 config/api.yml 中填入有效的 anthropic_api_key")

    # fallback 到 Ollama
    cfg = _load_yaml("config/api_local.yml")
    return OllamaClient(
        base_url=cfg.get("ollama_base_url", "http://127.0.0.1:11434"),
        model=cfg.get("model", "qwen2.5:latest"),
        timeout=cfg.get("timeout", 300)
    )


def _load_yaml(relative_path: str) -> dict:
    path = BASE_DIR / relative_path
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
