# Career-Ops 🚀

**AI 驱动的实习求职自动化系统** — 输入招聘链接，自动爬取 JD、AI 评分、生成 PDF 报告、可视化追踪申请进度。

> 受 [santifer/career-ops](https://github.com/santifer/career-ops) 启发，专为中国互联网实习求职场景定制。

---

## ✨ 功能

| 功能 | 说明 |
|------|------|
| 🔍 **AI 职位评估** | 输入招聘链接或 JD，Claude / Ollama 自动 7 维度打分（A–F 等级） |
| 🌐 **自动爬取 JD** | Playwright 自动抓取字节、腾讯、美团、小红书等主流平台 |
| 📄 **PDF 报告生成** | 每次评估自动生成带维度进度条的中文 PDF |
| 📊 **可视化看板** | 深色主题 HTML 看板，支持筛选、搜索、状态追踪 |
| 🎯 **AI 职位推荐** | 输入求职方向，AI 推荐 10–15 个匹配公司和职位 |
| 📥 **简历导入** | 直接导入 PDF / TXT / MD 格式简历 |

---

## 🚀 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/yhdd-ai/career-ops.git
cd career-ops
```

### 2. 一键配置环境

```bash
bash setup.sh
```

脚本自动完成：检查 Python → 安装依赖 → 安装 Playwright Chromium → 引导填写 API Key。

> **手动安装**：`pip install -r requirements.txt && playwright install chromium`

### 3. 导入你的简历

```bash
python3 run.py import-cv ~/Downloads/你的简历.pdf
```

### 4. 配置个人偏好

编辑 `config/profile.yml`，设置目标岗位、城市、薪资期望等（约 2 分钟）。

### 5. 开始使用！

```bash
# 输入招聘链接，全自动评估
python3 run.py evaluate --url "https://jobs.bytedance.com/..."
```

---

## 🔑 API Key 配置

本项目支持两种模式：

### 模式一：Claude API（推荐，质量最高）

1. 前往 [console.anthropic.com](https://console.anthropic.com/settings/keys) 获取 API Key
2. 编辑 `config/api.yml`：

```yaml
anthropic_api_key: "sk-ant-你的key"
model: "claude-opus-4-6"
```

3. 使用 `run.py` 运行

### 模式二：Ollama 本地模型（免费，适合调试）

```bash
# 安装 Ollama：https://ollama.com
ollama serve
ollama pull qwen2.5:7b   # 推荐中文模型
```

编辑 `config/api_local.yml`，然后使用 `run_local.py` 运行。

---

## 📖 命令手册

### `run.py` — Claude API 版

```bash
# 导入简历
python3 run.py import-cv <简历路径>

# 评估职位（传入 URL 自动爬取）
python3 run.py evaluate --url "招聘链接"
python3 run.py evaluate --url "招聘链接" --visible   # 显示浏览器（调试）
python3 run.py evaluate --jd "JD文本" --company "字节" --title "后端实习"

# AI 推荐职位
python3 run.py recommend --direction "大模型算法"

# 管理申请进度
python3 run.py list                       # 查看所有职位
python3 run.py update <ID> <状态>         # 更新状态
python3 run.py stats                      # 统计概览

# 报告与看板
python3 run.py pdf <ID>                   # 生成 PDF
python3 run.py dashboard                  # 打开可视化看板
```

### `run_local.py` — Ollama 本地版

命令与上方完全相同，额外支持：

```bash
python3 run_local.py models   # 查看本地已安装模型
```

### 申请状态可选值

`待申请` → `已申请` → `笔试/测评` → `面试中` → `已拿Offer` / `已拒绝` / `已放弃`

---

## 📊 评分体系

| 维度 | 权重 | 说明 |
|------|------|------|
| 岗位匹配度 | 25% | 技能与 JD 要求的契合程度 |
| 成长空间 | 20% | 学习机会与职业发展潜力 |
| 公司质量 | 15% | 品牌、规模与行业地位 |
| 地点匹配 | 10% | 与偏好城市的匹配程度 |
| 薪资水平 | 10% | 与期望薪资的对比 |
| 经验要求匹配 | 10% | 门槛是否适合实习生 |
| 工作强度与文化 | 10% | 工作环境与节奏 |

**等级对照：** A（85+）强烈推荐 · B（70–84）推荐 · C（55–69）可尝试 · D（40–54）不推荐 · F（<40）跳过

---

## 🌐 支持的招聘平台

字节跳动 · 腾讯 · 阿里巴巴 · 美团 · 京东 · 快手 · 百度 · 小红书 · 实习僧 · 牛客网，以及通用页面兜底解析。

---

## 📁 项目结构

```
career-ops/
├── run.py                  # 主入口（Claude API）
├── run_local.py            # 本地调试入口（Ollama）
├── setup.sh                # 一键配置脚本
├── requirements.txt
├── cv.md                   # 你的简历（import-cv 自动写入）
├── config/
│   ├── api.yml             # Claude API Key
│   ├── api_local.yml       # Ollama 配置
│   └── profile.yml         # 求职偏好
├── modes/
│   ├── evaluate.md         # 评估 Prompt 模板
│   └── recommend.md        # 推荐 Prompt 模板
├── src/
│   ├── evaluator.py        # 评估引擎
│   ├── recommender.py      # 推荐模块
│   ├── scraper.py          # JD 爬虫（Playwright）
│   ├── tracker.py          # 职位追踪
│   ├── pdf_gen.py          # PDF 生成
│   ├── dashboard_gen.py    # 看板生成
│   ├── cv_importer.py      # 简历导入
│   └── ollama_client.py    # Ollama 客户端
├── data/
│   └── jobs.json           # 职位追踪数据
├── reports/                # 评估报告（MD + PDF）
└── dashboard/
    └── index.html          # 可视化看板
```

---

## 🛠 常见问题

**Q：爬取失败 / 超时**
尝试加 `--visible` 查看浏览器行为，或直接粘贴 JD 文本：
```bash
python3 run.py evaluate --jd "职位描述内容" --company "公司" --title "职位"
```

**Q：PDF 中文显示方框**
macOS 字体通常自动识别。如仍有问题，在 `src/pdf_gen.py` 的 `CHINESE_FONT_PATHS` 列表中添加你系统的字体路径。

**Q：Ollama 模型响应慢**
在 `config/api_local.yml` 中增大 `timeout` 值，或换用更小的模型如 `qwen2.5:3b`。

**Q：`Client.__init__() got unexpected argument 'proxies'`**
```bash
pip install --upgrade anthropic
# 或
pip install "httpx<0.28.0"
```

---

## 📌 Roadmap

- [x] AI 职位评估（7 维度 · A–F 等级）
- [x] Playwright 自动爬取主流平台
- [x] PDF 报告生成
- [x] 可视化看板
- [x] AI 职位推荐
- [x] 简历导入（PDF/TXT/MD）
- [x] Ollama 本地模型支持
- [ ] 批量 URL 并行评估
- [ ] 简历按 JD 自动定制
- [ ] 求职信生成

---

## License

MIT
