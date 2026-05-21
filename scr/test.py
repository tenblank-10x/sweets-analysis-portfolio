import pandas as pd
import numpy as np
import random
import os
from datetime import datetime, timedelta

# ======================
# 設定
# ======================
START_DATE = "2023-01-01"
END_DATE = "2024-12-31"
AVG_ORDERS_PER_DAY = 100

OUTPUT_DIR = "data_raw"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ======================
# 商品タイプ
# ======================
product_types = [
    "和生菓子", "米菓", "豆菓子", "和干菓子その他",
    "クッキー", "焼き菓子その他", "ケーキ", "シュー菓子",
    "チョコ", "ゼリー・プリン", "ギフト", "定期便"
]

# ======================
# 商品マスタ作成
# ======================
products = []
product_id = 1

for pt in product_types:
    for i in range(5):

        sales_type = "単品"
        if pt == "ギフト":
            sales_type = "ギフト"
        elif pt == "定期便":
            sales_type = "定期便"

        match sales_type:
            case "単品":
                if pt == "ケーキ" or pt =="和生菓子":
                    price = random.randint(400, 800)
                elif pt == "シュー菓子":
                    price = random.randint(300, 500)
                else:
                    price = random.randint(200, 300)

            case "ギフト" | "定期便":
                price = random.randint(1000, 3500)

        cost = int(price * random.uniform(0.4, 0.7))

        products.append({
            "product_id": product_id,
            "product_name": f"{pt}_{i+1}",
            "product_type": pt,
            "sales_type": sales_type,
            "price": price,
            "cost": cost
        })
        product_id += 1

products_df = pd.DataFrame(products)
products_df.to_csv(f"{OUTPUT_DIR}/products.csv", index=False)

# ======================
# 顧客マスタ
# ======================
all_prefectures = ["北海道", "青森県", "岩手県", "宮城県", "秋田県","山形県", "福島県",
                   "茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県",
                   "新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県", "岐阜県",
                   "静岡県", "愛知県", "三重県", "滋賀県", "京都府", "大阪府", "兵庫県",
                   "奈良県", "和歌山県", "鳥取県", "島根県", "岡山県", "広島県", "山口県",
                   "徳島県", "香川県", "愛媛県", "高知県", "福岡県", "佐賀県", "長崎県",
                   "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県"]

# 都道府県の重みづけ
prefecture_weights = []
for prefecture in all_prefectures:
    match prefecture:
        case "大阪府": prefecture_weights.append(3)
        case "東京都": prefecture_weights.append(2.25)
        case "神奈川県" | "京都府" | "兵庫県": prefecture_weights.append(1.5)
        case _:  prefecture_weights.append(1.0)

customers = []
for i in range(10000):
    customers.append({
        "customer_id": i+1,
        "birth_date": datetime.strptime("1950-01-01", "%Y-%m-%d") + timedelta(days=random.randint(0, 20000)),
        "customer_prefecture": random.choices(all_prefectures, weights=prefecture_weights, k=1)[0]
    })

customers_df = pd.DataFrame(customers)
customers_df.to_csv(f"{OUTPUT_DIR}/customers.csv", index=False)

# ======================
# 店舗マスタ
# ======================
stores = [
    # 実店舗
    ("東京店1", "東京都", "STORE"),
    ("東京店2", "東京都", "STORE"),
    ("神奈川店", "神奈川県", "STORE"),
    ("静岡店", "静岡県", "STORE"),
    ("大阪店1", "大阪府", "STORE"),
    ("大阪店2", "大阪府", "STORE"),
    ("大阪店3", "大阪府", "STORE"),
    ("大阪店4", "大阪府", "STORE"),
    ("大阪店5", "大阪府", "STORE"),
    ("兵庫店1", "兵庫県", "STORE"),
    ("兵庫店2", "兵庫県", "STORE"),
    ("京都店", "京都府", "STORE"),
    # EC
    ("楽天", "EC", "EC"),
    ("Amazon", "EC", "EC"),
    ("自社サイト", "EC", "EC"),
]

stores_df = pd.DataFrame(stores, columns=["store_name", "region", "channel_type"])
stores_df["store_id"] = stores_df.index + 1

# 店舗マスタをCSVで出力
stores_df.to_csv(f"{OUTPUT_DIR}/stores.csv", index=False)

# 店舗ごとの重みのリストを作成
store_weights = []
for name, region, type in stores:
    match name:
        case "大阪店1": store_weights.append(2.5)
        case "東京店1" | "兵庫店1": store_weights.append(2.0)
        case _:
            if region == "EC":
                store_weights.append(1.0)
            else:
                store_weights.append(1.15)

# ======================
# 店舗のchannel_typeと掛け合わせた商品の重みづけ
# ======================
EC_prduct_weights = []
STORE_product_weights = []

for  _, row in products_df.iterrows():
    ec_w = 1
    store_w = 1

    # ギフトはECで強い
    if row["product_type"] == "ギフト" or row["product_type"] == "定期便":
        ec_w *= 2
        store_w *= 0.7

    EC_prduct_weights.append(ec_w)
    STORE_product_weights.append(store_w)

# ======================
# 季節補正
# ======================
def month_multiplier(date):
    # 月ごとの偏り

    month = date.month

    match month:
        case 2: return 3.0
        case 12: return 4.0
        case 7 | 8: return 2.0
    
    return 1.0

def seasonal_product_multiplier(date, product_type):
    month = date.month

    # バレンタイン
    if month == 2 and product_type == "チョコ":
        return 3.0

    # クリスマス
    if month == 12 and product_type in ["ケーキ", "シュー菓子"]:
        return 4.0

    # 夏ギフト
    if month == 7 or month == 8:
        match product_type:
            case "ギフト": return 2.5
            case "和生菓子": return 1.2
            case "ゼリー・プリン": return 2.0
        return 0.7

    return 1.0

# ======================
# channel_typeによる顧客選定の変更対応
# ======================
def make_candidate_df(customers_df, channel_type, store_region):
    customer_regions = {"東京都":["東京都", "神奈川県", "千葉県", "埼玉県", "群馬県"],
                        "神奈川県":["東京都", "神奈川県", "静岡県", "山梨県"],
                        "静岡県":["神奈川県", "山梨県", "静岡県", "愛知県"],
                        "大阪府":["大阪府","兵庫県","京都府","奈良県","和歌山県"],
                        "京都府":["京都府","大阪府"],
                        "兵庫県":["兵庫県","大阪府"]}

    if channel_type == "STORE":
        # 実店舗であれば特定の地域から選ぶ
        return customers_df[customers_df["customer_prefecture"].isin(customer_regions[store_region])]
    else:
        # ECは全国
        return customers_df

# ======================
# 取引データ生成
# ======================
transactions = []
current_date = datetime.strptime(START_DATE, "%Y-%m-%d")
end_date = datetime.strptime(END_DATE, "%Y-%m-%d")

transaction_id = 1

while current_date <= end_date:
    month_weight = month_multiplier(current_date)
    daily_orders = int(np.random.poisson(AVG_ORDERS_PER_DAY) * month_weight)

    for _ in range(daily_orders):
        store = stores_df.sample(1, weights=store_weights).iloc[0]

        # 店舗のchannel_typeとregionにより顧客の選択範囲を変更
        candidates = make_candidate_df(customers_df, store["channel_type"], store["region"])

        # 店舗のchannel_typeにより商品選択の重みづけを変更
        if store["channel_type"] == "EC":
            product_weights = EC_prduct_weights
        else:
            product_weights = STORE_product_weights
        
        product = products_df.sample(1, weights=product_weights).iloc[0]

        # イベントごとに売上個数を変動
        seasonal_weight = seasonal_product_multiplier(current_date, product["product_type"])
        quantity = max(1, int(np.random.poisson(2) * seasonal_weight))

        unit_price = product["price"]
        
        # 月によって割引率を変動
        match current_date.month:
            case 2 | 7 | 8 | 12: discount = random.choice([0, 0.1, 0.3])
            case _: discount = random.choice([0, 0.05, 0.1])

        transactions.append({
            "transaction_id": transaction_id,
            "purchase_datetime": current_date + timedelta(minutes=random.randint(0, 1440)),
            "customer_id": candidates.sample(1).iloc[0]["customer_id"],
            "product_id": product["product_id"],
            "quantity": quantity,
            "unit_price": unit_price,
            "discount_rate": discount,
            "store_id": store["store_id"]
        })

        transaction_id += 1

    current_date += timedelta(days=1)

transactions_df = pd.DataFrame(transactions)

# 分割出力（1ファイル5万件）
chunk_size = 50000
for i in range(0, len(transactions_df), chunk_size):
    transactions_df.iloc[i:i+chunk_size].to_csv(
        f"{OUTPUT_DIR}/transactions_part_{i//chunk_size+1}.csv",
        index=False
    )

print("データ生成完了！")