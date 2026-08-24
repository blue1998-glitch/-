import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, date, timezone, timedelta
import json
import os
import requests

st.set_page_config(page_title="台股動能 RS 排行與風控儀表板", layout="wide", initial_sidebar_state="collapsed")

DATA_FILE = "portfolio.json"

# 設定台灣時區 (UTC+8)
TW_TZ = timezone(timedelta(hours=8))

def get_tw_now():
    return datetime.now(TW_TZ)

def get_tw_now_str(fmt="%Y-%m-%d %H:%M:%S"):
    return get_tw_now().strftime(fmt)

if "last_portfolio_refresh" not in st.session_state:
    st.session_state.last_portfolio_refresh = get_tw_now_str()

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

@st.cache_data(ttl=60)
def load_market_data():
    if os.path.exists("market_rankings.json"):
        try:
            mtime = os.path.getmtime("market_rankings.json")
            mtime_str = datetime.fromtimestamp(mtime, tz=TW_TZ).strftime("%Y-%m-%d %H:%M:%S")
            with open("market_rankings.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    return data, f"本機檔案載入成功 (產出時間: {mtime_str})"
        except Exception:
            pass

    try:
        url = "https://raw.githubusercontent.com/blue1998-glitch/-/main/market_rankings.json"
        res = requests.get(url, timeout=8)
        if res.status_code == 200:
            data = res.json()
            if isinstance(data, list) and len(data) > 0:
                fetch_time = get_tw_now_str()
                return data, f"GitHub 線上同步成功 (同步時間: {fetch_time})"
    except Exception as e:
        return [], f"連線異常: {str(e)}"

    return [], "無可用資料"

def get_stock_rs_info(symbol, market_list):
    sym_clean = str(symbol).strip().upper()
    for item in market_list:
        if str(item.get('symbol', '')).strip().upper() == sym_clean:
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
        
        current_price = round(float(df['Close'].iloc[-1]), 2)
        max_high = round(float(df['High'].max()), 2)
        
        df_all = stock.history(period="6mo")
        ma20 = round(float(df_all['Close'].tail(20).mean()), 2) if len(df_all) >= 20 else current_price

        closes = df_all['Close']
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

st.title("🚀 台股動能 RS 領袖排行與風控儀表板")

with st.expander("🛡️ 系統五大自動化量化風控機制速查指南（交易紀律鐵律）", expanded=True):
    fc1, fc2, fc3, fc4, fc5 = st.columns(5)
    with fc1:
        st.markdown("**1. 🔴 初始固定停損**")
        st.caption("跌破設定趴數（預設 -7%）無條件停損，截斷重大虧損。")
    with fc2:
        st.markdown("**2. 🛡️ 動態保本停損**")
        st.caption("波段獲利達標（預設 +8%）自動啟動，停損點推至零虧損保本價。")
    with fc3:
        st.markdown("**3. 🟣 高點回檔停利**")
        st.caption("自歷史最高價回檔達設定幅度（預設 10%），觸發分批減碼。")
    with fc4:
        st.markdown("**4. 🟠 月線乖離過熱**")
        st.caption("現價與 20MA 正乖離過大（預設 +30%），短線過熱建議調節。")
    with fc5:
        st.markdown("**5. ⏳ 時間動能停損**")
        st.caption("持有天數達標（預設 10 天）且損益在 ±2% 內停滯，建議換股。")

if len(market_rankings) > 0:
    st.info(f"🟢 **全市場 RS 資料庫已就緒** ｜ 收錄 **{len(market_rankings)}** 檔台股 ｜ 狀態：{db_status}")
else:
    st.warning("🟡 正在等待全市場 RS 排名資料載入...")

tab_leaderboard, tab_portfolio = st.tabs(["🏆 全市場 RS 排行榜 & 萬用個股查詢", "📈 個人持倉風控監控"])

# ==========================================
# 分頁 1：全市場 RS 排行榜與個股查詢
# ==========================================
with tab_leaderboard:
    st.subheader("🔍 萬用個股 RS 評分查詢")
    search_col1, search_col2 = st.columns([3, 1])
    with search_col1:
        search_query = st.text_input("輸入股票代號或名稱查詢（例如：2330、聯一光、3441）", placeholder="請輸入代號或名稱...")
    
    if search_query:
        query_str = search_query.strip().upper()
        matched = [
            item for item in market_rankings 
            if query_str in str(item.get('symbol', '')).upper() or query_str in str(item.get('name', ''))
        ]
        
        if matched:
            st.write(f"找到 **{len(matched)}** 筆符合標的：")
            for m in matched:
                score = m.get('rs_rating', 50)
                m_type = m.get('market', '上市/上櫃')
                name = m.get('name', m.get('symbol'))
                sym = m.get('symbol')
                raw_score = m.get('score', 0.0)
                
                if score >= 85:
                    badge_style = "🚀 極致動能領袖股 (前 15%)"
                elif score >= 75:
                    badge_style = "⚡ 強勢突破多頭股 (前 25%)"
                elif score >= 50:
                    badge_style = "➖ 盤整中平標的"
                else:
                    badge_style = "⚠️ 落後弱勢標的"

                r_col1, r_col2, r_col3, r_col4 = st.columns(4)
                r_col1.metric("標的", f"{name} ({sym})", m_type)
                r_col2.metric("RS Rating 評分", f"{score} 分", badge_style)
                r_col3.metric("綜合動能得分", f"{raw_score:+.2f}")
                r_col4.metric("全市場地位", f"贏過全台 {score}% 股票")
                st.markdown("---")
        else:
            st.error(f"查無符合「{search_query}」的標的，請確認代號或名稱是否正確。")

    st.subheader("🏆 全市場 RS ≥ 75 領袖股強勢排行榜")
    
    df_raw = pd.DataFrame(market_rankings)
    if not df_raw.empty:
        if 'name' not in df_raw.columns:
            df_raw['name'] = df_raw['symbol']
        if 'market' not in df_raw.columns:
            df_raw['market'] = "台股"

        filter_col1, filter_col2 = st.columns([1, 3])
        with filter_col1:
            min_rs = st.slider("最低 RS 門檻篩選", 70, 95, 75, 1)
        with filter_col2:
            market_filter = st.multiselect("市場別篩選", ["上市", "上櫃"], default=["上市", "上櫃"])

        filtered_df = df_raw[
            (df_raw['rs_rating'] >= min_rs) & 
            (df_raw['market'].isin(market_filter))
        ].copy()

        filtered_df = filtered_df.sort_values(by="rs_rating", ascending=False)
        filtered_df['動能梯隊'] = filtered_df['rs_rating'].apply(
            lambda x: "🚀 第一梯隊 (RS 90+)" if x >= 90 else ("⚡ 第二梯隊 (RS 80-89)" if x >= 80 else "🔥 第三梯隊 (RS 75-79)")
        )

        display_df = filtered_df[['rs_rating', 'symbol', 'name', 'market', 'score', '動能梯隊']].rename(columns={
            'rs_rating': 'RS 評分 (PR)',
            'symbol': '股票代碼',
            'name': '中文名稱',
            'market': '上市櫃',
            'score': '綜合動能得分'
        })

        st.caption(f"共計 **{len(display_df)}** 檔標的符合條件（RS ≥ {min_rs}）：")
        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            height=500
        )
    else:
        st.info("尚無排名資料，請先執行 Actions 排程產生資料。")

# ==========================================
# 分頁 2：個人持倉風控監控儀表板
# ==========================================
with tab_portfolio:
    with st.expander("⚙️ 風控與動能參數設定", expanded=False):
        c1, c2, c3 = st.columns(3)
        with c1:
            st.write("##### 🛡️ 停損與保本防禦")
            stop_loss_pct = st.slider("🔴 初始停損趴數 (%)", 1.0, 15.0, 7.0, 0.5, format="-%0.1f%%")
            breakeven_trigger_pct = st.slider("🛡️ 保本停損啟動門檻", 3.0, 20.0, 8.0, 0.5, format="+%0.1f%%")
            pyramid_safety_margin = st.slider("⚖️ 加碼安全邊際底線", 1.0, 10.0, 4.0, 0.5, format="%0.1f%%")
        with c2:
            st.write("##### 🚀 獲利奔馳與回檔")
            pullback_target_pct = st.slider("🟣 高點回檔停利趴數 (%)", 3.0, 25.0, 10.0, 0.5, format="-%0.1f%%")
            bias_threshold = st.slider("🟠 月線正乖離過熱閥值 (%)", 15.0, 60.0, 30.0, 1.0, format="+%0.0f%%")
        with c3:
            st.write("##### ⏳ 時間與手續費")
            time_stop_days = st.slider("⏳ 時間停損天數（天）", 5, 30, 10, 1)
            discount_display = st.slider("💰 券商手續費折數", 0.1, 1.0, 0.6, 0.01, format="%0.2f")

    portfolio = load_data()

    with st.expander("➕ 新增持股 / 建倉", expanded=False):
        with st.form("add_stock_form"):
            col1, col2, col3 = st.columns(3)
            with col1:
                sym = st.text_input("股票代號", placeholder="例如: 3441 或 2330")
                name = st.text_input("股票名稱", placeholder="例如: 聯一光")
            with col2:
                mkt = st.selectbox("市場別", ["TWO (上櫃)", "TW (上市)"])
                entry_d = st.date_input("進場日期", value=get_tw_now().date())
            with col3:
                price = st.number_input("買進價格", min_value=0.1, step=0.1, value=100.0)
                shs = st.number_input("買進股數", min_value=1, step=1000, value=1000)
                
            submitted = st.form_submit_button("確認建立持倉")
            if submitted and sym:
                mkt_code = "TWO" if "TWO" in mkt else "TW"
                new_item = {
                    "symbol": sym.strip(),
                    "name": name.strip() if name else sym.strip(),
                    "market": mkt_code,
                    "entry_date": str(entry_d),
                    "avg_cost": price,
                    "shares": int(shs),
                    "record_high": price,
                    "realized_pnl": 0,
                    "history": [
                        {
                            "時間": get_tw_now_str("%Y-%m-%d %H:%M"),
                            "動作": "🌱 初始建倉",
                            "成交價": price,
                            "異動股數": f"+{int(shs)}",
                            "剩餘股數": int(shs),
                            "單筆實現損益": "0 元",
                            "備註": f"起始成本 ${price}"
                        }
                    ]
                }
                portfolio.append(new_item)
                save_data(portfolio)
                st.success(f"已新增 {new_item['name']} ({sym})")
                st.rerun()

    if not portfolio:
        st.info("目前尚無持倉，請點擊上方「➕ 新增持股」建立第一檔股票。")
    else:
        rf_col1, rf_col2 = st.columns([1, 4])
        with rf_col1:
            if st.button("🔄 刷新最新市價與動能評分", use_container_width=True):
                st.cache_data.clear()
                st.session_state.last_portfolio_refresh = get_tw_now_str()
                st.rerun()
        with rf_col2:
            st.success(f"🕒 **台灣時間（最新市價更新成功）：{st.session_state.last_portfolio_refresh}**")

        for idx, item in enumerate(portfolio):
            sym = item['symbol']
            name = item['name']
            mkt = item['market']
            entry_d = item['entry_date']
            avg_cost = item['avg_cost']
            shares = item['shares']
            stored_high = item.get('record_high', avg_cost)
            realized_pnl = item.get('realized_pnl', 0)
            history_logs = item.get('history', [])

            info = get_stock_rs_info(sym, market_rankings)
            rs_score = info.get('rs_rating', 50) if info else 50
            
            cur_price, max_high, ma20, r_5d, r_1m, r_1q = fetch_stock_and_momentum(sym, mkt, entry_d)
            if cur_price is None:
                cur_price, max_high, ma20 = avg_cost, stored_high, avg_cost

            actual_high = max(stored_high, avg_cost, max_high)
            if actual_high != stored_high:
                portfolio[idx]['record_high'] = actual_high
                save_data(portfolio)

            net_pnl, roi, breakeven_p = calc_pnl(shares, avg_cost, cur_price, discount_display)
            pullback_pct = round(((actual_high - cur_price) / actual_high) * 100, 1) if actual_high > 0 else 0
            bias_20 = round(((cur_price - ma20) / ma20) * 100, 1) if ma20 > 0 else 0
            
            try:
                days_held = (get_tw_now().date() - datetime.strptime(entry_d, "%Y-%m-%d").date()).days
            except Exception:
                days_held = 0

            if rs_score >= 85:
                rs_badge = f"🚀 極致爆發 (RS {rs_score} / 前 15%)"
            elif rs_score >= 70:
                rs_badge = f"⚡ 強勢動能 (RS {rs_score})"
            elif rs_score >= 50:
                rs_badge = f"➖ 動能中平 (RS {rs_score})"
            else:
                rs_badge = f"⚠️ 動能落後 (RS {rs_score})"

            max_gain_pct = ((actual_high - avg_cost) / avg_cost) * 100
            is_breakeven_active = max_gain_pct >= breakeven_trigger_pct
            initial_stop_price = round(avg_cost * (1 - stop_loss_pct / 100), 2)
            effective_stop_price = max(initial_stop_price, breakeven_p) if is_breakeven_active else initial_stop_price
            pullback_price = round(actual_high * (1 - pullback_target_pct / 100), 2)

            status_text = "⚪ 持股續抱中"
            status_color = "gray"

            if cur_price <= effective_stop_price:
                if is_breakeven_active:
                    status_text = f"🛡️ 觸發保本出場線（{effective_stop_price} 元）！強制保護本金零虧損出場"
                    status_color = "red"
                else:
                    status_text = f"🔴 觸發 -{stop_loss_pct}% 停損線（{effective_stop_price} 元）！全數出場"
                    status_color = "red"
            elif cur_price <= pullback_price and cur_price > avg_cost:
                status_text = f"🟣 觸發高點回檔 {pullback_target_pct}%（跌破 {pullback_price} 元）！建議減碼"
                status_color = "purple"
            elif bias_20 >= bias_threshold:
                status_text = f"🟠 月線正乖離達 {bias_20}%（過熱）！建議減碼"
                status_color = "orange"
            elif days_held >= time_stop_days and abs(roi) <= 2.0:
                status_text = f"⏳ 觸發時間停損（持股已 {days_held} 天，動能停滯）！建議換股"
                status_color = "orange"

            with st.container():
                st.markdown("---")
                st.subheader(f"{name} ({sym}.{mkt}) ｜ 📦 剩餘: {shares:,} 股 ｜ 持有 {days_held} 天 ｜ {rs_badge}")
                
                m_col1, m_col2, m_col3, m_col4 = st.columns(4)
                m_col1.metric("近 5 日累積動能", f"{r_5d:+}%")
                m_col2.metric("近 1 個月累積動能", f"{r_1m:+}%")
                m_col3.metric("近 1 季累積動能", f"{r_1q:+}%")
                m_col4.metric("全市場 RS Rating", f"{rs_score} 分")

                c1, c2, c3, c4, c5 = st.columns(5)
                c1.metric("剩餘持股 / 均價", f"{shares:,} 股", f"均價: ${avg_cost}")
                c2.metric("最新市價", f"${cur_price}", f"高點回檔: -{pullback_pct}%")
                c3.metric("未實現損益", f"{net_pnl:+,} 元", f"{roi:+}%")
                c4.metric("累積已實現損益", f"{realized_pnl:+,} 元")
                stop_label = "🛡️ 保本停損線" if is_breakeven_active else f"🔴 初始停損 (-{stop_loss_pct}%)"
                c5.metric(stop_label, f"${effective_stop_price}", f"回檔價: ${pullback_price}")

                st.markdown(f"**風控狀態：** :{status_color}[{status_text}]")

                with st.expander(f"⚙️ 操作 {name}（加碼 / 減碼 / 結清）"):
                    op_col1, op_col2, op_col3 = st.columns(3)
                    with op_col1:
                        st.write("##### 🔼 順勢金字塔加碼")
                        add_p = st.number_input("加碼價格", min_value=0.1, step=0.1, value=cur_price, key=f"add_p_{idx}")
                        add_s = st.number_input("加碼股數", min_value=1, step=100, value=1000, key=f"add_s_{idx}")
                        new_tot = shares + int(add_s)
                        sim_avg = round(((shares * avg_cost) + (int(add_s) * add_p)) / new_tot, 2)
                        buf = round(((cur_price - sim_avg) / cur_price) * 100, 1)
                        st.caption(f"試算新均價：**${sim_avg}** ｜ 安全緩衝：**{buf:+}%**")
                        
                        if st.button("確認加碼", key=f"btn_add_{idx}"):
                            new_log = {
                                "時間": get_tw_now_str("%Y-%m-%d %H:%M"),
                                "動作": "🔼 順勢加碼",
                                "成交價": add_p,
                                "異動股數": f"+{int(add_s)}",
                                "剩餘股數": new_tot,
                                "單筆實現損益": "-",
                                "備註": f"新均價 ${sim_avg} (緩衝 {buf:+}%)"
                            }
                            if 'history' not in portfolio[idx]:
                                portfolio[idx]['history'] = []
                            portfolio[idx]['history'].append(new_log)
                            portfolio[idx]['shares'] = new_tot
                            portfolio[idx]['avg_cost'] = sim_avg
                            save_data(portfolio)
                            st.rerun()

                    with op_col2:
                        st.write("##### 🔽 分批減碼")
                        red_p = st.number_input("減碼價格", min_value=0.1, step=0.1, value=cur_price, key=f"red_p_{idx}")
                        red_s = st.number_input("減碼股數", min_value=1, max_value=shares, step=100, value=min(1000, shares), key=f"red_s_{idx}")
                        
                        sim_red_pnl, sim_red_roi, _ = calc_pnl(int(red_s), avg_cost, red_p, discount_display)
                        st.caption(f"試算本次實現損益：**{sim_red_pnl:+,} 元** ({sim_red_roi:+}%)")
                        
                        if st.button("確認減碼", key=f"btn_red_{idx}"):
                            new_shares = shares - int(red_s)
                            current_realized = item.get('realized_pnl', 0)
                            
                            new_log = {
                                "時間": get_tw_now_str("%Y-%m-%d %H:%M"),
                                "動作": "🔽 分批減碼",
                                "成交價": red_p,
                                "異動股數": f"-{int(red_s)}",
                                "剩餘股數": new_shares,
                                "單筆實現損益": f"{sim_red_pnl:+,} 元",
                                "備註": f"報酬率 {sim_red_roi:+}%"
                            }
                            if 'history' not in portfolio[idx]:
                                portfolio[idx]['history'] = []
                            portfolio[idx]['history'].append(new_log)

                            if new_shares > 0:
                                portfolio[idx]['shares'] = new_shares
                                portfolio[idx]['realized_pnl'] = current_realized + sim_red_pnl
                                save_data(portfolio)
                            else:
                                portfolio.pop(idx)
                                save_data(portfolio)
                            st.rerun()

                    with op_col3:
                        st.write("##### 🗑️ 結清出場")
                        if st.button("結清持倉", key=f"del_{idx}"):
                            portfolio.pop(idx)
                            save_data(portfolio)
                            st.rerun()

                if history_logs:
                    with st.expander(f"📜 {name} 交易歷程 (剩餘 {shares:,} 股)", expanded=False):
                   
