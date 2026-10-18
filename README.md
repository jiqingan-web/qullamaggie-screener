# 库拉马吉风格美股一键筛选（GitHub Pages）

纯静态站点：中文界面观察名单、规则说明、仓位（10 万美元）、流动性门槛 1000 万美元、市场区提示。

**在线地址：** https://jiqingan-web.github.io/qullamaggie-screener/

## 「一键筛选」如何工作

浏览器点击「一键筛选」会重新拉取本仓库的 `data/last_scan.json`，并按页面勾选（振幅 / 结构）在前端过滤。

全市场扫描由 GitHub Actions（`.github/workflows/refresh.yml`）在 Ubuntu 上用 `yfinance` 每日（工作日）或手动运行，更新并推送 JSON。Pages 始终展示最新预计算结果，**用户无需安装 Python**。

## 本地预览

```bash
cd qullamaggie-screener
python3 -m http.server 8080
# 打开 http://127.0.0.1:8080
```

## 手动刷新数据

仓库 → Actions →「刷新筛选数据」→ Run workflow。

或本地：

```bash
pip install -r requirements.txt
python -c "from screener import run_screen; import json; from pathlib import Path; r=run_screen(); Path('data/last_scan.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')"
```

## 限制

- 数据源为免费雅虎财经（yfinance），有延迟与偶发缺数
- 股票池约 370 只高流动性美股子集，非全市场
- 相对强度在本池内百分位近似「前 1–2%」
- 静态站无法在浏览器内对全池做实时批量下载（CORS / 请求量）；刷新依赖 Actions

## 免责声明

仅供学习研究，不构成投资建议。
