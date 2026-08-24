import streamlit as st
import pandas as pd
import json
import os
import requests

st.set_page_config(page_title="台股動能 RS 綜合排行榜系統", layout="wide")

# ----------------- 1. 樣式設定 -----------------
st.markdown("""
<style>
.block-container {
    padding-top: 1rem !important;
    padding-bottom: 1.5rem !important;
}
[data-testid="stDataFrame"] {
    width: 100% !important;
}
</style>
""", unsafe_allow_html=True)

# ----------------- 2. 資料載入 -----------------
@st.cache_data(ttl=60)
def load_market_data():
    raw_data = None
    status_msg = "備援資料"

    if os.path.exists("market_rankings.json"):
        try:
            with open("market_rankings.json", "r", encoding="utf-8") as f:
                d = json.load(f)
                if isinstance(d, list) and len(d) > 0:
                    raw_data = d
                    status_msg = "本機檔案載入成功"
        except Exception:
            pass

    if not raw_data:
        try:
            url = "https://raw.githubusercontent.com/blue1998-glitch/-/main/market_rankings.json"
            res = requests.get(url, timeout=8)
            if res.status_code == 200:
                d = res.json()
                if isinstance(d, list) and len(d) > 0:
                    raw_data = d
                    status_msg = "GitHub 線上同步成功"
        except Exception:
            pass

    if not raw_data:
        raw_data = [
            {"symbol": "8033", "name": "雷虎", "market": "上市", "close_price": 62.0, "r_5d": 6.8, "r_20d": 16.0, "r_60d": 30.0, "score": 24.36, "rs_rating": 99, "main_industry": "其他"},
            {"symbol": "2645", "name": "長榮航太", "market": "上市", "close_price": 108.5, "r_5d": 3.2, "r_20d": 12.5, "r_60d": 25.0, "score": 18.39, "rs_rating": 94, "main_industry": "航運業"},
            {"symbol": "2330", "name": "台積電", "market": "上市", "close_price": 980.0, "r_5d": 4.5, "r_20d": 15.0, "r_60d": 32.0, "score": 22.00, "rs_rating": 98, "main_industry": "半導體業"}
        ]

    df = pd.DataFrame(raw_data)
    df["symbol"] = df["symbol"].astype(str)
    df["name"] = df["name"].astype(str)
    df["market"] = df.get("market", "上市").fillna("上市").astype(str)
    df["main_industry"] = df.get("main_industry", "其他").fillna("其他").astype(str)
    df["close_price"] = pd.to_numeric(df.get("close_price", 0.0), errors="coerce").fillna(0.0).round(2)
    df["r_5d"] = pd.to_numeric(df.get("r_5d", 0.0), errors="coerce").fillna(0.0).round(2)
    df["r_20d"] = pd.to_numeric(df.get("r_20d", 0.0), errors="coerce").fillna(0.0).round(2)
    df["r_60d"] = pd.to_numeric(df.get("r_60d", 0.0), errors="coerce").fillna(0.0).round(2)
    df["score"] = pd.to_numeric(df.get("score", 0.0), errors="coerce").fillna(0.0).round(2)
    df["rs_rating"] = pd.to_numeric(df.get("rs_rating", 50), errors="coerce").fillna(50).astype(int)

    return df, status_msg

df_market, db_status = load_market_data()

# ----------------- 3. 頂部狀態列與搜尋 -----------------
head_col1, head_col2 = st.columns([3, 1])
with head_col1:
    st.title("🎯 台股動能 RS 綜合排行榜")
    st.caption(f"🟢 資料庫：收錄 **{len(df_market)}** 檔股票 ｜ 狀態：`{db_status}`")
with head_col2:
    if st.button("🔄 重新整理"):
        st.cache_data.clear()
        st.rerun()

search_txt = st.text_input("🔍 個股搜尋 (輸入代碼如 2330 或名稱如 台積電):", "").strip()
if search_txt:
    matched = df_market[df_market["symbol"].str.contains(search_txt) | df_market["name"].str.contains(search_txt)]
    if not matched.empty:
        stk = matched.iloc[0]
        st.success(
            f"### 📍 【{stk['name']} ({stk['symbol']})】\n"
            f"* **RS 強勢評分**：`{stk['rs_rating']}` ｜ **綜合動能得分**：`{stk['score']:.2f}`\n"
            f"* **所屬產業**：`{stk['main_industry']} ({stk['market']})` ｜ **收盤價**：`${stk['close_price']:.2f}`\n"
            f"* **動能拆解**：近5日 `{stk['r_5d']:+.2f}%` ｜ 近1月 `{stk['r_20d']:+.2f}%` ｜ 近1季 `{stk['r_60d']:+.2f}%`"
        )

st.markdown("---")

# ----------------- 4. 篩選條件 -----------------
all_industries = sorted([i for i in df_market["main_industry"].unique() if i])

with st.expander("⚙️ 篩選條件 (RS 門檻、市場、產業)", expanded=True):
    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        rs_min_val = st.slider("最低 RS Rating 門檻", 1, 99, 80)
    with fc2:
        market_types = st.multiselect("上市 / 上櫃", ["上市", "上櫃"], default=["上市", "上櫃"])
    with fc3:
        main_ind_filter = st.selectbox("主產業篩選", ["全部"] + all_industries)

filtered_df = df_market[
    (df_market["rs_rating"] >= rs_min_val) &
    (df_market["market"].isin(market_types))
].copy()

if main_ind_filter != "全部":
    filtered_df = filtered_df[filtered_df["main_industry"] == main_ind_filter]

# 指標列
k1, k2, k3 = st.columns(3)
k1.metric("符合條件檔數", f"{len(filtered_df)} 檔")
k2.metric("平均 RS 評分", f"{filtered_df['rs_rating'].mean():.1f}" if not filtered_df.empty else "0")
k3.metric("RS ≥ 90 領袖股", f"{len(filtered_df[filtered_df['rs_rating'] >= 90])} 檔")

# ----------------- 5. 排行榜表格 -----------------
display_df = filtered_df.sort_values(by=["rs_rating", "score"], ascending=[False, False])[
    ["symbol", "name", "close_price", "score", "rs_rating", "r_5d", "r_20d", "r_60d", "main_industry", "market"]
].rename(
    columns={
        "symbol": "代號",
        "name": "名稱",
        "close_price": "收盤價",
        "score": "綜合動能",
        "rs_rating": "RS 強勢度",
        "r_5d": "近5日(%)",
        "r_20d": "近1月(%)",
        "r_60d": "近1季(%)",
        "main_industry": "所屬產業",
        "market": "市場"
    }
)

st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "RS 強勢度": st.column_config.ProgressColumn("RS 強勢度", format="%d", min_value=1, max_value=99)
    }
)
