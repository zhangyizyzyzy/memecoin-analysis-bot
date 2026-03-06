# 🚀 Memecoin Intelligence Station

链上Memecoin情报自动收集系统，每小时自动运行，发布到 GitHub Pages。

## 📊 Live Dashboard
👉 **https://zhangyizyzyzy.github.io/memecoin-reports/**

## 🏗 架构

```
memecoin-reports/
├── .github/
│   └── workflows/
│       └── collect.yml      # GitHub Actions 定时任务（每小时）
├── scripts/
│   └── collect.py           # 主数据收集脚本
└── docs/                    # GitHub Pages 静态站点
    ├── index.html           # 情报展示页面
    └── data/
        ├── latest.json      # 最新报告
        ├── index.json       # 报告索引
        └── archive/         # 历史报告归档
```

## 📡 数据源

| 数据源 | 用途 | API |
|--------|------|-----|
| DexScreener | 链上交易数据 | 免费公开 |
| Twitter API | 社区热度/KOL提及 | Bearer Token |
| NewsAPI | 新闻媒体报道 | API Key |
| OKX | 聪明钱/大户信号 | API Key |
| OpenRouter | AI 分析报告生成 | API Key |

## ⚙️ GitHub Secrets 配置

在仓库 Settings → Secrets and variables → Actions 中添加：

| Secret 名称 | 说明 |
|-------------|------|
| `OPENROUTER_API_KEY` | OpenRouter API Key |
| `TWITTER_BEARER_TOKEN` | Twitter Bearer Token |
| `NEWS_API_KEY` | NewsAPI.org API Key |
| `OKX_API_KEY` | OKX API Key |
| `OKX_SECRET` | OKX Secret Key |
| `OKX_PASSPHRASE` | OKX Passphrase |

## 🌐 启用 GitHub Pages

1. 仓库 Settings → Pages
2. Source: `Deploy from a branch`
3. Branch: `main`, Folder: `/docs`
4. 保存后等待几分钟即可访问

## 🔧 监控的链

- **Solana** (SOL)
- **Ethereum** (ETH)
- **Base** (BASE)
- **BSC** (BNB Chain)

## ⚠️ 免责声明

本工具仅供学习研究使用，不构成任何投资建议。Memecoin 风险极高，请谨慎操作。
