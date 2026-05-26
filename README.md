# 🚇 台北城市移動行為分析儀表板

整合捷運客流 × YouBike 即時 × 天氣 × 空氣品質的城市脈動分析平台。

## 🏗️ 架構

```
mrt_dashboard/
├── app.py                  ← Streamlit 主程式（前端 + 路由）
├── etl/
│   ├── pipeline.py         ← ETL Pipeline（抓資料 + 寫入 DB）
│   └── scheduler.py        ← 背景排程（每5分鐘自動刷新）
├── data/
│   └── dashboard.db        ← SQLite 資料庫（自動建立）
├── .streamlit/
│   └── config.toml         ← 深色主題設定
└── requirements.txt
```

## 📊 資料來源

| 資料 | 來源 | 更新頻率 |
|------|------|---------|
| 捷運月旅次 | 台北捷運開放資料 | 每月 |
| YouBike 即時 | YouBike 2.0 API | 每5分鐘 |
| 氣象資料 | Open-Meteo (免費) | 每小時 |
| AQI 空品 | 環保署開放 API | 每小時 |

## 🚀 本機執行

```bash
# 1. 安裝套件
pip install -r requirements.txt

# 2. 啟動
streamlit run app.py
```

## ☁️ 部署到 Streamlit Cloud（免費）

1. 將此資料夾推上 GitHub（公開 repo）
2. 前往 [share.streamlit.io](https://share.streamlit.io)
3. 點 **New app** → 選你的 repo → Main file: `app.py`
4. 點 **Deploy** → 約 2 分鐘後取得公開 URL ✅

> ⚠️ 記得把 `data/` 加入 `.gitignore`，SQLite DB 會在雲端自動建立。

## 📋 .gitignore 建議

```
data/
__pycache__/
*.pyc
.env
```

## 🎯 功能亮點

- **5個分析頁籤**：客流趨勢、YouBike地圖、天氣關聯、空品分析、綜合趨勢
- **即時KPI**：旅次、YouBike可借率、氣溫、AQI
- **COVID-19 影響視覺化**：2021-2022 客流下降清晰可見
- **多維交叉分析**：捷運 × YouBike 跨運具分析
- **自動資料刷新**：每5分鐘 background scheduler
