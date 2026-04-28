"""
PDF 评估报告生成器
使用 reportlab 生成中文 PDF 报告
"""
from pathlib import Path
from datetime import datetime

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                     Table, TableStyle, HRFlowable)
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    REPORTLAB_OK = True
except ImportError:
    REPORTLAB_OK = False

BASE_DIR = Path(__file__).parent.parent

# 中文字体路径（优先级：macOS → Linux）
CHINESE_FONT_PATHS = [
    # macOS
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/Library/Fonts/Arial Unicode MS.ttf",
    "/System/Library/Fonts/Supplemental/Songti.ttc",
    # macOS Homebrew / 用户字体
    "/Users/Shared/fonts/NotoSansSC-Regular.ttf",
    # Linux
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
]


def _register_chinese_font() -> str:
    """注册中文字体，返回字体名称"""
    for font_path in CHINESE_FONT_PATHS:
        if Path(font_path).exists():
            try:
                pdfmetrics.registerFont(TTFont("ChineseFont", font_path))
                print(f"  ✓ PDF 字体：{Path(font_path).name}")
                return "ChineseFont"
            except Exception:
                continue
    print("  ⚠ 未找到中文字体，PDF 中文可能显示为方框")
    print("    macOS 解决：字体已内置，请检查路径是否正确")
    return "Helvetica"


def _grade_color(grade: str):
    """根据等级返回颜色"""
    return {
        "A": colors.HexColor("#27ae60"),
        "B": colors.HexColor("#2980b9"),
        "C": colors.HexColor("#f39c12"),
        "D": colors.HexColor("#e67e22"),
        "F": colors.HexColor("#e74c3c"),
    }.get(grade, colors.grey)


def _score_bar(score: int, max_width: float = 120) -> str:
    """生成文字版进度条"""
    filled = int(score / 100 * 10)
    return "█" * filled + "░" * (10 - filled)


def generate_pdf(job: dict, output_path: Path = None) -> Path:
    """
    生成职位评估 PDF 报告
    job: tracker.py 中的职位字典
    output_path: 输出路径，默认保存到 reports/
    """
    if not REPORTLAB_OK:
        raise ImportError("请先安装 reportlab: pip install reportlab")

    # 输出路径
    if output_path is None:
        reports_dir = BASE_DIR / "reports"
        reports_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = job["company"].replace("/", "-").replace(" ", "_")
        output_path = reports_dir / f"{timestamp}_{safe_name}_{job['grade']}{job['score']}.pdf"

    font_name = _register_chinese_font()

    # 创建文档
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )

    # 样式
    base_style = ParagraphStyle("Base", fontName=font_name, fontSize=10, leading=16)
    title_style = ParagraphStyle("Title", fontName=font_name, fontSize=20,
                                  leading=28, textColor=colors.HexColor("#1a1a2e"),
                                  spaceAfter=4)
    subtitle_style = ParagraphStyle("Subtitle", fontName=font_name, fontSize=12,
                                     textColor=colors.HexColor("#555555"), spaceAfter=2)
    section_style = ParagraphStyle("Section", fontName=font_name, fontSize=13,
                                    textColor=colors.HexColor("#2c3e50"),
                                    spaceBefore=12, spaceAfter=6,
                                    borderPad=4)
    body_style = ParagraphStyle("Body", fontName=font_name, fontSize=10,
                                  leading=18, textColor=colors.HexColor("#333333"))
    small_style = ParagraphStyle("Small", fontName=font_name, fontSize=9,
                                   textColor=colors.HexColor("#777777"))

    grade = job.get("grade", "?")
    score = job.get("score", 0)
    grade_col = _grade_color(grade)
    dims = job.get("dimensions", {})

    story = []

    # ── 标题区域 ──────────────────────────────────────────────
    story.append(Paragraph(f"{job['company']}  ·  {job['title']}", title_style))
    story.append(Paragraph(
        f"{job.get('location', '地点未知')}  ·  评估时间：{job.get('evaluated_at', '')}",
        subtitle_style
    ))
    story.append(HRFlowable(width="100%", thickness=2,
                             color=colors.HexColor("#1a1a2e"), spaceAfter=12))

    # ── 综合评分卡 ────────────────────────────────────────────
    score_data = [
        [
            Paragraph(f"<font size='36' color='#{grade_col.hexval()[2:]}'>{score}</font>",
                      ParagraphStyle("Score", fontName=font_name, alignment=TA_CENTER)),
            Paragraph(f"<font size='48' color='#{grade_col.hexval()[2:]}'>{grade}</font>",
                      ParagraphStyle("Grade", fontName=font_name, alignment=TA_CENTER)),
            Paragraph(
                f"<font size='11'><b>{job.get('recommendation', '')}</b></font>",
                ParagraphStyle("Rec", fontName=font_name, alignment=TA_CENTER,
                               leading=16)
            ),
        ]
    ]
    score_table = Table(score_data, colWidths=[50 * mm, 40 * mm, 80 * mm])
    score_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8f9fa")),
        ("ROUNDEDCORNERS", [5]),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#dee2e6")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LINEBEFORE", (1, 0), (1, -1), 1, colors.HexColor("#dee2e6")),
        ("LINEBEFORE", (2, 0), (2, -1), 1, colors.HexColor("#dee2e6")),
    ]))
    story.append(score_table)
    story.append(Spacer(1, 10 * mm))

    # ── 维度评分 ───────────────────────────────────────────────
    story.append(Paragraph("📊 维度评分", section_style))

    dim_labels = {
        "role_match": ("岗位匹配度", 25),
        "growth_potential": ("成长空间", 20),
        "company_quality": ("公司质量", 15),
        "location_fit": ("地点匹配", 10),
        "compensation": ("薪资水平", 10),
        "experience_match": ("经验要求匹配", 10),
        "workload_culture": ("工作强度与文化", 10),
    }

    dim_data = [["维度", "分数", "进度", "权重"]]
    for key, (label, weight) in dim_labels.items():
        dim_score = dims.get(key, 0)
        bar = _score_bar(dim_score)
        dim_data.append([
            Paragraph(label, base_style),
            Paragraph(f"<b>{dim_score}</b>", ParagraphStyle(
                "DimScore", fontName=font_name, alignment=TA_CENTER, fontSize=10)),
            Paragraph(f"<font size='8'>{bar}</font>",
                      ParagraphStyle("Bar", fontName=font_name, fontSize=8)),
            Paragraph(f"{weight}%",
                      ParagraphStyle("W", fontName=font_name,
                                     alignment=TA_CENTER, fontSize=9,
                                     textColor=colors.HexColor("#888888"))),
        ])

    dim_table = Table(dim_data, colWidths=[55 * mm, 20 * mm, 65 * mm, 20 * mm])
    dim_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), font_name),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ALIGN", (0, 1), (0, -1), "LEFT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.HexColor("#ffffff"), colors.HexColor("#f8f9fa")]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(dim_table)
    story.append(Spacer(1, 8 * mm))

    # ── 完整评估报告（Markdown → PDF）────────────────────────────
    full_report = job.get("full_report", "")
    if full_report:
        story.append(HRFlowable(width="100%", thickness=1,
                                color=colors.HexColor("#dee2e6"), spaceAfter=6))
        story.append(Paragraph("📝 评估详情", section_style))

        for line in full_report.split("\n"):
            raw = line.rstrip()

            # 空行
            if not raw:
                story.append(Spacer(1, 2 * mm))
                continue

            # 转义 XML 特殊字符
            safe = (raw.replace("&", "&amp;")
                       .replace("<", "&lt;")
                       .replace(">", "&gt;"))

            # Markdown 表格行（跳过，已在维度评分里展示）
            if safe.strip().startswith("|"):
                continue

            # 分割线
            if set(raw.strip()) <= set("─—=－-"):
                story.append(HRFlowable(width="100%", thickness=0.5,
                                        color=colors.HexColor("#dddddd"), spaceAfter=2))
                continue

            # 二级标题 ##
            if safe.startswith("## "):
                text = safe[3:].strip().lstrip("#").strip()
                story.append(Spacer(1, 3 * mm))
                story.append(Paragraph(text, section_style))
                continue

            # 一级标题 #
            if safe.startswith("# "):
                continue  # 已有顶部标题，跳过

            # 列表项 - / *
            if raw.lstrip().startswith(("- ", "* ", "• ")):
                text = safe.lstrip().lstrip("-*•").strip()
                story.append(Paragraph(
                    f"&nbsp;&nbsp;• {text}",
                    ParagraphStyle("Li", fontName=font_name, fontSize=10,
                                   leading=16, leftIndent=8,
                                   textColor=colors.HexColor("#333333"))
                ))
                continue

            # 加粗处理 **text**
            import re as _re
            safe = _re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", safe)

            story.append(Paragraph(safe, body_style))

    # ── 底部信息 ───────────────────────────────────────────────
    story.append(Spacer(1, 8 * mm))
    story.append(HRFlowable(width="100%", thickness=1,
                             color=colors.HexColor("#dee2e6"), spaceAfter=4))
    if job.get("url"):
        story.append(Paragraph(f"链接：{job['url']}", small_style))
    story.append(Paragraph(
        f"由 Career-Ops 生成  ·  {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        ParagraphStyle("Footer", fontName=font_name, fontSize=8,
                       textColor=colors.HexColor("#aaaaaa"), alignment=TA_RIGHT)
    ))

    doc.build(story)
    return output_path
