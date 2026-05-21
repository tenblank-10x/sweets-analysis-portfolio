import pandas as pd
from pathlib import Path 
import shutil
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

OUTPUT_PATH = BASE_DIR / "dashbord_data"
REPORT_PATH = BASE_DIR / "report_data" 

# ログ格納用フォルダのパス
LOG_DIR = BASE_DIR / "logs"


# =========================
# ログ設定
# =========================
LOG_DIR.mkdir(parents=True, exist_ok=True)

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
    "discount_rate"
]


# =========================
# 関数定義
# =========================
def load_transactions() -> pd.DataFrame:
    """取引明細データ全読み込み　→　DataFrame化"""

    files = list(TRANSACTION_DIR.glob( "*.csv"))

    if not files:
        raise FileNotFoundError("transactionsフォルダにCSVがありません")

    df_list = []

    for file in sorted(files):
        df = pd.read_csv(file)

        # カラムチェック
        actual_cols = set(df.columns)
        expected_cols = set(EXPECTED_COLUMNS)

        missing = expected_cols - actual_cols
        extra = actual_cols - expected_cols

        if missing or extra:
            raise ValueError(
                f"{file.name} のカラム不一致 "
                f"missing={missing}, extra={extra}"
            )

        df_list.append(df)

    return pd.concat(df_list, ignore_index=True)


def convert_datetime(df: pd.DataFrame) -> pd.DataFrame:
    """取引明細データのpurchase_datetimeの日付変換、日付分解"""

    def get_fiscal_year(dt: datetime) -> int:
        """ 年度計算 """
        if pd.isna(dt):
            return pd.NA
        
        return dt.year if dt.month >= 4 else dt.year - 1

    # "purchase_datetime"をdatetime型に変換
    df["purchase_datetime"] = pd.to_datetime(
            df["purchase_datetime"],
            errors="coerce"
        )

    if df["purchase_datetime"].isnull().any():
        logging.warning("purchase_datetimeが日付変換できない取引明細データあり")
        print("＜warning＞purchase_datetimeが日付変換できない取引明細データあり")

    # "purchase_datetime"の日付分解
    df["year"] = df["purchase_datetime"].dt.year
    df["month"] = df["purchase_datetime"].dt.month
    df["day"] = df["purchase_datetime"].dt.day
    df["hour"] = df["purchase_datetime"].dt.hour
    df["fiscal_year"] = df["purchase_datetime"].apply(get_fiscal_year)

    # int化
    for col in ["year", "month", "day", "hour", "fiscal_year"]:
        df[col] = df[col].astype("Int64")

    return df


def load_masters() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """customers,products,storesのマスタをDataFrame化"""

    customers = pd.read_csv(CUSTOMERS_PATH)
    customers["birth_date"] = pd.to_datetime(
        customers["birth_date"],
        errors="coerce"
    )   

    if customers["birth_date"].isnull().any():
        logging.warning("birth_dateが日付変換できない顧客データあり")
        print("＜warning＞birth_dateが日付変換できない顧客データあり")
        
    products = pd.read_csv(PRODUCTS_PATH)
    stores = pd.read_csv(STORES_PATH)

    return customers, products, stores    


def check_master(
        df: pd.DataFrame, col: str, master_df: pd.DataFrame, master_col: str)-> None:
    """ 取引明細データにマスタ定義されている以外のデータが含まれていないかチェック """ 
    
    invalid = ~df[col].isin(master_df[master_col])
    if invalid.any():
        logging.warning(f"{col} に不正データあり: {df.loc[invalid, col].unique()}")
        print(f"＜warning＞{col} に不正データあり: {df.loc[invalid, col].unique()}")


def convert_numeric_columns(df: pd.DataFrame, col_names: list) -> pd.DataFrame:
    """ 数値想定カラムに数値以外のデータがないかチェック→数値以外はNanに変換 """ 

    for col in col_names:
            df[col] = pd.to_numeric(df[col], errors="coerce")

            if df[col].isnull().any():
                logging.warning(f"{col} に数値変換できないデータあり")
                print(f"＜warning＞{col} に数値変換できないデータあり")
    
    return df
        

def create_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """ DataFrameに金額関連の指標と年齢指標を追加 """

    # 金額関連
    df["sales_amount"] = df["unit_price"] * df["quantity"]
    df["sales_after_discount"] = df["sales_amount"] *  (1 - df["discount_rate"])
    df["profit"] = df["sales_after_discount"] - (df["quantity"] * df["cost"])

    # 顧客の誕生日からの購入時の年齢を算出してage_at_purchase列に入れる
    df["age_at_purchase"] = (
        df["purchase_datetime"].dt.year - df["birth_date"].dt.year - 
        (
            (df["purchase_datetime"].dt.month < df["birth_date"].dt.month) | 
            (
                (df["purchase_datetime"].dt.month == df["birth_date"].dt.month) & 
                (df["purchase_datetime"].dt.day < df["birth_date"].dt.day)
            )
        ).astype(int)
    )

    return df


def create_wide_table(
        df: pd.DataFrame, customers: pd.DataFrame, products: pd.DataFrame, stores: pd.DataFrame) -> pd.DataFrame:
    """ワイドデータ用DataFrame作成、顧客年代追加"""

    df = df.merge(stores, on="store_id", how="left")
    df = pd.merge(df, products[["product_id", "product_name", "product_type","sales_type"]], on="product_id", how="left")
    df = pd.merge(df, customers, on="customer_id", how="left")
    df = df.drop(columns=["product_id", "store_id"])

    # ワイドテーブル用顧客年代の追加
    df["age_group_at_purchase"] = pd.cut(
        df["age_at_purchase"], 
        bins=[0, 10, 20, 30, 40, 50, 60, 120], 
        labels=["10代未満", "10代", "20代", "30代", "40代", "50代", "60代以上"], 
        right=False)
    
    return df


# =========================
# メイン処理
# =========================
def main():

    try:
        log_file = LOG_DIR / "process.log"
        with log_file.open("a", encoding="utf-8") as f:
            f.write("=" * 50 + "\n")

        logging.info("処理開始")
        print("========処理開始========")

        # 1. 取引明細データ全読み込み →　DataFrame化
        logging.info("取引明細データの読み込み")
        transactions = load_transactions()

        # 2. datetime変換、日付分割
        logging.info("取引明細データ purchase_datetimeの変換処理")
        transactions = convert_datetime(transactions)

        # 3. マスタ読み込み、顧客マスタのbirth_dateの日付変換
        logging.info("マスタ読み込み")
        customers, products, stores = load_masters()

        # 4. 不備チェック(マスタの存在有無、数値チェック)
        logging.info("マスタIDの存在チェック")
        check_master(transactions, "customer_id", customers, "customer_id")
        check_master(transactions, "product_id", products, "product_id")
        check_master(transactions, "store_id", stores, "store_id")

        logging.info("取引データ数値型エラーのチェック")
        transactions = convert_numeric_columns(transactions, ["quantity", "unit_price"])

        # 5. 製品データと顧客データのマージ
        merge_df = pd.merge(transactions, products[["product_id", "cost"]], on="product_id", how="left")
        merge_df = pd.merge(merge_df, customers[["customer_id", "birth_date"]], on="customer_id", how="left")
        
        # 6. 指標作成（sales_amount、sales_after_discount、profit、age_at_purchase）
        logging.info("指標カラム追加")
        merge_df= create_metrics(merge_df) 
        merge_df = merge_df.drop(columns=["birth_date"])

        # 7. 出力 
        logging.info("出力CSV作成")

        ## PowerQuery用(各マスタと取引明細データの出力)
        OUTPUT_PATH.mkdir(parents=True, exist_ok=True)
        merge_df.to_csv(OUTPUT_PATH / "transactions.csv", index=False)

        customers_cleaned = customers[["customer_id", "customer_prefecture"]]
        customers_cleaned.to_csv(OUTPUT_PATH / "customers.csv", index=False)

        stores.to_csv(OUTPUT_PATH / "stores.csv", index=False)
        products.to_csv(OUTPUT_PATH / "products.csv", index=False)
    
        ## ワイドデータ(人が分析する用データの出力)
        df_for_wide = create_wide_table(merge_df, customers_cleaned, products, stores)
        REPORT_PATH.mkdir(parents=True, exist_ok=True)
        df_for_wide.to_csv(REPORT_PATH / "wide_table_data.csv", index=False)

        logging.info("処理完了")

    except FileNotFoundError as e:
        logging.exception("＜ファイル存在なし＞")
        print(f"ファイル存在なし: {e}")

    except pd.errors.ParserError as e:
        logging.exception("＜ファイルの区切り崩れ＞")
        print(f"ファイルの区切り崩れ: {e}")

    except UnicodeDecodeError as e:
        logging.exception("＜ファイルの文字コード異常＞")
        print(f"ファイルの文字コード異常: {e}")

    except pd.errors.EmptyDataError as e:
        logging.exception("＜空白のファイル＞")
        print(f"空白のファイル: {e}")
    
    except KeyError as e:
        logging.exception("＜存在しない列あり＞")
        print(f"列不足エラー: {e}")

    except Exception as e:
        logging.exception("＜エラー発生＞")
        print(f"エラー発生: {type(e).__name__}")
        print(f"詳細: {e}")
    
    finally:
        print("========処理終了========")


if __name__ == "__main__":
    main()