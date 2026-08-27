import streamlit as st, yfinance as yf, pandas as pd, numpy as np, json, os, re, requests
from datetime import datetime, timezone, timedelta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from streamlit_gsheets import GSheetsConnection

st.set_page_config(layout="wide", initial_sidebar_state="collapsed", page_title="台股動能 RS 與大盤寬度監控")

DATA_FILE, TW_TZ = "portfolio.json", timezone(timedelta(hours=8))
get_tw_now = lambda: datetime.now(TW_TZ)
get_tw_now_str = lambda fmt="%Y-%m-%d %H:%M:%S": get_tw_now().strftime(fmt)

if "last_portfolio_refresh" not in st.session_state:
    st.session_state.last_portfolio_refresh = get_tw_now_str()
if "search_kw" not in st.session_state:
    st.session_state.search_kw = ""

def _load_names():
    try:
        if os.path.exists("stock_names.json"):
            with open("stock_names.json", "r", encoding="utf-8") as f: return json.load(f)
    except Exception: pass
    return {}

OFFICIAL_STOCK_NAMES = _load_names()
clean_sym = lambda val: str(val or "").strip()[:-2] if str(val or "").strip().endswith(".0") else str(val or "").strip()

def clean_stock_name(name, symbol=None):
    sym = clean_sym(symbol).upper()
    if sym in OFFICIAL_STOCK_NAMES: return OFFICIAL_STOCK_NAMES[sym]
    if not name: return sym
    raw = str(name).strip()
    for _, std_n in OFFICIAL_STOCK_NAMES.items():
        if (raw == std_n or raw.startswith(std_n)) and len(raw) <= len(std_n) + 12: return std_n
    for suf in ["股份有限公司台灣分公司", "股份有限公司", "有限股份公司", "有限公司", "(股)公司", "（股）公司"]:
        raw = raw.replace(suf, "")
    return raw.strip() or sym

def _clean_date_series(df):
    if df is None or df.empty: return pd.DataFrame()
    d = df.reset_index() if "Date" not in df.columns else df.copy()
    for col in ["Date", "Datetime", "index", "date"]:
        if col in d.columns:
            try: d["Date"] = pd.to_datetime(pd.to_datetime(d[col], utc=True).dt.tz_convert("Asia/Taipei").dt.strftime("%Y-%m-%d"))
            except Exception: d["Date"] = pd.to_datetime(pd.to_datetime(d[col]).dt.strftime("%Y-%m-%d"))
            if col != "Date": d = d.drop(columns=[col])
            break
    return d

@st.cache_data(ttl=1800)
def get_benchmark_returns():
    bm_data = {}
    for mkt_key, sym in [("TW", "^TWII"), ("TWO", "^TWOII")]:
        try:
            df = yf.Ticker(sym).history(period="1y")
            if df.empty or len(df) < 20: df = yf.Ticker("0050.TW" if mkt_key == "TW" else "^TWII").history(period="1y")
        except Exception:
            try: df = yf.Ticker("0050.TW").history(period="1y")
            except Exception: df = pd.DataFrame()
        if not df.empty:
            df_c = _clean_date_series(df)
            c = df_c["Close"].values
            calc_r = lambda d: round(((c[-1] - c[-d-1]) / c[-d-1]) * 100, 2) if len(c) > d else 0.0
            bm_data[mkt_key] = {"df": df_c[["Date", "Close"]].rename(columns={"Close": "benchmark_close"}), "r_5d": calc_r(5), "r_20d": calc_r(20), "r_60d": calc_r(60)}
    bm_data.setdefault("TW", {"df": pd.DataFrame(), "r_5d": 0.0, "r_20d": 0.0, "r_60d": 0.0})
    bm_data.setdefault("TWO", bm_data["TW"])
    return bm_data

def calculate_rs_ratio_series(target_df, benchmark_df, rs_w=60, mom_w=20):
    try:
        if target_df is None or target_df.empty or benchmark_df is None or benchmark_df.empty: return pd.DataFrame()
        t_df, b_df = _clean_date_series(target_df), _clean_date_series(benchmark_df)
        if "Close" not in t_df.columns: return pd.DataFrame()
        b_df = b_df.rename(columns={"Close": "benchmark_close"}) if "benchmark_close" not in b_df.columns and "Close" in b_df.columns else b_df
        if "benchmark_close" not in b_df.columns: return pd.DataFrame()

        merged = pd.merge(t_df[["Date", "Close"]].rename(columns={"Close": "target_close"}), b_df[["Date", "benchmark_close"]], on="Date", how="inner").sort_values("Date").reset_index(drop=True)
        if len(merged) < 10: merged = merged.ffill().bfill()
        merged = merged[(merged["benchmark_close"] > 0) & (merged["target_close"] > 0)].copy()
        if merged.empty: return pd.DataFrame()

        merged["rs_raw"] = (merged["target_close"] / merged["benchmark_close"]) * 100.0
        merged["rs_ma60"] = merged["rs_raw"].rolling(rs_w, min_periods=min(len(merged), max(5, rs_w // 4))).mean().bfill()
        merged["rs_ratio"] = np.where(merged["rs_ma60"] > 0, 100.0 * (merged["rs_raw"] / merged["rs_ma60"]), 100.0)
        rs_ratio_ma20 = merged["rs_ratio"].rolling(mom_w, min_periods=min(len(merged), max(3, mom_w // 4))).mean().bfill()
        merged["rs_momentum"] = np.where(rs_ratio_ma20 > 0, 100.0 * (merged["rs_ratio"] / rs_ratio_ma20), 100.0)
        return merged
    except Exception: return pd.DataFrame()

def get_trend_master_status(row):
    rs, badge, r_5d = float(row.get("rs_rating", 50) or 50), str(row.get("pattern_badge", "")), float(row.get("r_5d", 0.0) or 0.0)
    rs_ratio = float(row.get("rs_ratio", 100.0) or 100.0)
    p = "🔥[強勢] " if rs_ratio >= 100.0 else "❄️[弱勢] "
    if rs >= 95: sub = "👑 頂級領袖・突破新高 (主力首選)" if "新高" in badge or r_5d >= 10.0 else ("🎯 頂級VCP・即將噴出 (極限強勢)" if "VCP" in badge else "🚀 極致飆股・主升奔馳 (最強5%)")
    elif rs >= 90: sub = "🎯 VCP蓄勢・突破在即 (黃金買點)" if "VCP" in badge else ("⭐ 領袖新高・順風追擊 (多頭先鋒)" if "新高" in badge else "🚀 狂暴主升・沿線抱牢 (第一梯隊)")
    elif rs >= 80: sub = "🎯 VCP收縮・縮量待發 (觀察進場)" if "VCP" in badge else ("⭐ 區間突破・趨勢確立 (順勢加碼)" if "新高" in badge else ("⚠️ 短線強彈・觀察季線 (謹慎試單)" if "反彈" in badge else "⚡ 強大多頭・順勢推升 (右側安全)"))
    elif rs >= 75: sub = "⚠️ 左側反彈・上方有壓 (短打勿追)" if "反彈" in badge else ("🎯 底部收斂・轉強蓄勢 (第二梯隊)" if "VCP" in badge else "🔥 突破初升・動能成型 (第三梯隊)")
    elif rs >= 50: sub = "📦 區間整理・等待表態 (動能平平)"
    else: sub = "⛔ 弱勢落後・左側不碰 (避開死水)"
    return f"{p}{sub}"

def _get_gsheet_conn():
    try: return st.connection("gsheets", type=GSheetsConnection)
    except Exception: return None

def load_data():
    conn = _get_gsheet_conn()
    if conn:
        try:
            df = conn.read(ttl="0")
            if df is not None and not df.empty:
                records = []
                for _, r in df.iterrows():
                    d = r.dropna().to_dict()
                    sym = clean_sym(d.get("symbol", ""))
                    if not sym: continue
                    hist = d.get("history", "[]")
                    records.append({
                        "symbol": sym, "name": clean_stock_name(d.get("name"), sym),
                        "market": str(d.get("market", "TW")).strip().upper(),
                        "entry_date": str(d.get("entry_date", get_tw_now_str("%Y-%m-%d"))).strip(),
                        "avg_cost": float(d.get("avg_cost", 0.0) or 0.0),
                        "shares": int(float(d.get("shares", 0) or 0)),
                        "record_high": float(d.get("record_high", d.get("avg_cost", 0.0)) or 0.0),
                        "realized_pnl": float(d.get("realized_pnl", 0) or 0.0),
                        "status_override": str(d.get("status_override", "")),
                        "history": json.loads(hist) if isinstance(hist, str) else (hist if isinstance(hist, list) else [])
                    })
                return records
        except Exception: pass

    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                for d in data:
                    d["symbol"] = clean_sym(d.get("symbol", ""))
                    d["name"] = clean_stock_name(d.get("name"), d.get("symbol"))
                return data
        except Exception: return []
    return []

def save_data(data):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception: pass
    conn = _get_gsheet_conn()
    if conn:
        try:
            cols = ["symbol", "name", "market", "entry_date", "avg_cost", "shares", "record_high", "realized_pnl", "status_override", "history"]
            if not data:
                conn.update(data=pd.DataFrame(columns=cols))
                return
            rows = [{
                "symbol": clean_sym(it.get("symbol", "")), "name": it.get("name", ""),
                "market": it.get("market", "TW"), "entry_date": str(it.get("entry_date", "")),
                "avg_cost": float(it.get("avg_cost", 0.0)), "shares": int(it.get("shares", 0)),
                "record_high": float(it.get("record_high", 0.0)), "realized_pnl": float(it.get("realized_pnl", 0)),
                "status_override": str(it.get("status_override", "")),
                "history": json.dumps(it.get("history", []), ensure_ascii=False)
            } for it in data]
            conn.update(data=pd.DataFrame(rows))
        except Exception as e: st.error(f"Google Sheets 寫入失敗: {e}")

def make_log_entry(action, price, share_delta, remaining_shares, pnl_text, note):
    return {"時間": get_tw_now_str("%Y-%m-%d %H:%M"), "動作": action, "成交價": price, "異動股數": share_delta, "剩餘股數": remaining_shares, "單筆實現損益": pnl_text, "備註": note}

@st.cache_data(ttl=60)
def load_market_data():
    raw_list, status_msg = [], "無可用資料"
    if os.path.exists("market_rankings.json"):
        try:
            mtime = datetime.fromtimestamp(os.path.getmtime("market_rankings.json"), tz=TW_TZ).strftime("%Y-%m-%d %H:%M:%S")
            with open("market_rankings.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and data: raw_list, status_msg = data, f"本機檔案載入成功 (產出時間: {mtime})"
        except Exception: pass
    if not raw_list:
        try:
            res = requests.get("https://raw.githubusercontent.com/blue1998-glitch/-/main/market_rankings.json", timeout=8)
            if res.status_code == 200:
                data = res.json()
                if isinstance(data, list) and data: raw_list, status_msg = data, f"線上同步成功 (同步時間: {get_tw_now_str()})"
        except Exception as e: return [], f"連線異常: {str(e)}"

    bm_dict = get_benchmark_returns()
    for item in raw_list:
        item["symbol"], item["name"] = clean_sym(item.get("symbol", "")), clean_stock_name(item.get("name"), item.get("symbol"))
        mkt_key = "TWO" if "上櫃" in str(item.get("market", "")) or "TWO" in str(item.get("market", "")).upper() else "TW"
        bm_info = bm_dict.get(mkt_key, bm_dict["TW"])
        bm_r60, bm_r20, s_r60, s_r20 = bm_info.get("r_60d", 0.0), bm_info.get("r_20d", 0.0), float(item.get("r_60d", 0.0) or 0.0), float(item.get("r_20d", 0.0) or 0.0)
        if "rs_ratio" not in item or item["rs_ratio"] in (100.0, None): item["rs_ratio"] = round(100.0 * (1.0 + s_r60 / 100.0) / max(0.01, (1.0 + bm_r60 / 100.0)), 2)
        if "rs_momentum" not in item or item["rs_momentum"] in (100.0, None): item["rs_momentum"] = round(100.0 * (1.0 + s_r20 / 100.0) / max(0.01, (1.0 + bm_r20 / 100.0)), 2)
    return raw_list, status_msg

def fetch_stock_and_momentum(symbol, market, entry_date_str=None):
    sym_clean = clean_sym(symbol)
    is_otc = "TWO" in str(market).upper() or "上櫃" in str(market)
    ticker, alt_ticker, bm_key = f"{sym_clean}.TWO" if is_otc else f"{sym_clean}.TW", f"{sym_clean}.TW" if is_otc else f"{sym_clean}.TWO", "TWO" if is_otc else "TW"
    try:
        df_all = yf.Ticker(ticker).history(period="1y")
        if df_all.empty:
            df_all = yf.Ticker(alt_ticker).history(period="1y")
            if df_all.empty: return None, None, None, 0.0, 0.0, 0.0, 100.0, 100.0
        cur = round(float(df_all["Close"].iloc[-1]), 2)
        try:
            df_e = df_all.loc[df_all.index.astype(str) >= str(entry_date_str)] if entry_date_str else pd.DataFrame()
            max_h = round(float(df_e["High"].max()), 2) if not df_e.empty else cur
        except Exception: max_h = cur
        ma20 = round(float(df_all["Close"].tail(20).mean()), 2) if len(df_all) >= 20 else cur
        c = df_all["Close"]
        r5 = round(((c.iloc[-1] - c.iloc[-6]) / c.iloc[-6]) * 100, 2) if len(c) >= 6 else 0.0
        r1m = round(((c.iloc[-1] - c.iloc[-21]) / c.iloc[-21]) * 100, 2) if len(c) >= 21 else r5
        r1q = round(((c.iloc[-1] - c.iloc[-61]) / c.iloc[-61]) * 100, 2) if len(c) >= 61 else r1m
        bm_info = get_benchmark_returns().get(bm_key, {})
        rs_calc = calculate_rs_ratio_series(df_all, bm_info.get("df", pd.DataFrame()), 60, 20)
        if not rs_calc.empty and "rs_ratio" in rs_calc.columns:
            vr, vm = rs_calc["rs_ratio"].dropna(), rs_calc["rs_momentum"].dropna()
            rs_r = round(float(vr.iloc[-1]), 2) if not vr.empty else 100.0
            rs_m = round(float(vm.iloc[-1]), 2) if not vm.empty else 100.0
        else:
            rs_r = round(100.0 * (1.0 + r1q / 100.0) / max(0.01, (1.0 + bm_info.get("r_60d", 0.0) / 100.0)), 2)
            rs_m = round(100.0 * (1.0 + r1m / 100.0) / max(0.01, (1.0 + bm_info.get("r_20d", 0.0) / 100.0)), 2)
        return cur, max_h, ma20, r5, r1m, r1q, rs_r, rs_m
    except Exception: return None, None, None, 0.0, 0.0, 0.0, 100.0, 100.0

def calc_pnl(shares, avg_cost, current_price, discount):
    fee = 0.001425 * discount
    t_cost, t_sell = (shares * avg_cost) * (1 + fee), (shares * current_price) * (1 - fee - 0.003)
    pnl = round(t_sell - t_cost)
    return pnl, round((pnl / t_cost) * 100, 2) if t_cost > 0 else 0.0, round(avg_cost * (1 + fee * 2 + 0.003), 2)

@st.cache_data(ttl=3600)
def compute_market_breadth_data(market_list, mkt_filter="TW"):
    filtered = [f"{clean_sym(it.get('symbol','')).upper()}.{'TWO' if '上櫃' in str(it.get('market','')) or 'TWO' in str(it.get('market','')).upper() else 'TW'}" for it in market_list if mkt_filter in ("ALL", "TWO" if "上櫃" in str(it.get("market","")) or "TWO" in str(it.get("market","")).upper() else "TW") and clean_sym(it.get("symbol",""))]
    if not filtered: return None
    try:
        bm_hist = yf.Ticker("^TWII" if mkt_filter == "TW" else "^TWOII").history(period="1y")
        if bm_hist.empty: bm_hist = yf.Ticker("0050.TW").history(period="1y")
        bm_clean = _clean_date_series(bm_hist).set_index("Date")
        data = yf.download(filtered, period="1y", interval="1d", group_by="column", auto_adjust=True, progress=False)
    except Exception: return None
    if data.empty: return None

    closes, highs, lows = (data[k].to_frame() if isinstance(data[k], pd.Series) else data[k] for k in ["Close", "High", "Low"])
    closes, highs, lows = closes.dropna(how="all").ffill(), highs.dropna(how="all").ffill(), lows.dropna(how="all").ffill()
    if len(closes) < 30: return None

    ma20, ma60, ma120, ma240 = [closes.rolling(w, min_periods=min(5, w//4)).mean() for w in [20, 60, 120, 240]]
    total_valid = closes.notna().sum(axis=1).replace(0, np.nan)
    calc_ratio = lambda c: (c.sum(axis=1) / total_valid * 100).round(2)
    above_20, above_60, above_240 = calc_ratio(closes > ma20), calc_ratio(closes > ma60), calc_ratio(closes > ma240)
    nh_c, nl_c = (highs >= (highs.rolling(240, min_periods=30).max() - 1e-4)).sum(axis=1), (lows <= (lows.rolling(240, min_periods=30).min() + 1e-4)).sum(axis=1)
    diff = closes.diff()

    base_dates = closes.index.strftime("%Y-%m-%d").tolist()
    bm_closes = bm_clean["Close"].reindex(pd.to_datetime(base_dates)).ffill().bfill().values if not bm_clean.empty and "Close" in bm_clean.columns else np.linspace(20000, 23000, len(base_dates))
    adv, dec = (diff > 0).sum(axis=1).values, (diff < 0).sum(axis=1).values
    
    r_adv, r_dec = pd.Series(adv).rolling(20, min_periods=5).sum(), pd.Series(dec).rolling(20, min_periods=5).sum()
    roll_ad = np.where(r_adv + r_dec > 0, (r_adv / (r_adv + r_dec)) * 100.0, 50.0).round(2)
    net_adv = pd.Series(adv - dec)
    mcclellan = (net_adv.ewm(span=19, adjust=False).mean() - net_adv.ewm(span=39, adjust=False).mean()).round(2).values

    df_adv = pd.DataFrame({"close": bm_closes, "rolling_ad_ratio": roll_ad, "mcclellan_osc": mcclellan})
    r_hc, r_lc = df_adv["close"].rolling(20, min_periods=5).max(), df_adv["close"].rolling(20, min_periods=5).min()
    r_ha, r_hm = df_adv["rolling_ad_ratio"].rolling(20, min_periods=5).max(), df_adv["mcclellan_osc"].rolling(20, min_periods=5).max()
    r_la, r_lm = df_adv["rolling_ad_ratio"].rolling(20, min_periods=5).min(), df_adv["mcclellan_osc"].rolling(20, min_periods=5).min()
    
    bm_ma60 = pd.Series(bm_closes).rolling(60, min_periods=5).mean()
    return pd.DataFrame({
        "Date": base_dates, "close": bm_closes, "above_20ma": above_20.values, "above_60ma": above_60.values, "above_240ma": above_240.values,
        "new_high_count": nh_c.values, "new_low_count": nl_c.values, "new_high_ratio": (nh_c / total_valid * 100).round(2).values,
        "new_low_ratio": (nl_c / total_valid * 100).round(2).values, "net_high_low": (nh_c - nl_c).values,
        "rolling_ad_ratio": roll_ad, "mcclellan_osc": mcclellan,
        "bearish_divergence": (df_adv["close"] >= r_hc - 1e-4) & ((df_adv["rolling_ad_ratio"] < r_ha - 1.5) | (df_adv["mcclellan_osc"] < r_hm - 5.0)),
        "bullish_divergence": (df_adv["close"] <= r_lc + 1e-4) & ((df_adv["rolling_ad_ratio"] > r_la + 1.5) | (df_adv["mcclellan_osc"] > r_lm + 5.0)),
        "dist_60ma_pct": (((pd.Series(bm_closes) - bm_ma60) / bm_ma60) * 100.0).round(2).values,
        "short_bull_ratio": calc_ratio((closes > ma20) & (ma20 > ma60)).values,
        "long_bull_ratio": calc_ratio((closes > ma20) & (ma20 > ma60) & (ma60 > ma120) & (ma120 > ma240)).values
    }).set_index("Date")

def render_metric_grid(pairs):
    for (l1, v1, d1), (l2, v2, d2) in pairs:
        c1, c2 = st.columns(2)
        c1.metric(l1, v1, d1)
        c2.metric(l2, v2, d2)

# ==========================================
# 介面渲染
# ==========================================
market_rankings, db_status = load_market_data()
st.title("🚀 台股儀表板")

with st.expander("🛡️ 說明", expanded=False):
    st.markdown("**RS_ratio 雙軸指標**：以 60 日季線為強弱中軸（≥100 為 🔥[強勢]，<100 為 ❄️[弱勢]）；以 20 日 SMA 為短線動能加速度。")
    r1, r2 = st.columns(2)
    r1.markdown("**1. 🔴 初始停損**：跌破預設趴數無條件停損。\n\n**2. 🛡️ 保本停損**：獲利達標鎖定零虧損。\n\n**3. 🟣 高點回檔**：自高點拉回觸發分批停利。")
    r2.markdown("**4. 🟠 月線過熱**：20MA 正乖離過大建議調節。\n\n**5. ⏳ 時間停損**：持股過久動能停滯建議換股。")

if market_rankings: st.info(f"🟢 **全市場 RS 資料庫已就緒** ｜ 收錄 **{len(market_rankings)}** 檔台股 ｜ 狀態：{db_status}")
else: st.warning("🟡 正在等待全市場 RS 排名資料載入...")

tab_portfolio, tab_leaderboard, tab_market_breadth = st.tabs(["📈 獲利監控系統", "🏆 個股查詢", "📊 大盤"])

with tab_portfolio:
    with st.expander("⚙️ 參數設定", expanded=False):
        c1, c2 = st.columns(2)
        stop_loss_pct = c1.number_input("🔴 初始停損趴數 (%)", 1.0, 50.0, 7.0, 0.5, format="%.1f")
        breakeven_trigger_pct = c1.number_input("🛡️ 保本停損啟動門檻 (%)", 1.0, 50.0, 8.0, 0.5, format="%.1f")
        pullback_target_pct = c1.number_input("🟣 高點回檔停利趴數 (%)", 1.0, 50.0, 10.0, 0.5, format="%.1f")
        bias_threshold = c2.number_input("🟠 月線正乖離過熱閥值 (%)", 5.0, 100.0, 30.0, 1.0, format="%.0f")
        time_stop_days = c2.number_input("⏳ 時間停損天數（天）", 1, 100, 10, 1)
        discount_display = c2.number_input("💰 券商手續費折數", 0.01, 1.0, 0.60, 0.05, format="%.2f")

    portfolio = load_data()

    with st.expander("➕ 新增持股", expanded=False):
        with st.form("add_stock_form"):
            fc1, fc2 = st.columns(2)
            sym = fc1.text_input("股票代號", placeholder="例如: 3441 或 2330")
            name = fc1.text_input("股票名稱", placeholder="例如: 聯一光")
            mkt = fc1.selectbox("市場別", ["TWO (上櫃)", "TW (上市)"])
            entry_d = fc2.date_input("進場日期", value=get_tw_now().date())
            price = fc2.number_input("買進價格", min_value=0.1, step=0.1, value=100.0)
            shs = fc2.number_input("買進股數", min_value=1, step=1000, value=1000)
                
            if st.form_submit_button("確認建立持倉", use_container_width=True) and sym:
                sym_clean = clean_sym(sym)
                clean_n = clean_stock_name(name.strip(), sym_clean) if name else clean_stock_name(sym_clean, sym_clean)
                portfolio.append({
                    "symbol": sym_clean, "name": clean_n, "market": "TWO" if "TWO" in mkt else "TW",
                "entry_date": str(entry_d), "avg_cost": float(price), "shares": int(shs),
                    "record_high": float(price), "realized_pnl": 0.0, "status_override": "",
                    "history": [make_log_entry("🌱 初始建倉", price, f"+{int(shs)}", int(shs), "0 元", f"起始成本 ${price}")]
                })
                save_data(portfolio)
                st.success(f"已新增 {clean_n} ({sym_clean})")
                st.rerun()

    if not portfolio:
        st.info("目前尚無持倉，請點擊上方「➕ 新增持股」建立第一檔股票。")
    else:
        if st.button("🔄 刷新資料", use_container_width=True):
            st.cache_data.clear()
            st.session_state.last_portfolio_refresh = get_tw_now_str()
            st.rerun()
        st.caption(f"🕒 最新市價更新時間：{st.session_state.last_portfolio_refresh}")

        for idx, item in enumerate(portfolio):
            sym, name, mkt, entry_d = clean_sym(item["symbol"]), clean_stock_name(item.get("name", ""), item.get("symbol")), item["market"], item["entry_date"]
            avg_cost, shares, stored_high = item["avg_cost"], item["shares"], item.get("record_high", item["avg_cost"])
            realized_pnl, history_logs = item.get("realized_pnl", 0.0), item.get("history", [])

            info = next((it for it in market_rankings if clean_sym(it.get("symbol", "")).upper() == sym.upper()), None)
            rs_score = info.get("rs_rating", 50) if info else 50
            cur_price, max_high, ma20, r_5d, r_1m, r_1q, rs_ratio_val, rs_mom_val = fetch_stock_and_momentum(sym, mkt, entry_d)
            if cur_price is None: cur_price, max_high, ma20 = avg_cost, stored_high, avg_cost

            actual_high = max(stored_high, avg_cost, max_high or stored_high)
            if actual_high != stored_high:
                portfolio[idx]["record_high"] = actual_high
                save_data(portfolio)

            net_pnl, roi, breakeven_p = calc_pnl(shares, avg_cost, cur_price, discount_display)
            pullback_pct = round(((actual_high - cur_price) / actual_high) * 100, 1) if actual_high > 0 else 0
            bias_20 = round(((cur_price - ma20) / ma20) * 100, 1) if ma20 > 0 else 0
            try: days_held = (get_tw_now().date() - datetime.strptime(entry_d, "%Y-%m-%d").date()).days
            except Exception: days_held = 0

            status_item = (info.copy() if info else {"rs_rating": rs_score, "pattern_badge": "", "r_5d": r_5d})
            status_item["rs_ratio"] = rs_ratio_val
            status_badge = get_trend_master_status(status_item)

            is_breakeven_active = ((actual_high - avg_cost) / avg_cost) * 100 >= breakeven_trigger_pct
            init_stop = round(avg_cost * (1 - stop_loss_pct / 100), 2)
            effective_stop = max(init_stop, breakeven_p) if is_breakeven_active else init_stop
            pullback_p = round(actual_high * (1 - pullback_target_pct / 100), 2)

            status_text, status_color = "⚪ 持股續抱中", "gray"
            if item.get("status_override") == "持股續抱中":
                status_text, status_color = "⚪ 持股續抱中 (已執行減碼調節)", "green"
            elif cur_price <= effective_stop:
                status_text, status_color = f"🛡️ 觸發保本出場線（{effective_stop} 元）！強制保護本金零虧損出場" if is_breakeven_active else f"🔴 觸發 -{stop_loss_pct}% 停損線（{effective_stop} 元）！全數出場", "red"
            elif cur_price <= pullback_p and cur_price > avg_cost:
                status_text, status_color = f"🟣 觸發高點回檔 {pullback_target_pct}%（跌破 {pullback_p} 元）！建議減碼", "purple"
            elif bias_20 >= bias_threshold:
                status_text, status_color = f"🟠 月線正乖離達 {bias_20}%（過熱）！建議減碼", "orange"
            elif days_held >= time_stop_days and abs(roi) <= 2.0:
                status_text, status_color = f"⏳ 觸發時間停損（持股已 {days_held} 天，動能停滯）！建議換股", "orange"

            with st.container():
                st.divider()
                st.subheader(f"{name} ({sym}.{mkt}) ｜ 📦 {shares:,} 股 ｜ {status_badge}")
                render_metric_grid([
                    (("RS Rating 評分", f"{rs_score} 分", None), ("RS動能比率(20MA)", f"{rs_mom_val}", "🔥 短期動能增強" if rs_mom_val >= 100 else "❄️ 動能未達臨界點")),
                    (("RS_ratio 比率 (60MA)", f"{rs_ratio_val}", "🔥 超越大盤" if rs_ratio_val >= 100 else "❄️ 落後大盤"), ("近 5 日動能", f"{r_5d:+}%", None)),
                    (("近 20 日動能", f"{r_1m:+}%", None), ("近 60 日動能", f"{r_1q:+}%", None)),
                    (("高點回檔", f"${actual_high}", f"-{pullback_pct}%"), ("最新市價", f"${cur_price}", None)),
                    (("剩餘股數 / 均價", f"{shares:,} 股", f"均價: ${avg_cost}"), ("未實現損益", f"{net_pnl:+,} 元", f"{roi:+}%")),
                    (("累積已實現損益", f"{realized_pnl:+,} 元", None), ("🛡️ 保本停損線" if is_breakeven_active else f"🔴 初始停損 (-{stop_loss_pct}%)", f"${effective_stop}", None))
                ])

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
                        portfolio[idx].setdefault("history", []).append(make_log_entry("🔼 順勢加碼", add_p, f"+{int(add_s)}", new_tot, "-", f"新均價 ${sim_avg} (緩衝 {buf:+}%)"))
                        portfolio[idx]["shares"], portfolio[idx]["avg_cost"], portfolio[idx]["status_override"] = new_tot, sim_avg, ""
                        save_data(portfolio)
                        st.rerun()

                    st.divider()
                    st.write("##### 🔽 分批減碼")
                    red_p = st.number_input("減碼價格", min_value=0.1, step=0.1, value=cur_price, key=f"red_p_{idx}")
                    red_s = st.number_input("減碼股數", min_value=1, max_value=shares, step=100, value=min(1000, shares), key=f"red_s_{idx}")
                    
                    default_reason_idx = 0
                    if "高點回檔" in status_text: default_reason_idx = 1
                    elif "正乖離" in status_text or "過熱" in status_text: default_reason_idx = 2
                    elif "時間停損" in status_text: default_reason_idx = 3
                    elif "停損" in status_text or "保本" in status_text: default_reason_idx = 4
                    
                    risk_reasons = ["🎯 自行主動調節", "🟣 高點回檔停利", "🟠 月線正乖離過熱", "⏳ 時間停損換股", "🔴 保本/停損觸發", "📦 其他策略調節"]
                    selected_reason = st.selectbox("減碼風控原因", risk_reasons, index=default_reason_idx, key=f"risk_reason_{idx}")

                    sim_red_pnl, sim_red_roi, _ = calc_pnl(int(red_s), avg_cost, red_p, discount_display)
                    st.caption(f"試算本次損益：**{sim_red_pnl:+,} 元** ({sim_red_roi:+}%)")
                    if st.button("確認減碼", key=f"btn_red_{idx}", use_container_width=True):
                        new_shares = shares - int(red_s)
                        note_text = f"【{selected_reason}】報酬率 {sim_red_roi:+}%"
                        portfolio[idx].setdefault("history", []).append(make_log_entry("🔽 分批減碼", red_p, f"-{int(red_s)}", new_shares, f"{sim_red_pnl:+,} 元", note_text))
                        if new_shares > 0:
                            portfolio[idx]["shares"] = new_shares
                            portfolio[idx]["realized_pnl"] = item.get("realized_pnl", 0.0) + sim_red_pnl
                            portfolio[idx]["status_override"] = "持股續抱中"
                        else:
                            portfolio.pop(idx)
                        save_data(portfolio)
                        st.rerun()

                    st.divider()
                    if st.button("🗑️ 結清出場", key=f"del_{idx}", use_container_width=True):
                        portfolio.pop(idx)
                        save_data(portfolio)
                        st.rerun()

                if history_logs:
                    with st.expander(f"📜 {name} 交易歷程", expanded=False):
                        st.dataframe(pd.DataFrame(history_logs), use_container_width=True, hide_index=True)

with tab_leaderboard:
    st.subheader("🔍 個股查詢")
    
    def on_search_change():
        st.session_state.search_kw = st.session_state.search_box_input

    search_query = st.text_input("輸入股票代號或名稱查詢（支援單檔或多檔，多檔請用空白、逗號或換行分隔）", value=st.session_state.search_kw, placeholder="例如：2330 聯一光 3441 2454", key="search_box_input", on_change=on_search_change)
    active_search = search_query.strip() or st.session_state.search_kw.strip()
    
    if active_search:
        matched_dict = {}
        for tok in [t.strip() for t in re.split(r"[\s,;，、\n]+", active_search) if t.strip()]:
            q_token = clean_sym(tok).upper()
            found = False
            for item in market_rankings:
                s_i, n_i = clean_sym(item.get("symbol", "")).upper(), str(item.get("name", "")).upper()
                if q_token in (s_i, n_i) or q_token in s_i or q_token in n_i:
                    matched_dict[s_i] = item
                    found = True
            if not found and (q_token.isdigit() or len(q_token) >= 2):
                std_n = clean_stock_name(q_token, q_token)
                matched_dict[q_token] = {"symbol": q_token, "name": std_n if std_n != q_token else q_token, "market": "TW", "rs_rating": 50, "score": 0.0}

        matched = list(matched_dict.values())
        if matched:
            st.write(f"找到 **{len(matched)}** 筆符合標的：")
            compare_rows, detailed_data = [], []
            for m in matched:
                score, m_type = m.get("rs_rating", 50), m.get("market", "上市/上櫃")
                sym, name = clean_sym(m.get("symbol")), clean_stock_name(m.get("name", m.get("symbol")), m.get("symbol"))
                cur_p, _, _, q_r5, q_r20, q_r60, query_rs_ratio, query_rs_mom = fetch_stock_and_momentum(sym, m_type, get_tw_now_str("%Y-%m-%d"))
                m_eval = m.copy()
                m_eval["rs_ratio"] = query_rs_ratio
                badge_style = get_trend_master_status(m_eval)
                detailed_data.append({"name": name, "sym": sym, "m_type": m_type, "score": score, "query_rs_mom": query_rs_mom, "query_rs_ratio": query_rs_ratio, "q_r5": q_r5, "q_r20": q_r20, "q_r60": q_r60, "badge_style": badge_style})
                compare_rows.append({"股票代號": sym, "股票名稱": name, "市場別": m_type, "目前市價": f"${cur_p:.2f}" if cur_p is not None else "-", "RS 評分": score, "RS 動能 (20MA)": query_rs_mom, "RS_ratio (60MA)": query_rs_ratio, "5日漲跌幅 (%)": f"{q_r5:+0.2f}%", "20日漲跌幅 (%)": f"{q_r20:+0.2f}%", "60日漲跌幅 (%)": f"{q_r60:+0.2f}%", "動能狀態": badge_style})

            st.markdown("#### 📊 查詢標的數值比較表")
            st.dataframe(pd.DataFrame(compare_rows), use_container_width=True, hide_index=True)
            st.divider()
            st.markdown("#### 📌 查詢標的詳細指標")
            for d in detailed_data:
                st.columns(1)[0].metric("標的與市場", f"{d['name']} ({d['sym']})", f"{d['m_type']} ｜ {d['badge_style']}")
                render_metric_grid([
                    (("RS Rating 評分", f"{d['score']} 分", None), ("RS動能比率(20MA)", f"{d['query_rs_mom']}", "🔥 短期動能增強" if d['query_rs_mom'] >= 100 else "❄️ 短期動能減弱")),
                    (("RS_ratio (60MA)", f"{d['query_rs_ratio']}", "🔥 大盤領先者" if d['query_rs_ratio'] >= 100 else "❄️ 大盤落後者"), ("近 5 日動能", f"{d['q_r5']:+}%", None)),
                    (("近 20 日動能", f"{d['q_r20']:+}%", None), ("近 60 日動能", f"{d['q_r60']:+}%", None))
                ])
                st.divider()
        else: st.error(f"查無符合「{active_search}」的標的。")

    st.subheader("🏆 強勢股排行榜")
    df_raw = pd.DataFrame(market_rankings)
    if not df_raw.empty:
        for c, default_v in [("name", df_raw.get("symbol")), ("market", "上市"), ("rs_ratio", 100.0), ("rs_momentum", 100.0)]:
            if c not in df_raw.columns: df_raw[c] = default_v
        f1, f2 = st.columns(2)
        min_rs = f1.number_input("最低 RS 門檻篩選", 1, 99, 85, 1)
        market_filter = f2.multiselect("市場別篩選", ["上市", "上櫃"], default=["上市", "上櫃"])
        filtered_df = df_raw[(df_raw["rs_rating"] >= min_rs) & (df_raw["market"].isin(market_filter))].copy()
        filtered_df["name"] = filtered_df.apply(lambda r: clean_stock_name(r.get("name"), r.get("symbol")), axis=1)
        filtered_df = filtered_df.sort_values(by="rs_rating", ascending=False).reset_index(drop=True)
        filtered_df["順勢操作狀態"] = filtered_df.apply(get_trend_master_status, axis=1)
        display_df = filtered_df[["rs_rating", "symbol", "name", "market", "score", "rs_ratio", "rs_momentum", "順勢操作狀態"]].rename(columns={"rs_rating": "RS Rating (PR)", "symbol": "股票代號", "name": "中文名稱", "market": "上市櫃", "score": "綜合動能得分", "rs_ratio": "RS_ratio (60MA)", "rs_momentum": "RS動能比率(20MA)"})
        st.caption(f"共計 **{len(display_df)}** 檔標的符合條件（RS ≥ {min_rs}） ｜ 💡 **提示：點選表格中任意個股可直接在上方帶入查詢**")
        
        event = st.dataframe(display_df, use_container_width=True, hide_index=True, height=450, on_select="rerun", selection_mode="single-row", key="rank_df_table")
        if event and hasattr(event, "selection") and event.selection.get("rows"):
            sel_idx = event.selection["rows"][0]
            chosen_sym = str(display_df.iloc[sel_idx]["股票代號"])
            if st.session_state.search_kw != chosen_sym:
                st.session_state.search_kw = chosen_sym
                st.session_state.search_box_input = chosen_sym
                st.rerun()
    else: st.info("尚無排名資料。")

with tab_market_breadth:
    st.subheader("📊 大盤指標")
    b_col1, b_col2 = st.columns(2)
    mkt_view = b_col1.selectbox("市場選擇", ["上市 (TWSE)", "上櫃 (TPEX)"], index=0)
    show_days = {"近 20 個交易日": 20, "近 60 個交易日": 60, "近 120 個交易日": 120}[b_col2.selectbox("時間跨度", ["近 20 個交易日", "近 60 個交易日", "近 120 個交易日"], index=1)]

    with st.spinner("正在計算大盤寬度指標..."):
        breadth_df = compute_market_breadth_data(market_rankings, "TW" if "上市" in mkt_view else "TWO")

    if breadth_df is None or breadth_df.empty:
        st.warning("⚠️ 暫時無法取得大盤寬度資料。")
    else:
        plot_df = breadth_df.tail(show_days)
        latest, prev = plot_df.iloc[-1], plot_df.iloc[-2] if len(plot_df) >= 2 else plot_df.iloc[-1]
        st.markdown("##### 📌 當日即時總覽")
        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("站上 20MA 比例", f"{latest['above_20ma']:.1f}%", f"{latest['above_20ma'] - prev['above_20ma']:+.1f}%")
        k2.metric("短均多頭排列", f"{latest['short_bull_ratio']:.1f}%", f"{latest['short_bull_ratio'] - prev['short_bull_ratio']:+.1f}%")
        k3.metric("52週新高家數", f"{int(latest['new_high_count'])} 家", f"{latest['new_high_ratio']:.1f}%")
        k4.metric("滾動騰落比率 (20D)", f"{latest['rolling_ad_ratio']:.1f}%", f"{latest['rolling_ad_ratio'] - prev['rolling_ad_ratio']:+.1f}%")
        k5.metric("大盤與 60MA 距離", f"{latest['dist_60ma_pct']:+.2f}%", f"{'🔥 季線之上' if latest['dist_60ma_pct']>=0 else '❄️ 季線之下'}")

        st.divider()
        cfg, layout = {"scrollZoom": False, "displayModeBar": False}, dict(hovermode="x unified", margin=dict(l=40, r=20, t=40, b=30), dragmode=False, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))

        # 1. 均線覆蓋率
        st.markdown("#### 1. 均線覆蓋率 (%)")
        fig1 = go.Figure([go.Scatter(x=plot_df.index, y=plot_df[c], mode="lines", name=n, line=dict(color=col, width=2)) for c, n, col in [("above_20ma", "站上 20MA (月線)", "#FF5722"), ("above_60ma", "站上 60MA (季線)", "#2196F3"), ("above_240ma", "站上 240MA (年線)", "#4CAF50")]])
        fig1.add_hline(y=50, line_dash="dash", line_color="gray", annotation_text="50% 多空分水嶺")
        fig1.update_layout(layout, yaxis=dict(title="比例 (%)", range=[0, 100], fixedrange=True), xaxis=dict(fixedrange=True))
        st.plotly_chart(fig1, use_container_width=True, config=cfg)

        # 2. 創新高/創新低指標
        st.markdown("#### 2. 52週創新高/新低指標與淨差")
        fig2 = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08, subplot_titles=("創新高 / 創新低比例 (%) 與家數", "新高新低差 (Net New Highs/Lows)"))
        fig2.add_trace(go.Scatter(x=plot_df.index, y=plot_df["new_high_ratio"], mode="lines", name="創新高比例 (%)", line=dict(color="#E91E63", width=2)), row=1, col=1)
        fig2.add_trace(go.Scatter(x=plot_df.index, y=plot_df["new_low_ratio"], mode="lines", name="創新低比例 (%)", line=dict(color="#00BCD4", width=2)), row=1, col=1)
        fig2.add_trace(go.Bar(x=plot_df.index, y=plot_df["net_high_low"], name="新高新低家數差", marker_color=["#4CAF50" if v >= 0 else "#F44336" for v in plot_df["net_high_low"]]), row=2, col=1)
        fig2.add_hline(y=0, line_dash="dash", line_color="gray", row=2, col=1)
        fig2.update_layout(layout, height=520)
        fig2.update_xaxes(fixedrange=True); fig2.update_yaxes(fixedrange=True)
        st.plotly_chart(fig2, use_container_width=True, config=cfg)

        # 3. 進化版騰落指標
        st.markdown("#### 4. 進化版騰落指標")
        fig3 = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.07, subplot_titles=(f"{mkt_view} 指數收盤價 ＆ 背離訊號監測", f"20 日滾動騰落比率 ｜ 最新: {latest['rolling_ad_ratio']:.1f}%", f"麥克連震盪指標 ｜ 最新: {latest['mcclellan_osc']:+.1f}"))
        fig3.add_trace(go.Scatter(x=plot_df.index, y=plot_df["close"], mode="lines", name="大盤指數收盤", line=dict(color="#212121", width=2)), row=1, col=1)
        for cond, name_b, sym_b, c_b in [(plot_df["bearish_divergence"], "⚠️ 頂部背離", "triangle-down", "#D32F2F"), (plot_df["bullish_divergence"], "🌱 底部背離", "triangle-up", "#388E3C")]:
            pts = plot_df[cond]
            if not pts.empty: fig3.add_trace(go.Scatter(x=pts.index, y=pts["close"], mode="markers", name=name_b, marker=dict(symbol=sym_b, size=11, color=c_b)), row=1, col=1)
        fig3.add_trace(go.Scatter(x=plot_df.index, y=plot_df["rolling_ad_ratio"], mode="lines", name="滾動 AD 比率 (%)", line=dict(color="#673AB7", width=2.2)), row=2, col=1)
        for y_v, col_l, ann in [(75, "#E91E63", "75% 過熱超買"), (50, "gray", "50% 多空中軸"), (25, "#00BCD4", "25% 冰凍超賣")]:
            fig3.add_hline(y=y_v, line_dash="dash", line_color=col_l, annotation_text=ann, annotation_position="top right" if y_v>=50 else "bottom right", row=2, col=1)
        fig3.add_trace(go.Bar(x=plot_df.index, y=plot_df["mcclellan_osc"], name="McClellan 震盪動能", marker_color=["#F44336" if v >= 0 else "#4CAF50" for v in plot_df["mcclellan_osc"]]), row=3, col=1)
        fig3.add_hline(y=0, line_dash="solid", line_color="black", row=3, col=1)
        fig3.update_layout(layout, height=780)
        fig3.update_xaxes(fixedrange=True); fig3.update_yaxes(title_text="指數點位", row=1, col=1, fixedrange=True); fig3.update_yaxes(title_text="比率 (%)", range=[0, 100], row=2, col=1, fixedrange=True); fig3.update_yaxes(title_text="震盪數值", row=3, col=1, fixedrange=True)
        st.plotly_chart(fig3, use_container_width=True, config=cfg)

        # 4. 均線多頭排列
        st.markdown("#### 5. 均線多頭排列比例 (%)")
        fig4 = go.Figure([
            go.Scatter(x=plot_df.index, y=plot_df["short_bull_ratio"], mode="lines", name="短均多頭排列", line=dict(color="#9C27B0", width=2)),
            go.Scatter(x=plot_df.index, y=plot_df["long_bull_ratio"], mode="lines", name="長均多頭排列", line=dict(color="#3F51B5", width=2))
        ])
        fig4.add_hline(y=50, line_dash="dash", line_color="gray", annotation_text="50% 多空分水嶺")
        fig4.update_layout(layout, yaxis=dict(title="多頭排列比例 (%)", range=[0, 100], fixedrange=True), xaxis=dict(fixedrange=True))
        st.plotly_chart(fig4, use_container_width=True, config=cfg)

        # 5. 季線距離
        st.markdown(f"#### 6. 大盤現價與 60日 MA 距離 (%) ｜ 最新：**{latest['dist_60ma_pct']:+.2f}%**")
        fig5 = go.Figure([
            go.Bar(x=plot_df.index, y=plot_df["dist_60ma_pct"], name="季線乖離距離 (%)", marker_color=["#F44336" if v >= 0 else "#4CAF50" for v in plot_df["dist_60ma_pct"]]),
            go.Scatter(x=plot_df.index, y=plot_df["dist_60ma_pct"], mode="lines+markers", name="趨勢軌跡", line=dict(color="#1976D2", width=1.5), marker=dict(size=4))
        ])
        fig5.add_hline(y=0, line_dash="solid", line_color="black")
        fig5.add_hline(y=10, line_dash="dash", line_color="#E91E63", annotation_text="+10% 正向過熱區", annotation_position="top right")
        fig5.add_hline(y=-10, line_dash="dash", line_color="#00BCD4", annotation_text="-10% 負向超跌區", annotation_position="bottom right")
        fig5.update_layout(layout, yaxis=dict(title="距離 (%)", fixedrange=True), xaxis=dict(fixedrange=True))
        st.plotly_chart(fig5, use_container_width=True, config=cfg)
