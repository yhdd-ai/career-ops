"""
职位 JD 爬取模块
支持主流中文招聘平台，使用 Playwright 处理动态渲染页面。

依赖安装（在你的电脑上运行）：
  pip install playwright beautifulsoup4 requests
  playwright install chromium
"""
import re
import time
from urllib.parse import urlparse
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class JobInfo:
    title: str = ""
    company: str = ""
    location: str = ""
    salary: str = ""
    jd_text: str = ""          # 完整 JD 文本（职责 + 要求）
    responsibilities: str = ""
    requirements: str = ""
    url: str = ""
    source: str = ""           # 来源平台


# ── 平台路由表 ────────────────────────────────────────────────────
PLATFORM_RULES = {
    "zhaopin.meituan.com":  "_parse_meituan",
    "jobs.bytedance.com":   "_parse_bytedance",
    "job.xiaohongshu.com":  "_parse_xiaohongshu",
    "campus.jd.com":        "_parse_jd",
    "campus.kuaishou.cn":   "_parse_kuaishou",
    "join.qq.com":          "_parse_tencent",
    "talent.baidu.com":     "_parse_baidu",
    "shixiseng.com":        "_parse_shixiseng",
    "nowcoder.com":         "_parse_nowcoder",
    "campus.alibaba.com":   "_parse_alibaba",
    "campus-talent.alibaba.com": "_parse_alibaba",
}


class JobScraper:
    def __init__(self, headless: bool = True, timeout: int = 20000):
        self.headless = headless
        self.timeout = timeout  # ms
        self._browser = None
        self._page = None

    def scrape(self, url: str) -> JobInfo:
        """主入口：传入 URL，返回解析好的 JobInfo"""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise ImportError(
                "请先安装 Playwright：\n"
                "  pip install playwright\n"
                "  playwright install chromium"
            )

        domain = urlparse(url).netloc.replace("www.", "")
        parser_name = self._get_parser(domain)

        with sync_playwright() as p:
            browser = p.webkit.launch(
                headless=self.headless,
            )
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 800},
            )
            page = context.new_page()

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=self.timeout)
                time.sleep(2)  # 等待动态内容加载

                parser = getattr(self, parser_name)
                info = parser(page, url)
                info.url = url
                info.source = domain
                info.jd_text = self._build_jd_text(info)
                return info
            finally:
                browser.close()

    def _get_parser(self, domain: str) -> str:
        for key, parser in PLATFORM_RULES.items():
            if key in domain:
                return parser
        return "_parse_generic"

    def _build_jd_text(self, info: JobInfo) -> str:
        """把职责和要求拼成完整 JD 文本"""
        parts = []
        if info.title:
            parts.append(f"职位名称：{info.title}")
        if info.company:
            parts.append(f"公司：{info.company}")
        if info.location:
            parts.append(f"地点：{info.location}")
        if info.salary:
            parts.append(f"薪资：{info.salary}")
        if info.responsibilities:
            parts.append(f"\n岗位职责\n{info.responsibilities}")
        if info.requirements:
            parts.append(f"\n任职要求\n{info.requirements}")
        return "\n".join(parts)

    def _safe_text(self, page, selector: str, default: str = "") -> str:
        """安全获取元素文本"""
        try:
            el = page.query_selector(selector)
            return el.inner_text().strip() if el else default
        except Exception:
            return default

    def _safe_texts(self, page, selector: str) -> str:
        """获取多个元素文本，换行拼接"""
        try:
            els = page.query_selector_all(selector)
            return "\n".join(e.inner_text().strip() for e in els if e.inner_text().strip())
        except Exception:
            return ""

    # ── 各平台解析器 ──────────────────────────────────────────────

    def _parse_meituan(self, page, url: str) -> JobInfo:
        # 等网络空闲，比等特定选择器更稳
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        time.sleep(2)

        # 尝试多个可能的选择器
        title = (
            self._safe_text(page, "h1") or
            self._safe_text(page, ".position-name") or
            self._safe_text(page, ".job-name") or
            self._safe_text(page, "[class*='title']")
        )
        resp = (
            self._safe_text(page, "[class*='responsibility']") or
            self._safe_text(page, "[class*='desc']") or
            self._safe_text(page, "[class*='content']")
        )
        req = (
            self._safe_text(page, "[class*='requirement']") or
            self._safe_text(page, "[class*='require']")
        )

        # 兜底：直接抓 body 全文，让大模型自己解析
        if not resp and not req:
            resp = self._safe_text(page, "body")

        return JobInfo(
            title=title,
            company="美团",
            location=self._safe_text(page, "[class*='city'], [class*='location']"),
            salary=self._safe_text(page, "[class*='salary']"),
            responsibilities=resp,
            requirements=req,
        )

    def _parse_bytedance(self, page, url: str) -> JobInfo:
        page.wait_for_selector(".job-name, h1", timeout=8000)
        return JobInfo(
            title=self._safe_text(page, ".job-name, h1.position-name"),
            company="字节跳动",
            location=self._safe_text(page, ".job-city, .location"),
            salary=self._safe_text(page, ".salary"),
            responsibilities=self._safe_text(page, ".job-desc, .description"),
            requirements=self._safe_text(page, ".job-requirement, .requirement"),
        )

    def _parse_xiaohongshu(self, page, url: str) -> JobInfo:
        page.wait_for_selector(".position-name, .title", timeout=8000)
        return JobInfo(
            title=self._safe_text(page, ".position-name, .title"),
            company="小红书",
            location=self._safe_text(page, ".location, .city"),
            salary=self._safe_text(page, ".salary"),
            responsibilities=self._safe_text(page, ".content, .job-content"),
            requirements=self._safe_text(page, ".requirement"),
        )

    def _parse_jd(self, page, url: str) -> JobInfo:
        page.wait_for_selector(".job-name, h2", timeout=8000)
        return JobInfo(
            title=self._safe_text(page, ".job-name, h2"),
            company="京东",
            location=self._safe_text(page, ".job-city, .work-place"),
            salary=self._safe_text(page, ".salary"),
            responsibilities=self._safe_text(page, ".job-detail, .job-desc"),
            requirements=self._safe_text(page, ".job-require"),
        )

    def _parse_kuaishou(self, page, url: str) -> JobInfo:
        page.wait_for_selector(".job-title, h1", timeout=8000)
        return JobInfo(
            title=self._safe_text(page, ".job-title, h1"),
            company="快手",
            location=self._safe_text(page, ".job-location, .location"),
            salary=self._safe_text(page, ".salary"),
            responsibilities=self._safe_text(page, ".job-desc, .description"),
            requirements=self._safe_text(page, ".job-require, .requirement"),
        )

    def _parse_tencent(self, page, url: str) -> JobInfo:
        page.wait_for_selector(".posit-title, h2", timeout=8000)
        return JobInfo(
            title=self._safe_text(page, ".posit-title, h2.job-name"),
            company="腾讯",
            location=self._safe_text(page, ".posit-place, .location"),
            salary=self._safe_text(page, ".salary"),
            responsibilities=self._safe_text(page, ".posit-description, .job-desc"),
            requirements=self._safe_text(page, ".posit-require, .require"),
        )

    def _parse_baidu(self, page, url: str) -> JobInfo:
        page.wait_for_selector(".job-title, h2", timeout=8000)
        return JobInfo(
            title=self._safe_text(page, ".job-name, .job-title, h2"),
            company="百度",
            location=self._safe_text(page, ".city, .location"),
            salary=self._safe_text(page, ".salary"),
            responsibilities=self._safe_text(page, ".job-description, .desc"),
            requirements=self._safe_text(page, ".job-requirement, .require"),
        )

    def _parse_shixiseng(self, page, url: str) -> JobInfo:
        page.wait_for_selector(".name, h1", timeout=8000)
        return JobInfo(
            title=self._safe_text(page, ".position-name, h1.name"),
            company=self._safe_text(page, ".company-name, .corp-name"),
            location=self._safe_text(page, ".position-label, .city"),
            salary=self._safe_text(page, ".position-label .salary, .pay"),
            responsibilities=self._safe_text(page, ".position-desc, .desc"),
            requirements=self._safe_text(page, ".position-require, .require"),
        )

    def _parse_nowcoder(self, page, url: str) -> JobInfo:
        page.wait_for_selector(".job-name, h1", timeout=8000)
        return JobInfo(
            title=self._safe_text(page, ".job-name, h1"),
            company=self._safe_text(page, ".company-name"),
            location=self._safe_text(page, ".job-city, .city"),
            salary=self._safe_text(page, ".job-salary, .salary"),
            responsibilities=self._safe_text(page, ".job-description"),
            requirements=self._safe_text(page, ".job-require"),
        )

    def _parse_alibaba(self, page, url: str) -> JobInfo:
        page.wait_for_selector("h1, .position-title", timeout=8000)
        return JobInfo(
            title=self._safe_text(page, "h1, .position-title"),
            company="阿里巴巴",
            location=self._safe_text(page, ".location, .city"),
            salary=self._safe_text(page, ".salary"),
            responsibilities=self._safe_text(page, ".job-description, .desc"),
            requirements=self._safe_text(page, ".job-requirement, .require"),
        )

    def _parse_generic(self, page, url: str) -> JobInfo:
        """通用解析：用启发式规则提取主要文本块"""
        # 等待页面稳定
        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass

        # 尝试常见选择器
        title = (
            self._safe_text(page, "h1") or
            self._safe_text(page, ".job-title") or
            self._safe_text(page, ".position-title")
        )

        # 提取页面主体文本，过滤导航/页脚
        body_text = ""
        for selector in ["main", "article", ".job-detail", ".content", "body"]:
            text = self._safe_text(page, selector)
            if len(text) > 200:
                body_text = text
                break

        # 用关键词切分职责和要求
        responsibilities, requirements = _split_jd_text(body_text)

        return JobInfo(
            title=title,
            company=_extract_company_from_title(page.title()),
            location="",
            salary="",
            responsibilities=responsibilities,
            requirements=requirements,
        )


def _split_jd_text(text: str):
    """启发式切分：职责 vs 要求"""
    resp_keywords = ["岗位职责", "工作职责", "职责描述", "Job Description", "工作内容"]
    req_keywords = ["任职要求", "岗位要求", "职位要求", "Requirements", "技能要求"]

    resp_idx = req_idx = -1
    for kw in resp_keywords:
        idx = text.find(kw)
        if idx != -1:
            resp_idx = idx
            break
    for kw in req_keywords:
        idx = text.find(kw)
        if idx != -1:
            req_idx = idx
            break

    if resp_idx != -1 and req_idx != -1:
        return text[resp_idx:req_idx].strip(), text[req_idx:].strip()
    elif req_idx != -1:
        return text[:req_idx].strip(), text[req_idx:].strip()
    else:
        mid = len(text) // 2
        return text[:mid].strip(), text[mid:].strip()


def _extract_company_from_title(page_title: str) -> str:
    """从页面标题猜公司名"""
    separators = [" - ", " | ", " · ", "–", "—"]
    for sep in separators:
        if sep in page_title:
            parts = page_title.split(sep)
            return parts[-1].strip()
    return ""


# ── 便捷函数 ─────────────────────────────────────────────────────
def scrape_job(url: str, headless: bool = True) -> JobInfo:
    """一行调用：传入 URL，返回 JobInfo"""
    return JobScraper(headless=headless).scrape(url)
