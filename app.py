import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, date
import json
import os

st.set_page_config(page_title="台股持倉風控系統", layout="wide", initial_sidebar_state="collapsed")

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

def fetch_stock_info(symbol, market, entry_date_str):
    ticker = f"{symbol}.TWO" if market.upper() == "TWO" else f"{symbol}.TW"
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(start=entry_date_str)
        if df.empty:
            df = stock.history(period="1mo")
        if df.empty:
            return None, None, None
        
        current_price = round(float(df['Close'].iloc[-1]), 2)
        max_high = round(float(df['High'].max()), 2)
        
        df_all = stock.history(period="3mo")
        if len(df_all) >= 20:
            ma20 = round(float(df_all['Close'].tail(20).mean()), 2)
        else:
            ma20 = current_price
            
        return current_price, max_high, ma20
    except Exception as e:
        return None, None, None

def calc_pnl(shares, avg_cost, current_price, fee_discount):
    # 手續費率 = 0.1425% * 券商折數 (例如 0.6 代表 6 折)
    buy_fee_rate = 0.001425 * fee_discount
    sell_fee_rate = 0.001425 * fee_discount
    tax_rate = 0.003
    
    total_buy_cost = (shares * avg_cost) * (1 + buy_fee_rate)
    total_sell_net = (shares * current_price) * (1 - sell_fee_rate - tax_rate)
    
    net_pnl = round(total_sell_net - total_buy_cost)
    roi = round((net_pnl / total_buy_cost) * 100, 2)
    return net_pnl, roi

# --- 介面開始 ---
st.title("📈 台股持倉管理與自訂風控系統")

# 1. 自訂風控與費用參數區 (手機展開即可調整)
with st.expander("⚙️ 自訂風控參數與手續費折數（點此展開調整）", expanded=False):
    st.caption("調整下方滑桿後，所有持股的停損線、停利線、扣除稅費之淨損益將立即重新計算。")
    c_set1, c_set2 = st.columns(2)
    with c_set1:
        stop_loss_pct = st.slider("🔴 停損趴數 (%)", min_value=1.0, max_value=20.0, value=7.0, step=0.5, format="-%0.1f%%")
        pullback_target_pct = st.slider("🟣 高點回檔停利趴數 (%)", min_value=3.0, max_value=30.0, value=10.0, step=0.5, format="-%0.1f%%")
        take_profit_pct = st.slider("🟢 波段目標停利趴數 (%)", min_value=5.0, max_value=100.0, value=20.0, step=1.0, format="+%0.0f%%")
    with c_set2:
        bias_threshold = st.slider("🟠 月線正乖離過熱閥值 (%)", min_value=10.0, max_value=60.0, value=30.0, step=1.0, format="+%0.0f%%")
        discount_display = st.slider("💰 券商手續費折數（例：0.6 = 6 折，0.28 = 2.8 折）", min_value=0.1, max_value=1.0, value=0.6, step=0.01, format="%0.2f")
        st.info(f"當前設定：停損 -{stop_loss_pct}% ｜ 高點回檔 -{pullback_target_pct}% ｜ 目標 +{take_profit_pct}% ｜ 乖離 +{bias_threshold}% ｜ 手續費 {discount_display*10:.1f} 折")

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

# 3. 持倉列表與風控即時判定
if not portfolio:
    st.info("目前尚無持倉，請點擊上方「➕ 新增持股」建立第一檔股票。")
else:
    if st.button("🔄 刷新最新市價與風控比對"):
        st.rerun()

    for idx, item in enumerate(portfolio):
        sym = item['symbol']
        name = item['name']
        mkt = item['market']
        entry_d = item['entry_date']
        avg_cost = item['avg_cost']
        shares = item['shares']
        stored_high = item.get('record_high', avg_cost)

        cur_price, max_high, ma20 = fetch_stock_info(sym, mkt, entry_d)
        if cur_price is None:
            cur_price = avg_cost
            max_high = stored_high
            ma20 = avg_cost

        # 鎖定進場後最高價（只升不降）
        actual_high = max(stored_high, avg_cost, max_high)
        if actual_high != stored_high:
            portfolio[idx]['record_high'] = actual_high
            save_data(portfolio)

        # 計算淨損益 (傳入自訂手續費折數)
        net_pnl, roi = calc_pnl(shares, avg_cost, cur_price, discount_display)
        pullback_pct = round(((actual_high - cur_price) / actual_high) * 100, 1) if actual_high > 0 else 0
        bias_20 = round(((cur_price - ma20) / ma20) * 100, 1) if ma20 > 0 else 0

        # 計算動態觸發門檻價格
        stop_price = round(avg_cost * (1 - stop_loss_pct / 100), 2)
        pullback_price = round(actual_high * (1 - pullback_target_pct / 100), 2)
        tp_price = round(avg_cost * (1 + take_profit_pct / 100), 2)

        # 動態風控判定
        status_text = "⚪ 持股續抱中"
        status_color = "gray"
        
        if cur_price <= stop_price:
            status_text = f"🔴 觸發 -{stop_loss_pct}% 停損線（{stop_price} 元）！建議全數出場（{shares} 股）"
            status_color = "red"
        elif cur_price <= pullback_price and cur_price > avg_cost:
            status_text = f"🟣 觸發高點回檔 {pullback_target_pct}%（跌破 {pullback_price} 元）！波段高點 {actual_high} 元（目前回檔 {pullback_pct}%），建議減碼 30%~50%（{int(shares*0.3)}～{int(shares*0.5)} 股）"
            status_color = "purple"
        elif cur_price >= tp_price:
            status_text = f"🟢 達到 +{take_profit_pct}% 波段目標（突破 {tp_price} 元）！建議減碼 30%~50%（{int(shares*0.3)}～{int(shares*0.5)} 股）"
            status_color = "green"
        elif bias_20 >= bias_threshold:
            status_text = f"🟠 月線正乖離達 {bias_20}%（閥值 {bias_threshold}%）！短線過熱，建議減碼 30%~50%"
            status_color = "orange"

        # 渲染單檔卡片
        with st.container():
            st.markdown("---")
            st.subheader(f"{name} ({sym}.{mkt})")
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("最新市價 / 均價", f"${cur_price}", f"均價: ${avg_cost}")
            c2.metric("未實現損益 (已扣稅費)", f"{net_pnl:+,} 元", f"{roi:+}%")
            c3.metric(f"波段最高 / 回檔線 (-{pullback_target_pct}%)", f"${actual_high}", f"回檔價: ${pullback_price}")
            c4.metric(f"當前 20MA / 乖離率", f"${ma20}", f"乖離 {bias_20}%")

            st.markdown(f"**風控狀態：** :{status_color}[{status_text}]")

            # 加碼 / 減碼 / 刪除 操作區
            with st.expander(f"⚙️ 操作 {name} 持股（加碼 / 減碼 / 結清）"):
                op_col1, op_col2, op_col3 = st.columns(3)
                
                with op_col1:
                    st.write("##### 🔼 加碼買進")
                    add_p = st.number_input("加碼價格", min_value=0.1, step=0.1, key=f"add_p_{idx}")
                    add_s = st.number_input("加碼股數", min_value=1, step=100, key=f"add_s_{idx}")
                    if st.button("確認加碼", key=f"btn_add_{idx}"):
                        new_total_shares = shares + int(add_s)
                        new_avg_cost = round(((shares * avg_cost) + (int(add_s) * add_p)) / new_total_shares, 2)
                        portfolio[idx]['shares'] = new_total_shares
                        portfolio[idx]['avg_cost'] = new_avg_cost
                        save_data(portfolio)
                        st.success(f"加碼成功！新均價為 {new_avg_cost}，新總股數為 {new_total_shares}")
                        st.rerun()

                with op_col2:
                    st.write("##### 🔽 分批減碼")
                    reduce_s = st.number_input("減碼股數", min_value=1, max_value=shares, step=100, key=f"red_s_{idx}")
                    if st.button("確認減碼", key=f"btn_red_{idx}"):
                        portfolio[idx]['shares'] = shares - int(reduce_s)
                        save_data(portfolio)
                        st.success(f"已減碼 {reduce_s} 股，剩餘 {shares - int(reduce_s)} 股")
                        st.rerun()

                with op_col3:
                    st.write("##### 🗑️ 結清 / 刪除")
                    if st.button("結清並移除持倉", key=f"del_{idx}"):
                        portfolio.pop(idx)
                        save_data(portfolio)
                        st.warning(f"已移除 {name}")
                        st.rerun()
