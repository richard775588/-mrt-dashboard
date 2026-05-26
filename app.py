"""
Taipei Pulse 台北脈動
Taipei Urban Mobility Dashboard
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import sqlite3
import os
import sys
from datetime import datetime, timedelta
import math

# Add parent path for imports
sys.path.insert(0, os.path.dirname(__file__))
from etl.pipeline import run_all, get_conn, DB_PATH, STATION_COORDS, MRT_STATIONS
from etl.scheduler import start_scheduler

# Start background refresh scheduler (runs once per process)
start_scheduler()

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Taipei Pulse 台北脈動",
    page_icon="🚇",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  /* Main background */
  .stApp { background-color: #0f1117; color: #e8eaf0; }

  /* Cards */
  .metric-card {
    background: linear-gradient(135deg, #1a1d2e 0%, #16192a 100%);
    border: 1px solid #2a2d3e;
    border-radius: 12px;
    padding: 20px 24px;
    margin-bottom: 12px;
    text-align: center;
  }
  .metric-value { font-size: 2rem; font-weight: 700; color: #7c9ef5; }
  .metric-label { font-size: 0.85rem; color: #8b8fa8; margin-top: 4px; }
  .metric-delta { font-size: 0.8rem; margin-top: 4px; }
  .delta-up { color: #4ade80; }
  .delta-down { color: #f87171; }

  /* Section headers */
  .section-header {
    font-size: 1.1rem; font-weight: 600;
    color: #c5cae9; margin: 24px 0 12px 0;
    border-left: 3px solid #5c7cfa;
    padding-left: 12px;
  }

  /* Status badges */
  .badge { display: inline-block; padding: 2px 10px; border-radius: 20px; font-size: 0.75rem; font-weight: 600; }
  .badge-green  { background: #1a3a2a; color: #4ade80; }
  .badge-yellow { background: #3a3010; color: #fbbf24; }
  .badge-red    { background: #3a1a1a; color: #f87171; }

  /* Sidebar */
  section[data-testid="stSidebar"] { background: #12141f; }

  /* Tabs */
  .stTabs [data-baseweb="tab-list"] { background: #1a1d2e; border-radius: 10px; padding: 4px; display: flex; justify-content: center; }
  .stTabs [data-baseweb="tab"] { color: #8b8fa8; flex: 1; text-align: center; justify-content: center; }
  .stTabs [aria-selected="true"] { color: #7c9ef5 !important; background: #252840 !important; border-radius: 8px; }

  /* Last updated */
  .last-updated { font-size: 0.75rem; color: #555870; text-align: right; margin-top: -10px; }
</style>
""", unsafe_allow_html=True)


# ── Data loading ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)  # refresh every 5 minutes
def load_mrt_monthly():
    conn = get_conn()
    df = pd.read_sql("SELECT * FROM mrt_monthly", conn)
    conn.close()
    return df


@st.cache_data(ttl=300)
def load_youbike_latest():
    conn = get_conn()
    df = pd.read_sql("""
        SELECT * FROM youbike_snapshot
        WHERE fetched_at = (SELECT MAX(fetched_at) FROM youbike_snapshot)
    """, conn)
    conn.close()
    return df


@st.cache_data(ttl=300)
def load_weather_latest():
    conn = get_conn()
    df = pd.read_sql("""
        SELECT * FROM weather_hourly ORDER BY fetched_at DESC LIMIT 48
    """, conn)
    conn.close()
    return df


@st.cache_data(ttl=300)
def load_aqi_latest():
    conn = get_conn()
    df = pd.read_sql("""
        SELECT * FROM aqi_snapshot
        WHERE fetched_at = (SELECT MAX(fetched_at) FROM aqi_snapshot)
    """, conn)
    conn.close()
    return df


# ── Plotly theme ──────────────────────────────────────────────────────────────
PLOTLY_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(26,29,46,0.6)",
    font=dict(color="#c5cae9", size=12),
    margin=dict(l=16, r=16, t=32, b=16),
    xaxis=dict(gridcolor="#2a2d3e", linecolor="#2a2d3e"),
    yaxis=dict(gridcolor="#2a2d3e", linecolor="#2a2d3e"),
)
COLOR_LINE = {
    "淡水信義線": "#E3224E",
    "板南線":     "#0070BD",
    "中和新蘆線": "#F5A700",
    "文湖線":     "#C48B20",
    "松山新店線": "#008659",
}


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🚇 Taipei Pulse 台北脈動")
    st.markdown("---")

    st.markdown("### ⚙️ Settings")
    selected_lines = st.multiselect(
        "捷運路線篩選",
        options=list(COLOR_LINE.keys()),
        default=list(COLOR_LINE.keys()),
    )

    _max_year = datetime.now().year
    year_range = st.slider("年份範圍", 2020, _max_year, (2020, _max_year))

    st.markdown("---")

    if st.button("🔄 更新所有資料", use_container_width=True):
        with st.spinner("ETL Pipeline 執行中..."):
            st.cache_data.clear()
            run_all()
        st.success("資料更新完成！")

    st.markdown("---")
    st.markdown("""
    **資料來源**
    - 🚇 台北捷運開放資料
    - 🚲 YouBike 2.0 即時 API
    - 🌤️ Open-Meteo 氣象 API
    - 🌬️ 環保署 AQI API

    **自動刷新**：每 5 分鐘
    """)


# ── Ensure data exists ────────────────────────────────────────────────────────
if not os.path.exists(DB_PATH):
    with st.spinner("🔄 首次載入，建立資料庫..."):
        run_all()
else:
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in c.fetchall()]
    conn.close()
    if "mrt_monthly" not in tables:
        with st.spinner("🔄 初始化資料..."):
            run_all()

# Load data
df_mrt = load_mrt_monthly()
df_youbike = load_youbike_latest()
df_weather = load_weather_latest()
df_aqi = load_aqi_latest()

# Filter by selected lines and years
df_mrt_f = df_mrt[
    (df_mrt["line"].isin(selected_lines)) &
    (df_mrt["year"] >= year_range[0]) &
    (df_mrt["year"] <= year_range[1])
]

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("""
<div style='text-align:center; padding: 8px 0 4px 0;'>
  <div style='font-size:2.4rem; font-weight:800; color:#e8eaf6;'>🚇 Taipei Pulse 台北脈動</div>
  <div style='font-size:1rem; color:#8b8fa8; margin-top:4px;'>整合捷運客流 · YouBike · 天氣 · 空品的城市脈動儀表板</div>
  <div style='font-size:0.75rem; color:#555870; margin-top:6px;'>最後更新：{}</div>
</div>
""".format(datetime.now().strftime('%Y/%m/%d %H:%M')), unsafe_allow_html=True)

st.markdown("---")

# ── KPI Row ───────────────────────────────────────────────────────────────────
k1, k2, k3, k4, k5 = st.columns(5)

# Total passengers last month
if not df_mrt_f.empty:
    latest = df_mrt_f[df_mrt_f["year"] == df_mrt_f["year"].max()]
    latest = latest[latest["month"] == latest["month"].max()]
    total_pass = latest["passengers"].sum()
    prev_month = df_mrt_f[df_mrt_f["year"] == df_mrt_f["year"].max()]
    prev_month = prev_month[prev_month["month"] == (latest["month"].max() - 1)]
    delta_pass = ((total_pass - prev_month["passengers"].sum()) / max(prev_month["passengers"].sum(), 1)) * 100
else:
    total_pass, delta_pass = 0, 0

with k1:
    st.markdown(f"""
    <div class='metric-card'>
      <div class='metric-value'>{total_pass/1e6:.1f}M</div>
      <div class='metric-label'>本月捷運總旅次</div>
      <div class='metric-delta {"delta-up" if delta_pass >= 0 else "delta-down"}'>
        {"▲" if delta_pass >= 0 else "▼"} {abs(delta_pass):.1f}% vs 上月
      </div>
    </div>
    """, unsafe_allow_html=True)

# YouBike availability
if not df_youbike.empty:
    total_bikes = df_youbike["available_bikes"].sum()
    total_slots = df_youbike["available_slots"].sum()
    avail_rate = total_bikes / (total_bikes + total_slots) * 100 if (total_bikes + total_slots) > 0 else 0
else:
    total_bikes, avail_rate = 0, 0

with k2:
    st.markdown(f"""
    <div class='metric-card'>
      <div class='metric-value'>{total_bikes}</div>
      <div class='metric-label'>YouBike 可借車輛</div>
      <div class='metric-delta delta-up'>可用率 {avail_rate:.0f}%</div>
    </div>
    """, unsafe_allow_html=True)

# Weather
if not df_weather.empty:
    latest_w = df_weather.iloc[0]
    temp = latest_w["temperature"]
    precip = latest_w["precipitation"]
else:
    temp, precip = 25.0, 0.0

with k3:
    st.markdown(f"""
    <div class='metric-card'>
      <div class='metric-value'>{temp:.0f}°C</div>
      <div class='metric-label'>台北當前氣溫</div>
      <div class='metric-delta {"delta-down" if precip > 0 else "delta-up"}'>
        {"🌧️" if precip > 0 else "☀️"} 降雨 {precip:.1f} mm
      </div>
    </div>
    """, unsafe_allow_html=True)

# AQI
if not df_aqi.empty:
    avg_aqi = df_aqi["aqi"].mean()
    aqi_status = "良好" if avg_aqi < 50 else ("普通" if avg_aqi < 100 else "不健康")
    badge_cls = "badge-green" if avg_aqi < 50 else ("badge-yellow" if avg_aqi < 100 else "badge-red")
else:
    avg_aqi, aqi_status, badge_cls = 55, "普通", "badge-yellow"

with k4:
    st.markdown(f"""
    <div class='metric-card'>
      <div class='metric-value'>{avg_aqi:.0f}</div>
      <div class='metric-label'>平均 AQI 空氣品質</div>
      <div class='metric-delta'><span class='badge {badge_cls}'>{aqi_status}</span></div>
    </div>
    """, unsafe_allow_html=True)

# Active stations
with k5:
    st.markdown(f"""
    <div class='metric-card'>
      <div class='metric-value'>{len(df_youbike)}</div>
      <div class='metric-label'>YouBike 活躍站點</div>
      <div class='metric-delta delta-up'>台北市 {len(df_aqi)} 個 AQI 測站</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab0, tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🗺️ 出行建議",
    "📊 捷運客流分析",
    "🚲 YouBike 即時地圖",
    "🌤️ 天氣 × 客流",
    "🌬️ 空氣品質",
    "📈 綜合趨勢",
])


# ─────────────────────────────────────────────────────────────────────────────
# TAB 0: 出行建議
# ─────────────────────────────────────────────────────────────────────────────
with tab0:
    st.markdown("<div class='section-header'>📍 我的出行建議</div>", unsafe_allow_html=True)
    try:
        from streamlit_js_eval import get_geolocation

        col_btn, _ = st.columns([1, 2])
        with col_btn:
            if st.button("🔍 取得我的位置", use_container_width=True):
                st.session_state["get_loc"] = True

        if st.session_state.get("get_loc"):
            loc = get_geolocation()
            user_lat, user_lng = None, None
            if loc and isinstance(loc, dict):
                if "coords" in loc:
                    user_lat = loc["coords"].get("latitude")
                    user_lng = loc["coords"].get("longitude")
                elif "latitude" in loc:
                    user_lat = loc.get("latitude")
                    user_lng = loc.get("longitude")

            if user_lat and user_lng:
                def haversine(lat1, lng1, lat2, lng2):
                    R = 6371000
                    phi1, phi2 = math.radians(lat1), math.radians(lat2)
                    dphi, dlam = math.radians(lat2-lat1), math.radians(lng2-lng1)
                    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
                    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

                temp, precip, aqi_val, aqi_status, district = None, None, None, None, "未知"
                if not df_weather.empty:
                    latest_w = df_weather.sort_values("fetched_at").iloc[-1]
                    temp = latest_w["temperature"]
                    precip = latest_w["precipitation"]
                if not df_aqi.empty:
                    aqi_val = int(df_aqi["aqi"].mean())
                    aqi_status = df_aqi.iloc[0]["status"]

                nearest_yb, yb_dist, df_near = None, None, None
                if not df_youbike.empty:
                    df_near = df_youbike[df_youbike["lat"] != 0].copy()
                    df_near["dist"] = df_near.apply(
                        lambda r: haversine(user_lat, user_lng, r["lat"], r["lng"]), axis=1)
                    df_near = df_near.sort_values("dist")
                    nearest_yb = df_near.iloc[0]
                    yb_dist = int(nearest_yb["dist"])
                    district = nearest_yb["district"]

                nearest_mrt, mrt_dist = None, None
                mrt_coords = [(name, lat, lng) for name, (lat, lng) in STATION_COORDS.items()]
                if mrt_coords:
                    mrt_dists = [(name, haversine(user_lat, user_lng, lat, lng))
                                 for name, lat, lng in mrt_coords]
                    nearest_mrt, mrt_dist = min(mrt_dists, key=lambda x: x[1])
                    mrt_dist = int(mrt_dist)

                rain = precip and precip > 1
                hot = temp and temp > 33
                bad_aqi = aqi_val and aqi_val > 100
                yb_ok = nearest_yb is not None and int(nearest_yb["available_bikes"]) >= 3

                if rain:
                    suggestion, suggestion_color = "🌧️ 現在有降雨，建議搭捷運為主", "#60a5fa"
                elif bad_aqi:
                    suggestion, suggestion_color = "😷 空氣品質不佳，建議減少戶外騎乘", "#f87171"
                elif hot:
                    suggestion, suggestion_color = "🥵 氣溫偏高，短程可騎 YouBike，長程建議搭捷運", "#fbbf24"
                elif yb_ok:
                    suggestion, suggestion_color = "✅ 天氣良好，適合騎 YouBike！", "#4ade80"
                else:
                    suggestion, suggestion_color = "🚇 附近 YouBike 車輛不足，建議搭捷運", "#a78bfa"

                temp_str = f"{temp:.0f}°C" if temp else "N/A"
                precip_str = f"{precip:.1f} mm" if precip is not None else "N/A"
                aqi_str = f"{aqi_val} {aqi_status}" if aqi_val else "N/A"
                yb_avail = int(nearest_yb["available_bikes"]) if nearest_yb is not None else 0
                yb_name = nearest_yb["station_name"] if nearest_yb is not None else "N/A"
                mrt_name = nearest_mrt or "N/A"

                col_card, col_list = st.columns([1, 1])
                with col_card:
                    st.markdown(f"""
                    <div style='background:linear-gradient(135deg,#1a1d2e,#16192a);
                                border:1px solid #2a2d3e;border-radius:14px;padding:24px;'>
                        <div style='font-size:1.2rem;font-weight:700;color:{suggestion_color};margin-bottom:18px;'>
                            {suggestion}
                        </div>
                        <div style='display:grid;grid-template-columns:auto 1fr;gap:12px 16px;font-size:0.9rem;align-items:center;'>
                            <div style='color:#8b8fa8;'>📍 所在區域</div>
                            <div style='color:#e8eaf6;font-weight:600;'>{district}</div>
                            <div style='color:#8b8fa8;'>🌡️ 氣溫 / 降雨</div>
                            <div style='color:#e8eaf6;'>{temp_str} &nbsp;／&nbsp; {precip_str}</div>
                            <div style='color:#8b8fa8;'>🌬️ 空氣品質</div>
                            <div style='color:#e8eaf6;'>{aqi_str}</div>
                            <div style='color:#8b8fa8;'>🚲 最近 YouBike</div>
                            <div style='color:#e8eaf6;'>{yb_name[:16]}<br>
                                <span style='color:#4ade80;font-weight:700;'>可借 {yb_avail} 輛</span>
                                &nbsp;·&nbsp; {yb_dist} 公尺
                            </div>
                            <div style='color:#8b8fa8;'>🚇 最近捷運站</div>
                            <div style='color:#e8eaf6;'>{mrt_name} &nbsp;·&nbsp; {mrt_dist} 公尺</div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                with col_list:
                    st.markdown("<div class='section-header'>附近 YouBike 站點</div>", unsafe_allow_html=True)
                    if df_near is not None:
                        for _, row in df_near.head(5).iterrows():
                            d = int(row["dist"])
                            avail = int(row["available_bikes"])
                            total = int(row["total_bikes"])
                            slots = int(row["available_slots"])
                            rate = avail / total * 100 if total > 0 else 0
                            c = "#4ade80" if rate > 60 else ("#fbbf24" if rate > 20 else "#f87171")
                            st.markdown(f"""
                            <div style='background:#1a1d2e;border:1px solid #2a2d3e;border-radius:10px;
                                        padding:10px 14px;margin-bottom:6px;'>
                                <div style='font-weight:600;color:#e8eaf6;font-size:0.88rem;'>{row["station_name"]}</div>
                                <div style='font-size:0.78rem;color:#8b8fa8;margin-top:2px;'>📏 {d} 公尺 · {row["district"]}</div>
                                <div style='margin-top:6px;display:flex;gap:14px;'>
                                    <span style='color:{c};font-weight:700;'>🚲 可借 {avail}</span>
                                    <span style='color:#7c9ef5;'>🅿️ 可還 {slots}</span>
                                    <span style='color:#555870;font-size:0.8rem;'>共 {total}</span>
                                </div>
                            </div>
                            """, unsafe_allow_html=True)

            elif loc is not None and "error" in loc:
                code = loc["error"].get("code", 0)
                if code == 1:
                    st.warning("❌ 位置權限被拒絕。請點瀏覽器網址列左側的 🔒 圖示 → 位置 → 允許，然後重新整理頁面再試。")
                elif code == 2:
                    st.warning("❌ 無法取得位置訊號，請確認裝置已開啟 GPS 或網路定位。")
                else:
                    st.warning(f"❌ 定位失敗：{loc['error'].get('message', '未知錯誤')}")
            else:
                st.info("⏳ 等待定位中，請允許瀏覽器存取位置權限…")
    except ImportError:
        st.info("請安裝 streamlit-js-eval 套件以啟用定位功能")


# ─────────────────────────────────────────────────────────────────────────────
# TAB 1: MRT Analysis
# ─────────────────────────────────────────────────────────────────────────────
with tab1:
    st.markdown("<div class='section-header'>各路線月旅次趨勢</div>", unsafe_allow_html=True)

    if not df_mrt_f.empty:
        # Monthly total by line
        df_line_monthly = df_mrt_f.groupby(["year", "month", "line"])["passengers"].sum().reset_index()
        df_line_monthly["date"] = pd.to_datetime(
            df_line_monthly["year"].astype(str) + "-" + df_line_monthly["month"].astype(str).str.zfill(2) + "-01"
        )

        fig_trend = go.Figure()
        for line in selected_lines:
            d = df_line_monthly[df_line_monthly["line"] == line]
            fig_trend.add_trace(go.Scatter(
                x=d["date"], y=d["passengers"] / 1e6,
                name=line, mode="lines+markers",
                line=dict(color=COLOR_LINE.get(line, "#888"), width=2),
                marker=dict(size=4),
                hovertemplate="%{x|%Y-%m}<br>%{y:.2f}M 旅次<extra>" + line + "</extra>"
            ))

        # COVID annotation
        fig_trend.add_vrect(x0="2021-01-01", x1="2022-12-31",
                            fillcolor="#f87171", opacity=0.05,
                            annotation_text="COVID-19 影響期", annotation_position="top left",
                            annotation_font_color="#f87171", annotation_font_size=10)

        fig_trend.update_layout(**PLOTLY_LAYOUT, height=360,
                                title=dict(text="捷運各路線月旅次（百萬）", font=dict(size=14)))
        st.plotly_chart(fig_trend, use_container_width=True)

    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("<div class='section-header'>熱門站點排行（最新月份）</div>", unsafe_allow_html=True)
        if not df_mrt_f.empty:
            latest_m = df_mrt_f[df_mrt_f["year"] == df_mrt_f["year"].max()]
            latest_m = latest_m[latest_m["month"] == latest_m["month"].max()]
            top20 = latest_m.groupby("station")["passengers"].sum().sort_values(ascending=True).tail(20)

            fig_bar = go.Figure(go.Bar(
                y=top20.index,
                x=top20.values / 1000,
                orientation="h",
                marker=dict(
                    color=top20.values,
                    colorscale=[[0, "#1a3a6e"], [0.5, "#4a6cf7"], [1, "#7c9ef5"]],
                    showscale=False,
                ),
                hovertemplate="%{y}<br>%{x:.0f}K 旅次<extra></extra>"
            ))
            fig_bar.update_layout(**PLOTLY_LAYOUT, height=480,
                                  title=dict(text="旅次前20站（千人次）", font=dict(size=13)),
                                  xaxis_title="旅次（千）")
            st.plotly_chart(fig_bar, use_container_width=True)

    with col_b:
        st.markdown("<div class='section-header'>各路線旅次佔比</div>", unsafe_allow_html=True)
        if not df_mrt_f.empty:
            line_total = df_mrt_f.groupby("line")["passengers"].sum()
            fig_pie = go.Figure(go.Pie(
                labels=line_total.index,
                values=line_total.values,
                marker_colors=[COLOR_LINE.get(l, "#888") for l in line_total.index],
                hole=0.45,
                textinfo="label+percent",
                hovertemplate="%{label}<br>%{value:,.0f} 旅次<extra></extra>"
            ))
            fig_pie.update_layout(**PLOTLY_LAYOUT, height=280,
                                  title=dict(text="各路線總旅次佔比", font=dict(size=13)),
                                  showlegend=False)
            st.plotly_chart(fig_pie, use_container_width=True)

        st.markdown("<div class='section-header'>年度旅次比較</div>", unsafe_allow_html=True)
        if not df_mrt_f.empty:
            yr_total = df_mrt_f.groupby("year")["passengers"].sum().reset_index()
            yr_total["color"] = yr_total["passengers"].apply(
                lambda x: "#f87171" if x == yr_total["passengers"].min()
                          else ("#4ade80" if x == yr_total["passengers"].max() else "#5c7cfa")
            )
            fig_yr = go.Figure(go.Bar(
                x=yr_total["year"].astype(str), y=yr_total["passengers"] / 1e6,
                marker_color=yr_total["color"],
                hovertemplate="%{x}<br>%{y:.1f}M 旅次<extra></extra>"
            ))
            fig_yr.update_layout(**PLOTLY_LAYOUT, height=200,
                                 title=dict(text="年度總旅次（百萬）", font=dict(size=13)))
            st.plotly_chart(fig_yr, use_container_width=True)

    # Heatmap
    st.markdown("<div class='section-header'>月份熱力圖：旅次分布</div>", unsafe_allow_html=True)
    if not df_mrt_f.empty:
        pivot = df_mrt_f.groupby(["year", "month"])["passengers"].sum().reset_index()
        pivot = pivot.pivot(index="year", columns="month", values="passengers")
        month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                       "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

        fig_heat = go.Figure(go.Heatmap(
            z=pivot.values / 1e6,
            x=[month_names[m-1] for m in pivot.columns],
            y=pivot.index.astype(str),
            colorscale=[[0, "#0d1b3e"], [0.4, "#2b4ea8"], [0.7, "#5c7cfa"], [1, "#93b4ff"]],
            hovertemplate="Year %{y} · %{x}<br>%{z:.1f}M 旅次<extra></extra>",
            colorbar=dict(title="百萬旅次", tickfont=dict(color="#8b8fa8"))
        ))
        fig_heat.update_layout(**PLOTLY_LAYOUT, height=220,
                               title=dict(text="年月旅次熱力圖（COVID影響清晰可見）", font=dict(size=13)))
        st.plotly_chart(fig_heat, use_container_width=True)



# ─────────────────────────────────────────────────────────────────────────────
# TAB 2: YouBike Map
# ─────────────────────────────────────────────────────────────────────────────
with tab2:
    col_map, col_info = st.columns([2, 1])

    with col_map:
        st.markdown("<div class='section-header'>YouBike 站點即時狀態地圖</div>", unsafe_allow_html=True)

        if not df_youbike.empty:
            # Availability rate color
            df_youbike["avail_rate"] = df_youbike["available_bikes"] / df_youbike["total_bikes"].replace(0, 1) * 100
            df_youbike["status_label"] = df_youbike["avail_rate"].apply(
                lambda x: "充足 (>60%)" if x > 60 else ("普通 (20-60%)" if x > 20 else "偏少 (<20%)")
            )
            df_youbike["color_val"] = df_youbike["avail_rate"]

            fig_map = px.scatter_map(
                df_youbike,
                lat="lat", lon="lng",
                size="total_bikes",
                color="avail_rate",
                color_continuous_scale=["#f87171", "#fbbf24", "#4ade80"],
                range_color=[0, 100],
                hover_name="station_name",
                hover_data={
                    "district": True,
                    "available_bikes": True,
                    "available_slots": True,
                    "total_bikes": True,
                    "avail_rate": ":.0f",
                    "lat": False, "lng": False
                },
                labels={
                    "avail_rate": "可借率 (%)",
                    "available_bikes": "可借車輛",
                    "available_slots": "可還空位",
                    "total_bikes": "總車位",
                    "district": "行政區",
                },
                zoom=12,
                center=dict(lat=25.04, lon=121.54),
                map_style="carto-darkmatter",
                height=520,
            )
            fig_map.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                margin=dict(l=0, r=0, t=0, b=0),
                coloraxis_colorbar=dict(
                    title="可借率%", tickfont=dict(color="#8b8fa8"),
                    bgcolor="rgba(26,29,46,0.8)",
                )
            )
            st.plotly_chart(fig_map, use_container_width=True)


    with col_info:
        st.markdown("<div class='section-header'>各行政區 YouBike 統計</div>", unsafe_allow_html=True)
        if not df_youbike.empty:
            district_stats = df_youbike.groupby("district").agg(
                站點數=("station_id", "count"),
                可借車輛=("available_bikes", "sum"),
                可還空位=("available_slots", "sum"),
            ).sort_values("可借車輛", ascending=False)

            fig_dist = go.Figure(go.Bar(
                y=district_stats.index,
                x=district_stats["可借車輛"],
                orientation="h",
                marker_color="#4a6cf7",
                name="可借車輛",
            ))
            fig_dist.add_trace(go.Bar(
                y=district_stats.index,
                x=district_stats["可還空位"],
                orientation="h",
                marker_color="#2a2d3e",
                name="可還空位",
            ))
            fig_dist.update_layout(
                **PLOTLY_LAYOUT, height=280, barmode="stack",
                title=dict(text="各區可借/可還", font=dict(size=13)),
                showlegend=True,
                legend=dict(orientation="h", y=1.1, x=0, font=dict(color="#8b8fa8"))
            )
            st.plotly_chart(fig_dist, use_container_width=True)



# ─────────────────────────────────────────────────────────────────────────────
# TAB 3: Weather × MRT
# ─────────────────────────────────────────────────────────────────────────────
with tab3:
    st.markdown("<div class='section-header'>天氣與捷運客流關聯分析</div>", unsafe_allow_html=True)

    if not df_weather.empty and not df_mrt_f.empty:
        col_w1, col_w2 = st.columns(2)

        with col_w1:
            # Weather history
            df_w = df_weather.copy()
            df_w["fetched_at"] = pd.to_datetime(df_w["fetched_at"])
            df_w = df_w.sort_values("fetched_at")

            fig_weather = make_subplots(specs=[[{"secondary_y": True}]])
            fig_weather.add_trace(go.Scatter(
                x=df_w["fetched_at"], y=df_w["temperature"],
                name="氣溫 (°C)", mode="lines",
                line=dict(color="#f59e0b", width=2),
            ), secondary_y=False)
            fig_weather.add_trace(go.Bar(
                x=df_w["fetched_at"], y=df_w["precipitation"],
                name="降雨量 (mm)", marker_color="#60a5fa", opacity=0.6,
            ), secondary_y=True)
            fig_weather.update_layout(**PLOTLY_LAYOUT, height=300,
                                      title=dict(text="近期台北氣溫與降雨", font=dict(size=13)))
            fig_weather.update_yaxes(title_text="°C", secondary_y=False, gridcolor="#2a2d3e")
            fig_weather.update_yaxes(title_text="mm", secondary_y=True, gridcolor="#2a2d3e")
            st.plotly_chart(fig_weather, use_container_width=True)

        with col_w2:
            # Scatter: weather effect simulation
            import numpy as np
            np.random.seed(42)
            n = 200
            temps = np.random.uniform(15, 35, n)
            precip = np.random.exponential(2, n)
            # Higher temp + less rain = more passengers
            base = 1_500_000
            passengers = base * (1 - 0.008*(temps - 22)**2) * (1 - 0.03*np.minimum(precip, 15)) + np.random.normal(0, 50000, n)
            passengers = np.maximum(passengers, 800000)

            df_scatter = pd.DataFrame({
                "temperature": temps, "precipitation": precip,
                "passengers_M": passengers / 1e6,
                "rain_type": ["有雨" if p > 2 else "無雨" for p in precip],
            })
            fig_scatter = px.scatter(
                df_scatter, x="temperature", y="passengers_M",
                color="rain_type",
                color_discrete_map={"有雨": "#60a5fa", "無雨": "#f59e0b"},
                trendline="lowess",
                labels={"temperature": "氣溫 (°C)", "passengers_M": "旅次（百萬）"},
                title="氣溫 vs 旅次（模擬相關性）",
                height=300,
            )
            fig_scatter.update_layout(**PLOTLY_LAYOUT)
            fig_scatter.update_traces(marker=dict(size=5, opacity=0.6))
            st.plotly_chart(fig_scatter, use_container_width=True)

        # Monthly seasonal pattern
        st.markdown("<div class='section-header'>捷運季節性模式（月份）</div>", unsafe_allow_html=True)
        seasonal = df_mrt_f.groupby("month")["passengers"].mean().reset_index()
        seasonal["month_name"] = seasonal["month"].map({
            1:"1月",2:"2月",3:"3月",4:"4月",5:"5月",6:"6月",
            7:"7月",8:"8月",9:"9月",10:"10月",11:"11月",12:"12月"
        })
        fig_seasonal = go.Figure(go.Bar(
            x=seasonal["month_name"],
            y=seasonal["passengers"] / 1e6,
            marker=dict(
                color=seasonal["passengers"],
                colorscale=[[0,"#1a3a2a"],[0.5,"#2a6e4f"],[1,"#4ade80"]],
                showscale=False,
            ),
            hovertemplate="%{x}<br>平均 %{y:.2f}M 旅次<extra></extra>",
        ))
        fig_seasonal.add_annotation(
            x="2月", y=seasonal[seasonal["month"]==2]["passengers"].values[0]/1e6 + 0.05,
            text="農曆新年\n旅次下降", showarrow=True, arrowhead=2,
            font=dict(color="#f87171", size=11), arrowcolor="#f87171",
        )
        fig_seasonal.update_layout(**PLOTLY_LAYOUT, height=300,
                                   title=dict(text="月份平均旅次（百萬）", font=dict(size=13)))
        st.plotly_chart(fig_seasonal, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# TAB 4: AQI
# ─────────────────────────────────────────────────────────────────────────────
with tab4:
    st.markdown("<div class='section-header'>台北市各行政區空氣品質</div>", unsafe_allow_html=True)

    if not df_aqi.empty:
        col_aqi1, col_aqi2 = st.columns([3, 2])

        with col_aqi1:
            def aqi_color(val):
                if val < 50:   return "#4ade80"
                if val < 100:  return "#fbbf24"
                if val < 150:  return "#f97316"
                return "#f87171"

            df_aqi_sorted = df_aqi.sort_values("aqi", ascending=True)
            colors = [aqi_color(v) for v in df_aqi_sorted["aqi"]]

            fig_aqi_bar = go.Figure(go.Bar(
                y=df_aqi_sorted["station"],
                x=df_aqi_sorted["aqi"],
                orientation="h",
                marker_color=colors,
                text=df_aqi_sorted["status"],
                textposition="outside",
                textfont=dict(color="#8b8fa8", size=11),
                hovertemplate="%{y}<br>AQI: %{x}<extra></extra>",
            ))
            # AQI threshold lines
            for threshold, label, color in [(50,"良好","#4ade80"),(100,"普通","#fbbf24")]:
                fig_aqi_bar.add_vline(x=threshold, line_dash="dash",
                                      line_color=color, opacity=0.5,
                                      annotation_text=label, annotation_font_color=color)

            fig_aqi_bar.update_layout(**PLOTLY_LAYOUT, height=420,
                                      title=dict(text="各測站 AQI 即時值", font=dict(size=13)),
                                      xaxis_title="AQI 值")
            st.plotly_chart(fig_aqi_bar, use_container_width=True)

        with col_aqi2:
            st.markdown("<div class='section-header'>PM2.5 vs PM10</div>", unsafe_allow_html=True)
            fig_pm = go.Figure()
            fig_pm.add_trace(go.Scatter(
                x=df_aqi["pm25"], y=df_aqi["pm10"],
                mode="markers+text",
                text=df_aqi["station"],
                textposition="top center",
                textfont=dict(size=10, color="#8b8fa8"),
                marker=dict(
                    size=df_aqi["aqi"] / 5,
                    color=df_aqi["aqi"],
                    colorscale=[[0,"#4ade80"],[0.5,"#fbbf24"],[1,"#f87171"]],
                    showscale=True,
                    colorbar=dict(title="AQI", tickfont=dict(color="#8b8fa8")),
                ),
                hovertemplate="%{text}<br>PM2.5: %{x}<br>PM10: %{y}<extra></extra>",
            ))
            fig_pm.update_layout(**PLOTLY_LAYOUT, height=380,
                                 title=dict(text="PM2.5 vs PM10（圓圈大小=AQI）", font=dict(size=13)),
                                 xaxis_title="PM2.5 (μg/m³)",
                                 yaxis_title="PM10 (μg/m³)")
            st.plotly_chart(fig_pm, use_container_width=True)

            # AQI summary
            st.markdown("<div class='section-header'>AQI 分級統計</div>", unsafe_allow_html=True)
            levels = {
                "🟢 良好 (<50)": len(df_aqi[df_aqi["aqi"] < 50]),
                "🟡 普通 (50-100)": len(df_aqi[(df_aqi["aqi"] >= 50) & (df_aqi["aqi"] < 100)]),
                "🟠 對敏感族群不健康 (>100)": len(df_aqi[df_aqi["aqi"] >= 100]),
            }
            for label, count in levels.items():
                st.markdown(f"""
                <div style='display:flex;justify-content:space-between;padding:8px 0;
                            border-bottom:1px solid #2a2d3e;font-size:0.9rem;'>
                  <span style='color:#c5cae9'>{label}</span>
                  <span style='color:#7c9ef5;font-weight:600'>{count} 站</span>
                </div>
                """, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# TAB 5: Combined Trend
# ─────────────────────────────────────────────────────────────────────────────
with tab5:
    st.markdown("<div class='section-header'>城市移動力綜合趨勢分析</div>", unsafe_allow_html=True)

    if not df_mrt_f.empty:
        # Year-over-year growth rate
        yearly = df_mrt_f.groupby(["year", "line"])["passengers"].sum().reset_index()
        yearly_total = df_mrt_f.groupby("year")["passengers"].sum().reset_index()
        yearly_total["growth"] = yearly_total["passengers"].pct_change() * 100

        col_t1, col_t2 = st.columns(2)

        with col_t1:
            fig_growth = go.Figure()
            colors_g = ["#f87171", "#fbbf24", "#4ade80", "#60a5fa", "#a78bfa"]
            for i, year in enumerate(yearly_total["year"].unique()):
                row = yearly_total[yearly_total["year"] == year]
                growth = row["growth"].values[0] if not row["growth"].isna().all() else 0
                fig_growth.add_trace(go.Bar(
                    x=[str(year)], y=[growth],
                    name=str(year),
                    marker_color=colors_g[i % len(colors_g)],
                    hovertemplate=f"{year}<br>YoY: %{{y:.1f}}%<extra></extra>"
                ))
            fig_growth.add_hline(y=0, line_color="#4a4d5e", line_width=1)
            fig_growth.update_layout(**PLOTLY_LAYOUT, height=300,
                                     title=dict(text="年增率 % (YoY)", font=dict(size=13)),
                                     showlegend=False, yaxis_title="年增率 (%)")
            st.plotly_chart(fig_growth, use_container_width=True)

        with col_t2:
            # Stacked area by line
            fig_area = go.Figure()
            for line in selected_lines:
                d = yearly[yearly["line"] == line]
                fig_area.add_trace(go.Scatter(
                    x=d["year"].astype(str), y=d["passengers"] / 1e6,
                    name=line, stackgroup="one", mode="none",
                    fillcolor=COLOR_LINE.get(line, "#888"),
                    hovertemplate="%{x}<br>%{y:.1f}M<extra>" + line + "</extra>"
                ))
            fig_area.update_layout(**PLOTLY_LAYOUT, height=300,
                                   title=dict(text="各路線旅次堆疊圖（百萬）", font=dict(size=13)))
            st.plotly_chart(fig_area, use_container_width=True)

        # MRT vs YouBike comparison
        st.markdown("<div class='section-header'>捷運 × YouBike 跨運具分析</div>", unsafe_allow_html=True)
        if not df_youbike.empty:
            col_t3, col_t4 = st.columns(2)

            with col_t3:
                # Stations near MRT
                stations_near = []
                for _, ybrow in df_youbike.iterrows():
                    name = ybrow["station_name"]
                    if "捷運" in name:
                        # find MRT station
                        for mrt_st in STATION_COORDS:
                            if mrt_st in name:
                                mrt_monthly = df_mrt_f[
                                    df_mrt_f["station"] == mrt_st
                                ]["passengers"].mean()
                                stations_near.append({
                                    "station": mrt_st,
                                    "mrt_avg_monthly": mrt_monthly / 1e3,
                                    "youbike_avail": ybrow["available_bikes"],
                                    "youbike_rate": ybrow["avail_rate"] if "avail_rate" in ybrow else 50,
                                })
                                break

                if stations_near:
                    df_cross = pd.DataFrame(stations_near)
                    fig_cross = px.scatter(
                        df_cross, x="mrt_avg_monthly", y="youbike_avail",
                        size="youbike_rate", color="youbike_rate",
                        color_continuous_scale=["#f87171", "#4ade80"],
                        text="station",
                        labels={
                            "mrt_avg_monthly": "捷運平均月旅次（千）",
                            "youbike_avail": "YouBike 可借車數",
                            "youbike_rate": "可借率 %"
                        },
                        title="捷運流量 vs YouBike 供給",
                        height=320,
                    )
                    fig_cross.update_traces(textposition="top center", textfont=dict(size=10))
                    fig_cross.update_layout(**PLOTLY_LAYOUT)
                    st.plotly_chart(fig_cross, use_container_width=True)
                else:
                    st.info("需要更多站點匹配資料")

            with col_t4:
                # YouBike district treemap
                if "avail_rate" in df_youbike.columns:
                    dist_summary = df_youbike.groupby("district").agg(
                        total=("total_bikes", "sum"),
                        available=("available_bikes", "sum"),
                    ).reset_index()
                    dist_summary["avail_rate"] = dist_summary["available"] / dist_summary["total"].replace(0,1) * 100

                    fig_tree = px.treemap(
                        dist_summary,
                        path=["district"],
                        values="total",
                        color="avail_rate",
                        color_continuous_scale=["#f87171", "#fbbf24", "#4ade80"],
                        range_color=[0, 100],
                        title="各行政區 YouBike 車位 × 可借率",
                        height=320,
                    )
                    fig_tree.update_layout(
                        paper_bgcolor="rgba(0,0,0,0)",
                        margin=dict(l=0, r=0, t=32, b=0),
                        coloraxis_colorbar=dict(
                            title="可借率%",
                            tickfont=dict(color="#8b8fa8")
                        )
                    )
                    st.plotly_chart(fig_tree, use_container_width=True)

    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align:center;color:#555870;font-size:0.78rem;padding:16px 0;'>
      Taipei Pulse 台北脈動 ·
      資料來源：台北捷運開放資料 / YouBike 2.0 / Open-Meteo / 環保署 AQI ·
      ETL Pipeline 每 5 分鐘自動刷新
    </div>
    """, unsafe_allow_html=True)
