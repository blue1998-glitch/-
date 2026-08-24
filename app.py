import streamlit as st
import pandas as pd
import json
import os
import requests

st.set_page_config(page_title="台股動能 RS 產業與順勢大師 VCP 題材系統", layout="wide")

# ----------------- 1. 手機極簡緊湊膠囊與自然滑動 CSS -----------------
st.markdown("""
<style>
div.stButton > button {
    width: 100% !important;
    min-height: 34px !important;
    height: 35px !important;
    border-radius: 6px !important;
    border: 1px solid #3b4252 !important;
    background: #1e222b !important;
    color: #e5e9f0 !important;
    font-size: 12px !important;
    font-weight: 500 !important;
    white-space: nowrap !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    padding: 1px 6px !important;
    margin-bottom: 2px !important;
    transition: all 0.1s ease-in-out !important;
}

div.stButton > button:hover {
    border-color: #88c0d0 !important;
    background: #2e3440 !important;
    color: #eceff4 !important;
}

.block-container {
    padding-top: 0.8rem !important;
    padding-bottom: 1.2rem !important;
    padding-left: 0.8rem !important;
    padding-right: 0.8rem !important;
}

[data-testid="stDataFrame"] {
    width: 100% !important;
    overflow-x: auto !important;
    -webkit-overflow-scrolling: touch !important;
}
</style>
""", unsafe_allow_html=True)

# ----------------- 2. 載入資料庫 -----------------
@st.cache_data(ttl=60)
def load_market_data():
    if os.path.exists("market_rankings.json"):
        try:
            with open("market_rankings.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    return pd.DataFrame(data), "本機檔案載入成功"
        except Exception:
            pass

    try:
        url = "https://raw.githubusercontent.com/blue1998-glitch/-/main/market_rankings.json"
        res = requests.get(url, timeout=8)
        if res.status_code == 200:
            data = res.json()
            if isinstance(data, list) and len(data) > 0:
                return pd.DataFrame(data), "GitHub 線上同步成功"
    except Exception:
        pass

    return pd.DataFrame([
        {"symbol": "8033", "name": "雷虎", "market": "上市", "close_price": 62.0, "r_5d": 6.8, "r_20d": 16.0, "r_60d": 30.0, "score": 24.36, "rs_rating": 99, "main_industry": "航太與國防", "sub_industry": "無人載具製造", "themes": ["軍用商規無人機"], "micro_themes": ["⭐ 歷史/區間新高", "軍用商規無人機"]},
        {"symbol": "2645", "name": "長榮航太", "market": "上市", "close_price": 108.5, "r_5d": 3.2, "r_20d": 12.5, "r_60d": 25.0, "score": 18.39, "rs_rating": 94, "main_industry": "航太與國防", "sub_industry": "航太維修與發動機製造", "themes": ["軍用商規無人機", "GE航太發動機供應鏈"], "micro_themes": ["🎯 VCP收縮蓄勢", "GE航太發動機供應鏈"]},
        {"symbol": "2330", "name": "台積電", "market": "上市", "close_price": 980.0, "r_5d": 4.5, "r_20d": 15.0, "r_60d": 32.0, "score": 22.00, "rs_rating": 98, "main_industry": "半導體業", "sub_industry": "晶圓代工龍頭", "themes": ["矽光子(CPO)", "CoWoS先進封裝"], "micro_themes": ["⭐ 歷史/區間新高", "矽光子(CPO)"]}
    ]), "備援範例資料"

df_market, db_status = load_market_data()

# ----------------- 3. 自適應雙軌題材動能計算引擎 -----------------
def calc_adaptive_theme_score(sub_df):
    sorted_rs = sorted(sub_df["rs_rating"].tolist(), reverse=True)
    n = len(sorted_rs)
    if n == 0:
        return 0.0, "📦 潛伏盤整", 0, 0, 0.0
    
    top1_rs = sorted_rs[0]
    strong_stocks = [r for r in sorted_rs if r >= 80]
    strong_count = len(strong_stocks)

    if n == 1:
        base_top = float(top1_rs)
    elif n == 2:
        base_top = float(sorted_rs[0] * 0.65 + sorted_rs[1] * 0.35)
    else:
        base_top = float(sorted_rs[0] * 0.50 + sorted_rs[1] * 0.30 + sorted_rs[2] * 0.20)

    smoothed_rate = (strong_count + 0.4) / (n + 2)
    depth_ratio = min(strong_count, 4) / 4.0
    resonance_multiplier = 1.0 + (0.12 * smoothed_rate + 0.06 * depth_ratio)

    vanguard_score = top1_rs * 0.92
    resonance_score = base_top * resonance_multiplier
    final_score = max(vanguard_score, resonance_score)

    raw_rate = strong_count / n
    if top1_rs >= 90 and raw_rate <= 0.34 and strong_count <= 2:
        stage_badge = "🚀 先鋒突圍"
    elif top1_rs >= 85 and (raw_rate >= 0.35 or strong_count >= 3):
        stage_badge = "🔥 集團共振"
    elif strong_count >= 2:
        stage_badge = "⚡ 補漲擴散"
    else:
        stage_badge = "📦 潛伏盤整"

    return round(final_score, 1), stage_badge, top1_rs, strong_count, round(base_top, 1)

all_themes = sorted(list(set(t for sublist in df_market["themes"] for t in sublist if t)))
theme_stats = []
theme_badge_map = {}
theme_score_map = {}

for th in all_themes:
    sub_df = df_market[df_market["themes"].apply(lambda tags: th in tags)]
    if not sub_df.empty:
        f_score, badge, top1, strong_cnt, base_top = calc_adaptive_theme_score(sub_df)
        theme_score_map[th] = f_score
        theme_badge_map[th] = badge
        theme_stats.append({
            "theme": th,
            "final_score": f_score,
            "stage_badge": badge,
            "top1_rs": top1,
            "strong_count": strong_cnt,
            "base_top": base_top,
            "total_count": len(sub_df)
        })

df_theme_ranked = pd.DataFrame(theme_stats).sort_values(by="final_score", ascending=False)

# 產業統計
all_industries = sorted(df_market["main_industry"].unique().tolist())
industry_stats = []
ind_rs_map = {}

for ind in all_industries:
    sub_df = df_market[df_market["main_industry"] == ind]
    if not sub_df.empty:
        avg_rs = sub_df["rs_rating"].mean()
        ind_rs_map[ind] = avg_rs
        industry_stats.append({
            "industry": ind,
            "avg_rs": avg_rs,
            "t1_count": len(sub_df[sub_df["rs_rating"] >= 90]),
            "total_count": len(sub_df)
        })

df_industry_ranked = pd.DataFrame(industry_stats).sort_values(by="avg_rs", ascending=False)

def assign_stock_badge(row):
    stock_themes = row.get("themes", [])
    rs = row.get("rs_rating", 50)
    if not stock_themes:
        return "📦 潛伏盤整"
    badges = [theme_badge_map.get(t, "📦 潛伏盤整") for t in stock_themes]
    if "🔥 集團共振" in badges and rs >= 80:
        return "🔥 集團共振"
    elif "🚀 先鋒突圍" in badges and rs >= 90:
        return "🚀 先鋒突圍"
    elif any(b in ["🔥 集團共振", "🚀 先鋒突圍", "⚡ 補漲擴散"] for b in badges) and rs >= 75:
        return "⚡ 補漲擴散"
    elif "⚡ 補漲擴散" in badges and rs >= 70:
        return "⚡ 補漲擴散"
    else:
        return "📦 潛伏盤整"

df_market["共振"] = df_market.apply(assign_stock_badge, axis=1)

# 初始化狀態
if "selected_theme" not in st.session_state:
    st.session_state.selected_theme = df_theme_ranked["theme"].iloc[0] if not df_theme_ranked.empty else "軍用商規無人機"
if "selected_industry" not in st.session_state:
    st.session_state.selected_industry = df_industry_ranked["industry"].iloc[0] if not df_industry_ranked.empty else "航太與國防"

# ----------------- 4. 嚴格依資料長度適度配置（前短後長，自然滑動） -----------------
NATURAL_FIT_CONFIG = {
    "代號": st.column_config.TextColumn("代號", width="small"),
    "名稱": st.column_config.TextColumn("名稱", width="small"),
    "收盤價": st.column_config.NumberColumn("收盤價", width="small", format="%.2f"),
    "綜合動能": st.column_config.NumberColumn("綜合動能", width="small", format="%.2f"),
    "RS 強勢度": st.column_config.ProgressColumn("RS 強勢度", width="small", format="%d", min_value=1, max_value=99),
    "共振": st.column_config.TextColumn("共振", width="small"),
    "詳細業務特徵": st.column_config.TextColumn("詳細業務特徵", width="large")
}

# ----------------- 5. 頂部狀態列與萬用搜尋 -----------------
head_col1, head_col2 = st.columns([3, 1])
with head_col1:
    st.title("🎯 台股 RS 動能：自適應雙軌題材與 VCP 系統")
    st.caption(f"🟢 資料庫：收錄 **{len(df_market)}** 檔股票 ｜ **{len(all_themes)}** 個非重複題材 ｜ 狀態：`{db_status}`")
with head_col2:
    if st.button("🔄 盤中即時重新整理"):
        st.cache_data.clear()
        st.rerun()

search_txt = st.text_input("🔍 萬用個股搜尋 (輸入代碼如 2645 或名稱如 長榮航太):", "").strip()
if search_txt:
    matched = df_market[df_market["symbol"].str.contains(search_txt) | df_market["name"].str.contains(search_txt)]
    if not matched.empty:
        stk = matched.iloc[0]
        ind_avg = ind_rs_map.get(stk['main_industry'], 0)
        theme_str = "、".join(stk["themes"]) if stk["themes"] else "一般產業標的"
        micro_str = " | ".join([f"🎯 {m}" for m in stk["micro_themes"]]) if stk["micro_themes"] else "標準業務"

        with st.container():
            st.success(
                f"### 📍 【{stk['name']} ({stk['symbol']})】\n"
                f"* **動能狀態**：`{stk['共振']}` | **RS 強勢評分**：`{stk['rs_rating']}` | **VCP 動能得分**：`{stk.get('score', 0):.2f}`\n"
                f"* **縱向產業**：`{stk['main_industry']} (產業均分: {ind_avg:.1f})` ➔ `{stk['sub_industry']}`\n"
                f"* **涵蓋題材**：`{theme_str}`\n"
                f"* **型態與特徵**：`{micro_str}`\n"
                f"* **動能拆解**：近5日 `{stk.get('r_5d', 0):+.2f}%` | 近1月 `{stk.get('r_20d', 0):+.2f}%` | 近1季 `{stk.get('r_60d', 0):+.2f}%`"
            )
            
            if stk['themes']:
                st.write("👉 **點擊題材標籤快速置頂穿透：**")
                b_cols = st.columns(len(stk['themes']) + 1)
                with b_cols[0]:
                    if st.button(f"🏭 {stk['main_industry']}", key=f"s_btn_ind_{stk['symbol']}"):
                        st.session_state.selected_industry = stk['main_industry']
                        st.rerun()
                for idx, tag in enumerate(stk['themes']):
                    with b_cols[idx + 1]:
                        if st.button(f"🔥 {tag}", key=f"s_btn_t_{stk['symbol']}_{tag}"):
                            st.session_state.selected_theme = tag
                            st.rerun()

st.markdown("---")

# ----------------- 6. 主導航分頁 -----------------
tab1, tab2, tab3, tab4 = st.tabs([
    "🔥 自適應雙軌題材庫 (置頂成分股)",
    "🏭 產業視角 (看法定類股輪動)",
    "⚡ 主流領袖專區 (先鋒突圍+集團共振)",
    "🏆 全市場 RS 總榜"
])

# =========================================================
# TAB 1: 自適應雙軌題材庫
# =========================================================
with tab1:
    cur_t = st.session_state.selected_theme
    t_constituents = df_market[df_market["themes"].apply(lambda tags: cur_t in tags)].sort_values(by=["rs_rating", "score"], ascending=[False, False]).copy()

    cur_t_info = df_theme_ranked[df_theme_ranked["theme"] == cur_t]
    if not cur_t_info.empty:
        t_row = cur_t_info.iloc[0]
        cur_badge = t_row["stage_badge"]
        cur_score = t_row["final_score"]
        cur_top1 = t_row["top1_rs"]
        cur_strong = t_row["strong_count"]
    else:
        cur_badge, cur_score, cur_top1, cur_strong = "📦 潛伏盤整", 0.0, 0, 0

    st.markdown(f"### 📋 【{cur_t}】 題材成分股真實動能明細 (依 RS 評分排序)")

    covered_inds = t_constituents["main_industry"].value_counts().to_dict()
    covered_str = " | ".join([f"{k} ({v}檔)" for k, v in covered_inds.items()])

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("當前題材與階段", cur_t, cur_badge)
    k1.caption(f"橫跨產業: {covered_str}")
    k2.metric("題材雙軌總分", f"{cur_score} 分")
    k3.metric("先鋒龍頭 RS", f"{cur_top1} 分")
    k4.metric("RS ≥ 80 強勢股", f"{cur_strong} / {len(t_constituents)} 檔")

    t_constituents["詳細業務特徵"] = t_constituents["micro_themes"].apply(
        lambda tags: " | ".join([f"🎯 {t}" if not t.startswith("⭐") and not t.startswith("🎯") and not t.startswith("🚀") and not t.startswith("⚠️") else t for t in tags]) if tags else "—"
    )

    display_t_df = t_constituents[
        ["symbol", "name", "close_price", "score", "rs_rating", "共振", "詳細業務特徵"]
    ].rename(
        columns={
            "symbol": "代號",
            "name": "名稱",
            "close_price": "收盤價",
            "score": "綜合動能",
            "rs_rating": "RS 強勢度",
            "共振": "共振",
            "詳細業務特徵": "詳細業務特徵"
        }
    )

    st.dataframe(
        display_t_df,
        use_container_width=False,
        hide_index=True,
        column_config=NATURAL_FIT_CONFIG
    )

    st.markdown("---")

    t_header_c1, t_header_c2 = st.columns([2, 1])
    with t_header_c1:
        st.subheader(f"⚡ 全市場動態題材庫 (共收錄 {len(df_theme_ranked)} 個非重複題材，依雙軌動能排序)")
    with t_header_c2:
        theme_search = st.text_input("🔍 過濾題材名稱 (如：散熱、低軌、無人機、半導體):", "").strip()

    filtered_themes_df = df_theme_ranked
    if theme_search:
        filtered_themes_df = df_theme_ranked[df_theme_ranked["theme"].str.contains(theme_search, case=False)]

    cols_per_row = 3
    for row_idx in range(0, len(filtered_themes_df), cols_per_row):
        cols = st.columns(cols_per_row)
        for col_idx in range(cols_per_row):
            idx = row_idx + col_idx
            if idx < len(filtered_themes_df):
                item = filtered_themes_df.iloc[idx]
                t_name = item["theme"]
                t_score = item["final_score"]
                t_badge = item["stage_badge"]
                t_strong = item["strong_count"]
                t_cnt = item["total_count"]
                is_active = "▶ " if t_name == cur_t else ""
                btn_label = f"{is_active}{t_badge} {t_name} | {t_score}分 (強勢:{t_strong}/{t_cnt})"
                with cols[col_idx]:
                    if st.button(btn_label, key=f"tab1_p_{t_name}"):
                        st.session_state.selected_theme = t_name
                        st.rerun()

# =========================================================
# TAB 2: 產業視角
# =========================================================
with tab2:
    cur_ind = st.session_state.selected_industry
    ind_constituents = df_market[df_market["main_industry"] == cur_ind].sort_values(by=["rs_rating", "score"], ascending=[False, False]).copy()

    st.markdown(f"### 📋 【{cur_ind}】 產業成分股明細")

    i1, i2, i3, i4 = st.columns(4)
    i1.metric("鎖定產業", cur_ind)
    i2.metric("產業成分股", f"{len(ind_constituents)} 檔")
    i3.metric("產業平均 RS", f"{ind_constituents['rs_rating'].mean():.1f}" if not ind_constituents.empty else "0")
    i4.metric("RS ≥ 90 領袖股", f"{len(ind_constituents[ind_constituents['rs_rating'] >= 90])} 檔")

    ind_constituents["詳細業務特徵"] = ind_constituents["micro_themes"].apply(
        lambda tags: " | ".join([f"🎯 {t}" if not t.startswith("⭐") and not t.startswith("🎯") and not t.startswith("🚀") and not t.startswith("⚠️") else t for t in tags]) if tags else "—"
    )

    display_ind_df = ind_constituents[
        ["symbol", "name", "close_price", "score", "rs_rating", "共振", "詳細業務特徵"]
    ].rename(
        columns={
            "symbol": "代號",
            "name": "名稱",
            "close_price": "收盤價",
            "score": "綜合動能",
            "rs_rating": "RS 強勢度",
            "共振": "共振",
            "詳細業務特徵": "詳細業務特徵"
        }
    )

    st.dataframe(
        display_ind_df,
        use_container_width=False,
        hide_index=True,
        column_config=NATURAL_FIT_CONFIG
    )

    st.markdown("---")
    st.subheader("🏭 快速切換法定產業 (依產業輪動強弱排序)")
    for row_idx in range(0, len(df_industry_ranked), cols_per_row):
        cols = st.columns(cols_per_row)
        for col_idx in range(cols_per_row):
            idx = row_idx + col_idx
            if idx < len(df_industry_ranked):
                item = df_industry_ranked.iloc[idx]
                i_name = item["industry"]
                i_avg = item["avg_rs"]
                i_cnt = item["total_count"]
                icon = "🔥" if i_avg >= 80 else ("⚡" if i_avg >= 60 else "📦")
                is_active = "▶ " if i_name == cur_ind else ""
                btn_label = f"{is_active}{icon} {i_name} | {i_avg:.1f} ({i_cnt}檔)"
                with cols[col_idx]:
                    if st.button(btn_label, key=f"tab2_p_{i_name}"):
                        st.session_state.selected_industry = i_name
                        st.rerun()

# =========================================================
# TAB 3: 主流領袖專區 (先鋒突圍 + 集團共振)
# =========================================================
with tab3:
    st.subheader("⚡ 全市場「主流領袖」超級專區")
    st.caption("條件：個股所屬題材處於【🚀 先鋒突圍】或【🔥 集團共振】階段，且個股動能居於引領地位")

    leading_df = df_market[df_market["共振"].isin(["🚀 先鋒突圍", "🔥 集團共振"])].sort_values(by=["rs_rating", "score"], ascending=[False, False]).copy()

    r1, r2, r3 = st.columns(3)
    r1.metric("主流領袖標的", f"{len(leading_df)} 檔")
    r1.caption("先鋒與共振核心部隊")
    r2.metric("領袖股平均 RS", f"{leading_df['rs_rating'].mean():.1f}" if not leading_df.empty else "0")
    r3.metric("平均動能得分", f"{leading_df['score'].mean():.2f}" if not leading_df.empty else "0")

    leading_df["詳細業務特徵"] = leading_df["micro_themes"].apply(
        lambda tags: " | ".join([f"🎯 {t}" if not t.startswith("⭐") and not t.startswith("🎯") and not t.startswith("🚀") and not t.startswith("⚠️") else t for t in tags])
    )

    display_lead_df = leading_df[
        ["symbol", "name", "close_price", "score", "rs_rating", "共振", "詳細業務特徵"]
    ].rename(
        columns={
            "symbol": "代號",
            "name": "名稱",
            "close_price": "收盤價",
            "score": "綜合動能",
            "rs_rating": "RS 強勢度",
            "共振": "共振",
            "詳細業務特徵": "詳細業務特徵"
        }
    )

    st.dataframe(
        display_lead_df,
        use_container_width=False,
        hide_index=True,
        column_config=NATURAL_FIT_CONFIG
    )

# =========================================================
# TAB 4: 全市場真實 RS 排行榜
# =========================================================
with tab4:
    st.subheader("🏆 全市場真實 RS 動能綜合排行榜")
    
    with st.expander("⚙️ 篩選條件 (RS 門檻、市場、產業)", expanded=True):
        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            rs_min_val = st.slider("最低 RS Rating 門檻", 1, 99, 80, key="all_rs_slider")
        with fc2:
            market_types = st.multiselect("上市 / 上櫃", ["上市", "上櫃"], default=["上市", "上櫃"], key="all_market_types")
        with fc3:
            main_ind_filter = st.selectbox("主產業篩選", ["全部"] + all_industries, key="all_main_filter")

    all_filtered = df_market[
        (df_market["rs_rating"] >= rs_min_val) &
        (df_market["market"].isin(market_types))
    ].copy()

    if main_ind_filter != "全部":
        all_filtered = all_filtered[all_filtered["main_industry"] == main_ind_filter]

    k1, k2, k3 = st.columns(3)
    k1.metric("符合條件檔數", f"{len(all_filtered)} 檔")
    k2.metric("平均 RS 評分", f"{all_filtered['rs_rating'].mean():.1f}" if not all_filtered.empty else "0")
    k3.metric("RS ≥ 90 領袖股檔數", f"{len(all_filtered[all_filtered['rs_rating'] >= 90])} 檔")

    all_filtered["詳細業務特徵"] = all_filtered["micro_themes"].apply(
        lambda tags: " | ".join([f"🎯 {t}" if not t.startswith("⭐") and not t.startswith("🎯") and not t.startswith("🚀") and not t.startswith("⚠️") else t for t in tags]) if tags else "—"
    )
    
    view_all_df = all_filtered.sort_values(by=["rs_rating", "score"], ascending=[False, False])[
        ["symbol", "name", "close_price", "score", "rs_rating", "共振", "詳細業務特徵"]
    ].rename(
        columns={
            "symbol": "代號",
            "name": "名稱",
            "close_price": "收盤價",
            "score": "綜合動能",
            "rs_rating": "RS 強勢度",
            "共振": "共振",
            "詳細業務特徵": "詳細業務特徵"
        }
    )

    st.dataframe(
        view_all_df,
        use_container_width=False,
        hide_index=True,
        column_config=NATURAL_FIT_CONFIG
    )
