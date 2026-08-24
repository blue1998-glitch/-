import os
import json
import time
import math
import requests
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

def load_theme_mapping():
    mapping_path = "data/theme_mapping.json"
    if os.path.exists(mapping_path):
        try:
            with open(mapping_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def fetch_all_tw_stocks():
    stocks = {}
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        twse = requests.get("https://openapi.twse.com.tw/v1/opendata/t187ap03_L", headers=headers, timeout=12).json()
        for r in twse:
            c = str(r.get("公司代號", "")).strip()
            n = str(r.get("公司名稱", "")).strip()
            ind = str(r.get("產業別", "")).strip()
            if len(c) == 4 and c.isdigit():
                stocks[c] = {"name": n, "market": "上市", "symbol_yf": f"{c}.TW", "main_industry": ind}
    except Exception as e:
        print(f"TWSE 清單抓取異常: {e}")

    try:
        tpex = requests.get("https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O", headers=headers, timeout=12).json()
        for r in tpex:
            c = str(r.get("SecuritiesCompanyCode", "")).strip()
            n = str(r.get("CompanyName", "")).strip()
            ind = str(r.get("Industry", "")).strip()
            if len(c) == 4 and c.isdigit():
                stocks[c] = {"name": n, "market": "上櫃", "symbol_yf": f"{c}.TWO", "main_industry": ind}
    except Exception as e:
        print(f"TPEx 清單抓取異常: {e}")

    return stocks

# =========================================================================
# 🎯 替換核心：taiwan-stock-rs-main 之最新順勢大師 VCP 計算公式
# =========================================================================
def calculate_master_vcp_score(df_hist):
    """
    1. 創新高強烈獎勵 (H_prox)
    2. VCP 波動極窄收斂加乘 (V_tight)
    3. 趨勢均線濾網 (T_trend)
    4. 破底死貓反彈重度懲罰
    """
    if len(df_hist) < 60:
        return None

    closes = df_hist['Close'].values
    highs = df_hist['High'].values
    lows = df_hist['Low'].values

    p_now = float(closes[-1])
    p_5d = float(closes[-6])
    p_20d = float(closes[-21])
    p_60d = float(closes[-61])

    # 1. 多週期實質動能 (5日30%、20日45%、60日25%)
    r_5d = ((p_now - p_5d) / p_5d) * 100.0
    r_20d = ((p_now - p_20d) / p_20d) * 100.0
    r_60d = ((p_now - p_60d) / p_60d) * 100.0
    base_momentum = (r_5d * 0.30) + (r_20d * 0.45) + (r_60d * 0.25)

    # 2. 距 60 日高點距離 (Proximity to 60D High)
    high_60d = float(np.max(highs[-60:]))
    if high_60d <= 0:
        return None
    off_high_pct = max(0.0, ((high_60d - p_now) / high_60d) * 100.0)

    if off_high_pct <= 0.5:
        h_prox = 1.25  # 創 60 日新高，給予 1.25 倍突破爆發獎勵
    elif off_high_pct <= 8.0:
        h_prox = 1.12 - (off_high_pct / 8.0) * 0.12  # 距高點 8% 內，微幅加成 (1.12 ~ 1.0)
    elif off_high_pct <= 18.0:
        h_prox = 1.0 - ((off_high_pct - 8.0) / 10.0) * 0.25  # 距高點 8~18%，輕微衰減 (1.0 ~ 0.75)
    else:
        # 跌幅大於 18%，上方套牢賣壓沉重，重罰
        h_prox = max(0.20, 0.75 - ((off_high_pct - 18.0) / 20.0) * 0.55)

    # 3. VCP 波動收斂度 (10日極窄震幅)
    high_10d = float(np.max(highs[-10:]))
    low_10d = float(np.min(lows[-10:]))
    range_10d = ((high_10d - low_10d) / max(0.01, low_10d)) * 100.0

    if range_10d <= 7.0 and off_high_pct <= 10.0:
        v_tight = 1.18  # 經典 VCP 收縮蓄勢（即將突破）
    elif range_10d <= 12.0 and off_high_pct <= 12.0:
        v_tight = 1.08  # 次級收縮
    elif range_10d > 22.0:
        v_tight = 0.85  # 寬幅震盪洗盤
    else:
        v_tight = 1.00

    # 4. 均線趨勢濾網與死貓反彈懲罰
    ma20 = float(np.mean(closes[-20:]))
    ma60 = float(np.mean(closes[-60:]))

    t_trend = 1.0
    if p_now < ma60:
        t_trend *= 0.35  # 季線之下，嚴格壓制
    if p_now < ma20:
        t_trend *= 0.75  # 月線之下
    if r_20d < 0 and r_5d > 0:
        t_trend *= 0.65  # 月線走跌之短線反彈（死貓反彈折扣）

    final_score = base_momentum * h_prox * v_tight * t_trend

    # 5. 型態特徵標籤
    if off_high_pct <= 1.0 and r_5d >= 2.0:
        pattern_badge = "⭐ 歷史/區間新高"
    elif off_high_pct <= 8.0 and range_10d <= 8.0:
        pattern_badge = "🎯 VCP收縮蓄勢"
    elif off_high_pct <= 12.0 and p_now >= ma20:
        pattern_badge = "🚀 右側強勢整理"
    elif r_20d < 0 and r_5d > 0:
        pattern_badge = "⚠️ 左側弱勢反彈"
    else:
        pattern_badge = "📦 區間整理"

    return {
        "close_price": round(p_now, 2),
        "r_5d": round(r_5d, 2),
        "r_20d": round(r_20d, 2),
        "r_60d": round(r_60d, 2),
        "score": round(final_score, 2),
        "pattern_badge": pattern_badge,
        "off_high_pct": round(off_high_pct, 1),
        "range_10d": round(range_10d, 1)
    }

def main():
    print("🚀 [1/4] 啟動全市場順勢大師 VCP 動能排程...")
    stock_dict = fetch_all_tw_stocks()
    theme_mapping = load_theme_mapping()
    all_symbols = list(stock_dict.keys())
    print(f"  ✔ 抓取到 {len(all_symbols)} 檔個股母體")

    batch_size = 80
    calculated_results = []
    
    print("📡 [2/4] 批次下載歷史 K 線並執行 VCP/新高接近度量化運算...")
    for i in range(0, len(all_symbols), batch_size):
        batch_syms = all_symbols[i:i+batch_size]
        yf_tickers = [stock_dict[s]["symbol_yf"] for s in batch_syms]
        try:
            data = yf.download(yf_tickers, period="6mo", interval="1d", group_by="ticker", threads=True, progress=False)
            for s in batch_syms:
                yf_sym = stock_dict[s]["symbol_yf"]
                if yf_sym in data.columns.levels[0]:
                    df_sub = data[yf_sym].dropna()
                    if len(df_sub) >= 60:
                        calc_res = calculate_master_vcp_score(df_sub)
                        if calc_res:
                            meta = stock_dict[s]
                            theme_info = theme_mapping.get(s, {})
                            themes = theme_info.get("themes", [])
                            micro_themes = theme_info.get("micro_themes", [])
                            
                            pattern_tag = calc_res["pattern_badge"]
                            merged_micro = [pattern_tag] + [t for t in micro_themes if t != pattern_tag]

                            calculated_results.append({
                                "symbol": s,
                                "name": meta["name"],
                                "market": meta["market"],
                                "main_industry": theme_info.get("main_industry", meta["main_industry"]),
                                "sub_industry": theme_info.get("sub_industry", f"{meta['main_industry']}應用"),
                                "close_price": calc_res["close_price"],
                                "r_5d": calc_res["r_5d"],
                                "r_20d": calc_res["r_20d"],
                                "r_60d": calc_res["r_60d"],
                                "score": calc_res["score"],
                                "themes": themes,
                                "micro_themes": merged_micro,
                                "pattern_badge": pattern_tag
                            })
        except Exception as e:
            print(f"批次處理異常 ({i}~{i+batch_size}): {e}")
        time.sleep(0.3)

    print(f"📊 [3/4] 成功計算 {len(calculated_results)} 檔個股，執行全市場 PR 換算...")
    if not calculated_results:
        print("❌ 計算結果為空，中止寫入")
        return

    df_calc = pd.DataFrame(calculated_results)
    df_calc = df_calc.sort_values(by="score", ascending=False).reset_index(drop=True)
    total_valid = len(df_calc)

    def compute_pr(rank_idx):
        pr = math.floor(((total_valid - rank_idx) / total_valid) * 100.0)
        return max(1, min(99, pr))

    df_calc["rs_rating"] = [compute_pr(i) for i in range(total_valid)]

    final_output = df_calc.to_dict(orient="records")
    with open("market_rankings.json", "w", encoding="utf-8") as f:
        json.dump(final_output, f, ensure_ascii=False, indent=2)

    print(f"🎉 [4/4] market_rankings.json 產出完成！全市場共 {len(final_output)} 檔個股完成順勢大師 RS 評級。")

if __name__ == "__main__":
    main()
