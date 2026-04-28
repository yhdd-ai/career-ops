"""
简历导入模块
支持 PDF / TXT / MD 格式，提取文本后写入 cv.md
"""
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent


def import_from_pdf(file_path: str) -> str:
    """从 PDF 提取文本"""
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ImportError("请先安装：pip install pypdf")

    reader = PdfReader(file_path)
    return "\n".join(page.extract_text() or "" for page in reader.pages).strip()


def import_from_txt(file_path: str) -> str:
    return Path(file_path).read_text(encoding="utf-8").strip()


def import_cv(file_path: str, overwrite: bool = False) -> Path:
    """
    导入简历文件，写入 cv.md
    支持 .pdf / .txt / .md
    """
    src = Path(file_path)
    if not src.exists():
        raise FileNotFoundError(f"找不到文件：{file_path}")

    suffix = src.suffix.lower()
    if suffix == ".pdf":
        text = import_from_pdf(file_path)
    elif suffix in (".txt", ".md"):
        text = import_from_txt(file_path)
    else:
        raise ValueError(f"不支持的格式：{suffix}（支持 .pdf / .txt / .md）")

    if not text.strip():
        raise ValueError("提取的文本为空，请检查文件内容")

    cv_path = BASE_DIR / "cv.md"

    # 备份旧 cv.md
    if cv_path.exists() and not overwrite:
        backup = BASE_DIR / "cv.md.bak"
        backup.write_text(cv_path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  已备份旧简历到 cv.md.bak")

    cv_path.write_text(text, encoding="utf-8")
    return cv_path
