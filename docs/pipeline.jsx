import { useState } from "react";

const COLORS = {
  input:    { bg: "#1e3a5f", border: "#4a9eff", text: "#a8d4ff", label: "#4a9eff" },
  cache:    { bg: "#1a3a2a", border: "#3dba6f", text: "#90e8b0", label: "#3dba6f" },
  stage1:   { bg: "#2d2a1e", border: "#f0c040", text: "#fde99a", label: "#f0c040" },
  stage2:   { bg: "#2a1e3a", border: "#a970ff", text: "#d4b0ff", label: "#a970ff" },
  gate:     { bg: "#3a1e1e", border: "#ff6060", text: "#ffb0b0", label: "#ff6060" },
  output:   { bg: "#1a2e3a", border: "#40c0d0", text: "#90dde8", label: "#40c0d0" },
  monitor:  { bg: "#2a2a2a", border: "#888", text: "#ccc", label: "#aaa" },
};

const steps = [
  {
    id: "input",
    color: "input",
    icon: "📥",
    title: "① 输入层",
    sub: "URL / 手动JD / 简历导入",
    detail: `三种输入方式：
• 招聘链接 URL → Playwright 无头浏览器自动爬取 JD 正文
• 手动粘贴 JD → 直接进入评估流程（跳过爬虫）
• import-cv → PDF/TXT/MD 简历解析写入 cv.md

面试要点：爬虫兜底设计——字节/腾讯/美团等平台各有专属解析器，
匹配失败时降级到通用 CSS 选择器，进一步失败时提示手动粘贴。`,
  },
  {
    id: "cache",
    color: "cache",
    icon: "🗄",
    title: "② 三级缓存",
    sub: "命中直接返回，跳过全部 LLM 调用",
    detail: `Level 1 — URL 精确匹配（eval_cache.json）
  去掉 utm_source 等追踪参数后做 key，同一岗位换推广链接仍命中。

Level 2 — JD 文本 MD5 精确匹配（eval_cache.json）
  手动粘贴场景，相同内容哈希一致即命中。

Level 3 — 语义相似度匹配（semantic_cache.json）
  对 JD 文本用 sentence-transformers 编码为 384 维向量，
  与缓存中所有向量算 cosine similarity，≥ 0.92 命中。
  解决"同岗位换链接""两家公司发同一模板 JD"的重复消耗。

三级全未命中 → 进入 Stage 1。命中率越高，LLM 成本越低。`,
  },
  {
    id: "stage1",
    color: "stage1",
    icon: "🏷",
    title: "③ Stage 1：Archetype 分类",
    sub: "关键词规则（80%）+ LLM 语义分类（20%）",
    detail: `目的：在正式评估前识别岗位类型，用类型专属权重打分。

关键词规则（零 LLM 消耗）：
  统计各 Archetype 的关键词命中数，≥ 2 个直接返回，覆盖约 80% 明确 JD。

LLM 语义分类（chat_structured，约 200 tokens）：
  关键词置信度不足时触发，传入 ARCHETYPE_SCHEMA，
  LLM 输出 {"archetype_id": "llm_nlp"} 等结构体，直接读字段，零正则。

7 种 Archetype：
  llm_nlp · ml_algo · backend · data · frontend · product · general

输出：Archetype 对象（含维度权重 + 专属门控规则）→ 传入 Stage 2。`,
  },
  {
    id: "stage2",
    color: "stage2",
    icon: "🤖",
    title: "④ Stage 2：LLM 评估",
    sub: "Structured Output + 指数退避重试",
    detail: `构建 Prompt：
  CV摘要（压缩69%）+ 偏好配置 + Archetype 权重块 + 评估规则 + JD（截断后）

chat_structured() 调用：
  Claude → tool_use + tool_choice 强制返回 tool_use block，
          直接读 block.input dict，零正则解析
  Ollama → format=json + schema hint 双重约束，json.loads() 解析

EVALUATION_SCHEMA 包含：
  score(int) · grade(enum A-F) · dimensions(7个int) · recommendation · full_report

指数退避重试（with_retry）：
  1s → 2s → 4s，±20% jitter，最多3次
  429/5xx/Timeout 触发重试；401/400 快速失败
  全部失败 → 回退文本解析，设 parse_failed=True 标记`,
  },
  {
    id: "gate",
    color: "gate",
    icon: "🔒",
    title: "⑤ Gate-Pass 门控",
    sub: "业务规则一票否决，防止低匹配岗位被高估",
    detail: `全局门控（所有岗位共用）：
  岗位匹配度 < 35 → 等级上限 C（方向不符）
  经验要求匹配 < 20 → 等级上限 D（明确要工作经验）

Archetype 专属门控：
  大模型/NLP：role_match < 50 → B
  机器学习/算法：role_match < 45 → B
  后端工程：experience_match < 30 → C
  产品/运营：company_quality < 40 → C

多条同时触发取最严格上限，记录 original_grade + gate_reasons。
终端输出示例：
  ⚠ 门控触发：岗位匹配度 28 < 35 → 等级 A 压至 C

设计动机：LLM 容易被公司知名度/薪资蒙蔽，
门控是不可绕过的业务规则层，强制约束输出。`,
  },
  {
    id: "output",
    color: "output",
    icon: "📤",
    title: "⑥ 输出层",
    sub: "写缓存 · PDF报告 · 追踪看板 · STAR故事",
    detail: `写入三级缓存（L1/L2 + L3 semantic）。

PDF 报告（reports/xxx.pdf）：
  含维度进度条，若门控触发在报告头部注明原因。

jobs.json 追踪：
  记录公司/职位/等级/分数/Archetype/申请状态，状态流：
  待申请 → 已申请 → 面试中 → 已拿Offer / 已拒绝

HTML 可视化看板（dashboard/index.html）：
  深色主题，支持按等级筛选、关键词搜索、状态更新。

STAR 故事（--star 参数）：
  评估完成后自动生成面试素材，追加到 story_bank.md，支持关键词搜索。

A/B 测试报告（reports/ab_tests/）：
  量化 Token 优化方案的质量代价，多轮取均值消除 LLM 随机性。`,
  },
];

const monitorItems = [
  {
    icon: "📊",
    title: "parse_failed 率",
    desc: "结构化输出成功率。parse_failed=True 表示 tool_use 失败并回退文本解析。目标：Claude 后端 ≈0%，Ollama ≈ <5%。",
    cmd: "python3 run.py cache stats  # 查看命中率\ngrep parse_failed data/jobs.json | wc -l",
  },
  {
    icon: "🔁",
    title: "重试成功率",
    desc: "with_retry() 打印 ⏳ 日志时记录触发次数。若频繁重试说明 API 限流或网络不稳定，可调大 base_delay 或升级 API 等级。",
    cmd: "# 查看重试日志（INFO 级别）\npython3 -m logging -l INFO run.py evaluate ...",
  },
  {
    icon: "🏷",
    title: "Archetype 分类准确性",
    desc: "看 archetype_method 字段：rule 分类覆盖率越高越好（零成本）。若 llm 分类比例 >30%，说明 JD 表述模糊，可补充关键词列表。",
    cmd: "# jobs.json 中统计 archetype_method 分布\npython3 -c \"import json; d=json.load(open('data/jobs.json')); print([(x.get('archetype_method')) for x in d])\"",
  },
  {
    icon: "🔒",
    title: "门控触发率",
    desc: "gate_triggered=True 的比例反映申请质量。触发率过高（>30%）说明在投不匹配岗位，需调整求职方向。适当触发（10-20%）是正常过滤。",
    cmd: "# 统计门控触发情况\npython3 -c \"import json; d=json.load(open('data/jobs.json')); print(sum(1 for x in d if x.get('gate_triggered')), '/', len(d))\"",
  },
  {
    icon: "🧪",
    title: "A/B 测试：评分偏差",
    desc: "每隔一段时间对同一批 JD 跑 A/B 测试，监控摘要CV的评分偏差是否仍 ≤3分。偏差增大说明 CV 摘要质量下降，需重新运行 gen-cv-summary。",
    cmd: "python3 run.py ab-test --url 招聘链接 --rounds 5",
  },
  {
    icon: "📈",
    title: "长期准确性：Offer 反馈回路",
    desc: "将实际结果（拿到Offer/被拒）与评估等级对比。A/B 级岗位 Offer 率高说明评分准确。可用 jobs.json 中的 status 字段定期统计转化率。",
    cmd: "python3 run.py stats  # 查看各状态统计\npython3 run.py dashboard  # 可视化追踪",
  },
];

export default function PipelineDiagram() {
  const [activeStep, setActiveStep] = useState(null);
  const [activeMonitor, setActiveMonitor] = useState(null);

  const c = (key) => COLORS[key];

  return (
    <div style={{ background: "#0d1117", minHeight: "100vh", padding: "24px", fontFamily: "'SF Mono', 'Fira Code', monospace", color: "#e6edf3" }}>
      <div style={{ maxWidth: 900, margin: "0 auto" }}>

        {/* Header */}
        <div style={{ textAlign: "center", marginBottom: 32 }}>
          <h1 style={{ fontSize: 22, fontWeight: 700, color: "#fff", marginBottom: 6 }}>
            Career-Ops · 全流程 Pipeline
          </h1>
          <p style={{ color: "#8b949e", fontSize: 13 }}>点击每个节点查看详细说明 · 面试话术参考</p>
        </div>

        {/* Pipeline Steps */}
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {steps.map((step, idx) => {
            const col = c(step.color);
            const isActive = activeStep === step.id;
            return (
              <div key={step.id}>
                {/* Arrow between steps */}
                {idx > 0 && (
                  <div style={{ display: "flex", justifyContent: "center", height: 24, alignItems: "center" }}>
                    <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
                      <div style={{ width: 2, height: 12, background: "#30363d" }} />
                      <div style={{ width: 0, height: 0, borderLeft: "6px solid transparent", borderRight: "6px solid transparent", borderTop: "8px solid #30363d" }} />
                    </div>
                  </div>
                )}

                {/* Step Card */}
                <div
                  onClick={() => setActiveStep(isActive ? null : step.id)}
                  style={{
                    background: col.bg,
                    border: `1.5px solid ${isActive ? col.border : col.border + "80"}`,
                    borderRadius: 10,
                    padding: "14px 18px",
                    cursor: "pointer",
                    transition: "all 0.2s",
                    boxShadow: isActive ? `0 0 16px ${col.border}40` : "none",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <span style={{ fontSize: 22 }}>{step.icon}</span>
                    <div style={{ flex: 1 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                        <span style={{ color: col.border, fontWeight: 700, fontSize: 14 }}>{step.title}</span>
                        <span style={{ color: col.text, fontSize: 12, opacity: 0.8 }}>— {step.sub}</span>
                      </div>
                    </div>
                    <span style={{ color: col.border, fontSize: 16, transform: isActive ? "rotate(90deg)" : "rotate(0)", transition: "0.2s" }}>▶</span>
                  </div>

                  {/* Expanded Detail */}
                  {isActive && (
                    <div style={{
                      marginTop: 14,
                      padding: "14px 16px",
                      background: "#0d1117",
                      borderRadius: 8,
                      border: `1px solid ${col.border}40`,
                      fontSize: 12.5,
                      color: col.text,
                      lineHeight: 1.8,
                      whiteSpace: "pre-line",
                    }}>
                      {step.detail}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* Side Branches */}
        <div style={{ marginTop: 24, display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10 }}>
          {[
            { icon: "✂️", label: "简历裁剪", desc: "tailor-cv\n完整CV + JD → 重排经历对齐关键词" },
            { icon: "💌", label: "求职信生成", desc: "cover-letter\n基于简历+JD 生成中文求职信" },
            { icon: "🎯", label: "AI职位推荐", desc: "recommend\n摘要CV + 方向 → 推荐10-15个岗位" },
          ].map(b => (
            <div key={b.label} style={{
              background: "#161b22", border: "1px solid #30363d", borderRadius: 8,
              padding: "10px 12px", fontSize: 11.5, color: "#8b949e", lineHeight: 1.7,
            }}>
              <div style={{ fontSize: 16, marginBottom: 4 }}>{b.icon} <span style={{ color: "#c9d1d9", fontWeight: 600 }}>{b.label}</span></div>
              <div style={{ whiteSpace: "pre-line" }}>{b.desc}</div>
            </div>
          ))}
        </div>

        {/* Monitoring Section */}
        <div style={{ marginTop: 36 }}>
          <h2 style={{ fontSize: 16, color: "#fff", marginBottom: 16, borderBottom: "1px solid #30363d", paddingBottom: 10 }}>
            📡 精度监控方案
          </h2>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
            {monitorItems.map((m, i) => {
              const isOpen = activeMonitor === i;
              return (
                <div
                  key={i}
                  onClick={() => setActiveMonitor(isOpen ? null : i)}
                  style={{
                    background: "#161b22",
                    border: `1px solid ${isOpen ? "#4a9eff" : "#30363d"}`,
                    borderRadius: 8, padding: "12px 14px", cursor: "pointer",
                    transition: "border-color 0.2s",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: isOpen ? 10 : 0 }}>
                    <span style={{ fontSize: 18 }}>{m.icon}</span>
                    <span style={{ color: "#c9d1d9", fontWeight: 600, fontSize: 13 }}>{m.title}</span>
                  </div>
                  {isOpen && (
                    <>
                      <p style={{ color: "#8b949e", fontSize: 12, lineHeight: 1.7, margin: "0 0 10px 0" }}>{m.desc}</p>
                      <pre style={{
                        background: "#0d1117", border: "1px solid #30363d", borderRadius: 6,
                        padding: "8px 10px", fontSize: 11, color: "#7ee787",
                        margin: 0, whiteSpace: "pre-wrap", wordBreak: "break-all",
                      }}>{m.cmd}</pre>
                    </>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Interview Quick Reference */}
        <div style={{ marginTop: 28, background: "#161b22", border: "1px solid #d29922", borderRadius: 10, padding: "16px 20px" }}>
          <div style={{ color: "#d29922", fontWeight: 700, fontSize: 14, marginBottom: 12 }}>⭐ 面试一句话概括</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {[
              ["两阶段Pipeline", "先关键词分类JD类型，再用类型专属权重做评估，使评分标准差异化"],
              ["三级缓存", "URL精确→MD5精确→embedding语义相似，≥0.92阈值命中，节省重复LLM消耗"],
              ["Structured Output", "用JSON Schema+tool_use强制约束LLM输出，解析层退化为dict读取，parse失败率≈0"],
              ["指数退避重试", "1s→2s→4s，±20%jitter防惊群，401/400快速失败不浪费重试"],
              ["门控评分", "LLM输出后叠加业务规则，关键维度一票否决，防止低匹配岗位被高估"],
              ["A/B测试框架", "量化Token优化质量代价，实测评分偏差≤3分，token节省27%"],
            ].map(([key, val]) => (
              <div key={key} style={{ display: "flex", gap: 12, fontSize: 12, lineHeight: 1.6 }}>
                <span style={{ color: "#d29922", minWidth: 100, fontWeight: 600 }}>{key}</span>
                <span style={{ color: "#c9d1d9" }}>{val}</span>
              </div>
            ))}
          </div>
        </div>

        <p style={{ textAlign: "center", color: "#30363d", fontSize: 11, marginTop: 20 }}>
          Career-Ops · 点击各节点展开详情
        </p>
      </div>
    </div>
  );
}
