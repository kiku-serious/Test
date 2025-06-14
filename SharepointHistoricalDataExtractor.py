import requests
from requests_ntlm import HttpNtlmAuth
from bs4 import BeautifulSoup
import re
import datetime
import json
import os
import traceback
import urllib3 # 追加: urllib3をインポート

# --- 環境変数の設定 ---
# これらの環境変数は、ローカルPCで実行する前に設定すること！
# 例: export DOMAIN_PASSWORD="your_password"
DOMAIN_PASSWORD = os.environ.get('DOMAIN_PASSWORD') # SharePointアクセス用パスワード (必須)
SITE_URL = os.environ.get('SITE_URL') # SharePointサイトのURL (必須)
DOMAIN = os.environ.get('DOMAIN') # SharePointドメイン (必須)
LOGINNAME = os.environ.get('LOGINNAME') # SharePointログインユーザー名 (必須)
LOGINPASSWORD = os.environ.get('LOGINPASSWORD') # SharePointログインパスワード（DOMAIN_PASSWORDと同じでも可） (必須)

# Bedrockモデル情報 (埋め込み生成に使う)
BEDROCK_SUMMARY_MODEL_ID = os.environ.get("BEDROCK_SUMMARY_MODEL_ID", "anthropic.claude-instant-v1") # 要約用BedrockモデルID
BEDROCK_EMBEDDING_MODEL_ID = os.environ.get("BEDROCK_EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v1") # 埋め込み用BedrockモデルID
AWS_REGION = os.environ.get("AWS_REGION", "ap-northeast-1") # Bedrockのリージョン

# プロキシ情報（必要なら）
HTTP_PROXY = os.environ.get('HTTP_PROXY')
HTTPS_PROXY = os.environ.get('HTTPS_PROXY')
proxies = {}
if HTTP_PROXY:
    proxies['http'] = HTTP_PROXY
if HTTPS_PROXY:
    proxies['https'] = HTTPS_PROXY
if not proxies:
    proxies = None

# 埋め込みベクトルの次元数
EMBEDDING_DIMS = 1536 

# SSL検証を無効にする設定（requests.get(verify=False)を使う場合）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- AWSクライアントの初期化 (ローカル実行なのでBedrockのみ) ---
# S3クライアントはS3への直接保存がなくなったので不要
bedrock_runtime = boto3.client(
    service_name = "bedrock-runtime",
    region_name = AWS_REGION
)

# --- SharePointのフィールド名マッピング ---
FIELD_TITLE = 'Title'
FIELD_ID = 'ID'
FIELD_BODY = 'mrtBody' # SharePointのHTML本文フィールド名
FIELD_APPROVED_DATE = 'mrtApprovedDate' # SharePointの承認日フィールド名
FIELD_FILE_REF = 'FileLeafRef' # SharePointのファイル名フィールド名
FIELD_CUSTOMER_PARTICIPANT = 'mrtCustomerParticipant'
FIELD_MURATA_PARTICIPANT = 'mrtMurataParticipant'
FIELD_SUMMARY_SP = 'mrtSummary' # SharePointの既存概要フィールド名

# 出張報告書のセクションラベル（HTMLから抽出するためのキーワード）
TRIP_REP_DATE = '訪問日'
TRIP_REP_CUSTOMER = "得意先参加者"
TRIP_REP_MURATA = "村田同行者"
TRIP_REP_SUMMARY = "概要"
TRIP_REP_DETAIL = "詳細"
TRIP_REP_COMMENT = "所感"

# 最終的な出力形式のキー名マッピング
KEY_MAP = {
    "Title": 'タイトル',
    "TripRep_Date": '訪問日',
    "TripRep_Customer": '得意先参加者',
    "TripRep_Murata": '村田同行者',
    "TripRep_Summary": '概要',
    "TripRep_Detail": '詳細',
    "TripRep_DetailSummary": '詳細要約',
    "URL": 'URL',
    "source_sharepoint_file_id": 'source_sharepoint_file_id',
    "source_sharepoint_filename": 'source_sharepoint_filename',
    "full_vector": '全文ベクトル',
    "summary_vector": '全文要約ベクトル',
}

# --- ヘルパー関数 (既存コードから流用・調整) ---

def summarize_text_with_bedrock(text):
    if not BEDROCK_SUMMARY_MODEL_ID:
        print("警告: Bedrockの要約モデルIDが設定されてないわ！要約をスキップするわよ。")
        return None
    if len(text) > 5000:
        print(f"警告: 要約対象テキストが長すぎるわよ ({len(text)}文字)。冒頭5000文字のみ要約するわ。")
        text = text[:5000]
    prompt = f"\n\nHuman: 以下の出張報告を簡潔に、かつ重要な情報を失わずに要約してください。\n\n<report>\n{text}\n</report>\n\nAssistant:"
    try:
        body = json.dumps({
            "prompt": prompt, "max_tokens_to_sample": 500, "temperature": 0.7, "top_p": 0.9, "stop_sequences": ["\n\nHuman:"]
        })
        response = bedrock_runtime.invoke_model(
            body=body, modelId=BEDROCK_SUMMARY_MODEL_ID, accept="application/json", contentType="application/json"
        )
        response_body = json.loads(response.get("body").read())
        return response_body.get("completion").strip()
    except Exception as e:
        print(f"Bedrockでの要約中にエラーが発生したわ: {e}", exc_info=True)
        return None

def get_embedding_from_bedrock(text: str) -> list[float] | None:
    if not BEDROCK_EMBEDDING_MODEL_ID:
        print("警告: Bedrockの埋め込みモデルIDが設定されてないわ！埋め込み生成をスキップするわよ。")
        return None
    if len(text) > 8000:
        print(f"警告: 埋め込み対象テキストが長すぎるわよ ({len(text)}文字)。冒頭8000文字のみで埋め込みを生成するわ。")
        text = text[:8000]
    try:
        body = json.dumps({"inputText": text})
        response = bedrock_runtime.invoke_model(
            body=body, modelId=BEDROCK_EMBEDDING_MODEL_ID, accept="application/json", contentType="application/json"
        )
        response_body = json.loads(response.get("body").read())
        return response_body.get("embedding")
    except Exception as e:
        print(f"Bedrockでの埋め込み生成中にエラーが発生したわ: {e}", exc_info=True)
        return None

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

def extract_text_from_html(html):
    soup = BeautifulSoup(html, 'html.parser')
    for script in soup(["script", "style"]):
        script.extract()
    text = soup.get_text()
    text = text.replace('\u200b', ' ').replace('\u3000', ' ').replace('\xa0', ' ')
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return " ".join(lines)

def extract_sections(body_text_html):
    soup = BeautifulSoup(body_text_html, 'html.parser')
    sections = {}
    summary_match = re.search(r'概要：\s*(.*?)(?:<br/>|\n|$)詳細：', soup.get_text(), re.DOTALL)
    if summary_match:
        sections[TRIP_REP_SUMMARY] = summary_match.group(1).strip()
    else:
        sections[TRIP_REP_SUMMARY] = "N/A"
        print("警告: 概要セクションを抽出できませんでした。")
    detail_match = re.search(r'詳細：\s*(.*?)(?:<br/>|\n|$)所感：', soup.get_text(), re.DOTALL)
    if detail_match:
        sections[TRIP_REP_DETAIL] = detail_match.group(1).strip()
    else:
        sections[TRIP_REP_DETAIL] = "N/A"
        print("警告: 詳細セクションを抽出できませんでした。")
    comment_match = re.search(r'所感：\s*(.*)', soup.get_text(), re.DOTALL)
    if comment_match:
        sections[TRIP_REP_COMMENT] = comment_match.group(1).strip()
    else:
        sections[TRIP_REP_COMMENT] = "N/A"
        print("警告: 所感セクションを抽出できませんでした。")
    return sections

# --- メイン処理関数 ---
def download_and_process_sharepoint_data(start_date_str: str, end_date_str: str, output_dir: str = "processed_sharepoint_reports"):
    print("SharePointデータダウンロード処理を開始するわ。")
    
    # 環境変数の必須チェック
    required_envs = ['DOMAIN_PASSWORD', 'SITE_URL', 'DOMAIN', 'LOGINNAME', 'LOGINPASSWORD', 'AWS_REGION', 'BEDROCK_EMBEDDING_MODEL_ID', 'BEDROCK_SUMMARY_MODEL_ID']
    for env_var in required_envs:
        if not os.environ.get(env_var):
            raise ValueError(f"必須環境変数 '{env_var}' が設定されてないわよ！")

    current_password = LOGINPASSWORD

    try:
        # 日付文字列をパース
        start_dt_utc = datetime.datetime.strptime(start_date_str, '%Y-%m-%d').replace(tzinfo=datetime.timezone.utc)
        end_dt_utc = datetime.datetime.strptime(end_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59, tzinfo=datetime.timezone.utc)

        print(f"指定された取得期間: {start_dt_utc.isoformat()} から {end_dt_utc.isoformat()} まで。")

    except Exception as e:
        print(f"日付パース中にエラーが発生したわ: {e}", exc_info=True)
        raise ValueError(f"不正な日付形式よ！YYYY-MM-DD形式でstart_dateとend_dateを指定しなさい: {str(e)}")

    all_sharepoint_items = []
    
    # SharePointクエリパラメータ（mrtApprovedDate をフィルター）
    query_params_base = {
        "$filter": f"mrtApprovedDate ge datetime'{start_dt_utc.strftime('%Y-%m-%dT%H:%M:%SZ')}' and mrtApprovedDate le datetime'{end_dt_utc.strftime('%Y-%m-%dT%H:%M:%SZ')}'",
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
        next_link = json_data.get('odata.nextLink', json_data.get('__next')) # ページネーションリンク

    if not all_sharepoint_items:
        print(f"指定された期間 ({start_date_str} - {end_date_str}) で新しいデータが見つかりませんでした。")
        return None # データがない場合はNoneを返す

    # データの構造化と処理
    reports_to_save = []

    for sp_raw_item in all_sharepoint_items:
        try:
            processed_item = {}

            # 1. 基本フィールドの抽出
            processed_item[KEY_MAP["Title"]] = sp_raw_item.get(FIELD_TITLE, 'N/A')
            processed_item[KEY_MAP["source_sharepoint_file_id"]] = str(sp_raw_item.get(FIELD_ID, 'N/A'))
            processed_item[KEY_MAP["TripRep_Date"]] = parse_visit_date(sp_raw_item.get(FIELD_APPROVED_DATE, ''))
            processed_item[KEY_MAP["URL"]] = f"{SITE_URL}/Lists/For%20Global/DispForm.aspx?ID={processed_item[KEY_MAP['source_sharepoint_file_id']]}"
            processed_item[KEY_MAP["source_sharepoint_filename"]] = sp_raw_item.get(FIELD_FILE_REF, f"SharePoint_Item_{processed_item[KEY_MAP['source_sharepoint_file_id']]}.txt")

            # SharePointの本文HTMLフィールド mrtBody からテキストを抽出 (これが「詳細」の全文)
            extracted_body_text = extract_text_from_html(sp_raw_item.get(FIELD_BODY, ''))
            processed_item[KEY_MAP["TripRep_Detail"]] = extracted_body_text

            # 2. 特定セクションの抽出 (概要)
            sections = extract_sections(sp_raw_item.get(FIELD_BODY, ''))
            processed_item[KEY_MAP["TripRep_Summary"]] = sections.get(TRIP_REP_SUMMARY, 'N/A')
            
            # 得意先参加者、村田同行者はSharePointのフィールドから直接取得
            processed_item[KEY_MAP["TripRep_Customer"]] = sp_raw_item.get(FIELD_CUSTOMER_PARTICIPANT, 'N/A')
            processed_item[KEY_MAP["TripRep_Murata"]] = sp_raw_item.get(FIELD_MURATA_PARTICIPANT, 'N/A')
            
            # 3. 「詳細要約」をBedrockで生成
            summary_text = summarize_text_with_bedrock(processed_item[KEY_MAP["TripRep_Detail"]])
            if not summary_text:
                print(f"警告: レポート '{processed_item[KEY_MAP['Title']]}' の詳細要約生成に失敗したためスキップするわ。")
                continue
            processed_item[KEY_MAP["TripRep_DetailSummary"]] = summary_text

            # 4. 埋め込みベクトル生成 (2種類)
            full_embedding_text = (
                f"タイトル: {processed_item[KEY_MAP['Title']]}\n"
                f"概要: {processed_item[KEY_MAP['TripRep_Summary']]}\n"
                f"詳細: {processed_item[KEY_MAP['TripRep_Detail']]}"
            )
            processed_item[KEY_MAP['full_vector']] = get_embedding_from_bedrock(full_embedding_text)
            if processed_item[KEY_MAP['full_vector']] is None:
                print(f"警告: レポート '{processed_item[KEY_MAP['Title']]}' の全文ベクトル生成に失敗したため、このレポートはスキップするわ。")
                continue

            summary_embedding_text = (
                f"タイトル: {processed_item[KEY_MAP['Title']]}\n"
                f"概要: {processed_item[KEY_MAP['TripRep_Summary']]}\n"
                f"詳細要約: {processed_item[KEY_MAP['TripRep_DetailSummary']]}"
            )
            processed_item[KEY_MAP['summary_vector']] = get_embedding_from_bedrock(summary_embedding_text)
            if processed_item[KEY_MAP['summary_vector']] is None:
                print(f"警告: レポート '{processed_item[KEY_MAP['Title']]}' の全文要約ベクトル生成に失敗したため、このレポートはスキップするわ。")
                continue
            
            reports_to_save.append(processed_item)

        except Exception as e:
            print(f"SharePointアイテム '{sp_raw_item.get('Title', 'N/A')}' の処理中にエラーが発生したわ: {e}")
            print(traceback.format_exc())
            continue

    if not reports_to_save:
        print(f"指定された期間 ({start_date_str} - {end_date_str}) で処理すべきレポートがなかったわ。")
        return None

    # ローカルの出力ディレクトリを作成
    os.makedirs(output_dir, exist_ok=True)
    # ファイル名に日付範囲を含めて分かりやすくする
    local_output_filename = os.path.join(output_dir, f"{start_dt_utc.strftime('%Y-%m-%d')}_to_{end_dt_utc.strftime('%Y-%m-%d')}_reports.json")
    
    try:
        with open(local_output_filename, 'w', encoding='utf-8') as f:
            json.dump(reports_to_save, f, ensure_ascii=False, indent=2)
        print(f"全ての処理済みレポートをローカルファイル'{local_output_filename}'に保存したわ！")
        return local_output_filename # 保存されたファイルパスを返す
    except Exception as e:
        print(f"ローカルファイルへの保存中にエラーが発生したわ: {e}")
        raise # エラー発生時は処理を中断する

# --- スクリプトのエントリポイント ---
if __name__ == "__main__":
    # コマンドライン引数から開始日と終了日を取得
    # 例: python SharepointHistoricalDataDownloader.py 2023-01-01 2023-01-31
    import sys
    if len(sys.argv) != 3:
        print("使い方： python SharepointHistoricalDataDownloader.py <開始日 YYYY-MM-DD> <終了日 YYYY-MM-DD>")
        sys.exit(1)
    
    start_date = sys.argv[1]
    end_date = sys.argv[2]
    
    try:
        downloaded_file_path = download_and_process_sharepoint_data(start_date, end_date)
        if downloaded_file_path:
            print(f"S3にアップロードするJSONファイルのパス: {downloaded_file_path}")
            print(f"このファイルを '{os.environ.get('BUCKET_NAME')}/processed_historical_reports/' に手動でアップロードしなさい！")
        else:
            print("処理されたデータがなかったので、ファイルは保存されなかったわ。")
    except Exception as e:
        print(f"処理中にエラーが発生したわ: {e}")
        sys.exit(1)