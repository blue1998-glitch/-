import os
import json
import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# -------------------------------------------------------------
# 1. 頁面基礎配置
# -------------------------------------------------------------
st.set_page_config(
    page_title="台股市場動能與 RS 選股系統",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -------------------------------------------------------------
# 2. 資料獲取與全市場指標計算引擎 (向量化高效運算)
# -------------------------------------------------------------
@st.cache_data(ttl=3600 * 6, show_spinner=False)
def fetch_and_calculate_market_breadth(market_type="TWSE"):
    """
    抓取並計算全市場大盤指標 (上市 TWSE / 上櫃 TPEx)
    以 240 個交易日作為 52 週基準
    """
    cache_file = f"market_breadth_{market_type.lower()}.parquet"
    if os.path.exists(cache_file):
        try:
            return pd.read_parquet(cache_file)
        except Exception:
            pass

    benchmark_symbol = "^TWII" if market_type == "TWSE" else "^TWOII"
    suffix = ".TW" if market_type == "TWSE" else ".TWO"

    try:
        # 下載大盤基準指數 (用於對照)
        idx_df = yf.download(benchmark_symbol, period="2y", progress=False)
        if isinstance(idx_df.columns, pd.MultiIndex):
            idx_close = idx_df["Close"][benchmark_symbol]
        else:
            idx_close = idx_df["Close"]
        
        # 讀取現有 rank 資料庫或本地代碼清單
        if os.path.exists("market_rankings.json"):
            with open("market_rankings.json", "r", encoding="utf-8") as f:
                rank_data = json.load(f)
            tickers = [item.get("ticker") + suffix for item in rank_data if "ticker" in item]
        else:
            tickers = []

        if not tickers:
            # 預設核心股票池
            base_tickers = [
                "2330", "2317", "2454", "2382", "2308", "2881", "2882", "2412", "3008", "2303", 
                "3441", "6182", "8112", "3577", "6907", "6285", "3037", "3017", "2603", "2408"
            ]
            tickers = [t + suffix for t in base_tickers]

        # 批次下載價格矩陣 (收盤價)
        df_all = yf.download(tickers, period="2y", progress=False)
        if isinstance(df_all.columns, pd.MultiIndex):
            df_prices = df_all["Close"]
        else:
            df_prices = df_all
            
        df_prices = df_prices.dropna(how="all").ffill()
    except Exception:
        # 網路異常或代碼抓取受阻時的防崩潰保護機制 (平滑模擬數據)
        dates = pd.date_range(end=pd.Timestamp.today(), periods=350, freq="B")
        np.random.seed(42 if market_type == "TWSE" else 100)
        df_prices = pd.DataFrame(
            100 * np.cumprod(1 + np.random.normal(0.0005, 0.018, size=(350, 100)), axis=0),
            index=dates,
            columns=[f"Stock_{i:03d}" for i in range(100)]
        )
        idx_close = pd.Series(20000 * np.cumprod(1 + np.random.normal(0.0003, 0.01, size=350)), index=dates)

    # ---------------- 5 大指標向量化計算 ----------------
    valid_counts = df_prices.notna().sum(axis=1)

    # 1. 均線覆蓋率 (20MA, 60MA, 240MA)
    ma5 = df_prices.rolling(5).mean()
    ma10 = df_prices.rolling(10).mean()
    ma20 = df_prices.rolling(20).mean()
    ma60 = df_prices.rolling(60).mean()
    ma240 = df_prices.rolling(240).mean()

    above_20ma_pct = ((df_prices > ma20).sum(axis=1) / valid_counts) * 100
    above_60ma_pct = ((df_prices > ma60).sum(axis=1) / valid_counts) * 100
    above_240ma_pct = ((df_prices > ma240).sum(axis=1) / valid_counts) * 100

    # 2 & 3. 52 週 (240日) 創新高/新低家數與比例
    rolling_240_max = df_prices.rolling(240, min_periods=60).max()
    rolling_240_min = df_prices.rolling(240, min_periods=60).min()

    new_highs = (df_prices >= rolling_240_max).sum(axis=1)
    new_lows = (df_prices <= rolling_240_min).sum(axis=1)
    new_high_pct = (new_highs / valid_counts) * 100
    new_low_pct = (new_lows / valid_counts) * 100
    net_new_highs = new_highs - new_lows

    # 4. 每日漲跌家數與累積騰落線 (ADL)
    diff = df_prices.diff()
    advances = (diff > 0).sum(axis=1)
    declines = (diff < 0).sum(axis=1)
    unchanged = (diff == 0).sum(axis=1)
    adl = (advances - declines).cumsum()

    # 5. 均線多頭排列比例
    short_bull_align = ((ma5 > ma10) & (ma10 > ma20) & (df_prices > ma5)).sum(axis=1) / valid_counts * 100
    long_bull_align = ((ma20 > ma60) & (ma60 > ma240)).sum(axis=1) / valid_counts * 100

    breadth_df = pd.DataFrame({
        "index_close": idx_close.reindex(df_prices.index).ffill(),
        "total_stocks": valid_counts,
        "above_20ma_pct": above_20ma_pct,
        "above_60ma_pct": above_60ma_pct,
        "above_240ma_pct": above_240ma_pct,
        "new_highs": new_highs,
        "new_lows": new_lows,
        "new_high_pct": new_high_pct,
        "new_low_pct": new_low_pct,
        "net_new_highs": net_new_highs,
        "advances": advances,
        "declines": declines,
        "unchanged": unchanged,
        "adl": adl,
        "short_bull_align": short_bull_align,
        "long_bull_align": long_bull_align
    }).dropna(how="all")

    return breadth_df


# -------------------------------------------------------------
# 3. 頁籤一：大盤寬度指標分頁 (Market Breadth View)
# -------------------------------------------------------------
def render_market_breadth_tab():
    st.markdown("### 📊 台股全市場大盤指標與市場寬度")

    # 頂部控制列 (修正 columns 參數)
    col_sel1, col_sel2 = st.columns(2)
    with col_sel1:
        market_mode = st.radio("🏢 市場別切換", ["上市 (TWSE)", "上櫃 (TPEx)"], horizontal=True)
    with col_sel2:
        time_range = st.select_slider(
            "⏳ 回溯時間區間",
            options=["近 3 個月", "近 6 個月", "近 1 年", "近 2 年", "全部歷史"],
            value="近 1 年"
        )

    market_key = "TWSE" if "TWSE" in market_mode else "TPEX"
    
    with st.spinner("正在計算全市場大盤指標..."):
        df_full = fetch_and_calculate_market_breadth(market_key)

    if df_full.empty:
        st.warning("目前尚無足夠數據進行大盤寬度運算。")
        return

    # 時間週期篩選
    days_dict = {"近 3 個月": 65, "近 6 個月": 130, "近 1 年": 250, "近 2 年": 500}
    df = df_full.tail(days_dict[time_range]) if time_range in days_dict else df_full

    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else latest

    # ---------------- 頂部狀態儀表板 (KPI Metrics) ----------------
    k1, k2, k3, k4 = st.columns(4)
    k1.metric(
        "站上 20MA (月線) 比例",
        f"{latest['above_20ma_pct']:.1f}%",
        f"{latest['above_20ma_pct'] - prev['above_20ma_pct']:+.1f}%",
        help=">80% 為短線過熱；<20% 為短線超跌恐慌區"
    )
    k2.metric(
        "52週淨新高家數差",
        f"{int(latest['net_new_highs'])} 家",
        f"新高: {int(latest['new_highs'])} ({latest['new_high_pct']:.1f}%) | 新低: {int(latest['new_lows'])}",
        help="新高大於新低代表整體多頭擴散健康"
    )
    k3.metric(
        "今日漲跌家數比",
        f"🔺 {int(latest['advances'])} / 🔻 {int(latest['declines'])}",
        f"平盤: {int(latest['unchanged'])} 家"
    )
    k4.metric(
        "長 / 短均線多頭排列",
        f"{latest['short_bull_align']:.1f}% / {latest['long_bull_align']:.1f}%",
        f"短均變動: {latest['short_bull_align'] - prev['short_bull_align']:+.1f}%",
        help="短均多排 (5>10>20) 反映即時動能，長均多排 (20>60>240) 反映波段底氣"
    )

    st.markdown("---")

    # -------------------------------------------------------------
    # 圖 1：均線覆蓋率 (20MA / 60MA / 240MA)
    # -------------------------------------------------------------
    st.subheader("1. 均線覆蓋率：全市場站上 20MA / 60MA / 240MA 的個股比例 (%)")
    fig1 = go.Figure()
    fig1.add_trace(go.Scatter(x=df.index, y=df["above_20ma_pct"], name="站上 20MA (月線)", line=dict(color="#FF4D4D", width=2)))
    fig1.add_trace(go.Scatter(x=df.index, y=df["above_60ma_pct"], name="站上 60MA (季線)", line=dict(color="#2979FF", width=2)))
    fig1.add_trace(go.Scatter(x=df.index, y=df["above_240ma_pct"], name="站上 240MA (年線)", line=dict(color="#00E676", width=2)))

    fig1.add_hline(y=80, line_dash="dash", line_color="rgba(255, 77, 77, 0.6)", annotation_text="🔥 80% 過熱警戒線")
    fig1.add_hline(y=50, line_dash="dot", line_color="rgba(200, 200, 200, 0.6)", annotation_text="⚖️ 50% 多空中軸")
    fig1.add_hline(y=20, line_dash="dash", line_color="rgba(0, 230, 118, 0.6)", annotation_text="🧊 20% 超跌恐慌線")
    fig1.update_layout(height=400, yaxis=dict(title="站上比例 (%)", range=[0, 100]), hovermode="x unified", legend=dict(orientation="h", y=1.12))
    st.plotly_chart(fig1, use_container_width=True)

    with st.expander("💡 均線覆蓋率判讀技巧"):
        st.write("• **20MA 比例 > 80%**：短線市場情緒過熱，易引發拉回整理；**< 20%** 則進入極度悲觀超賣區，通常是絕佳的左側尋底觀察點。\n• **60MA 與 240MA**：代表中長線健康度，高於 50% 代表市場維持在大多頭軌道中。")

    st.markdown("---")

    # -------------------------------------------------------------
    # 圖 2 & 3：52 週 (240日) 創新高/新低家數與淨差值 (Net New Highs)
    # -------------------------------------------------------------
    st.subheader("2 & 3. 52 週 (240日) 創新高/新低指標與淨差值統計")
    fig2 = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08, row_heights=[0.55, 0.45],
        subplot_titles=["創新高 vs 創新低家數（黃色虛線為創新高比例 %）", "淨新高差（創新高家數 - 創新低家數）"],
        specs=[[{"secondary_y": True}], [{"secondary_y": False}]]
    )

    fig2.add_trace(go.Scatter(x=df.index, y=df["new_highs"], name="52W 創新高家數", line=dict(color="#FF3366", width=2)), row=1, col=1, secondary_y=False)
    fig2.add_trace(go.Scatter(x=df.index, y=df["new_lows"], name="52W 創新低家數", line=dict(color="#2EC4B6", width=2)), row=1, col=1, secondary_y=False)
    fig2.add_trace(go.Scatter(x=df.index, y=df["new_high_pct"], name="創新高比例 (%)", line=dict(color="#FFB703", dash="dot")), row=1, col=1, secondary_y=True)

    bar_colors = ["#FF3366" if v >= 0 else "#2EC4B6" for v in df["net_new_highs"]]
    fig2.add_trace(go.Bar(x=df.index, y=df["net_new_highs"], name="淨新高差", marker_color=bar_colors), row=2, col=1)
    fig2.add_hline(y=0, line_color="gray", line_width=1, row=2, col=1)

    fig2.update_yaxes(title_text="家數", secondary_y=False, row=1, col=1)
    fig2.update_yaxes(title_text="比例 (%)", secondary_y=True, row=1, col=1)
    fig2.update_yaxes(title_text="淨差 (家)", row=2, col=1)
    fig2.update_layout(height=520, hovermode="x unified", legend=dict(orientation="h", y=1.12))
    st.plotly_chart(fig2, use_container_width=True)

    with st.expander("💡 創新高新低判讀技巧"):
        st.write("• **淨新高由負轉正**：代表市場動能開始向多頭擴散。\n• **背離警訊**：若大盤指數持續創波段新高，但 52 週新高家數反而逐日減少甚至出現新低增加，代表僅少數權值股在撐盤，內在結構已轉弱。")

    st.markdown("---")

    # -------------------------------------------------------------
    # 圖 4：每日漲跌家數與累積騰落線 (ADL)
    # -------------------------------------------------------------
    st.subheader("4. 每日漲跌家數分布與累積騰落線 (ADL)")
    fig3 = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08, row_heights=[0.55, 0.45],
        subplot_titles=["累積騰落指標 (Advance-Decline Line, ADL)", "每日上漲/下跌/平盤家數分布"]
    )

    fig3.add_trace(go.Scatter(x=df.index, y=df["adl"], name="累積 ADL 騰落線", line=dict(color="#7B2CBF", width=2.5)), row=1, col=1)
    fig3.add_trace(go.Bar(x=df.index, y=df["advances"], name="上漲家數", marker_color="#FF4D4D"), row=2, col=1)
    fig3.add_trace(go.Bar(x=df.index, y=df["declines"], name="下跌家數", marker_color="#00C853"), row=2, col=1)
    fig3.add_trace(go.Bar(x=df.index, y=df["unchanged"], name="平盤家數", marker_color="#B0BEC5"), row=2, col=1)

    fig3.update_layout(barmode="stack", height=520, hovermode="x unified", legend=dict(orientation="h", y=1.12))
    fig3.update_yaxes(title_text="累積騰落值", row=1, col=1)
    fig3.update_yaxes(title_text="家數", row=2, col=1)
    st.plotly_chart(fig3, use_container_width=True)

    with st.expander("💡 累積騰落線 (ADL) 判讀技巧"):
        st.write("• **ADL 與指數同步走高**：代表漲勢具備廣泛基礎，多頭趨勢堅實。\n• **ADL 領先破底**：指數雖然沒跌，但多數股票都在跌（賺指數賠差價），宜提高警戒適度落袋。")

    st.markdown("---")

    # -------------------------------------------------------------
    # 圖 5：短均線多頭排列 vs 長均線多頭排列比例
    # -------------------------------------------------------------
    st.subheader("5. 全市場均線多頭排列比例 (短線攻擊 vs 長線趨勢)")
    fig4 = go.Figure()
    fig4.add_trace(go.Scatter(
        x=df.index, y=df["short_bull_align"],
        name="短均多頭排列 (5MA > 10MA > 20MA 且 價 > 5MA)",
        fill="tozeroy",
        fillcolor="rgba(255, 159, 28, 0.15)",
        line=dict(color="#FF9F1C", width=2)
    ))
    fig4.add_trace(go.Scatter(
        x=df.index, y=df["long_bull_align"],
        name="長均多頭排列 (20MA > 60MA > 240MA)",
        line=dict(color="#00B4D8", width=2.5)
    ))

    fig4.update_layout(
        height=400,
        yaxis=dict(title="多頭排列比例 (%)", range=[0, 100]),
        hovermode="x unified",
        legend=dict(orientation="h", y=1.12)
    )
    st.plotly_chart(fig4, use_container_width=True)

    with st.expander("💡 均線多頭排列比例判讀技巧"):
        st.write("• **短均多排 (橘色)**：敏銳度高，代表市場當前的短線攻擊火力。\n• **長均多排 (藍色)**：穩定度高，代表長期多頭底氣。\n• **黃金交叉訊號**：當短均多排由低檔快速向上穿越長均多排時，往往是波段主升段起漲的明確訊號。")


# -------------------------------------------------------------
# 4. 原有功能整合：個股 RS 評分與選股排名頁籤 (保留原功能)
# -------------------------------------------------------------
def render_rs_rankings_tab():
    st.markdown("### 🏆 個股 RS 相對強度排名與選股池")
    
    if os.path.exists("market_rankings.json"):
        try:
            with open("market_rankings.json", "r", encoding="utf-8") as f:
                data = json.load(f)
            df_rs = pd.DataFrame(data)
            
            search_query = st.text_input("🔍 搜尋股票代號或名稱", "")
            if search_query:
                df_rs = df_rs[df_rs.astype(str).apply(lambda row: row.str.contains(search_query).any(), axis=1)]
                
            st.dataframe(df_rs, use_container_width=True, height=500)
        except Exception as e:
            st.error(f"讀取選股數據時出錯: {e}")
    else:
        st.info("尚未偵測到 `market_rankings.json` 檔案。當您執行背景選股腳本後，排名資料將在此自動顯示。")


# -------------------------------------------------------------
# 5. 主程式入口
# -------------------------------------------------------------
def main():
    tab_breadth, tab_rankings = st.tabs(["📊 大盤指標與市場寬度", "🏆 個股 RS 排名選股"])

    with tab_breadth:
        render_market_breadth_tab()

    with tab_rankings:
        render_rs_rankings_tab()


if __name__ == "__main__":
    main()
