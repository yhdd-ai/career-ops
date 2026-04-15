"""
Ollama 本地模型客户端
调用本地运行的 Ollama API，无需任何额外 Python 包（只用 requests）
"""
import yaml
import requests
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent


def load_local_config() -> dict:
    path = BASE_DIR / "config" / "api_local.yml"
    if not path.exists():
        raise FileNotFoundError("找不到 config/api_local.yml")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def chat(prompt: str, cfg: dict = None) -> str:
    if cfg is None:
        cfg = load_local_config()

    base_url = cfg.get("ollama_base_url", "http://127.0.0.1:11434").rstrip("/")
    model    = cfg.get("model", "qwen2.5:latest")
    timeout  = cfg.get("timeout", 120)

    resp = requests.post(
        f"{base_url}/api/chat",
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False
        },
        timeout=timeout
    )
    resp.raise_for_status()

    data = resp.json()
    return data["message"]["content"]


def list_models(base_url: str = "http://127.0.0.1:11434") -> list:
    """列出本地已安装的模型"""
    try:
        resp = requests.get(f"{base_url}/api/tags", timeout=5)
        return [m["name"] for m in resp.json().get("models", [])]
    except Exception:
        return []
