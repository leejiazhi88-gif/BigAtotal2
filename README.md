# 申万赛道研究总览

这是一个静态 HTML 行业研究看板，基于飞书表格中的模块设计，并使用真实行情数据生成页面输出。

## 页面

- 主页面：`outputs/index.html`
- 申万行业行情数据：`outputs/sector_real_data.js`
- 市场估值与情绪模块数据：`outputs/market_modules_data.js`

## 数据来源

- Tushare `index_classify` / `sw_daily`
- Tushare `daily_basic` / `daily` / `margin` / `moneyflow_hsgt` / `block_trade` / `new_share`

本仓库不提交飞书读取缓存、`.env`、密钥或访问 token。

## 重新生成

```powershell
python work/build_real_sector_data.py
python work/build_market_modules_data.py
```
