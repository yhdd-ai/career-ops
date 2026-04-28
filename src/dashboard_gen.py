"""
看板生成器
根据 jobs.json 生成内嵌数据的静态 HTML 看板
"""
import json
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent.parent
DASHBOARD_PATH = BASE_DIR / "dashboard" / "index.html"


def generate_dashboard():
    """读取 jobs.json 并生成 dashboard/index.html"""
    jobs_file = BASE_DIR / "data" / "jobs.json"
    jobs = []
    if jobs_file.exists():
        with open(jobs_file, encoding="utf-8") as f:
            jobs = json.load(f)

    # 统计
    total = len(jobs)
    avg_score = round(sum(j.get("score", 0) for j in jobs) / total, 1) if total else 0
    applied = sum(1 for j in jobs if j.get("status") in
                  ["已申请", "笔试/测评", "面试中", "已拿Offer"])
    offers = sum(1 for j in jobs if j.get("status") == "已拿Offer")

    jobs_json = json.dumps(jobs, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Career-Ops 求职看板</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "PingFang SC",
                 "Microsoft YaHei", sans-serif;
    background: #0f0e17;
    color: #fffffe;
    min-height: 100vh;
  }}
  .header {{
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
    padding: 32px 40px 24px;
    border-bottom: 1px solid #ffffff18;
  }}
  .header h1 {{
    font-size: 26px;
    font-weight: 700;
    letter-spacing: 1px;
    color: #fffffe;
  }}
  .header p {{
    color: #a7a9be;
    margin-top: 4px;
    font-size: 14px;
  }}
  .stats-row {{
    display: flex;
    gap: 16px;
    padding: 24px 40px;
  }}
  .stat-card {{
    background: #1a1a2e;
    border: 1px solid #ffffff15;
    border-radius: 12px;
    padding: 20px 28px;
    flex: 1;
    text-align: center;
  }}
  .stat-card .num {{
    font-size: 36px;
    font-weight: 700;
    line-height: 1;
  }}
  .stat-card .label {{
    font-size: 12px;
    color: #a7a9be;
    margin-top: 6px;
  }}
  .stat-card.total .num {{ color: #e0e0ff; }}
  .stat-card.avg .num {{ color: #5e60ce; }}
  .stat-card.applied .num {{ color: #48cae4; }}
  .stat-card.offers .num {{ color: #06d6a0; }}

  .controls {{
    display: flex;
    gap: 12px;
    padding: 0 40px 20px;
    align-items: center;
    flex-wrap: wrap;
  }}
  .filter-btn {{
    background: #1a1a2e;
    border: 1px solid #ffffff20;
    color: #a7a9be;
    padding: 7px 16px;
    border-radius: 20px;
    cursor: pointer;
    font-size: 13px;
    transition: all 0.2s;
  }}
  .filter-btn:hover, .filter-btn.active {{
    background: #5e60ce;
    border-color: #5e60ce;
    color: #fff;
  }}
  .search-box {{
    margin-left: auto;
    background: #1a1a2e;
    border: 1px solid #ffffff20;
    color: #fffffe;
    padding: 7px 16px;
    border-radius: 20px;
    font-size: 13px;
    width: 220px;
    outline: none;
  }}
  .search-box::placeholder {{ color: #a7a9be; }}

  .jobs-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
    gap: 16px;
    padding: 0 40px 40px;
  }}

  .job-card {{
    background: #1a1a2e;
    border: 1px solid #ffffff12;
    border-radius: 16px;
    padding: 20px;
    transition: transform 0.2s, box-shadow 0.2s;
    position: relative;
    overflow: hidden;
  }}
  .job-card:hover {{
    transform: translateY(-3px);
    box-shadow: 0 8px 32px #00000050;
    border-color: #ffffff25;
  }}
  .job-card::before {{
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    border-radius: 16px 16px 0 0;
  }}
  .job-card.grade-A::before {{ background: #27ae60; }}
  .job-card.grade-B::before {{ background: #2980b9; }}
  .job-card.grade-C::before {{ background: #f39c12; }}
  .job-card.grade-D::before {{ background: #e67e22; }}
  .job-card.grade-F::before {{ background: #e74c3c; }}

  .card-top {{
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 12px;
  }}
  .company {{ font-size: 11px; color: #a7a9be; margin-bottom: 2px; }}
  .job-title {{ font-size: 16px; font-weight: 600; color: #fffffe; line-height: 1.3; }}
  .score-badge {{
    font-size: 22px;
    font-weight: 700;
    line-height: 1;
    min-width: 52px;
    text-align: center;
  }}
  .grade-A .score-badge {{ color: #27ae60; }}
  .grade-B .score-badge {{ color: #2980b9; }}
  .grade-C .score-badge {{ color: #f39c12; }}
  .grade-D .score-badge {{ color: #e67e22; }}
  .grade-F .score-badge {{ color: #e74c3c; }}
  .score-label {{ font-size: 10px; color: #a7a9be; text-align: center; }}

  .tags {{
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
    margin: 10px 0;
  }}
  .tag {{
    font-size: 11px;
    padding: 3px 9px;
    border-radius: 10px;
    background: #ffffff10;
    color: #a7a9be;
  }}
  .tag.status {{
    font-weight: 600;
  }}
  .tag.status-待申请 {{ background: #5e60ce22; color: #818cf8; }}
  .tag.status-已申请 {{ background: #48cae422; color: #48cae4; }}
  .tag.status-笔试测评 {{ background: #f39c1222; color: #f39c12; }}
  .tag.status-面试中 {{ background: #e67e2222; color: #e67e22; }}
  .tag.status-已拿Offer {{ background: #06d6a022; color: #06d6a0; }}
  .tag.status-已拒绝 {{ background: #e74c3c22; color: #e74c3c; }}
  .tag.status-已放弃 {{ background: #ffffff10; color: #666; }}

  .dim-bars {{
    margin: 10px 0 4px;
  }}
  .dim-row {{
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 4px;
    font-size: 11px;
    color: #a7a9be;
  }}
  .dim-label {{ width: 80px; flex-shrink: 0; }}
  .dim-bar-wrap {{
    flex: 1;
    background: #ffffff10;
    border-radius: 3px;
    height: 5px;
    overflow: hidden;
  }}
  .dim-bar-fill {{
    height: 100%;
    border-radius: 3px;
    background: linear-gradient(90deg, #5e60ce, #48cae4);
  }}
  .dim-score-num {{ width: 24px; text-align: right; }}

  .recommendation {{
    font-size: 12px;
    color: #c8c8e0;
    margin-top: 10px;
    padding-top: 10px;
    border-top: 1px solid #ffffff10;
    line-height: 1.5;
  }}

  .card-footer {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 12px;
    font-size: 11px;
    color: #a7a9be;
  }}
  .card-footer a {{
    color: #5e60ce;
    text-decoration: none;
  }}
  .card-footer a:hover {{ text-decoration: underline; }}

  .empty-state {{
    text-align: center;
    padding: 80px 40px;
    color: #a7a9be;
    grid-column: 1 / -1;
  }}
  .empty-state .icon {{ font-size: 48px; margin-bottom: 16px; }}
  .empty-state p {{ font-size: 16px; }}

  .updated-at {{
    padding: 12px 40px;
    font-size: 11px;
    color: #a7a9be55;
    text-align: right;
  }}
</style>
</head>
<body>

<div class="header">
  <h1>🚀 Career-Ops 求职看板</h1>
  <p>岳淮东 · 实习求职追踪系统</p>
</div>

<div class="stats-row">
  <div class="stat-card total">
    <div class="num" id="stat-total">{total}</div>
    <div class="label">已评估职位</div>
  </div>
  <div class="stat-card avg">
    <div class="num" id="stat-avg">{avg_score}</div>
    <div class="label">平均评分</div>
  </div>
  <div class="stat-card applied">
    <div class="num" id="stat-applied">{applied}</div>
    <div class="label">已申请</div>
  </div>
  <div class="stat-card offers">
    <div class="num" id="stat-offers">{offers}</div>
    <div class="label">已拿 Offer</div>
  </div>
</div>

<div class="controls">
  <button class="filter-btn active" onclick="filterGrade('all')">全部</button>
  <button class="filter-btn" onclick="filterGrade('A')" style="color:#27ae60">A 级</button>
  <button class="filter-btn" onclick="filterGrade('B')" style="color:#2980b9">B 级</button>
  <button class="filter-btn" onclick="filterGrade('C')" style="color:#f39c12">C 级</button>
  <button class="filter-btn" onclick="filterStatus('待申请')">待申请</button>
  <button class="filter-btn" onclick="filterStatus('已申请')">已申请</button>
  <button class="filter-btn" onclick="filterStatus('面试中')">面试中</button>
  <button class="filter-btn" onclick="filterStatus('已拿Offer')">已拿 Offer</button>
  <input class="search-box" type="text" placeholder="搜索公司或职位..."
         oninput="searchJobs(this.value)" id="search-input">
</div>

<div class="jobs-grid" id="jobs-grid"></div>

<div class="updated-at">最后更新：{datetime.now().strftime("%Y-%m-%d %H:%M")}</div>

<script>
const JOBS = {jobs_json};

const DIM_LABELS = {{
  role_match: '岗位匹配',
  growth_potential: '成长空间',
  company_quality: '公司质量',
  location_fit: '地点匹配',
  compensation: '薪资水平',
  experience_match: '经验匹配',
  workload_culture: '工作强度',
}};

let currentGrade = 'all';
let currentStatus = null;
let currentSearch = '';

function render(jobs) {{
  const grid = document.getElementById('jobs-grid');
  if (!jobs.length) {{
    grid.innerHTML = `
      <div class="empty-state">
        <div class="icon">📭</div>
        <p>暂无匹配的职位记录</p>
      </div>`;
    return;
  }}
  grid.innerHTML = jobs.map(job => {{
    const dims = job.dimensions || {{}};
    const dimBars = Object.entries(DIM_LABELS).map(([key, label]) => {{
      const s = dims[key] || 0;
      return `<div class="dim-row">
        <span class="dim-label">${{label}}</span>
        <div class="dim-bar-wrap">
          <div class="dim-bar-fill" style="width:${{s}}%"></div>
        </div>
        <span class="dim-score-num">${{s}}</span>
      </div>`;
    }}).join('');

    const statusTag = job.status ? job.status.replace(/\//g, '') : '待申请';
    const urlHtml = job.url
      ? `<a href="${{job.url}}" target="_blank">查看原帖 →</a>`
      : `<span>无链接</span>`;

    return `<div class="job-card grade-${{job.grade}}">
      <div class="card-top">
        <div>
          <div class="company">${{job.company}}</div>
          <div class="job-title">${{job.title}}</div>
        </div>
        <div>
          <div class="score-badge">${{job.score}}</div>
          <div class="score-label">等级 ${{job.grade}}</div>
        </div>
      </div>
      <div class="tags">
        <span class="tag status status-${{statusTag}}">${{job.status || '待申请'}}</span>
        ${{job.location ? `<span class="tag">${{job.location}}</span>` : ''}}
        <span class="tag">#${{job.id}}</span>
      </div>
      <div class="dim-bars">${{dimBars}}</div>
      ${{job.recommendation ? `<div class="recommendation">${{job.recommendation}}</div>` : ''}}
      <div class="card-footer">
        <span>${{job.evaluated_at || ''}}</span>
        ${{urlHtml}}
      </div>
    </div>`;
  }}).join('');
}}

function applyFilters() {{
  let filtered = [...JOBS];
  if (currentGrade !== 'all') filtered = filtered.filter(j => j.grade === currentGrade);
  if (currentStatus) filtered = filtered.filter(j => j.status === currentStatus);
  if (currentSearch) {{
    const q = currentSearch.toLowerCase();
    filtered = filtered.filter(j =>
      (j.company || '').toLowerCase().includes(q) ||
      (j.title || '').toLowerCase().includes(q)
    );
  }}
  filtered.sort((a, b) => (b.score || 0) - (a.score || 0));
  render(filtered);
}}

function filterGrade(grade) {{
  currentGrade = grade; currentStatus = null;
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  event.target.classList.add('active');
  applyFilters();
}}

function filterStatus(status) {{
  currentStatus = (currentStatus === status) ? null : status;
  currentGrade = 'all';
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  if (currentStatus) event.target.classList.add('active');
  applyFilters();
}}

function searchJobs(q) {{
  currentSearch = q;
  applyFilters();
}}

// 初始渲染
applyFilters();
</script>
</body>
</html>"""

    DASHBOARD_PATH.parent.mkdir(exist_ok=True)
    DASHBOARD_PATH.write_text(html, encoding="utf-8")
    return DASHBOARD_PATH
