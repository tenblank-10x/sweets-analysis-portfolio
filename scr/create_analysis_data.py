import pandas as pd
from pathlib import Path 
import glob
import logging
from datetime import datetime

# =========================
# パス定義
# =========================
BASE_DIR = Path(__file__).resolve().parent.parent

# rawデータ関連のパス
RAW_DIR = BASE_DIR / "data_raw"
TRANSACTION_DIR = RAW_DIR / "transactions"

CUSTOMERS_PATH = RAW_DIR / "customers.csv"
PRODUCTS_PATH = RAW_DIR / "products.csv"
STORES_PATH = RAW_DIR / "stores.csv"

OUTPUT_PATH = BASE_DIR / "data_processed" / "sales_cleaned.csv"

# ログ格納用フォルダのパス
LOG_DIR = BASE_DIR / "logs"


# =========================
# ログ設定
# =========================
Path.makedir(LOG_DIR, exist_ok=True)

logging.basicConfig(
    filename=LOG_DIR / "process.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)


# =========================
# 取引明細データ想定カラム
# =========================
EXPECTED_COLUMNS = [
    "transaction_id",
    "customer_id",
    "product_id",
    "store_id",
    "purchase_datetime",
    "quantity",
    "unit_price",
    "discount"
]


# =========================
# 年度計算
# =========================
def get_fiscal_year(dt: datetime) -> int:
    return dt.year if dt.month >= 4 else dt.year - 1


# =========================
# メイン処理
# =========================
def main():
    try:
        logging.info("処理開始")

        # -------------------------
        # 1. 取引明細データ全読み込み →　DataFrame化
        # -------------------------
        files = list(TRANSACTION_DIR.glob( "*.csv"))

        if not files:
            raise Exception("transactionsフォルダにCSVがありません")

        df_list = []

        for file in sorted(files):
            logging.info(f"読み込み: {file}")
            df = pd.read_csv(file)

            # カラムチェック
            if sorted(list(df.columns)) != sorted(EXPECTED_COLUMNS):
                raise Exception(f"カラム不一致: {file}")

            df_list.append(df)

        transactions = pd.concat(df_list, ignore_index=True)

        # -------------------------
        # 2. datetime変換
        # -------------------------
        transactions["purchase_datetime"] = pd.to_datetime(
            transactions["purchase_datetime"],
            errors="coerce"
        )

        if transactions["purchase_datetime"].isnull().any():
            logging.warning("purchase_datetimeが日付変換できない取引明細データあり")

        # -------------------------
        # 3. "purchase_datetime"の日付分解
        # -------------------------
        transactions["year"] = transactions["purchase_datetime"].dt.year
        transactions["month"] = transactions["purchase_datetime"].dt.month
        transactions["day"] = transactions["purchase_datetime"].dt.day
        transactions["hour"] = transactions["purchase_datetime"].dt.hour
        transactions["fiscal_year"] = transactions["purchase_datetime"].apply(get_fiscal_year)

        # int化
        for col in ["year", "month", "day", "hour", "fiscal_year"]:
            transactions[col] = transactions[col].astype("Int64")

        # -------------------------
        # 4. マスタ読み込み、顧客マスタのbirth_dateの日付変換
        # -------------------------
        customers = pd.read_csv(CUSTOMERS_PATH)
        customers["birth_date"] = pd.to_datetime(
            customers["birth_date"],
            errors="coerce"
        )

        if customers["birth_date"].isnull().any():
            logging.warning("birth_dateが日付変換できない顧客データあり")
        
        products = pd.read_csv(PRODUCTS_PATH)
        stores = pd.read_csv(STORES_PATH)

        # -------------------------
        # 5. 不備チェック
        # -------------------------
        def check_master(
                df: pd.DataFrame, col: str, master_df: pd.DataFrame, master_col: str)-> None:
            
            invalid = ~df[col].isin(master_df[master_col])
            if invalid.any():
                logging.warning(f"{col} に不正データあり: {df.loc[invalid, col].unique()}")

        check_master(transactions, "customer_id", customers, "customer_id")
        check_master(transactions, "product_id", products, "product_id")
        check_master(transactions, "store_id", stores, "store_id")

        # 数値チェック
        for col in ["quantity", "unit_price"]:
            transactions[col] = pd.to_numeric(transactions[col], errors="coerce")

            if transactions[col].isnull().any():
                logging.warning(f"{col} に数値変換できないデータあり")
        

        # -------------------------
        # 6. 製品データと顧客データのマージ ＆ 指標作成
        # -------------------------
        df = pd.merge(transactions, products[["product_id", "cost"]], on="product_id", how="left")

        df["sales_amount"] = df["unit_price"] * df["quantity"]
        df["sales_after_discount"] = df["sales_amount"] * df["discount"]
        df["profit"] = df["sales_after_discount"] - (df["quantity"] * df["cost"])

        # 顧客の誕生日からの購入時の年齢を算出してage列に入れる
        df = pd.merge(df, customers[["customers_id", "birth_date"]], on="customer_id", how="left")
        df["age_at_purchase"] = (
            df["purchase_date"].dt.year - df["birth_date"].dt.year - 
            (
                (df["purchase_date"].dt.month < df["birth_date"].dt.month) | 
                (
                    (df["purchase_date"].dt.month == df["birth_date"].dt.month) & 
                    (df["purchase_date"].dt.day < df["birth_date"].dt.day)
                )
            ).astype(int)
        )
        df = df.drop(columns=["birth_date"])

        # -------------------------
        # 7. 出力用DF作成
        # -------------------------        
        # PowerQuery取り込み用customers
        customers_cleaned = customers[["customer_id", "customer_prefecture"]]

        # ワイドデータ用
        df_for_wide = df.merge(stores, on="store_id", how="left")
        df_for_wide = pd.merge(df_for_wide, products[["product_id", "product_name", "product_type","sales_type"]], on="product_id", how="left")
        df_for_wide = pd.merge(df_for_wide, customers[["customer_id", "customer_prefecture"]], on="product_id", how="left")
        df_for_wide = df_for_wide.drop(columns=["product_id", "store_id"])

        # ワイドテーブル用顧客年代の追加
        df_for_wide["age_group_at_purchase"] = pd.cut(
            df["age_at_purchase"], 
            bins=[0, 10, 20, 30, 40, 50, 60, 120], 
            labels=["10代未満", "10代", "20代", "30代", "40代", "50代", "60代以上"], 
            right=False)

        # -------------------------
        # 8. 出力
        # -------------------------

        Path.makedir(OUTPUT_PATH, exist_ok=True)
        df.to_csv(OUTPUT_PATH / "transactions.csv", index=False)
        customers_cleaned.to_csv(OUTPUT_PATH / "customers_cleaned.csv", index=False)
        df_for_wide.to_csv(OUTPUT_PATH / "wide_table_data.csv", index=False)

        logging.info("処理完了")

    except Exception as e:
        logging.error(f"エラー発生: {str(e)}")
        print(f"エラー: {e}")


if __name__ == "__main__":
    main()