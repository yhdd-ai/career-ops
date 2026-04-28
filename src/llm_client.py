"""
LLM 统一客户端接口
支持 Claude API 和 Ollama 本地模型，通过工厂函数按配置自动选择。

接口方法：
  chat(prompt)                                 — 自由文本输出（通用场景）
  chat_structured(prompt, tool_name, schema)   — JSON Schema 约束输出（评估/分类）

可靠性保障（指数退避重试）：
  两个方法均内置 with_retry()，默认最多重试 3 次（1s→2s→4s + ±20% jitter）。
  可重试：限流（429）、服务端错误（5xx）、超时、连接失败
  不可重试：认证失败（401/403）、参数错误（400/422）— 重试无意义，快速失败

使用方式：
    from src.llm_client import get_client
    client = get_client()          # 自动读取 config/api.yml
    client = get_client("ollama")  # 强制使用 Ollama
    response = client.chat(prompt)
    result   = client.chat_structured(prompt, "submit_evaluation", EVALUATION_SCHEMA)
"""
import json
import os
import yaml
from abc import ABC, abstractmethod
from pathlib import Path
from src.retry import with_retry, DEFAULT_RETRY, LIGHT_RETRY, RetryConfig

BASE_DIR = Path(__file__).parent.parent


# ── 抽象基类 ────────────────────────────────────────────────────────────────

class LLMClient(ABC):
    """所有 LLM 客户端的统一接口"""

    @abstractmethod
    def chat(self, prompt: str, max_tokens: int = 4096) -> str:
        """发送 prompt，返回模型回复文本（带指数退避重试）"""
        ...

    @abstractmethod
    def chat_structured(self, prompt: str, tool_name: str,
                        schema: dict, max_tokens: int = 4096) -> dict:
        """
        强制 LLM 按 JSON Schema 返回结构体（带指数退避重试）。
        Claude：tool_use + tool_choice；Ollama：format=json + schema hint。
        """
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """当前使用的模型名称"""
        ...


# ── Claude API 实现 ─────────────────────────────────────────────────────────

class ClaudeClient(LLMClient):
    """
    Anthropic Claude API 客户端。

    重试策略：
      可重试  — RateLimitError（429）、APIStatusError 5xx、APITimeoutError、APIConnectionError
      不可重试 — AuthenticationError（401）、PermissionDeniedError（403）、
                 BadRequestError（400）、UnprocessableEntityError（422）
    """

    def __init__(self, api_key: str, model: str = "claude-opus-4-6",
                 retry_config: RetryConfig = DEFAULT_RETRY):
        try:
            import anthropic
            self._anthropic = anthropic
        except ImportError:
            raise ImportError("请先安装：pip install anthropic")
        self._client       = anthropic.Anthropic(api_key=api_key)
        self._model        = model
        self._retry_config = retry_config

    def _retryable_exceptions(self) -> tuple:
        """构建可重试异常元组（延迟导入，避免 anthropic 未安装时报错）"""
        a = self._anthropic
        return (
            a.RateLimitError,
            a.APITimeoutError,
            a.APIConnectionError,
            a.InternalServerError,
        )

    # ── 自由文本 ──────────────────────────────────────────────────────────────

    def chat(self, prompt: str, max_tokens: int = 4096) -> str:
        print(f"  🤖 Claude API ({self._model})...")

        def _call():
            response = self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text

        return with_retry(
            _call,
            config=self._retry_config,
            retryable_exceptions=self._retryable_exceptions(),
            label=f"Claude.chat/{self._model}",
        )

    # ── 结构化输出（tool_use 强制调用）────────────────────────────────────────

    def chat_structured(self, prompt: str, tool_name: str,
                        schema: dict, max_tokens: int = 4096) -> dict:
        """
        使用 Claude tool_use 强制返回 JSON Schema 约束结构体。
        tool_choice={"type":"tool"} 确保模型必须调用工具，直接读取 block.input dict。
        """
        print(f"  🤖 Claude API ({self._model}) [structured]...")

        def _call():
            response = self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                tools=[{
                    "name":        tool_name,
                    "description": schema.get("description", f"Submit {tool_name} result"),
                    "input_schema": schema,
                }],
                tool_choice={"type": "tool", "name": tool_name},
                messages=[{"role": "user", "content": prompt}]
            )
            for block in response.content:
                if getattr(block, "type", None) == "tool_use" and block.name == tool_name:
                    return block.input
            raise ValueError(
                f"Claude 未返回 tool_use 块（tool={tool_name}）。"
                f"content types: {[getattr(b, 'type', '?') for b in response.content]}"
            )

        return with_retry(
            _call,
            config=self._retry_config,
            retryable_exceptions=self._retryable_exceptions(),
            label=f"Claude.structured/{tool_name}",
        )

    @property
    def model_name(self) -> str:
        return self._model


# ── Ollama 实现 ─────────────────────────────────────────────────────────────

class OllamaClient(LLMClient):
    """
    Ollama 本地模型客户端。

    重试策略：
      可重试  — ConnectionError（服务未启动/重启中）、Timeout、HTTPError 5xx
      不可重试 — HTTPError 4xx（模型不存在等参数问题）
    """

    def __init__(self, base_url: str = "http://127.0.0.1:11434",
                 model: str = "qwen2.5:latest", timeout: int = 300,
                 retry_config: RetryConfig = DEFAULT_RETRY):
        self._base_url     = base_url.rstrip("/")
        self._model        = model
        self._timeout      = timeout
        self._retry_config = retry_config

    def _retryable_exceptions(self) -> tuple:
        import requests
        return (
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
            requests.exceptions.ChunkedEncodingError,
        )

    # ── 自由文本 ──────────────────────────────────────────────────────────────

    def chat(self, prompt: str, max_tokens: int = 4096) -> str:
        import requests
        print(f"  🦙 Ollama ({self._model})...")

        def _call():
            resp = requests.post(
                f"{self._base_url}/api/chat",
                json={
                    "model":    self._model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream":   False,
                    "options":  {"num_predict": max_tokens},
                },
                timeout=self._timeout
            )
            resp.raise_for_status()
            return resp.json()["message"]["content"]

        return with_retry(
            _call,
            config=self._retry_config,
            retryable_exceptions=self._retryable_exceptions(),
            label=f"Ollama.chat/{self._model}",
        )

    # ── 结构化输出（format=json + schema hint）───────────────────────────────

    def chat_structured(self, prompt: str, tool_name: str,
                        schema: dict, max_tokens: int = 4096) -> dict:
        """
        Ollama 不支持 tool_use，用 format=json + schema hint 联合约束：
          1. format=json  — 保证输出可被 json.loads 解析
          2. Schema hint  — prompt 末尾注入字段描述，引导结构
        """
        import requests
        print(f"  🦙 Ollama ({self._model}) [structured]...")

        required_fields = schema.get("required", [])
        props_hint = {
            k: v.get("description", k)
            for k, v in schema.get("properties", {}).items()
            if k in required_fields
        }
        schema_hint = json.dumps(props_hint, ensure_ascii=False, indent=2)
        structured_prompt = (
            f"{prompt}\n\n"
            f"请严格按照以下 JSON 字段结构输出，不要包含任何额外文字或代码块：\n"
            f"{schema_hint}"
        )

        def _call():
            resp = requests.post(
                f"{self._base_url}/api/chat",
                json={
                    "model":    self._model,
                    "messages": [{"role": "user", "content": structured_prompt}],
                    "stream":   False,
                    "format":   "json",
                    "options":  {"num_predict": max_tokens},
                },
                timeout=self._timeout
            )
            resp.raise_for_status()
            content = resp.json()["message"]["content"]
            return json.loads(content)

        return with_retry(
            _call,
            config=self._retry_config,
            retryable_exceptions=self._retryable_exceptions(),
            label=f"Ollama.structured/{tool_name}",
        )

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

def get_client(backend: str = "auto",
               retry_config: RetryConfig = DEFAULT_RETRY) -> LLMClient:
    """
    根据 backend 参数返回对应的 LLM 客户端实例。

    backend:
        "auto"   - 读取 config/api.yml，有 api_key 则用 Claude，否则用 Ollama
        "claude" - 强制使用 Claude API（读 config/api.yml）
        "ollama" - 强制使用 Ollama（读 config/api_local.yml）

    retry_config:
        自定义重试策略；默认 DEFAULT_RETRY（3 次，1s→16s 退避）
    """
    if backend in ("claude", "auto"):
        cfg     = _load_yaml("config/api.yml")
        api_key = cfg.get("anthropic_api_key", "") or os.environ.get("ANTHROPIC_API_KEY", "")
        # 过滤掉所有 placeholder / 示例 key，防止用假 key 创建 Client 触发 401
        _PLACEHOLDERS = ("sk-ant-xxx", "YOUR_KEY", "sk-ant-YOUR", "your_key", "PLACEHOLDER")
        is_placeholder = not api_key or any(p in api_key for p in _PLACEHOLDERS)
        if not is_placeholder:
            try:
                return ClaudeClient(
                    api_key=api_key,
                    model=cfg.get("model", "claude-opus-4-6"),
                    retry_config=retry_config,
                )
            except ImportError:
                if backend == "claude":
                    raise ImportError("请先安装：pip install anthropic")
                print("  ⚠ anthropic 未安装，自动降级到 Ollama 本地模型")
        elif backend == "claude":
            raise ValueError(
                "请先配置 API Key：\n"
                "  cp config/api.yml.example config/api.yml\n"
                "  然后将 api.yml 中的 anthropic_api_key 替换为真实 Key"
            )

    cfg = _load_yaml("config/api_local.yml")
    return OllamaClient(
        base_url=cfg.get("ollama_base_url", "http://127.0.0.1:11434"),
        model=cfg.get("model", "qwen2.5:latest"),
        timeout=cfg.get("timeout", 300),
        retry_config=retry_config,
    )


def _load_yaml(relative_path: str) -> dict:
    path = BASE_DIR / relative_path
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
