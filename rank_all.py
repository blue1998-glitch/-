import os
import json
import time
import math
import requests
import numpy as np
import pandas as pd
import yfinance as yf

# 1. 抓取全市場官方母體清單 (維持原樣)
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

# 2. 升級後的 RS 核心公式：順勢大師 VCP × 新高接近度
def calculate_master_rs_score(df_hist):
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
        h_prox = 1.25  # 創 60 日新高獎勵
    elif off_high_pct <= 8.0:
        h_prox = 1.12 - (off_high_pct / 8.0) * 0.12  # 距高點 8% 內微幅加成
    elif off_high_pct <= 18.0:
        h_prox = 1.0 - ((off_high_pct - 8.0) / 10.0) * 0.25
    else:
        h_prox = max(0.20, 0.75 - ((off_high_pct - 18.0) / 20.0) * 0.55)  # 破位重罰

    # 3. VCP 波動收斂度 (10日極窄震幅)
    high_10d = float(np.max(highs[-10:]))
    low_10d = float(np.min(lows[-10:]))
    range_10d = ((high_10d - low_10d) / max(0.01, low_10d)) * 100.0

    if range_10d <= 7.0 and off_high_pct <= 10.0:
        v_tight = 1.18  # 經典 VCP 收縮蓄勢
    elif range_10d <= 12.0 and off_high_pct <= 12.0:
        v_tight = 1.08
    elif range_10d > 22.0:
        v_tight = 0.85
    else:
        v_tight = 1.00

    # 4. 均線趨勢濾網與死貓反彈懲罰
    ma20 = float(np.mean(closes[-20:]))
    ma60 = float(np.mean(closes[-60:]))

    t_trend = 1.0
    if p_now < ma60:
        t_trend *= 0.35  # 季線之下重罰
    if p_now < ma20:
        t_trend *= 0.75  # 月線之下
    if r_20d < 0 and r_5d > 0:
        t_trend *= 0.65  # 月線走跌之短線反彈折扣

    final_score = base_momentum * h_prox * v_tight * t_trend

    return {
        "close_price": round(p_now, 2),
        "r_5d": round(r_5d, 2),
        "r_20d": round(r_20d, 2),
        "r_60d": round(r_60d, 2),
        "score": round(final_score, 2)
    }

# 3. 批次下載、全市場排序與 JSON 產出 (維持原結構)
def main():
    print("🚀 啟動全市場 RS 動能排程...")
    stock_dict = fetch_all_tw_stocks()
    all_symbols = list(stock_dict.keys())
    print(f"  ✔ 抓取到 {len(all_symbols)} 檔個股母體")

    batch_size = 80
    calculated_results = []

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
                        calc_res = calculate_master_rs_score(df_sub)
                        if calc_res:
                            meta = stock_dict[s]
                            calculated_results.append({
                                "symbol": s,
                                "name": meta["name"],
                                "market": meta["market"],
                                "main_industry": meta["main_industry"],
                                "close_price": calc_res["close_price"],
                                "r_5d": calc_res["r_5d"],
                                "r_20d": calc_res["r_20d"],
                                "r_60d": calc_res["r_60d"],
                                "score": calc_res["score"]
                            })
        except Exception as e:
            print(f"批次處理異常 ({i}~{i+batch_size}): {e}")
        time.sleep(0.3)

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

    print(f"🎉 market_rankings.json 產出完成！全市場共 {len(final_output)} 檔個股完成 RS 評級。")

if __name__ == "__main__":
    main()
