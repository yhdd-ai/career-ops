"""
公共工具函数

统一管理文件加载逻辑，避免各模块重复定义 _load_cv / load_mode / load_profile。
所有需要读取 cv.md / modes/*.md / config/profile.yml 的模块都从这里导入。
"""
import yaml
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent


def load_cv() -> str:
    """读取 cv.md，不存在则抛出友好错误"""
    cv_path = BASE_DIR / "cv.md"
    if not cv_path.exists():
        raise FileNotFoundError("找不到 cv.md，请先导入简历：python3 run.py import-cv <file>")
    return cv_path.read_text(encoding="utf-8")


def load_mode(name: str) -> str:
    """
    读取 modes/<name>.md 提示词模板。
    name 可带或不带 .md 后缀，如 'evaluate' 或 'evaluate.md' 均可。
    """
    stem = name.removesuffix(".md")
    mode_path = BASE_DIR / "modes" / f"{stem}.md"
    if not mode_path.exists():
        raise FileNotFoundError(f"找不到 modes/{stem}.md")
    return mode_path.read_text(encoding="utf-8")


def load_profile() -> dict:
    """读取 config/profile.yml"""
    profile_path = BASE_DIR / "config" / "profile.yml"
    if not profile_path.exists():
        raise FileNotFoundError("找不到 config/profile.yml")
    with open(profile_path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
