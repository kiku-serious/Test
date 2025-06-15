import requests
from requests_ntlm import HttpNtlmAuth
from bs4 import BeautifulSoup
import re
import datetime
import json
import os
import traceback
import urllib3
import boto3

# --- 環境変数の設定 ---
# これらの環境変数はAWS Batchジョブ定義で設定される
DOMAIN_PASSWORD = os.environ.get('DOMAIN_PASSWORD') # SharePointアクセス用パスワード (必須)
SITE_URL = os.environ.get('SITE_URL') # SharePointサイトのURL (必須)
DOMAIN = os.environ.get('DOMAIN') # SharePointドメイン (必須)
LOGINNAME = os.environ.get('LOGINNAME') # SharePointログインユーザー名 (必須)
LOGINPASSWORD = os.environ.get('LOGINPASSWORD') # SharePointログインパスワード（DOMAIN_PASSWORDと同じでも可） (必須)

# プロキシ情報（必要なら、AWS Batch環境で設定）
HTTP_PROXY = os.environ.get('HTTP_PROXY')
HTTPS_PROXY = os.environ.get('HTTPS_PROXY')
proxies = {}
if HTTP_PROXY:
    proxies['http'] = HTTP_PROXY
if HTTPS_PROXY:
    proxies['https'] = HTTPS_PROXY
if not proxies:
    proxies = None

# S3バケット情報
BUCKET_NAME = os.environ.get('BUCKET_NAME') # S3バケット名 (必須)
S3_OUTPUT_PREFIX = os.environ.get('S3_OUTPUT_PREFIX', 'raw_sharepoint_reports_daily/') # S3に日次生データを保存する際のプレフィックス

# BedrockやElasticsearch関連の設定は、このファイルでは不要なので削除

# SSL検証を無効にする設定（requests.get(verify=False)を使う場合）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- AWSクライアントの初期化 ---
s3_client = boto3.client('s3', region_name=os.environ.get("AWS_REGION", "ap-northeast-1"))

# --- SharePointのフィールド名マッピング ---
FIELD_TITLE = 'Title'
FIELD_ID = 'ID'
FIELD_BODY = 'mrtBody' # SharePointのHTML本文フィールド名
FIELD_APPROVED_DATE = 'mrtApprovedDate' # SharePointの承認日フィールド名
FIELD_FILE_REF = 'FileLeafRef' # SharePointのファイル名フィールド名
FIELD_CUSTOMER_PARTICIPANT = 'mrtCustomerParticipant'
FIELD_MURATA_PARTICIPANT = 'mrtMurataParticipant'
FIELD_SUMMARY_SP = 'mrtSummary' # SharePointの既存概要フィールド名

# --- ヘルパー関数 (日付パースとS3保存のみ残す) ---

def parse_visit_date(date_str: str) -> str | None:
    if not date_str:
        return None
    match_single_date = re.match(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})(?:\(.*\))?', date_str)
    if match_single_date:
        try:
            year, month, day = int(match_single_date.group(1)), int(match_single_date.group(2)), int(match_single_date.group(3))
            return datetime.datetime(year, month, day).strftime('%Y-%m-%d')
        except ValueError:
            pass
    match_range_date = re.match(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})[～~-](\d{4})[/-](\d{1,2})[/-](\d{1,2})', date_str)
    if match_range_date:
        try:
            year, month, day = int(match_range_date.group(1)), int(match_range_date.group(2)), int(match_range_date.group(3))
            return datetime.datetime(year, month, day).strftime('%Y-%m-%d')
        except ValueError:
            pass
    print(f"警告：日付文字列'{date_str}'をパースできませんでした。")
    return None

def store_json_to_s3(data, filename):
    if not BUCKET_NAME:
        print("警告: BUCKET_NAME環境変数が設定されてないわ！S3への保存をスキップするわよ。")
        return False
    try:
        json_data = json.dumps(data, ensure_ascii=False, indent=2)
        s3_client.put_object(Bucket=BUCKET_NAME, Key=filename, Body=json_data.encode('utf-8'), ContentType='application/json')
        print(f"S3にファイル'{filename}'を保存したわ。")
        return True
    except Exception as e:
        print(f"S3への保存中にエラーが発生したわ: {e}", exc_info=True)
        return False

# --- メイン処理関数 (AWS Batchジョブのエントリポイントになる) ---
# この関数がAWS Batchから呼び出される
def process_sharepoint_data_for_batch(target_date_str: str): # 処理対象の日付を1日単位で受け取る
    print(f"SharePointデータ抽出処理を開始するわ。対象日: {target_date_str}")
    
    # 環境変数の必須チェック
    required_envs = ['DOMAIN_PASSWORD', 'SITE_URL', 'DOMAIN', 'LOGINNAME', 'LOGINPASSWORD', 'BUCKET_NAME']
    for env_var in required_envs:
        if not os.environ.get(env_var):
            raise ValueError(f"必須環境変数 '{env_var}' が設定されてないわよ！")

    current_password = LOGINPASSWORD

    try:
        # 1日分のデータ取得範囲を設定
        target_dt_utc = datetime.datetime.strptime(target_date_str, '%Y-%m-%d').replace(tzinfo=datetime.timezone.utc)
        start_string_gmt = target_dt_utc.strftime('%Y-%m-%dT%H:%M:%SZ')
        end_string_gmt = (target_dt_utc + datetime.timedelta(days=1) - datetime.timedelta(seconds=1)).strftime('%Y-%m-%dT%H:%M:%SZ')
            
        print(f"指定された取得期間: {start_string_gmt} から {end_string_gmt} まで。")

    except Exception as e:
        print(f"日付パース中にエラーが発生したわ: {e}", exc_info=True)
        raise ValueError(f"不正な日付形式よ！YYYY-MM-DD形式で日付を指定しなさい: {str(e)}")

    all_sharepoint_items = []
    
    query_params_base = {
        "$filter": f"mrtApprovedDate ge datetime'{start_string_gmt}' and mrtApprovedDate le datetime'{end_string_gmt}'",
        "$select": f"{FIELD_TITLE},{FIELD_ID},{FIELD_BODY},{FIELD_APPROVED_DATE},{FIELD_FILE_REF},{FIELD_CUSTOMER_PARTICIPANT},{FIELD_MURATA_PARTICIPANT},{FIELD_SUMMARY_SP},Author/Id",
        "$expand": "Author"
    }
    
    next_link = f"{SITE_URL}/_api/web/lists/getbytitle('For Global')/items?{urllib.parse.urlencode(query_params_base)}"

    while next_link:
        print(f"SharePointからデータを取得中: {next_link}")
        sharepoint_response = None
        for count in range(3):
            auth_info = HttpNtlmAuth(f"{DOMAIN}\\{LOGINNAME}", current_password)
            try:
                response = requests.get(next_link, auth=auth_info, headers={'Accept': 'application/json'}, proxies=proxies, verify=False, timeout=60)
                
                if response.status_code == 200:
                    sharepoint_response = response
                    print("SharePointアクセス成功。")
                    break
                elif response.status_code == 401:
                    print(f"SharePoint認証失敗 (401 Unauthorized)。パスワード変更ロジックは手動実行では適用しないわ。")
                    if count < 2:
                        continue
                    else:
                         raise Exception("SharePoint認証に繰り返し失敗しました。正しいパスワードを確認しなさい！")
                else:
                    print(f"SharePointアクセスエラー: ステータスコード {response.status_code}, 理由: {response.reason}")
                    response.raise_for_status()
            except requests.exceptions.RequestException as req_e:
                print(f"SharePointへのリクエスト中にエラーが発生しました: {req_e}")
                print(traceback.format_exc())
                if count < 2:
                    continue
                else:
                    raise

        if sharepoint_response is None:
            raise Exception("SharePointからのデータ取得に失敗しました。認証を再試行しても成功しませんでした。")

        json_data = sharepoint_response.json()
        all_sharepoint_items.extend(json_data.get('value', []))
        next_link = json_data.get('odata.nextLink', json_data.get('__next'))

    if not all_sharepoint_items:
        print(f"指定された期間 ({target_date_str}) で新しいデータが見つかりませんでした。")
        return {
            "status": "SUCCESS",
            "message": f"SharePointから日付 {target_date_str} のデータが見つかりませんでした。",
            "s3_output_key": None
        }

    # S3に全ての生データをリスト形式の単一JSONファイルとして保存するわ
    # ファイル名に日付を含めて分かりやすくする
    s3_output_filename = f"{S3_OUTPUT_PREFIX}{target_dt_utc.strftime('%Y-%m-%d')}_raw_reports.json"
    
    if not store_json_to_s3(all_sharepoint_items, s3_output_filename):
        print("S3へのレポートリストの保存に失敗したわ。")
        raise Exception("S3へのレポートリストの保存に失敗したわ。")
            
    print("SharePointからのデータ取得とS3への生データ保存が完了したわ。")
    return {
        "status": "SUCCESS",
        "message": f"SharePointから日付 {target_date_str} のデータ取得とS3への保存が完了したわ！S3キー: {s3_output_filename}",
        "s3_output_key": s3_output_filename # 次のBatchジョブに渡す情報（Step Functions連携なし）
    }

# --- スクリプトのエントリポイント (AWS Batchジョブとして実行) ---
if __name__ == "__main__":
    # AWS Batchは環境変数で引数を渡す
    target_date_from_env = os.environ.get('TARGET_DATE') # TARGET_DATEをYYYY-MM-DD形式で渡す
    
    if not target_date_from_env:
        print("エラー: 環境変数 'TARGET_DATE' が設定されてないわよ！")
        exit(1)
    
    try:
        result = process_sharepoint_data_for_batch(target_date_from_env)
        if result and result.get("status") == "SUCCESS":
            print(f"ジョブ成功: {result.get('message')}")
            # AWS Batchジョブの標準出力に結果を出力
            if result.get("s3_output_key"):
                print(f"S3_OUTPUT_KEY: {result.get('s3_output_key')}") # 後続プロセスが取得できるようにKEYを出力
            exit(0)
        else:
            print(f"ジョブ失敗（データなしまたは警告）: {result.get('message')}")
            exit(1)
    except Exception as e:
        print(f"処理中に致命的なエラーが発生し、ジョブが失敗したわ: {e}")
        exit(1)