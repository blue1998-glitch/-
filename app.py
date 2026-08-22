import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, date
import json
import os

st.set_page_config(page_title="大師級台股持倉風控系統", layout="wide", initial_sidebar_state="collapsed")

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

def fetch_stock_and_market(symbol, market, entry_date_str):
    ticker = f"{symbol}.TWO" if market.upper() == "TWO" else f"{symbol}.TW"
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(start=entry_date_str)
        if df.empty:
            df = stock.history(period="1mo")
        if df.empty:
            return None, None, None, 0.0
        
        current_price = round(float(df['Close'].iloc[-1]), 2)
        max_high = round(float(df['High'].max()), 2)
        
        # 20MA
        df_all = stock.history(period="3mo")
        ma20 = round(float(df_all['Close'].tail(20).mean()), 2) if len(df_all) >= 20 else current_price
        
        # 抓取大盤加權指數同期漲跌幅
        market_return = 0.0
        try:
            twii = yf.Ticker("^TWII")
            mdf = twii.history(start=entry_date_str)
            if len(mdf) >= 2:
                m_start = mdf['Close'].iloc[0]
                m_end = mdf['Close'].iloc[-1]
                market_return = round(((m_end - m_start) / m_start) * 100, 2)
        except:
            market_return = 0.0

        return current_price, max_high, ma20, market_return
    except Exception as e:
        return None, None, None, 0.0

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
st.title("📈 順勢交易大師持倉風控儀表板")

# 1. 頂部大師參數自訂區
with st.expander("⚙️ 順勢大師風控參數設定（停損 / 保本 / 回檔 / RS / 時間停損）", expanded=False):
    c1, c2, c3 = st.columns(3)
    with c1:
        st.write("##### 🛡️ 停損與保本防禦")
        stop_loss_pct = st.slider("🔴 初始停損趴數 (%)", 1.0, 15.0, 7.0, 0.5, format="-%0.1f%%")
        breakeven_trigger_pct = st.slider("🛡️ 保本停損啟動門檻（獲利達此%自動鎖保本）", 3.0, 20.0, 8.0, 0.5, format="+%0.1f%%")
        pyramid_safety_margin = st.slider("⚖️ 加碼安全邊際底線（新均價距現價%）", 1.0, 10.0, 4.0, 0.5, format="%0.1f%%")
    with c2:
        st.write("##### 🚀 獲利奔馳與回檔")
        pullback_target_pct = st.slider("🟣 高點回檔停利趴數 (%)", 3.0, 25.0, 10.0, 0.5, format="-%0.1f%%")
        take_profit_pct = st.slider("🟢 波段目標停利趴數 (%)", 10.0, 100.0, 20.0, 1.0, format="+%0.0f%%")
        bias_threshold = st.slider("🟠 月線正乖離過熱閥值 (%)", 15.0, 60.0, 30.0, 1.0, format="+%0.0f%%")
    with c3:
        st.write("##### ⏳ 時間與大盤濾網")
        time_stop_days = st.slider("⏳ 時間停損持有天數（天）", 5, 30, 10, 1)
        time_stop_pct = st.slider("⏳ 時間停損盤整門檻（±%）", 0.5, 5.0, 2.0, 0.5, format="±%0.1f%%")
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
    if st.button("🔄 刷新最新市價與大師風控比對"):
        st.rerun()

    for idx, item in enumerate(portfolio):
        sym = item['symbol']
        name = item['name']
        mkt = item['market']
        entry_d = item['entry_date']
        avg_cost = item['avg_cost']
        shares = item['shares']
        stored_high = item.get('record_high', avg_cost)

        # 抓取行情、20MA 與同期大盤漲跌幅
        cur_price, max_high, ma20, taiex_roi = fetch_stock_and_market(sym, mkt, entry_d)
        if cur_price is None:
            cur_price, max_high, ma20 = avg_cost, stored_high, avg_cost

        # 鎖定波段最高價
        actual_high = max(stored_high, avg_cost, max_high)
        if actual_high != stored_high:
            portfolio[idx]['record_high'] = actual_high
            save_data(portfolio)

        # 損益與保本價精算
        net_pnl, roi, breakeven_p = calc_pnl(shares, avg_cost, cur_price, discount_display)
        pullback_pct = round(((actual_high - cur_price) / actual_high) * 100, 1) if actual_high > 0 else 0
        bias_20 = round(((cur_price - ma20) / ma20) * 100, 1) if ma20 > 0 else 0
        
        # 持有天數計算
        try:
            entry_dt = datetime.strptime(entry_d, "%Y-%m-%d").date()
            days_held = (date.today() - entry_dt).days
        except:
            days_held = 0

        # 【功能四】相對強度 RS 比對 (個股報酬 vs 大盤加權指數)
        rs_diff = round(roi - taiex_roi, 1)
        if rs_diff >= 5.0:
            rs_badge = f"💎 強勢領頭羊（領先大盤 +{rs_diff}%）"
        elif rs_diff <= -5.0:
            rs_badge = f"⚠️ 弱於大盤（落後大盤 {rs_diff}%）"
        else:
            rs_badge = f"➖ 與大盤同步（差異 {rs_diff}%）"

        # 【功能二】保本停損判定（波段最高漲幅達標自動啟動）
        max_gain_pct = ((actual_high - avg_cost) / avg_cost) * 100
        is_breakeven_active = max_gain_pct >= breakeven_trigger_pct
        
        initial_stop_price = round(avg_cost * (1 - stop_loss_pct / 100), 2)
        effective_stop_price = max(initial_stop_price, breakeven_p) if is_breakeven_active else initial_stop_price

        # 目標與回檔價位
        pullback_price = round(actual_high * (1 - pullback_target_pct / 100), 2)
        tp_price = round(avg_cost * (1 + take_profit_pct / 100), 2)

        # 風控狀態綜合判定
        status_text = "⚪ 持股續抱中"
        status_color = "gray"

        if cur_price <= effective_stop_price:
            if is_breakeven_active:
                status_text = f"🛡️ 觸發保本出場線（{effective_stop_price} 元）！利潤回吐，強制保護本金零虧損出場（{shares} 股）"
                status_color = "red"
            else:
                status_text = f"🔴 觸發 -{stop_loss_pct}% 停損線（{effective_stop_price} 元）！嚴格執行停損，全數出場（{shares} 股）"
                status_color = "red"
        elif cur_price <= pullback_price and cur_price > avg_cost:
            status_text = f"🟣 觸發高點回檔 {pullback_target_pct}%（跌破 {pullback_price} 元）！波段高點 {actual_high} 元，建議減碼 30%~50%（{int(shares*0.3)}～{int(shares*0.5)} 股）"
            status_color = "purple"
        elif cur_price >= tp_price:
            status_text = f"🟢 達到 +{take_profit_pct}% 波段目標（突破 {tp_price} 元）！建議減碼 30%~50%（{int(shares*0.3)}～{int(shares*0.5)} 股）"
            status_color = "green"
        elif bias_20 >= bias_threshold:
            status_text = f"🟠 月線正乖離達 {bias_20}%（閥值 {bias_threshold}%）！短線過熱，建議減碼 30%~50%"
            status_color = "orange"
        elif days_held >= time_stop_days and abs(roi) <= time_stop_pct:
            # 【功能五】時間停損判定
            status_text = f"⏳ 觸發時間停損（持股已 {days_held} 天，報酬僅 {roi:+}%）！資金動能停滯，建議換股操作釋放資金"
            status_color = "orange"

        # 渲染單檔卡片
        with st.container():
            st.markdown("---")
            st.subheader(f"{name} ({sym}.{mkt}) ｜ 持有 {days_held} 天 ｜ {rs_badge}")
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("最新市價 / 均價", f"${cur_price}", f"均價: ${avg_cost}")
            c2.metric("未實現淨損益 (扣稅費)", f"{net_pnl:+,} 元", f"{roi:+}%")
            
            stop_label = f"🛡️ 保本停損線" if is_breakeven_active else f"🔴 初始停損 (-{stop_loss_pct}%)"
            c3.metric(stop_label, f"${effective_stop_price}", "已啟動保本" if is_breakeven_active else "常規防守")
            c4.metric(f"波段最高 / 回檔線 (-{pullback_target_pct}%)", f"${actual_high}", f"回檔價: ${pullback_price}")

            st.markdown(f"**大師風控狀態：** :{status_color}[{status_text}]")

            # 【功能三】金字塔加碼防禦與操作區
            with st.expander(f"⚙️ 操作 {name}（順勢加碼防禦試算 / 減碼 / 結清）"):
                op_col1, op_col2, op_col3 = st.columns(3)
                
                with op_col1:
                    st.write("##### 🔼 順勢金字塔加碼")
                    add_p = st.number_input("預計加碼價格", min_value=0.1, step=0.1, value=cur_price, key=f"add_p_{idx}")
                    add_s = st.number_input("預計加碼股數", min_value=1, step=100, value=1000, key=f"add_s_{idx}")
                    
                    # 即時加碼安全防禦試算
                    new_tot_shares = shares + int(add_s)
                    simulated_avg = round(((shares * avg_cost) + (int(add_s) * add_p)) / new_tot_shares, 2)
                    safety_buf = round(((cur_price - simulated_avg) / cur_price) * 100, 1)
                    
                    st.caption(f"試算新均價：**${simulated_avg}** ｜ 安全緩衝距離：**{safety_buf:+}%**")
                    if safety_buf < pyramid_safety_margin:
                        st.error(f"⚠️ 警告：加碼後安全緩衝僅 {safety_buf}%（低於設定的 {pyramid_safety_margin}%）！這會大幅拉高持倉成本，一旦回檔極易由盈轉虧。")
                    else:
                        st.success(f"✅ 符合防禦原則：安全緩衝達 {safety_buf}%，成本控制良好。")

                    if st.button("確認執行加碼", key=f"btn_add_{idx}"):
                        portfolio[idx]['shares'] = new_tot_shares
                        portfolio[idx]['avg_cost'] = simulated_avg
                        save_data(portfolio)
                        st.success(f"加碼成功！新均價 ${simulated_avg}，總股數 {new_tot_shares}")
                        st.rerun()

                with op_col2:
                    st.write("##### 🔽 分批停利減碼")
                    reduce_s = st.number_input("減碼股數", min_value=1, max_value=shares, step=100, key=f"red_s_{idx}")
                    if st.button("確認減碼", key=f"btn_red_{idx}"):
                        portfolio[idx]['shares'] = shares - int(reduce_s)
                        save_data(portfolio)
                        st.success(f"已減碼 {reduce_s} 股，剩餘 {shares - int(reduce_s)} 股")
                        st.rerun()

                with op_col3:
                    st.write("##### 🗑️ 結清出場")
                    if st.button("結清並移除持倉", key=f"del_{idx}"):
                        portfolio.pop(idx)
                        save_data(portfolio)
                        st.warning(f"已移除 {name}")
                        st.rerun()
