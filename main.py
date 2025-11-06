import requests
import pandas as pd
import itertools
import json
from datetime import datetime
import os

# ======================
#  LOAD CONFIG
# ======================
with open("config/settings.json", "r") as f:
    config = json.load(f)

ITEMS = config["items"]
LOCATIONS = config["cities"]
TRANSACTION_TAX = config.get("transaction_tax_pct", 0.04)
LISTING_TAX = config.get("tax_rate", 0.065)
MIN_PROFIT_PCT = config.get("min_profit_pct", 0.01)
WEBHOOK_URL = config.get("discord_webhook")  # tambahkan di settings.json
API_HOST = config["api_region_host"]

# ======================
#  FETCH SNAPSHOT DATA
# ======================
API_URL = f"{API_HOST}/api/v2/stats/prices/{','.join(ITEMS)}.json?locations={','.join(LOCATIONS)}&qualities=2"
print("Mengambil data snapshot dari API:")
print(API_URL)
response = requests.get(API_URL)
response.raise_for_status()
raw_snapshot = response.json()
df_snapshot = pd.DataFrame(raw_snapshot)
df_snapshot = df_snapshot[["item_id", "city", "sell_price_min", "buy_price_max"]]
df_snapshot = df_snapshot.rename(
    columns={"sell_price_min": "buy", "buy_price_max": "sell"}
)
df_snapshot = df_snapshot.fillna(0)
print(f"✅ Snapshot diambil: {len(df_snapshot)} entri")


# ======================
#  FUNSI HISTORICAL
# ======================
def get_historical_sell(item, city, time_scale=24):
    url = f"{API_HOST}/api/v2/stats/history/{item}.json?locations={city}&qualities=2&time-scale={time_scale}"
    try:
        r = requests.get(url)
        if r.status_code != 200:
            return None
        data = r.json()

        # support jika API mengembalikan dict dengan 'history'
        if isinstance(data, dict) and "history" in data:
            data = data["history"]

        # ambil median sell_price_min > 0
        prices = [
            entry.get("sell_price_min", 0)
            for entry in data
            if entry.get("sell_price_min", 0) > 0
        ]
        if not prices:
            return None
        median_price = int(sum(prices) / len(prices))
        return median_price
    except Exception as e:
        print(f"⚠️ Error fetch historical {item} @ {city}: {e}")
        return None


# ======================
#  PERBAIKI DATA SNAPSHOT
# ======================
for idx, row in df_snapshot.iterrows():
    if row["sell"] == 0:
        median_sell = get_historical_sell(row["item_id"], row["city"])
        if median_sell:
            df_snapshot.at[idx, "sell"] = median_sell

# Filter harga realistis
df_snapshot = df_snapshot[(df_snapshot["buy"] > 0) & (df_snapshot["sell"] > 0)]


# ======================
#  HITUNG PROFIT
# ======================
def compute_profit(buy_price, sell_price):
    if sell_price <= buy_price:
        return None
    gross_profit = sell_price - buy_price
    net_profit = (sell_price * (1 - LISTING_TAX)) - (buy_price * (1 + TRANSACTION_TAX))
    net_pct = (net_profit - buy_price) / buy_price * 100
    if net_profit <= 0:
        return None
    return {
        "spread": round(gross_profit, 2),
        "net_profit": round(net_profit, 2),
        "profit_%": round(net_pct, 2),
    }


# ======================
#  CARI PELUANG FLIPPING
# ======================
def find_flips(df):
    results = []
    for item in ITEMS:
        subset = df[df["item_id"] == item].to_dict("records")
        for a in subset:
            for b in subset:
                if a["city"] == b["city"]:
                    continue
                profit = compute_profit(a["buy"], b["sell"])
                if profit and profit["profit_%"] >= MIN_PROFIT_PCT * 100:
                    results.append(
                        {
                            "item": item,
                            "beli_di": a["city"],
                            "jual_di": b["city"],
                            "harga_beli": a["buy"],
                            "harga_jual": b["sell"],
                            "spread": profit["spread"],
                            "net_profit": profit["net_profit"],
                            "profit_%": profit["profit_%"],
                        }
                    )
    return pd.DataFrame(results)


df_flips = find_flips(df_snapshot)
df_flips_sorted = (
    df_flips.sort_values(by="profit_%", ascending=False)
    if not df_flips.empty
    else pd.DataFrame()
)

# ======================
#  DATA HISTORICAL SUMMARY
# ======================
hist_summary = []
for item in ITEMS:
    for city in LOCATIONS:
        median_sell = get_historical_sell(item, city)
        if median_sell:
            hist_summary.append(
                {"item": item, "city": city, "median_sell": median_sell}
            )
df_hist = pd.DataFrame(hist_summary)

# ======================
#  SAVE EXCEL
# ======================
os.makedirs("results", exist_ok=True)
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
file_path = f"results/flipping_results_{timestamp}.xlsx"

with pd.ExcelWriter(file_path) as writer:
    df_snapshot.to_excel(writer, sheet_name="Snapshot", index=False)
    df_flips_sorted.to_excel(writer, sheet_name="Flipping", index=False)
    df_hist.to_excel(writer, sheet_name="Historical", index=False)

print(f"📁 File Excel disimpan di: {file_path}")

# ======================
#  UPLOAD KE DISCORD
# ======================
if WEBHOOK_URL:
    try:
        with open(file_path, "rb") as f:
            payload = {
                "content": "📊 Hasil Flipping Albion terbaru (Snapshot + Historical):",
                "username": "Albion Flipper",
            }
            files = {"file": (os.path.basename(file_path), f)}
            response = requests.post(WEBHOOK_URL, data=payload, files=files)
        if response.status_code in [200, 204]:
            print("✅ File berhasil diupload ke Discord!")
        else:
            print("❌ Gagal upload:", response.status_code, response.text)
    except Exception as e:
        print("❌ Terjadi error saat upload ke Discord:", e)

print("\nSelesai.")
