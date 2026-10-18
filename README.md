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


## 自动刷新（可选）

本机 `gh` OAuth 令牌缺少 `workflow` 范围，未能把 `.github/workflows/refresh.yml` 推上仓库。
若需每日自动刷新 `data/last_scan.json`，请在仓库网页手动添加 Actions 工作流，或用带 `workflow` 权限的 PAT 推送本地文件：

` /workspace/qullamaggie-pages/.github/workflows/refresh.yml `

也可在 Actions 未启用时，本地运行 `screener.py` 后提交更新的 JSON。

## 限制

- 数据源为免费雅虎财经（yfinance），有延迟与偶发缺数
- 股票池约 370 只高流动性美股子集，非全市场
- 相对强度在本池内百分位近似「前 1–2%」
- 静态站无法在浏览器内对全池做实时批量下载（CORS / 请求量）；刷新依赖 Actions





## 最可能爆涨五只（评分模型）

综合「爆涨潜力」打分，只输出 **TOP 5**，仓位相对收紧（账户 10 万美元）：

| 参数 | 取值 |
|------|------|
| 单票典型仓位 | 约 **8–12%** |
| 隔夜单票上限 | 约 **15–20%**（默认 18%） |
| 单笔风险 | 约 **0.3–0.5%**（默认 0.4%） |
| 流动性 | 日成交额 ≥ **1000 万美元** |

### 权重（中文）

| 因子 | 权重 |
|------|------|
| 相对强度（1月/3月/6月涨幅百分位，子权重 45/35/20） | **40** |
| 均线贴近与盘整紧密度（距 10/20 日均线、盘整标记） | **20** |
| 振幅/波动够用（20 日 ADR%，利于盈亏比） | **15** |
| 接近突破 / 近期区间扩张 | **15** |
| 前期大涨结构 | **10** |
| 纳指软惩罚 | QQQ 未站上 10/20 日均线时总分 **×0.92** |

### 运行

```bash
pip install -r requirements.txt
python -m model top5
# 写出 data/top5.json；Pages「最可能爆涨五只」区块自动读取
```


## 回测与纸面交易

账户默认 **100,000 美元**。规则对齐库拉马吉风格文档：流动性 ≥ 1000 万美元日成交额、相对强度池内前约 1–2%、日线盘整突破近似入场、单笔风险 0.5%、止损取入场日低/ADR 封顶、3–5 日后分批卖出 1/3、余仓跌破 10 日均线离场；可选纳指（QQQ）站上 10/20 日均线过滤。

### 依赖

```bash
pip install -r requirements.txt
```

### 运行回测

默认用约 50 只高流动性动量名**样例子集**（加快演示）；全池加 `--full`（更慢）。

```bash
# 在仓库根目录
python -m backtest
# 或指定区间 / 全池
python -m backtest --start 2020-01-01 --end 2025-12-31
python -m backtest --full
```

输出（中文标签）：

| 文件 | 说明 |
|------|------|
| `backtest/output/equity_curve.png` | 权益曲线与回撤 |
| `backtest/output/stats.json` | 年化、最大回撤、胜率、利润因子、笔数等 |
| `backtest/output/trades.csv` | 成交明细 |
| `data/equity_curve.png` | 同步副本（可供 Pages 引用） |
| `data/backtest_stats.json` | 同步统计副本 |

样例限制：子集非全市场；日线近似开盘区间突破；yfinance 免费源可能缺数/延迟；含简化佣金滑点，**非实盘**。

### 运行纸面交易

读取 `data/last_scan.json` 信号，按相同风控规则模拟成交，状态写入 `paper/state/paper_state.json`。**无真实经纪商下单。**

```bash
python -m paper run      # 按最新信号模拟一步（更新持仓）
python -m paper status   # 查看现金、权益、持仓与最近成交
python -m paper reset    # 重置为 10 万美元空仓
```

### TOP5 纸面组合盈亏

按 `data/top5.json` 建议股数开仓（账户 10 万美元），每日刷新标记价，输出中文盈亏日报。**成员变动只记调仓提示，不自动换仓。**

```bash
python -m paper.portfolio_top5 init     # 用最新 TOP5 建账（覆盖）
python -m paper.portfolio_top5 update   # 刷新 yfinance 标记价与盈亏
python -m paper.portfolio_top5 report   # 打印中文摘要
```

| 文件 | 说明 |
|------|------|
| `data/portfolio_top5.json` | 持仓与盈亏状态 |
| `data/pnl_latest.md` | 最新中文日报 |

Pages「TOP5 纸面组合盈亏」区块读取 `data/portfolio_top5.json` 展示持仓与浮动盈亏。

### 目录（新增）

```
backtest/     # 回测包：下载、信号、引擎、统计与作图
paper/        # 纸面交易 CLI 与状态
```

## 免责声明

仅供学习研究，不构成投资建议。
