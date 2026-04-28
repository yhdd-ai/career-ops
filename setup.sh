#!/bin/bash
# Career-Ops 一键配置脚本
# 用法：cd career-ops && bash setup.sh

set -e
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo ""
echo "🚀 Career-Ops 配置开始"
echo "────────────────────────────────"

# ── 检查 Python ───────────────────────────────────────────────
echo ""
echo "① 检查 Python 环境..."
if ! command -v python3 &>/dev/null; then
  echo -e "${RED}✗ 未找到 python3，请先安装 Python 3.9+${NC}"
  echo "  下载地址：https://www.python.org/downloads/"
  exit 1
fi
PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo -e "${GREEN}✓ Python $PY_VERSION${NC}"

# ── 安装 pip 依赖 ─────────────────────────────────────────────
echo ""
echo "② 安装 Python 依赖..."
pip3 install -q reportlab pyyaml anthropic playwright beautifulsoup4
echo -e "${GREEN}✓ 依赖安装完成${NC}"

# ── 安装 Playwright 浏览器 ────────────────────────────────────
echo ""
echo "③ 安装 Playwright Chromium 浏览器..."
python3 -m playwright install chromium
echo -e "${GREEN}✓ Chromium 安装完成${NC}"

# ── 检查 API Key 配置 ─────────────────────────────────────────
echo ""
echo "④ 检查 API Key 配置..."
API_FILE="config/api.yml"
if grep -q "sk-ant-xxx" "$API_FILE" 2>/dev/null; then
  echo -e "${YELLOW}⚠ 尚未配置 API Key${NC}"
  echo ""
  echo "  请按以下步骤操作："
  echo "  1. 打开：https://console.anthropic.com/settings/keys"
  echo "  2. 创建一个 API Key（复制以 sk-ant- 开头的字符串）"
  echo "  3. 编辑文件 config/api.yml，把 Key 填入："
  echo "     anthropic_api_key: \"sk-ant-你的key\""
  echo ""
  read -p "  现在打开 config/api.yml 填写？(y/N) " OPEN
  if [[ "$OPEN" =~ ^[Yy]$ ]]; then
    if command -v code &>/dev/null; then
      code config/api.yml
    elif command -v open &>/dev/null; then
      open config/api.yml
    else
      echo "  请手动编辑：$(pwd)/config/api.yml"
    fi
  fi
else
  echo -e "${GREEN}✓ API Key 已配置${NC}"
fi

# ── 验证安装 ──────────────────────────────────────────────────
echo ""
echo "⑤ 验证安装..."
python3 -c "
import reportlab, yaml, anthropic
from playwright.sync_api import sync_playwright
print('所有依赖验证通过')
" && echo -e "${GREEN}✓ 验证成功${NC}" || echo -e "${RED}✗ 验证失败，请检查上方错误${NC}"

# ── 完成 ──────────────────────────────────────────────────────
echo ""
echo "────────────────────────────────"
echo -e "${GREEN}🎉 配置完成！${NC}"
echo ""
echo "使用方法："
echo "  python3 run.py evaluate --url \"招聘链接\""
echo "  python3 run.py list"
echo "  python3 run.py dashboard"
echo ""
