import requests
import pandas as pd
import itertools
import json

# ======================
#  LOAD CONFIG
# ======================
with open("config/settings.json", "r") as f:
    config = json.load(f)

ITEMS = config["items"]
LOCATIONS = config["cities"]
TRANSACTION_TAX = config["transaction_tax_pct"] / 100  # ubah ke desimal
MIN_PROFIT_PCT = config["min_profit_pct"]

API_URL = (
    f"https://east.albion-online-data.com/api/v2/stats/prices/"
    f"{','.join(ITEMS)}.json?locations={','.join(LOCATIONS)}"
)

# ======================
#  FETCH DATA
# ======================
print("Mengambil data dari API:")
print(API_URL)

response = requests.get(API_URL)
if response.status_code != 200:
    raise Exception(f"Gagal mengambil data API: {response.status_code}")

raw = response.json()
print(f"✅ Data API berhasil diambil: {len(raw)} entri.\n")

# ======================
#  SIAPKAN DATAFRAME
# ======================
df = pd.DataFrame(raw)
df = df[["item_id", "city", "buy_price_min", "sell_price_min"]]
df = df.rename(columns={"buy_price_min": "buy", "sell_price_min": "sell"})


# ======================
#  FUNGSI HITUNG PROFIT
# ======================
def compute_profit(buy_price, sell_price):
    if buy_price <= 100 or sell_price <= 100:
        return None
    spread = sell_price - buy_price
    if spread <= 0:
        return None
    gross_pct = (spread / buy_price) * 100
    net_pct = gross_pct * (1 - TRANSACTION_TAX)
    return {
        "spread": spread,
        "gross_pct": round(gross_pct, 2),
        "net_pct": round(net_pct, 2),
    }


# ======================
#  CARI PELUANG FLIPPING
# ======================
def find_flips():
    results = []
    for item in ITEMS:
        subset = df[df["item_id"] == item]
        for a, b in itertools.permutations(subset.to_dict("records"), 2):
            # abaikan transaksi di kota sama
            if a["city"] == b["city"]:
                continue
            # abaikan BM → BM
            if a["city"] == "Black Market" and b["city"] == "Black Market":
                continue
            # hanya BM sebagai tujuan jual
            if a["city"] == "Black Market" and b["city"] != "Black Market":
                continue

            profit = compute_profit(a["buy"], b["sell"])
            if profit and profit["net_pct"] >= MIN_PROFIT_PCT:
                results.append(
                    {
                        "item": item,
                        "beli_di": a["city"],
                        "jual_di": b["city"],
                        "harga_beli": a["buy"],
                        "harga_jual": b["sell"],
                        "spread": profit["spread"],
                        "profit_%": profit["net_pct"],
                    }
                )
    return results


flips = find_flips()
df_flips = pd.DataFrame(flips)

if df_flips.empty:
    print("⚠️ Tidak ditemukan peluang flipping.\n")
else:
    df_sorted = df_flips.sort_values(by="profit_%", ascending=False)
    print("=== 🔍 Top 10 Peluang Flipping (Net Profit) ===\n")
    print(df_sorted.head(10).to_string(index=False))
    df_sorted.to_csv("flipping_results.csv", index=False, encoding="utf-8-sig")


# ======================
#  TAMPILKAN SPREAD MENTAH
# ======================
def show_raw_spread():
    entries = []
    for item in ITEMS:
        subset = df[df["item_id"] == item]
        for a, b in itertools.permutations(subset.to_dict("records"), 2):
            if a["city"] == b["city"]:
                continue
            if a["city"] == "Black Market" and b["city"] == "Black Market":
                continue
            if a["city"] == "Black Market" and b["city"] != "Black Market":
                continue
            if a["buy"] <= 100 or b["sell"] <= 100:
                continue
            diff = b["sell"] - a["buy"]
            if diff <= 0:
                continue
            pct = (diff / a["buy"]) * 100
            entries.append(
                {
                    "item": item,
                    "dari": a["city"],
                    "ke": b["city"],
                    "buy": a["buy"],
                    "sell": b["sell"],
                    "spread": diff,
                    "spread_%": round(pct, 2),
                }
            )
    df_spread = pd.DataFrame(entries)
    if not df_spread.empty:
        df_spread = df_spread.sort_values(by="spread_%", ascending=False)
        print("\n=== 📊 Top 10 Spread Mentah (tanpa biaya) ===\n")
        print(df_spread.head(10).to_string(index=False))
        df_spread.to_csv("spread_raw.csv", index=False, encoding="utf-8-sig")


show_raw_spread()

print("\nSelesai.")
