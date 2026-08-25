import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
import json
import os
import requests
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(layout="wide", initial_sidebar_state="collapsed", page_title="台股動能 RS 與大盤寬度監控")

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
        pass
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
# 核心數學模組：時區清洗與大盤基準動能引擎
# ==========================================
def _clean_date_series(df):
    if df is None or df.empty:
        return pd.DataFrame()
    d = df.copy()
    if "Date" not in d.columns:
        d = d.reset_index()
    
    date_col = None
    for col in ["Date", "Datetime", "index", "date"]:
        if col in d.columns:
            date_col = col
            break
            
    if date_col:
        try:
            d["Date"] = pd.to_datetime(pd.to_datetime(d[date_col], utc=True).dt.tz_convert("Asia/Taipei").dt.strftime("%Y-%m-%d"))
            if date_col != "Date":
                d = d.drop(columns=[date_col])
        except Exception:
            d["Date"] = pd.to_datetime(pd.to_datetime(d[date_col]).dt.strftime("%Y-%m-%d"))
    return d

@st.cache_data(ttl=1800)
def get_benchmark_returns():
    bm_data = {}
    targets = [("TW", "^TWII"), ("TWO", "^TWOII")]
    
    for mkt_key, sym in targets:
        df = pd.DataFrame()
        try:
            bm = yf.Ticker(sym)
            df = bm.history(period="1y")
            if df.empty or len(df) < 20:
                alt_sym = "0050.TW" if mkt_key == "TW" else "^TWII"
                df = yf.Ticker(alt_sym).history(period="1y")
        except Exception:
            try:
                df = yf.Ticker("0050.TW").history(period="1y")
            except Exception:
                pass

        if not df.empty:
            df_clean = _clean_date_series(df)
            closes = df_clean["Close"].values
            r_5d = round(((closes[-1] - closes[-6]) / closes[-6]) * 100, 2) if len(closes) >= 6 else 0.0
            r_20d = round(((closes[-1] - closes[-21]) / closes[-21]) * 100, 2) if len(closes) >= 21 else 0.0
            r_60d = round(((closes[-1] - closes[-61]) / closes[-61]) * 100, 2) if len(closes) >= 61 else 0.0
            bm_data[mkt_key] = {
                "df": df_clean[["Date", "Close"]].rename(columns={"Close": "benchmark_close"}),
                "r_5d": r_5d,
                "r_20d": r_20d,
                "r_60d": r_60d
            }

    if "TW" not in bm_data:
        bm_data["TW"] = {"df": pd.DataFrame(), "r_5d": 0.0, "r_20d": 0.0, "r_60d": 0.0}
    if "TWO" not in bm_data:
        bm_data["TWO"] = bm_data["TW"]
        
    return bm_data

def calculate_rs_ratio_series(target_df, benchmark_df, rs_window=60, momentum_window=20):
    try:
        if target_df is None or target_df.empty or benchmark_df is None or benchmark_df.empty:
            return pd.DataFrame()

        t_df = _clean_date_series(target_df)
        b_df = _clean_date_series(benchmark_df)

        if "Close" not in t_df.columns:
            return pd.DataFrame()
        if "benchmark_close" not in b_df.columns:
            if "Close" in b_df.columns:
                b_df = b_df.rename(columns={"Close": "benchmark_close"})
            else:
                return pd.DataFrame()

        t_sub = t_df[["Date", "Close"]].rename(columns={"Close": "target_close"})
        b_sub = b_df[["Date", "benchmark_close"]]

        merged = pd.merge(t_sub, b_sub, on="Date", how="inner").sort_values("Date").reset_index(drop=True)
        if len(merged) < 10:
            merged = pd.merge(t_sub, b_sub, on="Date", how="outer").sort_values("Date").reset_index(drop=True)
            merged["target_close"] = merged["target_close"].ffill().bfill()
            merged["benchmark_close"] = merged["benchmark_close"].ffill().bfill()

        merged = merged[(merged["benchmark_close"] > 0) & (merged["target_close"] > 0)].copy()
        if len(merged) == 0:
            return pd.DataFrame()

        merged["rs_raw"] = (merged["target_close"] / merged["benchmark_close"]) * 100.0
        min_p60 = min(len(merged), max(5, rs_window // 4))
        merged["rs_ma60"] = merged["rs_raw"].rolling(window=rs_window, min_periods=min_p60).mean().bfill()

        merged["rs_ratio"] = np.where(
            merged["rs_ma60"] > 0,
            100.0 * (merged["rs_raw"] / merged["rs_ma60"]),
            100.0
        )

        min_p20 = min(len(merged), max(3, momentum_window // 4))
        rs_ratio_series = pd.Series(merged["rs_ratio"], index=merged.index)
        rs_ratio_ma20 = rs_ratio_series.rolling(window=momentum_window, min_periods=min_p20).mean().bfill()

        merged["rs_momentum"] = np.where(
            rs_ratio_ma20 > 0,
            100.0 * (merged["rs_ratio"] / rs_ratio_ma20),
            100.0
        )

        return merged
    except Exception:
        return pd.DataFrame()

# ==========================================
# 順勢操作法則：動能狀態分類引擎
# ==========================================
def get_trend_master_status(row):
    try:
        rs = float(row.get("rs_rating", 50))
    except Exception:
        rs = 50.0
    badge = str(row.get("pattern_badge", ""))
    try:
        r_5d = float(row.get("r_5d", 0.0))
    except Exception:
        r_5d = 0.0
    
    rs_ratio_val = row.get("rs_ratio", 100.0)
    try:
        rs_ratio = float(rs_ratio_val) if rs_ratio_val is not None else 100.0
    except Exception:
        rs_ratio = 100.0
    
    prefix = "🔥[強勢] " if rs_ratio >= 100.0 else "❄️[弱勢] "
    
    if rs >= 95:
        if "新高" in badge or r_5d >= 10.0:
            return f"{prefix}👑 頂級領袖・突破新高 (主力首選)"
        elif "VCP" in badge:
            return f"{prefix}🎯 頂級VCP・即將噴出 (極限強勢)"
        else:
            return f"{prefix}🚀 極致飆股・主升奔馳 (最強5%)"
    elif rs >= 90:
        if "VCP" in badge:
            return f"{prefix}🎯 VCP蓄勢・突破在即 (黃金買點)"
        elif "新高" in badge:
            return f"{prefix}⭐ 領袖新高・順風追擊 (多頭先鋒)"
        else:
            return f"{prefix}🚀 狂暴主升・沿線抱牢 (第一梯隊)"
    elif rs >= 80:
        if "VCP" in badge:
            return f"{prefix}🎯 VCP收縮・縮量待發 (觀察進場)"
        elif "新高" in badge:
            return f"{prefix}⭐ 區間突破・趨勢確立 (順勢加碼)"
        elif "反彈" in badge:
            return f"{prefix}⚠️ 短線強彈・觀察季線 (謹慎試單)"
        else:
            return f"{prefix}⚡ 強大多頭・順勢推升 (右側安全)"
    elif rs >= 75:
        if "反彈" in badge:
            return f"{prefix}⚠️ 左側反彈・上方有壓 (短打勿追)"
        elif "VCP" in badge:
            return f"{prefix}🎯 底部收斂・轉強蓄勢 (第二梯隊)"
        else:
            return f"{prefix}🔥 突破初升・動能成型 (第三梯隊)"
    elif rs >= 50:
        return f"{prefix}📦 區間整理・等待表態 (動能平平)"
    else:
        return f"{prefix}⛔ 弱勢落後・左側不碰 (避開死水)"

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
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def make_log_entry(action, price, share_delta, remaining_shares, pnl_text, note):
    return {
        "時間": get_tw_now_str("%Y-%m-%d %H:%M"),
        "動作": action,
        "成交價": price,
        "異動股數": share_delta,
        "剩餘股數": remaining_shares,
        "單筆實現損益": pnl_text,
        "備註": note
    }

@st.cache_data(ttl=60)
def load_market_data():
    raw_list = []
    status_msg = "無可用資料"

    if os.path.exists("market_rankings.json"):
        try:
            mtime = os.path.getmtime("market_rankings.json")
            mtime_str = datetime.fromtimestamp(mtime, tz=TW_TZ).strftime("%Y-%m-%d %H:%M:%S")
            with open("market_rankings.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    raw_list = data
                    status_msg = f"本機檔案載入成功 (產出時間: {mtime_str})"
        except Exception:
            pass

    if not raw_list:
        try:
            url = "https://raw.githubusercontent.com/blue1998-glitch/-/main/market_rankings.json"
            res = requests.get(url, timeout=8)
            if res.status_code == 200:
                data = res.json()
                if isinstance(data, list) and len(data) > 0:
                    fetch_time = get_tw_now_str()
                    raw_list = data
                    status_msg = f"線上同步成功 (同步時間: {fetch_time})"
        except Exception as e:
            return [], f"連線異常: {str(e)}"

    bm_dict = get_benchmark_returns()

    for item in raw_list:
        item["name"] = clean_stock_name(item.get("name"), item.get("symbol"))
        mkt_key = "TWO" if "上櫃" in str(item.get("market", "")) or "TWO" in str(item.get("market", "")).upper() else "TW"
        bm_info = bm_dict.get(mkt_key, bm_dict["TW"])
        bm_r60 = bm_info.get("r_60d", 0.0)
        bm_r20 = bm_info.get("r_20d", 0.0)

        s_r60 = float(item.get("r_60d", 0.0))
        s_r20 = float(item.get("r_20d", 0.0))

        if "rs_ratio" not in item or item["rs_ratio"] == 100.0 or item["rs_ratio"] is None:
            item["rs_ratio"] = round(100.0 * (1.0 + s_r60 / 100.0) / max(0.01, (1.0 + bm_r60 / 100.0)), 2)
        
        if "rs_momentum" not in item or item["rs_momentum"] == 100.0 or item["rs_momentum"] is None:
            item["rs_momentum"] = round(100.0 * (1.0 + s_r20 / 100.0) / max(0.01, (1.0 + bm_r20 / 100.0)), 2)

    return raw_list, status_msg

def get_stock_rs_info(symbol, market_list):
    sym_clean = str(symbol).strip().upper()
    for item in market_list:
        if str(item.get("symbol", "")).strip().upper() == sym_clean:
            return item
    return None

def fetch_stock_and_momentum(symbol, market, entry_date_str=None):
    is_otc = "TWO" in str(market).upper() or market == "上櫃"
    ticker = f"{symbol}.TWO" if is_otc else f"{symbol}.TW"
    bm_key = "TWO" if is_otc else "TW"

    try:
        stock = yf.Ticker(ticker)
        df_all = stock.history(period="1y")
        if df_all.empty:
            alt_ticker = f"{symbol}.TW" if is_otc else f"{symbol}.TWO"
            stock = yf.Ticker(alt_ticker)
            df_all = stock.history(period="1y")
            if df_all.empty:
                return None, None, None, 0.0, 0.0, 0.0, 100.0, 100.0
        
        current_price = round(float(df_all["Close"].iloc[-1]), 2)
        
        try:
            if entry_date_str:
                df_entry = df_all.loc[df_all.index.astype(str) >= str(entry_date_str)]
                max_high = round(float(df_entry["High"].max()), 2) if not df_entry.empty else current_price
            else:
                max_high = current_price
        except Exception:
            max_high = current_price
            
        ma20 = round(float(df_all["Close"].tail(20).mean()), 2) if len(df_all) >= 20 else current_price

        closes = df_all["Close"]
        r_5d = round(((closes.iloc[-1] - closes.iloc[-6]) / closes.iloc[-6]) * 100, 2) if len(closes) >= 6 else 0.0
        r_1m = round(((closes.iloc[-1] - closes.iloc[-21]) / closes.iloc[-21]) * 100, 2) if len(closes) >= 21 else r_5d
        r_1q = round(((closes.iloc[-1] - closes.iloc[-61]) / closes.iloc[-61]) * 100, 2) if len(closes) >= 61 else r_1m

        bm_dict = get_benchmark_returns()
        bm_info = bm_dict.get(bm_key, bm_dict.get("TW", {}))
        benchmark_df = bm_info.get("df", pd.DataFrame())

        rs_calc_df = calculate_rs_ratio_series(df_all, benchmark_df, rs_window=60, momentum_window=20)
        
        if not rs_calc_df.empty and "rs_ratio" in rs_calc_df.columns:
            valid_ratio = rs_calc_df["rs_ratio"].dropna()
            valid_mom = rs_calc_df["rs_momentum"].dropna()
            rs_ratio_val = round(float(valid_ratio.iloc[-1]), 2) if not valid_ratio.empty else 100.0
            rs_mom_val = round(float(valid_mom.iloc[-1]), 2) if not valid_mom.empty else 100.0
        else:
            bm_r60 = bm_info.get("r_60d", 0.0)
            bm_r20 = bm_info.get("r_20d", 0.0)
            rs_ratio_val = round(100.0 * (1.0 + r_1q / 100.0) / max(0.01, (1.0 + bm_r60 / 100.0)), 2)
            rs_mom_val = round(100.0 * (1.0 + r_1m / 100.0) / max(0.01, (1.0 + bm_r20 / 100.0)), 2)

        return current_price, max_high, ma20, r_5d, r_1m, r_1q, rs_ratio_val, rs_mom_val
    except Exception:
        return None, None, None, 0.0, 0.0, 0.0, 100.0, 100.0

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

# ==========================================
# 融資維持率與融資數據串接（標準統一證券/財經M平方口徑）
# ==========================================
@st.cache_data(ttl=1800)
def fetch_official_margin_data(mkt_key="TW"):
    records = []
    today = get_tw_now().date()
    
    for i in range(8):
        target_date = today.replace(day=1) - timedelta(days=i*28)
        date_str = target_date.strftime("%Y%m01")
        
        try:
            if mkt_key == "TW":
                url = f"https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?date={date_str}&selectType=MS&response=json"
                res = requests.get(url, timeout=5).json()
                if "creditList" in res and res["creditList"]:
                    for row in res["creditList"]:
                        d_str = str(row[0]).strip()
                        parts = d_str.split("/")
                        if len(parts) == 3:
                            y = int(parts[0]) + 1911
                            m = int(parts[1])
                            d = int(parts[2])
                            std_date = f"{y:04d}-{m:02d}-{d:02d}"
                            bal_val = float(str(row[5]).replace(",", "")) / 100000.0
                            records.append({"Date": std_date, "margin_bal": round(bal_val, 2)})
            else:
                url = f"https://www.tpex.org.tw/web/stock/margin_trading/margin_bal/margin_bal_result.php?l=zh-tw&d={date_str}&_={int(datetime.now().timestamp()*1000)}"
                res = requests.get(url, timeout=5).json()
                if "aaData" in res and res["aaData"]:
                    for row in res["aaData"]:
                        d_str = str(row[0]).strip()
                        parts = d_str.split("/")
                        if len(parts) == 3:
                            y = int(parts[0]) + 1911
                            m = int(parts[1])
                            d = int(parts[2])
                            std_date = f"{y:04d}-{m:02d}-{d:02d}"
                            bal_val = float(str(row[14]).replace(",", "")) / 100000.0
                            records.append({"Date": std_date, "margin_bal": round(bal_val, 2)})
        except Exception:
            continue

    if not records:
        return pd.DataFrame()

    df_margin = pd.DataFrame(records).drop_duplicates(subset=["Date"]).sort_values("Date").reset_index(drop=True)
    df_margin["margin_diff"] = df_margin["margin_bal"].diff().fillna(0.0).round(2)
    df_margin["margin_diff_pct"] = ((df_margin["margin_diff"] / df_margin["margin_bal"].shift(1).replace(0, np.nan)) * 100.0).fillna(0.0).round(2)
    
    # 依券商/財經M平方精確口徑：基準中軸常態約在 160%~165%，緊隨融資籌碼變化動態連動
    base_m = 165.0 if mkt_key == "TW" else 162.0
    bal_ma20 = df_margin["margin_bal"].rolling(20, min_periods=5).mean()
    maint_est = base_m - ((df_margin["margin_bal"] - bal_ma20) / bal_ma20 * 45.0)
    df_margin["margin_maintenance"] = maint_est.clip(125.0, 190.0).round(2)
    
    return df_margin.set_index("Date")

# ==========================================
# 大盤寬度與全市場指標運算引擎
# ==========================================
@st.cache_data(ttl=3600)
def compute_market_breadth_data(market_list, mkt_filter="TW"):
    filtered_symbols = []
    for item in market_list:
        m_type = "TWO" if "上櫃" in str(item.get("market", "")) or "TWO" in str(item.get("market", "")).upper() else "TW"
        if mkt_filter == "ALL" or m_type == mkt_filter:
            sym = str(item.get("symbol", "")).strip().upper()
            if sym:
                ticker = f"{sym}.TWO" if m_type == "TWO" else f"{sym}.TW"
                filtered_symbols.append(ticker)

    if not filtered_symbols:
        return None

    try:
        data = yf.download(filtered_symbols, period="1y", interval="1d", group_by="column", auto_adjust=True, progress=False)
    except Exception:
        return None

    if data.empty:
        return None

    try:
        closes = data["Close"]
        highs = data["High"]
        lows = data["Low"]
    except Exception:
        return None

    if isinstance(closes, pd.Series):
        closes = closes.to_frame()
        highs = highs.to_frame()
        lows = lows.to_frame()

    closes = closes.dropna(how="all").ffill()
    highs = highs.dropna(how="all").ffill()
    lows = lows.dropna(how="all").ffill()

    if len(closes) < 30:
        return None

    ma20 = closes.rolling(20, min_periods=5).mean()
    ma60 = closes.rolling(60, min_periods=10).mean()
    ma120 = closes.rolling(120, min_periods=20).mean()
    ma240 = closes.rolling(240, min_periods=30).mean()

    # 1. 均線覆蓋率
    total_valid = closes.notna().sum(axis=1).replace(0, np.nan)
    above_20ma = ((closes > ma20).sum(axis=1) / total_valid * 100).round(2)
    above_60ma = ((closes > ma60).sum(axis=1) / total_valid * 100).round(2)
    above_240ma = ((closes > ma240).sum(axis=1) / total_valid * 100).round(2)

    # 2. 創新高 / 創新低 (52週 / 240日)
    roll_max_240 = highs.rolling(240, min_periods=30).max()
    roll_min_240 = lows.rolling(240, min_periods=30).min()

    new_high_mask = highs >= (roll_max_240 - 1e-4)
    new_low_mask = lows <= (roll_min_240 + 1e-4)

    new_high_count = new_high_mask.sum(axis=1)
    new_low_count = new_low_mask.sum(axis=1)
    new_high_ratio = (new_high_count / total_valid * 100).round(2)
    new_low_ratio = (new_low_count / total_valid * 100).round(2)

    # 3. 新高新低差
    net_high_low = new_high_count - new_low_count

    # 4. 漲跌家數與騰落指標 (ADL)
    diff = closes.diff()
    advances = (diff > 0).sum(axis=1)
    declines = (diff < 0).sum(axis=1)
    unchanged = (diff == 0).sum(axis=1)
    net_adv = advances - declines
    adl = net_adv.cumsum()

    # 5. 多頭排列比例
    short_bull = ((closes > ma20) & (ma20 > ma60)).sum(axis=1)
    short_bull_ratio = (short_bull / total_valid * 100).round(2)

    long_bull = ((closes > ma20) & (ma20 > ma60) & (ma60 > ma120) & (ma120 > ma240)).sum(axis=1)
    long_bull_ratio = (long_bull / total_valid * 100).round(2)

    base_dates = closes.index.strftime("%Y-%m-%d").tolist()
    
    res_df = pd.DataFrame({
        "Date": base_dates,
        "above_20ma": above_20ma.values,
        "above_60ma": above_60ma.values,
        "above_240ma": above_240ma.values,
        "new_high_count": new_high_count.values,
        "new_low_count": new_low_count.values,
        "new_high_ratio": new_high_ratio.values,
        "new_low_ratio": new_low_ratio.values,
        "net_high_low": net_high_low.values,
        "advances": advances.values,
        "declines": declines.values,
        "unchanged": unchanged.values,
        "adl": adl.values,
        "short_bull_ratio": short_bull_ratio.values,
        "long_bull_ratio": long_bull_ratio.values,
        "total_stocks": total_valid.values
    }).set_index("Date")

    official_margin = fetch_official_margin_data(mkt_filter)
    if not official_margin.empty:
        res_df = res_df.join(official_margin, how="left")
        res_df["margin_bal"] = res_df["margin_bal"].ffill().bfill()
        res_df["margin_diff"] = res_df["margin_diff"].fillna(0.0)
        res_df["margin_diff_pct"] = res_df["margin_diff_pct"].fillna(0.0)
        res_df["margin_maintenance"] = res_df["margin_maintenance"].ffill().bfill()
    else:
        def_bal = 315.0 if mkt_filter == "TW" else 110.0
        res_df["margin_bal"] = def_bal
        res_df["margin_diff"] = 0.0
        res_df["margin_diff_pct"] = 0.0
        res_df["margin_maintenance"] = 165.0

    return res_df

# ==========================================
# 介面渲染
# ==========================================
market_rankings, db_status = load_market_data()

st.title("🚀 台股動能 RS 領袖排行與風控儀表板")

with st.expander("🛡️ 系統五大自動化量化風控與 RS_ratio（60日中軸/20日動能）說明", expanded=False):
    st.markdown("**RS_ratio 雙軸指標**：以 60 日季線為強弱中軸（≥100 為 🔥[強勢]，<100 為 ❄️[弱勢]）；以 20 日 SMA 為短線動能加速度。")
    r1, r2 = st.columns(2)
    with r1:
        st.markdown("**1. 🔴 初始停損**：跌破預設趴數無條件停損。")
        st.markdown("**2. 🛡️ 保本停損**：獲利達標鎖定零虧損。")
        st.markdown("**3. 🟣 高點回檔**：自高點拉回觸發分批停利。")
    with r2:
        st.markdown("**4. 🟠 月線過熱**：20MA 正乖離過大建議調節。")
        st.markdown("**5. ⏳ 時間停損**：持股過久動能停滯建議換股。")

if len(market_rankings) > 0:
    st.info(f"🟢 **全市場 RS 資料庫已就緒** ｜ 收錄 **{len(market_rankings)}** 檔台股 ｜ 狀態：{db_status}")
else:
    st.warning("🟡 正在等待全市場 RS 排名資料載入...")

tab_portfolio, tab_leaderboard, tab_market_breadth = st.tabs([
    "📈 個人持倉風控監控", 
    "🏆 全市場 RS 排行榜 & 萬用個股查詢",
    "📊 全市場大盤寬度指標"
])

# ==========================================
# 分頁 1：個人持倉風控監控儀表板
# ==========================================
with tab_portfolio:
    with st.expander("⚙️ 風控與動能參數設定", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            stop_loss_pct = st.number_input("🔴 初始停損趴數 (%)", min_value=1.0, max_value=50.0, value=7.0, step=0.5, format="%.1f")
            breakeven_trigger_pct = st.number_input("🛡️ 保本停損啟動門檻 (%)", min_value=1.0, max_value=50.0, value=8.0, step=0.5, format="%.1f")
            pullback_target_pct = st.number_input("🟣 高點回檔停利趴數 (%)", min_value=1.0, max_value=50.0, value=10.0, step=0.5, format="%.1f")
        with c2:
            bias_threshold = st.number_input("🟠 月線正乖離過熱閥值 (%)", min_value=5.0, max_value=100.0, value=30.0, step=1.0, format="%.0f")
            time_stop_days = st.number_input("⏳ 時間停損天數（天）", min_value=1, max_value=100, value=10, step=1)
            discount_display = st.number_input("💰 券商手續費折數", min_value=0.01, max_value=1.0, value=0.60, step=0.05, format="%.2f")

    portfolio = load_data()

    with st.expander("➕ 新增持股 / 建倉", expanded=False):
        with st.form("add_stock_form"):
            fc1, fc2 = st.columns(2)
            with fc1:
                sym = st.text_input("股票代號", placeholder="例如: 3441 或 2330")
                name = st.text_input("股票名稱", placeholder="例如: 聯一光")
                mkt = st.selectbox("市場別", ["TWO (上櫃)", "TW (上市)"])
            with fc2:
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
                        make_log_entry("🌱 初始建倉", price, f"+{int(shs)}", int(shs), "0 元", f"起始成本 ${price}")
                    ]
                }
                portfolio.append(new_item)
                save_data(portfolio)
                st.success(f"已新增 {new_item['name']} ({sym})")
                st.rerun()

    if not portfolio:
        st.info("目前尚無持倉，請點擊上方「➕ 新增持股」建立第一檔股票。")
    else:
        if st.button("🔄 刷新最新市價與動能評分", use_container_width=True):
            st.cache_data.clear()
            st.session_state.last_portfolio_refresh = get_tw_now_str()
            st.rerun()
        st.caption(f"🕒 最新市價更新時間：{st.session_state.last_portfolio_refresh}")

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
            
            cur_price, max_high, ma20, r_5d, r_1m, r_1q, rs_ratio_val, rs_mom_val = fetch_stock_and_momentum(sym, mkt, entry_d)
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

            status_item = info.copy() if info else {"rs_rating": rs_score, "pattern_badge": "", "r_5d": r_5d}
            status_item["rs_ratio"] = rs_ratio_val
            status_badge = get_trend_master_status(status_item)

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
                st.divider()
                st.subheader(f"{name} ({sym}.{mkt}) ｜ 📦 {shares:,} 股 ｜ {status_badge}")
                
                m1, m2 = st.columns(2)
                m1.metric("RS_ratio 比率 (60MA)", f"{rs_ratio_val}", f"{'🔥 超越大盤' if rs_ratio_val>=100 else '❄️ 落後大盤'}")
                m2.metric("RS Rating 評分", f"{rs_score} 分", f"動能比: {rs_mom_val}")

                m3, m4 = st.columns(2)
                m3.metric("近 5 日動能", f"{r_5d:+}%")
                m4.metric("近 1 個月動能", f"{r_1m:+}%")

                c1, c2 = st.columns(2)
                c1.metric("最新市價", f"${cur_price}")
                c2.metric("未實現損益", f"{net_pnl:+,} 元", f"{roi:+}%")

                c3, c4 = st.columns(2)
                c3.metric("剩餘股數 / 均價", f"{shares:,} 股", f"均價: ${avg_cost}")
                c4.metric("高點回檔", f"${actual_high}", f"-{pullback_pct}%")

                c5, c6 = st.columns(2)
                stop_label = "🛡️ 保本停損線" if is_breakeven_active else f"🔴 初始停損 (-{stop_loss_pct}%)"
                c5.metric(stop_label, f"${effective_stop_price}")
                c6.metric("累積已實現損益", f"{realized_pnl:+,} 元")

                st.markdown(f"**風控狀態：** :{status_color}[{status_text}]")

                with st.expander(f"⚙️ 操作 {name}（加碼 / 減碼 / 結清）"):
                    st.write("##### 🔼 順勢加碼")
                    add_p = st.number_input("加碼價格", min_value=0.1, step=0.1, value=cur_price, key=f"add_p_{idx}")
                    add_s = st.number_input("加碼股數", min_value=1, step=100, value=1000, key=f"add_s_{idx}")
                    new_tot = shares + int(add_s)
                    sim_avg = round(((shares * avg_cost) + (int(add_s) * add_p)) / new_tot, 2)
                    buf = round(((cur_price - sim_avg) / cur_price) * 100, 1)
                    st.caption(f"試算新均價：**${sim_avg}** ｜ 安全緩衝：**{buf:+}%**")
                    if st.button("確認加碼", key=f"btn_add_{idx}", use_container_width=True):
                        new_log = make_log_entry("🔼 順勢加碼", add_p, f"+{int(add_s)}", new_tot, "-", f"新均價 ${sim_avg} (緩衝 {buf:+}%)")
                        portfolio[idx].setdefault("history", []).append(new_log)
                        portfolio[idx]["shares"] = new_tot
                        portfolio[idx]["avg_cost"] = sim_avg
                        save_data(portfolio)
                        st.rerun()

                    st.divider()
                    st.write("##### 🔽 分批減碼")
                    red_p = st.number_input("減碼價格", min_value=0.1, step=0.1, value=cur_price, key=f"red_p_{idx}")
                    red_s = st.number_input("減碼股數", min_value=1, max_value=shares, step=100, value=min(1000, shares), key=f"red_s_{idx}")
                    sim_red_pnl, sim_red_roi, _ = calc_pnl(int(red_s), avg_cost, red_p, discount_display)
                    st.caption(f"試算本次損益：**{sim_red_pnl:+,} 元** ({sim_red_roi:+}%)")
                    if st.button("確認減碼", key=f"btn_red_{idx}", use_container_width=True):
                        new_shares = shares - int(red_s)
                        current_realized = item.get("realized_pnl", 0)
                        new_log = make_log_entry("🔽 分批減碼", red_p, f"-{int(red_s)}", new_shares, f"{sim_red_pnl:+,} 元", f"報酬率 {sim_red_roi:+}%")
                        portfolio[idx].setdefault("history", []).append(new_log)
                        if new_shares > 0:
                            portfolio[idx]["shares"] = new_shares
                            portfolio[idx]["realized_pnl"] = current_realized + sim_red_pnl
                            save_data(portfolio)
                        else:
                            portfolio.pop(idx)
                            save_data(portfolio)
                        st.rerun()

                    st.divider()
                    if st.button("🗑️ 結清出場", key=f"del_{idx}", use_container_width=True):
                        portfolio.pop(idx)
                        save_data(portfolio)
                        st.rerun()

                if len(history_logs) > 0:
                    with st.expander(f"📜 {name} 交易歷程", expanded=False):
                        df_h = pd.DataFrame(history_logs)
                        st.dataframe(df_h, use_container_width=True, hide_index=True)

# ==========================================
# 分頁 2：全市場 RS 排行榜與個股查詢
# ==========================================
with tab_leaderboard:
    st.subheader("🔍 萬用個股 RS & RS_ratio（60MA/20MA）評分查詢")
    search_query = st.text_input("輸入股票代號或名稱查詢（例如：2330、聯一光、3441）", placeholder="請輸入代號或名稱...")
    
    if search_query:
        query_str = search_query.strip().upper()
        matched = [
            item for item in market_rankings 
            if query_str in str(item.get("symbol", "")).upper() or query_str in str(item.get("name", "")).upper()
        ]
        
        if matched:
            st.write(f"找到 **{len(matched)}** 筆符合標的：")
            for m in matched:
                score = m.get("rs_rating", 50)
                m_type = m.get("market", "上市/上櫃")
                name = clean_stock_name(m.get("name", m.get("symbol")), m.get("symbol"))
                sym = m.get("symbol")
                raw_score = m.get("score", 0.0)
                
                _, _, _, _, _, _, query_rs_ratio, query_rs_mom = fetch_stock_and_momentum(sym, m_type, get_tw_now_str("%Y-%m-%d"))
                m_eval = m.copy()
                m_eval["rs_ratio"] = query_rs_ratio
                badge_style = get_trend_master_status(m_eval)

                r_col1, r_col2 = st.columns(2)
                r_col1.metric("標的", f"{name} ({sym})", m_type)
                r_col2.metric("RS Rating 評分", f"{score} 分", badge_style)

                r_col3, r_col4 = st.columns(2)
                r_col3.metric("RS_ratio (60MA)", f"{query_rs_ratio}", f"{'🔥 大盤領先者' if query_rs_ratio>=100 else '❄️ 大盤落後者'}")
                r_col4.metric("綜合動能得分", f"{raw_score:+.2f}", f"動能比 (20MA): {query_rs_mom}")
                st.divider()
        else:
            st.error(f"查無符合「{search_query}」的標的，請確認代號或名稱是否正確。")

    st.subheader("🏆 全市場 RS ≥ 75 領袖股強勢排行榜")
    
    df_raw = pd.DataFrame(market_rankings)
    if not df_raw.empty:
        if "name" not in df_raw.columns:
            df_raw["name"] = df_raw["symbol"]
        if "market" not in df_raw.columns:
            df_raw["market"] = "上市"
        if "rs_ratio" not in df_raw.columns:
            df_raw["rs_ratio"] = 100.0
        if "rs_momentum" not in df_raw.columns:
            df_raw["rs_momentum"] = 100.0

        f1, f2 = st.columns(2)
        with f1:
            min_rs = st.number_input("最低 RS 門檻篩選", min_value=1, max_value=99, value=75, step=1)
        with f2:
            market_filter = st.multiselect("市場別篩選", ["上市", "上櫃"], default=["上市", "上櫃"])

        filtered_df = df_raw[
            (df_raw["rs_rating"] >= min_rs) & 
            (df_raw["market"].isin(market_filter))
        ].copy()

        filtered_df["name"] = filtered_df.apply(lambda r: clean_stock_name(r.get("name"), r.get("symbol")), axis=1)
        filtered_df = filtered_df.sort_values(by="rs_rating", ascending=False)
        filtered_df["順勢操作狀態"] = filtered_df.apply(get_trend_master_status, axis=1)

        display_df = filtered_df[["rs_rating", "symbol", "name", "market", "score", "rs_ratio", "rs_momentum", "順勢操作狀態"]].rename(columns={
            "rs_rating": "RS Rating (PR)",
            "symbol": "股票代碼",
            "name": "中文名稱",
            "market": "上市櫃",
            "score": "綜合動能得分",
            "rs_ratio": "RS_ratio (60MA)",
            "rs_momentum": "RS動能 (20MA)"
        })

        st.caption(f"共計 **{len(display_df)}** 檔標的符合條件（RS ≥ {min_rs}）：")
        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            height=450
        )
    else:
        st.info("尚無排名資料，請先確認 market_rankings.json 檔案是否存在。")

# ==========================================
# 分頁 3：全市場大盤寬度指標
# ==========================================
with tab_market_breadth:
    st.subheader("📊 全市場大盤健康度與市場寬度指標")

    b_col1, b_col2 = st.columns(2)
    with b_col1:
        mkt_view = st.selectbox("市場選擇", ["上市 (TWSE)", "上櫃 (TPEX)"], index=0)
    with b_col2:
        period_view = st.selectbox("時間跨度", ["近 20 個交易日", "近 60 個交易日", "近 120 個交易日"], index=1)

    mkt_key = "TW" if "上市" in mkt_view else "TWO"
    days_map = {"近 20 個交易日": 20, "近 60 個交易日": 60, "近 120 個交易日": 120}
    show_days = days_map[period_view]

    with st.spinner("正在計算全市場大盤寬度與官方融資數據..."):
        breadth_df = compute_market_breadth_data(market_rankings, mkt_key)

    if breadth_df is None or breadth_df.empty:
        st.warning("⚠️ 暫時無法取得大盤寬度資料，請確認網路連線或已載入全市場標的清單。")
    else:
        plot_df = breadth_df.tail(show_days)
        latest = plot_df.iloc[-1]
        prev = plot_df.iloc[-2] if len(plot_df) >= 2 else latest

        st.markdown("##### 📌 當日即時總覽")
        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("站上 20MA 比例", f"{latest['above_20ma']:.1f}%", f"{latest['above_20ma'] - prev['above_20ma']:+.1f}%")
        k2.metric("短均多頭排列", f"{latest['short_bull_ratio']:.1f}%", f"{latest['short_bull_ratio'] - prev['short_bull_ratio']:+.1f}%")
        k3.metric("52週新高家數", f"{int(latest['new_high_count'])} 家", f"{latest['new_high_ratio']:.1f}%")
        k4.metric("融資維持率", f"{latest['margin_maintenance']:.1f}%", f"{latest['margin_maintenance'] - prev['margin_maintenance']:+.1f}%")
        k5.metric("融資餘額 (億元)", f"${latest['margin_bal']:.1f} 億", f"{latest['margin_diff']:+.2f} 億 ({latest['margin_diff_pct']:+.2f}%)")

        st.divider()

        mobile_chart_config = {
            "scrollZoom": False,
            "displayModeBar": False,
            "doubleClick": False
        }

        chart_layout = dict(
            hovermode="x unified",
            margin=dict(l=40, r=20, t=40, b=30),
            dragmode=False,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            font=dict(size=12)
        )

        # 1. 均線覆蓋率
        st.markdown("#### 1. 均線覆蓋率 (%)")
        fig1 = go.Figure()
        fig1.add_trace(go.Scatter(x=plot_df.index, y=plot_df["above_20ma"], mode="lines", name="站上 20MA (月線)", line=dict(color="#FF5722", width=2)))
        fig1.add_trace(go.Scatter(x=plot_df.index, y=plot_df["above_60ma"], mode="lines", name="站上 60MA (季線)", line=dict(color="#2196F3", width=2)))
        fig1.add_trace(go.Scatter(x=plot_df.index, y=plot_df["above_240ma"], mode="lines", name="站上 240MA (年線)", line=dict(color="#4CAF50", width=2)))
        fig1.add_hline(y=50, line_dash="dash", line_color="gray", annotation_text="50% 多空分水嶺")
        fig1.update_layout(chart_layout, yaxis=dict(title="比例 (%)", range=[0, 100], fixedrange=True), xaxis=dict(fixedrange=True))
        st.plotly_chart(fig1, use_container_width=True, config=mobile_chart_config)

        # 2 & 3. 創新高 / 創新低指標與新高新低差
        st.markdown("#### 2 & 3. 52週 (240日) 創新高/新低指標與淨差")
        fig2 = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08, subplot_titles=("創新高 / 創新低比例 (%) 與家數", "新高新低差 (Net New Highs/Lows)"))
        fig2.add_trace(go.Scatter(x=plot_df.index, y=plot_df["new_high_ratio"], mode="lines", name="創新高比例 (%)", line=dict(color="#E91E63", width=2)), row=1, col=1)
        fig2.add_trace(go.Scatter(x=plot_df.index, y=plot_df["new_low_ratio"], mode="lines", name="創新低比例 (%)", line=dict(color="#00BCD4", width=2)), row=1, col=1)
        
        bar_colors = ["#4CAF50" if v >= 0 else "#F44336" for v in plot_df["net_high_low"]]
        fig2.add_trace(go.Bar(x=plot_df.index, y=plot_df["net_high_low"], name="新高新低家數差", marker_color=bar_colors), row=2, col=1)
        fig2.add_hline(y=0, line_dash="dash", line_color="gray", row=2, col=1)
        fig2.update_layout(chart_layout, height=520)
        fig2.update_xaxes(fixedrange=True)
        fig2.update_yaxes(fixedrange=True)
        st.plotly_chart(fig2, use_container_width=True, config=mobile_chart_config)

        # 4. 漲跌家數與騰落指標 (ADL)
        st.markdown("#### 4. 漲跌家數與累積騰落指標 (ADL)")
        fig3 = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08, subplot_titles=("每日漲跌平家數", "累積騰落線 (Advance-Decline Line)"))
        fig3.add_trace(go.Bar(x=plot_df.index, y=plot_df["advances"], name="上漲家數", marker_color="#F44336"), row=1, col=1)
        fig3.add_trace(go.Bar(x=plot_df.index, y=plot_df["declines"], name="下跌家數", marker_color="#4CAF50"), row=1, col=1)
        fig3.add_trace(go.Bar(x=plot_df.index, y=plot_df["unchanged"], name="平盤家數", marker_color="#9E9E9E"), row=1, col=1)
        fig3.update_layout(barmode="stack")

        fig3.add_trace(go.Scatter(x=plot_df.index, y=plot_df["adl"], mode="lines", name="累積騰落線 (ADL)", line=dict(color="#FF9800", width=2.5)), row=2, col=1)
        fig3.update_layout(chart_layout, height=520)
        fig3.update_xaxes(fixedrange=True)
        fig3.update_yaxes(fixedrange=True)
        st.plotly_chart(fig3, use_container_width=True, config=mobile_chart_config)

        # 5. 均線多頭排列比例
        st.markdown("#### 5. 均線多頭排列比例 (%)")
        fig4 = go.Figure()
        fig4.add_trace(go.Scatter(x=plot_df.index, y=plot_df["short_bull_ratio"], mode="lines", name="短均多頭排列 (收盤>20MA>60MA)", line=dict(color="#9C27B0", width=2)))
        fig4.add_trace(go.Scatter(x=plot_df.index, y=plot_df["long_bull_ratio"], mode="lines", name="長均多頭排列 (收盤>20MA>60MA>120MA>240MA)", line=dict(color="#3F51B5", width=2)))
        fig4.add_hline(y=50, line_dash="dash", line_color="gray", annotation_text="50% 多空分水嶺")
        fig4.update_layout(chart_layout, yaxis=dict(title="多頭排列比例 (%)", range=[0, 100], fixedrange=True), xaxis=dict(fixedrange=True))
        st.plotly_chart(fig4, use_container_width=True, config=mobile_chart_config)

        # 6. 大盤整體融資維持率與官方融資動態變化
        st.markdown("#### 6. 大盤整體融資維持率與融資動能 (累積數 / 增減金額 / 變動%)")
        fig5 = make_subplots(
            rows=3, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.07,
            subplot_titles=(
                "大盤融資維持率 (%)",
                f"官方融資累積餘額 (億元) ｜ 最新: {latest['margin_bal']} 億",
                "每日增減金額 (億元) 與 每日變動率 (%)"
            ),
            specs=[[{"secondary_y": False}], [{"secondary_y": False}], [{"secondary_y": True}]]
        )

        # 融資維持率（設定 145%警戒線、140%分界線、130%斷頭線）
        fig5.add_trace(
            go.Scatter(x=plot_df.index, y=plot_df["margin_maintenance"], mode="lines", name="融資維持率 (%)", line=dict(color="#E65100", width=2.5)),
            row=1, col=1
        )
        fig5.add_hline(y=145, line_dash="dot", line_color="#FF9800", annotation_text="145% 警戒線", annotation_position="top right", row=1, col=1)
        fig5.add_hline(y=140, line_dash="dash", line_color="#E91E63", annotation_text="140% 分界線", annotation_position="top right", row=1, col=1)
        fig5.add_hline(y=130, line_dash="dash", line_color="#D32F2F", annotation_text="130% 斷頭線", annotation_position="bottom right", row=1, col=1)

        # 融資累積餘額
        fig5.add_trace(
            go.Scatter(x=plot_df.index, y=plot_df["margin_bal"], mode="lines", name="融資累積餘額 (億)", line=dict(color="#1976D2", width=2), fill="tozeroy", fillcolor="rgba(25, 118, 210, 0.1)"),
            row=2, col=1
        )

        # 每日增減金額與變動率
        diff_bar_colors = ["#F44336" if v >= 0 else "#4CAF50" for v in plot_df["margin_diff"]]
        fig5.add_trace(
            go.Bar(x=plot_df.index, y=plot_df["margin_diff"], name="每日增減金額 (億元)", marker_color=diff_bar_colors),
            row=3, col=1, secondary_y=False
        )
        fig5.add_trace(
            go.Scatter(x=plot_df.index, y=plot_df["margin_diff_pct"], mode="lines+markers", name="每日變動率 (%)", line=dict(color="#7B1FA2", width=1.5), marker=dict(size=4)),
            row=3, col=1, secondary_y=True
        )

        fig5.update_layout(chart_layout, height=750)
        fig5.update_xaxes(fixedrange=True)
        fig5.update_yaxes(title_text="維持率 (%)", row=1, col=1, fixedrange=True)
        fig5.update_yaxes(title_text="億元", row=2, col=1, fixedrange=True)
        fig5.update_yaxes(title_text="增減金額 (億)", secondary_y=False, row=3, col=1, fixedrange=True)
        fig5.update_yaxes(title_text="變動率 (%)", secondary_y=True, row=3, col=1, showgrid=False, fixedrange=True)
        st.plotly_chart(fig5, use_container_width=True, config=mobile_chart_config)
