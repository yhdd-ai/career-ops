"""
CV 定向裁剪引擎
根据 JD 自动生成针对特定职位的简历裁剪版本。
"""
import re
from pathlib import Path
from datetime import datetime
from src.utils import load_cv, load_mode

BASE_DIR = Path(__file__).parent.parent


def build_tailor_prompt(jd_text: str, company: str = "", title: str = "") -> str:
    """构建 CV 裁剪提示词"""
    cv   = load_cv()
    mode = load_mode("tailor_cv")

    target_info = ""
    if company or title:
        target_info = f"\n目标公司：{company}\n目标岗位：{title}\n"

    prompt = f"""你是一位专业的求职顾问。请根据以下候选人简历和目标职位 JD，生成一份定向裁剪版简历。

═══════════════════════════════════════════
裁剪规则
═══════════════════════════════════════════
{mode}

═══════════════════════════════════════════
候选人原始简历
═══════════════════════════════════════════
{cv}

═══════════════════════════════════════════
目标职位信息
═══════════════════════════════════════════{target_info}
{jd_text}

请按照裁剪规则，输出定向裁剪后的简历（Markdown 格式），结尾附上裁剪说明。
"""
    return prompt


def tailor_cv(jd_text: str, company: str = "", title: str = "",
              backend: str = "auto") -> str:
    """通过统一 LLM 接口生成裁剪版简历"""
    from src.llm_client import get_client
    client = get_client(backend)
    return client.chat(build_tailor_prompt(jd_text, company, title))


def save_tailored_cv(tailored_text: str, company: str, title: str) -> Path:
    """将裁剪版简历保存为 Markdown 文件"""
    out_dir = BASE_DIR / "reports" / "tailored_cvs"
    out_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_company = (company or "未知公司").replace("/", "-").replace(" ", "_")
    safe_title   = (title   or "未知岗位").replace("/", "-").replace(" ", "_")
    filename = f"{timestamp}_{safe_company}_{safe_title}_tailored.md"
    filepath = out_dir / filename

    # 提取裁剪说明（最后一行 **裁剪说明**:...）
    note_match = re.search(r'\*\*裁剪说明\*\*[：:](.*?)$', tailored_text, re.MULTILINE)
    note = note_match.group(1).strip() if note_match else ""

    header = f"# 定向简历 · {company} · {title}\n\n"
    header += f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}"
    if note:
        header += f"  |  裁剪策略：{note}"
    header += "\n\n---\n\n"

    # 去掉裁剪说明行，只保留简历主体
    body = re.sub(r'\n\*\*裁剪说明\*\*[：:].*$', '', tailored_text, flags=re.MULTILINE).strip()

    filepath.write_text(header + body + "\n", encoding="utf-8")
    return filepath
