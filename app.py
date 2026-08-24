import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, date, timezone, timedelta
import json
import os
import requests

# 頁面初始化：針對行動端預設展開與寬度設定
st.set_page_config(
    page_title="台股動能 RS 排行與風控儀表板",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 注入行動端專屬優化 CSS
st.markdown("""
<style>
    .block-container {
        padding-top: 1rem;
        padding-bottom: 2rem;
        padding-left: 0.6rem;
        padding-right: 0.6rem;
    }
    [data-testid="stMetricValue"] {
        font-size: 1.2rem !important;
    }
    [data-testid="stMetricDelta"] {
        font-size: 0.8rem !important;
    }
    .stButton > button {
        width: 100%;
        border-radius: 8px;
    }
</style>
""", unsafe_allow_html=True)

DATA_FILE = "portfolio.json"
TW_TZ = timezone(timedelta(hours=8))

def get_tw_now():
    return datetime.now(TW_TZ)

def get_tw_now_str(fmt="%Y-%m-%d %H:%M:%S"):
    return get_tw_now().strftime(fmt)

if "last_portfolio_refresh" not in st.session_state:
    st.session_state.last_portfolio_refresh = get_tw_now_str()

# ==========================================
# 官方標準券商下單簡稱對照庫
# ==========================================
def _load_official_names():
    try:
        if os.path.exists("stock_names.json"):
            with open("stock_names.json", "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        return {}
    return {}

OFFICIAL_STOCK_NAMES = _load_official_names()

def clean_stock_name(name, symbol=None):
    if symbol:
        sym_str = str(symbol).strip().upper()
        if sym_str in OFFICIAL_STOCK_NAMES:
            return OFFICIAL_STOCK_NAMES[sym_str]
    
    if not name:
        return str(symbol) if symbol else ""
    
    raw = str(name).strip()
    
    for sym_k, std_name in OFFICIAL_STOCK_NAMES.items():
        if raw == std_name or raw == f"{std_name}股份有限公司" or raw.startswith(std_name):
            if len(raw) <= len(std_name) + 12:
                return std_name

    cleaned = raw
    for suffix in [
        "股份有限公司台灣分公司", "股份有限公司", "有限股份公司",
        "有限公司", "(股)公司", "（股）公司"
    ]:
        cleaned = cleaned.replace(suffix, "")
    
    cleaned = cleaned.strip()
    return cleaned if cleaned else raw

# ==========================================
# 順勢大師操作法則：動能狀態分類引擎
# ==========================================
def get_trend_master_status(row):
    rs = row.get("rs_rating", 50)
    badge = str(row.get("pattern_badge", ""))
    r_5d = row.get("r_5d", 0.0)
    
    if rs >= 95:
        if "新高" in badge or r_5d >= 10.0:
            return "👑 頂級領袖・突破新高 (主力首選)"
        elif "VCP" in badge:
            return "🎯 頂級VCP・即將噴出 (極限強勢)"
        else:
            return "🚀 極致飆股・主升奔馳 (最強5%)"
    elif rs >= 90:
        if "VCP" in badge:
            return "🎯 VCP蓄勢・突破在即 (黃金買點)"
        elif "新高" in badge:
            return "⭐ 領袖新高・順風追擊 (多頭先鋒)"
        else:
            return "🚀 狂暴主升・沿線抱牢 (第一梯隊)"
    elif rs >= 80:
        if "VCP" in badge:
            return "🎯 VCP收縮・縮量待發 (觀察進場)"
        elif "新高" in badge:
            return "⭐ 區間突破・趨勢確立 (順勢加碼)"
        elif "反彈" in badge:
            return "⚠️ 短線強彈・觀察季線 (謹慎試單)"
        else:
            return "⚡ 強大多頭・順勢推升 (右側安全)"
    elif rs >= 75:
        if "反彈" in badge:
            return "⚠️ 左側反彈・上方有壓 (短打勿追)"
        elif "VCP" in badge:
            return "🎯 底部收斂・轉強蓄勢 (第二梯隊)"
        else:
            return "🔥 突破初升・動能成型 (第三梯隊)"
    elif rs >= 50:
        return "📦 區間整理・等待表態 (動能平平)"
    else:
        return "⛔ 弱勢落後・左側不碰 (避開死水)"

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                for d in data:
                    d["name"] = clean_stock_name(d.get("name"), d.get("symbol"))
                return data
        except Exception:
            return []
    return []

def save_data(data):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        st.error(f"資料儲存失敗: {str(e)}")

def make_log_entry(action, price, share_delta, remaining_shares, pnl_text, note):
    return {
        "時間": get_tw_now_str("%m/%d %H:%M"),
        "動作": action,
        "成交價": price,
        "異動": share_delta,
        "剩餘": remaining_shares,
        "損益": pnl_text,
        "備註": note
    }

@st.cache_data(ttl=60)
def load_market_data():
    raw_list = []
    status_msg = "無可用資料"

    if os.path.exists("market_rankings.json"):
        try:
            mtime = os.path.getmtime("market_rankings.json")
            mtime_str = datetime.fromtimestamp(mtime, tz=TW_TZ).strftime("%Y-%m-%d %H:%M")
            with open("market_rankings.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    raw_list = data
                    status_msg = f"本機檔案載入成功 ({mtime_str})"
        except Exception:
            pass

    if not raw_list:
        try:
            url = "https://raw.githubusercontent.com/blue1998-glitch/-/main/market_rankings.json"
            res = requests.get(url, timeout=8)
            if res.status_code == 200:
                data = res.json()
                if isinstance(data, list) and len(data) > 0:
                    fetch_time = get_tw_now_str("%H:%M:%S")
                    raw_list = data
                    status_msg = f"線上同步成功 ({fetch_time})"
        except Exception as e:
            return [], f"連線異常: {str(e)}"

    for item in raw_list:
        item["name"] = clean_stock_name(item.get("name"), item.get("symbol"))

    return raw_list, status_msg

def get_stock_rs_info(symbol, market_list):
    sym_clean = str(symbol).strip().upper()
    for item in market_list:
        if str(item.get("symbol", "")).strip().upper() == sym_clean:
            return item
    return None

def fetch_stock_and_momentum(symbol, market, entry_date_str):
    ticker = f"{symbol}.TWO" if "TWO" in str(market).upper() or market == "上櫃" else f"{symbol}.TW"
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(start=entry_date_str)
        if df.empty:
            df = stock.history(period="1mo")
        if df.empty:
            return None, None, None, 0.0, 0.0, 0.0
        
        current_price = round(float(df["Close"].iloc[-1]), 2)
        max_high = round(float(df["High"].max()), 2)
        
        df_all = stock.history(period="6mo")
        ma20 = round(float(df_all["Close"].tail(20).mean()), 2) if len(df_all) >= 20 else current_price

        closes = df_all["Close"]
        r_5d = round(((closes.iloc[-1] - closes.iloc[-6]) / closes.iloc[-6]) * 100, 2) if len(closes) >= 6 else 0.0
        r_1m = round(((closes.iloc[-1] - closes.iloc[-21]) / closes.iloc[-21]) * 100, 2) if len(closes) >= 21 else r_5d
        r_1q = round(((closes.iloc[-1] - closes.iloc[-61]) / closes.iloc[-61]) * 100, 2) if len(closes) >= 61 else r_1m

        return current_price, max_high, ma20, r_5d, r_1m, r_1q
    except Exception:
        return None, None, None, 0.0, 0.0, 0.0

def calc_pnl(shares, avg_cost, current_price, fee_discount):
    buy_fee_rate = 0.001425 * fee_discount
    sell_fee_rate = 0.001425 * fee_discount
    tax_rate = 0.003
    total_buy_cost = (shares * avg_cost) * (1 + buy_fee_rate)
    total_sell_net = (shares * current_price) * (1 - sell_fee_rate - tax_rate)
    net_pnl = round(total_sell_net - total_buy_cost)
    roi = round((net_pnl / total_buy_cost) * 100, 2) if total_buy_cost > 0 else 0.0
    breakeven_price = round(avg_cost * (1 + buy_fee_rate + sell_fee_rate + tax_rate), 2)
    return net_pnl, roi, breakeven_price

market_rankings, db_status = load_market_data()

# 主標題
st.title("🚀 台股動能 RS 風控儀表板")

with st.expander("🛡️ 五大量化風控機制速查指南", expanded=False):
    st.markdown("""
    - **1. 🔴 初始固定停損**：跌破設定趴數（預設 -7%）無條件停損，截斷重大虧損。
    - **2. 🛡️ 動態保本停損**：波段獲利達標（預設 +8%）啟動，停損推至零虧損保本價。
    - **3. 🟣 高點回檔停利**：自最高價回檔達設定幅度（預設 10%），觸發分批減碼。
    - **4. 🟠 月線乖離過熱**：現價與 20MA 正乖離過大（預設 +30%），短線過熱調節。
    - **5. ⏳ 時間動能停損**：持有達標（預設 10 天）且損益在 ±2% 內停滯，建議換股。
    """)

if len(market_rankings) > 0:
    st.caption(f"🟢 資料庫：**{len(market_rankings)}** 檔 ｜ {db_status}")
else:
    st.warning("🟡 正在等待全市場 RS 排名資料載入...")

tab_portfolio, tab_leaderboard = st.tabs(["📈 個人持倉風控", "🏆 全市場 RS 排行榜"])

# ==========================================
# 分頁 1：個人持倉風控監控儀表板
# ==========================================
with tab_portfolio:
    with st.expander("⚙️ 風控與參數設定", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            stop_loss_pct = st.number_input("🔴 初始停損 (%)", min_value=1.0, max_value=50.0, value=7.0, step=0.5, format="%.1f")
            breakeven_trigger_pct = st.number_input("🛡️ 保本門檻 (%)", min_value=1.0, max_value=50.0, value=8.0, step=0.5, format="%.1f")
            pyramid_safety_margin = st.number_input("⚖️ 加碼安全緩衝 (%)", min_value=0.5, max_value=50.0, value=4.0, step=0.5, format="%.1f")
        with c2:
            pullback_target_pct = st.number_input("🟣 高點回檔停利 (%)", min_value=1.0, max_value=50.0, value=10.0, step=0.5, format="%.1f")
            bias_threshold = st.number_input("🟠 月線正乖離閥值 (%)", min_value=5.0, max_value=100.0, value=30.0, step=1.0, format="%.0f")
            time_stop_days = st.number_input("⏳ 時間停損 (天)", min_value=1, max_value=100, value=10, step=1)
        discount_display = st.number_input("💰 手續費折數", min_value=0.01, max_value=1.0, value=0.60, step=0.05, format="%.2f")

    portfolio = load_data()

    with st.expander("➕ 新增持股 / 建倉", expanded=False):
        with st.form("add_stock_form"):
            f_col1, f_col2 = st.columns(2)
            with f_col1:
                sym = st.text_input("股票代號", placeholder="例: 2330")
                name = st.text_input("股票名稱", placeholder="例: 台積電")
                mkt = st.selectbox("市場別", ["TW (上市)", "TWO (上櫃)"])
            with f_col2:
                entry_d = st.date_input("進場日期", value=get_tw_now().date())
                price = st.number_input("買進價格", min_value=0.1, step=0.1, value=100.0)
                shs = st.number_input("買進股數", min_value=1, step=1000, value=1000)
                
            submitted = st.form_submit_button("確認建立持倉", use_container_width=True)
            if submitted and sym:
                mkt_code = "TWO" if "TWO" in mkt else "TW"
                clean_n = clean_stock_name(name.strip(), sym.strip()) if name else clean_stock_name(sym.strip(), sym.strip())
                new_item = {
                    "symbol": sym.strip(),
                    "name": clean_n,
                    "market": mkt_code,
                    "entry_date": str(entry_d),
                    "avg_cost": price,
                    "shares": int(shs),
                    "record_high": price,
                    "realized_pnl": 0,
                    "history": [
                        make_log_entry("🌱 初始建倉", price, f"+{int(shs)}", int(shs), "0 元", f"成本 ${price}")
                    ]
                }
                portfolio.append(new_item)
                save_data(portfolio)
                st.success(f"已新增 {new_item['name']} ({sym})")
                st.rerun()

    if not portfolio:
        st.info("目前尚無持倉，請點擊上方「➕ 新增持股」建立第一檔股票。")
    else:
        if st.button("🔄 刷新最新市價與評分", use_container_width=True):
            st.cache_data.clear()
            st.session_state.last_portfolio_refresh = get_tw_now_str("%H:%M:%S")
            st.rerun()
        st.caption(f"🕒 最新更新時間：{st.session_state.last_portfolio_refresh}")

        for idx, item in enumerate(portfolio):
            sym = item["symbol"]
            name = clean_stock_name(item.get("name", sym), sym)
            mkt = item["market"]
            entry_d = item["entry_date"]
            avg_cost = item["avg_cost"]
            shares = item["shares"]
            stored_high = item.get("record_high", avg_cost)
            realized_pnl = item.get("realized_pnl", 0)
            history_logs = item.get("history", [])

            info = get_stock_rs_info(sym, market_rankings)
            rs_score = info.get("rs_rating", 50) if info else 50
            
            cur_price, max_high, ma20, r_5d, r_1m, r_1q = fetch_stock_and_momentum(sym, mkt, entry_d)
            if cur_price is None:
                cur_price, max_high, ma20 = avg_cost, stored_high, avg_cost

            actual_high = max(stored_high, avg_cost, max_high if max_high is not None else stored_high)
            if actual_high != stored_high:
                portfolio[idx]["record_high"] = actual_high
                save_data(portfolio)

            net_pnl, roi, breakeven_p = calc_pnl(shares, avg_cost, cur_price, discount_display)
            pullback_pct = round(((actual_high - cur_price) / actual_high) * 100, 1) if actual_high > 0 else 0
            bias_20 = round(((cur_price - ma20) / ma20) * 100, 1) if ma20 > 0 else 0
            
            try:
                days_held = (get_tw_now().date() - datetime.strptime(entry_d, "%Y-%m-%d").date()).days
            except Exception:
                days_held = 0

            status_badge = get_trend_master_status(info if info else {"rs_rating": rs_score, "pattern_badge": "", "r_5d": r_5d})

            max_gain_pct = ((actual_high - avg_cost) / avg_cost) * 100
            is_breakeven_active = max_gain_pct >= breakeven_trigger_pct
            initial_stop_price = round(avg_cost * (1 - stop_loss_pct / 100), 2)
            effective_stop_price = max(initial_stop_price, breakeven_p) if is_breakeven_active else initial_stop_price
            pullback_price = round(actual_high * (1 - pullback_target_pct / 100), 2)

            status_text = "⚪ 正常續抱中"
            status_color = "gray"

            if cur_price <= effective_stop_price:
                if is_breakeven_active:
                    status_text = f"🛡️ 觸發保本停損（${effective_stop_price}）！保本出場"
                    status_color = "red"
                else:
                    status_text = f"🔴 觸發 -{stop_loss_pct}% 停損（${effective_stop_price}）！全數出場"
                    status_color = "red"
            elif cur_price <= pullback_price and cur_price > avg_cost:
                status_text = f"🟣 高點回檔 {pullback_target_pct}%（破 ${pullback_price}）！建議減碼"
                status_color = "purple"
            elif bias_20 >= bias_threshold:
                status_text = f"🟠 月線正乖離 {bias_20}%（過熱）！建議調節"
                status_color = "orange"
            elif days_held >= time_stop_days and abs(roi) <= 2.0:
                status_text = f"⏳ 觸發時間停損（持股 {days_held} 天動能停滯）！建議換股"
                status_color = "orange"

            with st.container(border=True):
                st.markdown(f"### {name} `({sym}.{mkt})`")
                st.caption(f"📦 持有: **{shares:,} 股** ｜ 持有 **{days_held} 天** ｜ {status_badge}")
                
                # 雙欄動能指標 (適合手機並排)
                m1, m2 = st.columns(2)
                m1.metric("5 日動能", f"{r_5d:+}%")
                m2.metric("RS Rating", f"{rs_score} 分")
                
                m3, m4 = st.columns(2)
                m3.metric("1 月動能", f"{r_1m:+}%")
                m4.metric("1 季動能", f"{r_1q:+}%")

                st.divider()

                # 雙欄持倉與損益
                p1, p2 = st.columns(2)
                p1.metric("最新市價", f"${cur_price}", f"成本: ${avg_cost}")
                p2.metric("未實現損益", f"{net_pnl:+,} 元", f"{roi:+}%")

                p3, p4 = st.columns(2)
                p3.metric("建倉最高價", f"${actual_high}", f"回檔: -{pullback_pct}%")
                stop_label = "🛡️ 保本防線" if is_breakeven_active else f"🔴 初始停損 (-{stop_loss_pct}%)"
                p4.metric(stop_label, f"${effective_stop_price}", f"回檔價: ${pullback_price}")

                if realized_pnl != 0:
                    st.caption(f"💵 累積已實現損益：**{realized_pnl:+,} 元**")

                st.markdown(f"**風控訊號：** :{status_color}[{status_text}]")

                # 操作選單改為頁籤形式，防止手機擠壓
                with st.expander(f"⚙️ 交易操作（加碼 / 減碼 / 結清）"):
                    tab_add, tab_red, tab_del = st.tabs(["🔼 加碼", "🔽 減碼", "🗑️ 結清"])
                    
                    with tab_add:
                        add_p = st.number_input("加碼價格", min_value=0.1, step=0.1, value=cur_price, key=f"add_p_{idx}")
                        add_s = st.number_input("加碼股數", min_value=1, step=100, value=1000, key=f"add_s_{idx}")
                        new_tot = shares + int(add_s)
                        sim_avg = round(((shares * avg_cost) + (int(add_s) * add_p)) / new_tot, 2)
                        buf = round(((cur_price - sim_avg) / cur_price) * 100, 1)
                        st.caption(f"試算新均價：**${sim_avg}** ｜ 安全緩衝：**{buf:+}%**")
                        
                        if st.button("確認加碼", key=f"btn_add_{idx}", use_container_width=True):
                            new_log = make_log_entry("🔼 順勢加碼", add_p, f"+{int(add_s)}", new_tot, "-", f"均價 ${sim_avg}")
                            portfolio[idx].setdefault("history", []).append(new_log)
                            portfolio[idx]["shares"] = new_tot
                            portfolio[idx]["avg_cost"] = sim_avg
                            save_data(portfolio)
                            st.rerun()

                    with tab_red:
                        red_p = st.number_input("減碼價格", min_value=0.1, step=0.1, value=cur_price, key=f"red_p_{idx}")
                        red_s = st.number_input("減碼股數", min_value=1, max_value=shares, step=100, value=min(1000, shares), key=f"red_s_{idx}")
                        
                        sim_red_pnl, sim_red_roi, _ = calc_pnl(int(red_s), avg_cost, red_p, discount_display)
                        st.caption(f"試算實現損益：**{sim_red_pnl:+,} 元** ({sim_red_roi:+}%)")
                        
                        if st.button("確認減碼", key=f"btn_red_{idx}", use_container_width=True):
                            new_shares = shares - int(red_s)
                            current_realized = item.get("realized_pnl", 0)
                            
                            new_log = make_log_entry("🔽 分批減碼", red_p, f"-{int(red_s)}", new_shares, f"{sim_red_pnl:+,} 元", f"報酬 {sim_red_roi:+}%")
                            portfolio[idx].setdefault("history", []).append(new_log)

                            if new_shares > 0:
                                portfolio[idx]["shares"] = new_shares
                                portfolio[idx]["realized_pnl"] = current_realized + sim_red_pnl
                                save_data(portfolio)
                            else:
                                portfolio.pop(idx)
                                save_data(portfolio)
                            st.rerun()

                    with tab_del:
                        st.write("確認全數結清並移除此持倉？")
                        if st.button("確認全數結清出場", key=f"del_{idx}", use_container_width=True):
                            portfolio.pop(idx)
                            save_data(portfolio)
                            st.rerun()

                if len(history_logs) > 0:
                    with st.expander(f"📜 歷史交易明細", expanded=False):
                        df_h = pd.DataFrame(history_logs)
                        st.dataframe(df_h, use_container_width=True, hide_index=True)

# ==========================================
# 分頁 2：全市場 RS 排行榜與個股查詢
# ==========================================
with tab_leaderboard:
    st.subheader("🔍 萬用個股 RS 查詢")
    search_query = st.text_input("輸入股票代號或名稱", placeholder="例：2330、聯一光")
    
    if search_query:
        query_str = search_query.strip().upper()
        matched = [
            item for item in market_rankings 
            if query_str in str(item.get("symbol", "")).upper() or query_str in str(item.get("name", "")).upper()
        ]
        
        if matched:
            st.caption(f"找到 **{len(matched)}** 筆符合標的：")
            for m in matched:
                score = m.get("rs_rating", 50)
                m_type = m.get("market", "上市/上櫃")
                name = clean_stock_name(m.get("name", m.get("symbol")), m.get("symbol"))
                sym = m.get("symbol")
                raw_score = m.get("score", 0.0)
                badge_style = get_trend_master_status(m)

                with st.container(border=True):
                    st.markdown(f"**{name} ({sym})** ｜ {m_type}")
                    st.caption(badge_style)
                    
                    sq1, sq2 = st.columns(2)
                    sq1.metric("RS Rating", f"{score} 分")
                    sq2.metric("綜合得分", f"{raw_score:+.2f}")
                    st.caption(f"📊 全市場地位：贏過全台 **{score}%** 股票")
        else:
            st.warning(f"查無「{search_query}」，請確認代號或名稱。")

    st.divider()
    st.subheader("🏆 RS 領袖強勢排行榜")
    
    df_raw = pd.DataFrame(market_rankings)
    if not df_raw.empty:
        if "name" not in df_raw.columns:
            df_raw["name"] = df_raw["symbol"]
        if "market" not in df_raw.columns:
            df_raw["market"] = "台股"

        f1, f2 = st.columns(2)
        with f1:
            min_rs = st.number_input("最低 RS 門檻", min_value=1, max_value=99, value=75, step=1)
        with f2:
            market_filter = st.multiselect("市場篩選", ["上市", "上櫃"], default=["上市", "上櫃"])

        filtered_df = df_raw[
            (df_raw["rs_rating"] >= min_rs) & 
            (df_raw["market"].isin(market_filter))
        ].copy()

        filtered_df["name"] = filtered_df.apply(lambda r: clean_stock_name(r.get("name"), r.get("symbol")), axis=1)
        filtered_df = filtered_df.sort_values(by="rs_rating", ascending=False)
        filtered_df["狀態"] = filtered_df.apply(get_trend_master_status, axis=1)

        display_df = filtered_df[["rs_rating", "symbol", "name", "market", "score", "狀態"]].rename(columns={
            "rs_rating": "RS",
            "symbol": "代碼",
            "name": "名稱",
            "market": "市場",
            "score": "得分"
        })

        st.caption(f"共 **{len(display_df)}** 檔符合（RS ≥ {min_rs}）：")
        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            height=420
        )
    else:
        st.info("尚無排名資料，請先執行 Actions 排程產生資料。")
