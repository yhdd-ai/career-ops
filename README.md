# 🚀 Career-Ops

> AI-powered Job Evaluation & Decision System · 用 AI 构建你的求职决策系统

---

## ✨ Overview | 项目简介

**Career-Ops** 是一个面向求职场景的 AI 工具链，帮助你从「海投」升级为「数据驱动决策」：

* 🔍 自动爬取岗位 JD（支持动态网页）
* 🧠 使用大模型进行岗位匹配评估
* 📊 输出结构化评分（0–100 + A–F 等级）
* 📄 自动生成 Markdown / PDF 报告
* 📈 构建个人求职看板（Dashboard）
* 🗂️ 管理职位、状态与历史记录

> Stop guessing. Start deciding.
> 不再凭感觉投递，而是用 AI + 数据做决策。

---

## 🎯 Why Career-Ops | 为什么做这个

现实求职中的痛点：

* ❌ JD 冗长，筛选成本高
* ❌ 难以量化「是否适合」
* ❌ 投递无记录，无法复盘
* ❌ 缺乏系统化决策工具

👉 Career-Ops 通过 **爬虫 + LLM + 数据管理 + 可视化**，将求职流程结构化、自动化。

---

## ⚙️ Features | 核心功能

### 🔹 1. 自动 JD 爬取（动态网页）

支持 Playwright 渲染页面，适配主流招聘平台（美团 / 字节 / 阿里 / 腾讯 / 通用解析）

```bash
python run.py evaluate --url <job_url>
```

---

### 🔹 2. AI 岗位评估（核心）

* 匹配度评分（0–100）
* 等级（A–F）
* 多维度分析（技能 / 经验 / 潜力）
* 建议（是否值得投）

---

### 🔹 3. 自动生成报告

* Markdown 报告（可编辑）
* PDF 报告（可分享）
* 用于面试准备 / 复盘分析

---

### 🔹 4. 求职看板（Dashboard）

```bash
python run.py dashboard
```

自动生成 HTML 页面，包含：

* 投递状态统计
* 平均评分
* Offer 数量
* 等级分布

---

### 🔹 5. CLI 工作流

```bash
# 评估岗位（推荐）
python run.py evaluate --url <job_url>

# 手动输入 JD
python run.py evaluate --jd "JD文本"

# 查看职位
python run.py list

# 更新状态
python run.py update <id> applied

# 查看统计
python run.py stats

# 生成 PDF
python run.py pdf <id>
```

---

## 🏗️ Architecture | 项目架构

```text
career-ops/
│
├── run.py                  # CLI 入口
├── src/
│   ├── scraper.py         # JD 爬取（Playwright）
│   ├── evaluator.py       # AI 评估（LLM 调用）
│   ├── tracker.py         # 职位数据管理（SQLite）
│   ├── pdf_gen.py         # PDF 报告生成
│   └── dashboard_gen.py   # HTML 看板
│
├── data/                  # 职位数据存储
├── reports/               # 分析报告
└── requirements.txt
```

---

## 🚀 Quick Start | 快速开始

### 1️⃣ 安装依赖

```bash
pip install -r requirements.txt
```

---

### 2️⃣ 安装浏览器（必须）

```bash
python -m playwright install webkit
```

> macOS 推荐使用 WebKit，稳定性更好

---

### 3️⃣ 配置 API Key（如使用 Claude）

在配置文件中填写：

```yaml
anthropic_api_key: YOUR_API_KEY
```

---

### 4️⃣ 运行

```bash
python run.py evaluate \
  --url "https://..." \
  --company "公司名" \
  --title "职位名"
```

---

## 📊 Example Output | 示例输出

```text
A 级 92/100 · 美团 · 大模型平台开发工程师

✓ 报告：report_xxx.md
✓ PDF：report_xxx.pdf
✓ 看板已更新
```

---

## 🧠 How It Works | 工作原理

```text
URL → 爬取 JD → 清洗文本
        ↓
     LLM 分析（技能 / 匹配度）
        ↓
   结构化结果（score / grade）
        ↓
   存储 + 报告 + 可视化
```

核心思想：

> 将「主观判断」转为「结构化决策」

---

## 🧩 Tech Stack | 技术栈

* Python
* Playwright（动态网页爬取）
* LLM（Claude / OpenAI）
* SQLite（数据存储）
* HTML / JS（可视化看板）

---

## 🔥 Highlights | 项目亮点

* ✅ AI + 工程结合（不是纯 demo）
* ✅ 完整 workflow（爬取 → 分析 → 存储 → 展示）
* ✅ 可扩展架构（多平台 / 多模型）
* ✅ 实际可用（真实求职场景）

---

## ⚠️ Notes | 注意事项

* 不提供自动投递（避免 spam）
* AI 评估仅供参考
* 建议结合个人背景使用

---

## 🧠 Roadmap | 未来规划

* [ ] 自动技能提取（RAG）
* [ ] 多岗位对比分析
* [ ] Tailored Resume 自动生成
* [ ] Agent 工作流（自动筛选岗位）
* [ ] Web UI（替代 CLI）

---

## 👨‍💻 Author

Made by 淮东

---

## ⭐ Support

如果这个项目对你有帮助，欢迎点个 Star ⭐
Your support helps this project grow!
