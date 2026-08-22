import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, date
import json
import os
import requests

st.set_page_config(page_title="順勢大師台股動能風控儀表板", layout="wide", initial_sidebar_state="collapsed")

DATA_FILE = "portfolio.json"

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return []
    return []

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# 【核心功能】全市場排名即時載入器
@st.cache_data(ttl=60)
def load_market_data():
    # 1. 優先嘗試從伺服器本機讀取
    if os.path.exists("market_rankings.json"):
        try:
            with open("market_rankings.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    return data, "本機檔案載入成功"
        except Exception as e:
            pass

    # 2. 自動連線 GitHub 抓取最新檔案
    try:
        url = "https://raw.githubusercontent.com/blue1998-glitch/-/main/market_rankings.json"
        res = requests.get(url, timeout=8)
        if res.status_code == 200:
            data = res.json()
            if isinstance(data, list) and len(data) > 0:
                return data, "GitHub 線上同步成功"
            else:
                return [], f"GitHub 回傳空資料 (長度 0)"
        else:
            return [], f"連線失敗 (HTTP {res.status_code})"
    except Exception as e:
        return [], f"連線異常: {str(e)}"

def get_rs_from_json(symbol, market_list):
    sym_clean = str(symbol).strip().upper()
    for item in market_list:
        if str(item.get('symbol', '')).strip().upper() == sym_clean:
            return item.get('rs_rating', 50)
    return 50

def fetch_stock_and_momentum(symbol, market, entry_date_str):
    ticker = f"{symbol}.TWO" if market.upper() == "TWO" else f"{symbol}.TW"
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
    except:
        return None, None, None, 0.0, 0.0, 0.0

def calc_pnl(shares, avg_cost, current_price, fee_discount):
    buy_fee_rate = 0.001425 * fee_discount
    sell_fee_rate = 0.001425 * fee_discount
    tax_rate = 0.003
    
    total_buy_cost = (shares * avg_cost) * (1 + buy_fee_rate)
    total_sell_net = (shares * current_price) * (1 - sell_fee_rate - tax_rate)
    
    net_pnl = round(total_sell_net - total_buy_cost)
    roi = round((net_pnl / total_buy_cost) * 100, 2)
    breakeven_price = round(avg_cost * (1 + buy_fee_rate + sell_fee_rate + tax_rate), 2)
    return net_pnl, roi, breakeven_price

# --- 介面開始 ---
st.title("📈 順勢大師台股動能風控儀表板")

# 載入全市場 RS 資料庫
market_rankings, db_status = load_market_data()

# 顯示頂部狀態診斷條
if len(market_rankings) > 0:
    st.success(f"🟢 全市場 RS 資料庫運作正常 ｜ 已載入 {len(market_rankings)} 檔標的排名 ｜ 狀態：{db_status}")
else:
    st.warning(f"🟡 RS 資料庫未載入成功 ｜ 狀態訊息：{db_status}（若專案為 Private，請至 GitHub 設為 Public）")

# 1. 頂部大師參數自訂區
with st.expander("⚙️ 順勢大師風控與動能參數設定（點此自訂）", expanded=False):
    c1, c2, c3 = st.columns(3)
    with c1:
        st.write("##### 🛡️ 停損與保本防禦")
        stop_loss_pct = st.slider("🔴 初始停損趴數 (%)", 1.0, 15.0, 7.0, 0.5, format="-%0.1f%%")
        breakeven_trigger_pct = st.slider("🛡️ 保本停損啟動門檻（獲利達此%鎖保本）", 3.0, 20.0, 8.0, 0.5, format="+%0.1f%%")
        pyramid_safety_margin = st.slider("⚖️ 加碼安全邊際底線（新均價距現價%）", 1.0, 10.0, 4.0, 0.5, format="%0.1f%%")
    with c2:
        st.write("##### 🚀 獲利奔馳與回檔")
        pullback_target_pct = st.slider("🟣 高點回檔停利趴數 (%)", 3.0, 25.0, 10.0, 0.5, format="-%0.1f%%")
        bias_threshold = st.slider("🟠 月線正乖離過熱閥值 (%)", 15.0, 60.0, 30.0, 1.0, format="+%0.0f%%")
    with c3:
        st.write("##### ⏳ 時間與手續費")
        time_stop_days = st.slider("⏳ 時間停損天數（天）", 5, 30, 10, 1)
        discount_display = st.slider("💰 券商手續費折數（例 0.6 = 6折）", 0.1, 1.0, 0.6, 0.01, format="%0.2f")

portfolio = load_data()

# 2. 新增持股區
with st.expander("➕ 新增持股 / 建倉", expanded=False):
    with st.form("add_stock_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            sym = st.text_input("股票代號", placeholder="例如: 3441 或 2330")
            name = st.text_input("股票名稱", placeholder="例如: 聯一光")
        with col2:
            mkt = st.selectbox("市場別", ["TWO (上櫃)", "TW (上市)"])
            entry_d = st.date_input("進場日期", value=date.today())
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
                "record_high": price
            }
            portfolio.append(new_item)
            save_data(portfolio)
            st.success(f"已新增 {new_item['name']} ({sym})")
            st.rerun()

# 3. 持倉列表
if not portfolio:
    st.info("目前尚無持倉，請點擊上方「➕ 新增持股」建立第一檔股票。")
else:
    if st.button("🔄 刷新最新市價與動能評分"):
        st.cache_data.clear()
        st.rerun()

    for idx, item in enumerate(portfolio):
        sym = item['symbol']
        name = item['name']
        mkt = item['market']
        entry_d = item['entry_date']
        avg_cost = item['avg_cost']
        shares = item['shares']
        stored_high = item.get('record_high', avg_cost)

        # 讀取全市場排名 RS
        rs_score = get_rs_from_json(sym, market_rankings)
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
            days_held = (date.today() - datetime.strptime(entry_d, "%Y-%m-%d").date()).days
        except:
            days_held = 0

        # RS 評級標籤
        if rs_score >= 85:
            rs_badge = f"🚀 極致爆發 (RS {rs_score} / 前 15%)"
        elif rs_score >= 70:
            rs_badge = f"⚡ 強勢動能 (RS {rs_score})"
        elif rs_score >= 50:
            rs_badge = f"➖ 動能中平 (RS {rs_score})"
        else:
            rs_badge = f"⚠️ 動能落後 (RS {rs_score})"

        # 保本停損判定
        max_gain_pct = ((actual_high - avg_cost) / avg_cost) * 100
        is_breakeven_active = max_gain_pct >= breakeven_trigger_pct
        initial_stop_price = round(avg_cost * (1 - stop_loss_pct / 100), 2)
        effective_stop_price = max(initial_stop_price, breakeven_p) if is_breakeven_active else initial_stop_price
        pullback_price = round(actual_high * (1 - pullback_target_pct / 100), 2)

        # 狀態判定
        status_text = "⚪ 持股續抱中"
        status_color = "gray"

        if cur_price <= effective_stop_price:
            if is_breakeven_active:
                status_text = f"🛡️ 觸發保本出場線（{effective_stop_price} 元）！強制保護本金零虧損出場（{shares} 股）"
                status_color = "red"
            else:
                status_text = f"🔴 觸發 -{stop_loss_pct}% 停損線（{effective_stop_price} 元）！全數出場（{shares} 股）"
                status_color = "red"
        elif cur_price <= pullback_price and cur_price > avg_cost:
            status_text = f"🟣 觸發高點回檔 {pullback_target_pct}%（跌破 {pullback_price} 元）！波段高點 {actual_high} 元，建議減碼 30%~50%"
            status_color = "purple"
        elif bias_20 >= bias_threshold:
            status_text = f"🟠 月線正乖離達 {bias_20}%（閥值 {bias_threshold}%）！短線過熱，建議減碼 30%~50%"
            status_color = "orange"
        elif days_held >= time_stop_days and abs(roi) <= 2.0:
            status_text = f"⏳ 觸發時間停損（持股已 {days_held} 天，報酬僅 {roi:+}%）！動能停滯，建議換股"
            status_color = "orange"

        # 渲染卡片
        with st.container():
            st.markdown("---")
            st.subheader(f"{name} ({sym}.{mkt}) ｜ 持有 {days_held} 天 ｜ {rs_badge}")
            
            # 第一排：多週期動能即時看板
            m_col1, m_col2, m_col3, m_col4 = st.columns(4)
            m_col1.metric("近 5 日累積動能", f"{r_5d:+}%", "極短期爆發")
            m_col2.metric("近 1 個月累積動能", f"{r_1m:+}%", "主升段核心")
            m_col3.metric("近 1 季累積動能", f"{r_1q:+}%", "中期多頭趨勢")
            m_col4.metric("全市場 RS Rating", f"{rs_score} 分", "GitHub 每日排定")

            # 第二排：損益與風控防禦
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("最新市價 / 均價", f"${cur_price}", f"均價: ${avg_cost}")
            c2.metric("未實現淨損益 (已扣稅費)", f"{net_pnl:+,} 元", f"{roi:+}%")
            stop_label = "🛡️ 保本停損線" if is_breakeven_active else f"🔴 初始停損 (-{stop_loss_pct}%)"
            c3.metric(stop_label, f"${effective_stop_price}", "已啟動保本" if is_breakeven_active else "常規防守")
            c4.metric(f"波段最高 / 回檔線 (-{pullback_target_pct}%)", f"${actual_high}", f"回檔價: ${pullback_price}")

            st.markdown(f"**大師風控狀態：** :{status_color}[{status_text}]")

            # 順勢加碼試算操作
            with st.expander(f"⚙️ 操作 {name}（順勢加碼防禦試算 / 減碼 / 結清）"):
                op_col1, op_col2, op_col3 = st.columns(3)
                with op_col1:
                    st.write("##### 🔼 順勢金字塔加碼")
                    add_p = st.number_input("加碼價格", min_value=0.1, step=0.1, value=cur_price, key=f"add_p_{idx}")
                    add_s = st.number_input("加碼股數", min_value=1, step=100, value=1000, key=f"add_s_{idx}")
                    
                    new_tot_shares = shares + int(add_s)
                    simulated_avg = round(((shares * avg_cost) + (int(add_s) * add_p)) / new_tot_shares, 2)
                    safety_buf = round(((cur_price - simulated_avg) / cur_price) * 100, 1)
                    
                    st.caption(f"試算新均價：**${simulated_avg}** ｜ 安全緩衝：**{safety_buf:+}%**")
                    if safety_buf < pyramid_safety_margin:
                        st.error(f"⚠️ 警告：安全緩衝僅 {safety_buf}%（低於 {pyramid_safety_margin}%）！這會大幅拉高成本，回檔極易侵蝕獲利。")
                    else:
                        st.success(f"✅ 符合防禦原則：安全緩衝達 {safety_buf}%。")

                    if st.button("確認執行加碼", key=f"btn_add_{idx}"):
                        portfolio[idx]['shares'] = new_tot_shares
                        portfolio[idx]['avg_cost'] = simulated_avg
                        save_data(portfolio)
                        st.success(f"加碼成功！新均價 ${simulated_avg}")
                        st.rerun()

                with op_col2:
                    st.write("##### 🔽 分批減碼")
                    reduce_s = st.number_input("減碼股數", min_value=1, max_value=shares, step=100, key=f"red_s_{idx}")
                    if st.button("確認減碼", key=f"btn_red_{idx}"):
                        portfolio[idx]['shares'] = shares - int(reduce_s)
                        save_data(portfolio)
                        st.success(f"已減碼 {reduce_s} 股")
                        st.rerun()

                with op_col3:
                    st.write("##### 🗑️ 結清出場")
                    if st.button("結清並移除持倉", key=f"del_{idx}"):
                        portfolio.pop(idx)
                        save_data(portfolio)
                        st.warning(f"已移除 {name}")
                        st.rerun()
