import json
import os
import traceback
from elasticsearch import Elasticsearch, ConnectionError
import boto3

# --- 環境変数の設定 ---
# これらの環境変数はAWS Batchジョブ定義で設定される
ELASTICSEARCH_HOST = os.environ.get("ELASTICSEARCH_HOST") # Elasticsearchのエンドポイント (必須)
ELASTICSEARCH_INDEX_NAME = os.environ.get("ELASTICSEARCH_INDEX_NAME") # Elasticsearchのインデックス名 (必須)
S3_BUCKET_NAME = os.environ.get("S3_BUCKET_NAME") # S3バケット名 (必須)
S3_INPUT_PREFIX = os.environ.get("S3_INPUT_PREFIX", "raw_sharepoint_reports_daily/") # 処理対象S3ファイルのプレフィックス (必須)

# Bedrockモデル情報 (要約・埋め込み生成に使う)
BEDROCK_SUMMARY_MODEL_ID = os.environ.get("BEDROCK_SUMMARY_MODEL_ID", "anthropic.claude-instant-v1")
BEDROCK_EMBEDDING_MODEL_ID = os.environ.get("BEDROCK_EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v1")
AWS_REGION = os.environ.get("AWS_REGION", "ap-northeast-1")

# 埋め込みベクトルの次元数
EMBEDDING_DIMS = 1536 

# --- AWSクライアントの初期化 ---
s3_client = boto3.client('s3', region_name=AWS_REGION)
bedrock_runtime = boto3.client(
    service_name = "bedrock-runtime",
    region_name = AWS_REGION
)

# --- Elasticsearchのクライアント取得ヘルパー関数 ---
def get_elasticsearch_client():
    if not ELASTICSEARCH_HOST:
        raise ValueError("ELASTICSEARCH_HOST環境変数が設定されてないわよ！")
    
    es_client_instance = Elasticsearch(hosts=[ELASTICSEARCH_HOST])
    if not es_client_instance.ping():
        raise ConnectionError(f"Elasticsearchホスト {ELASTICSEARCH_HOST} への接続に失敗したわ！")
    return es_client_instance

# --- ヘルパー関数 (要約・埋め込み・抽出) ---
# これらの関数は SharepointDataExtractor.py からコピーしたもの。
# 依存するライブラリもrequirements.txtにちゃんと含めること！
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

def extract_text_from_html(html):
    from bs4 import BeautifulSoup # ローカルでインポート
    soup = BeautifulSoup(html, 'html.parser')
    for script in soup(["script", "style"]):
        script.extract()
    text = soup.get_text()
    text = text.replace('\u200b', ' ').replace('\u3000', ' ').replace('\xa0', ' ')
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return " ".join(lines)

def extract_sections(body_text_html):
    from bs4 import BeautifulSoup
    import re # ローカルでインポート
    sections = {}
    summary_match = re.search(r'概要：\s*(.*?)(?:<br/>|\n|$)詳細：', body_text_html, re.DOTALL)
    if summary_match:
        sections['概要'] = summary_match.group(1).strip()
    else:
        sections['概要'] = "N/A"
        print("警告: 概要セクションを抽出できませんでした。")
    detail_match = re.search(r'詳細：\s*(.*?)(?:<br/>|\n|$)所感：', body_text_html, re.DOTALL)
    if detail_match:
        sections['詳細'] = detail_match.group(1).strip()
    else:
        sections['詳細'] = "N/A"
        print("警告: 詳細セクションを抽出できませんでした。")
    comment_match = re.search(r'所感：\s*(.*)', body_text_html, re.DOTALL)
    if comment_match:
        sections['所感'] = comment_match.group(1).strip()
    else:
        sections['所感'] = "N/A"
        print("警告: 所感セクションを抽出できませんでした。")
    return sections

# --- Elasticsearchへのインデックス関数 ---
# これは前のコードと同じ

# --- S3からJSONファイルをリストアップする関数 (あんたの提供コードを統合) ---
def list_json_files_from_s3():
    if not S3_BUCKET_NAME:
        raise ValueError("S3_BUCKET_NAME環境変数が設定されてないわよ！")

    input_prefix = S3_INPUT_PREFIX
    
    files = []
    continuation_token = None

    while True:
        if continuation_token:
            response = s3_client.list_objects_v2(
                Bucket=S3_BUCKET_NAME,
                Prefix=input_prefix,
                ContinuationToken=continuation_token
            )
        else:
            response = s3_client.list_objects_v2(
                Bucket=S3_BUCKET_NAME,
                Prefix=input_prefix,
            )
        
        if 'Contents' in response:
            files.extend(response['Contents'])
        
        if 'NextContinuationToken' in response:
            continuation_token = response['NextContinuationToken']
        else:
            break

    json_keys = [obj['Key'] for obj in files if obj['Key'].endswith('.json')]
    return json_keys

# --- メイン処理関数 (AWS Batchジョブのエントリポイントになる) ---
def process_s3_data_and_index_es(): # S3キーは環境変数から取得、引数では受け取らない
    print(f"S3バケット '{S3_BUCKET_NAME}' のプレフィックス '{S3_INPUT_PREFIX}' からJSONファイルをリストし、処理を開始するわ。")

    # 環境変数の必須チェック
    required_envs = ['ELASTICSEARCH_HOST', 'ELASTICSEARCH_INDEX_NAME', 'S3_BUCKET_NAME', 'S3_INPUT_PREFIX', 
                     'BEDROCK_EMBEDDING_MODEL_ID', 'BEDROCK_SUMMARY_MODEL_ID', 'AWS_REGION']
    for env_var in required_envs:
        if not os.environ.get(env_var):
            raise ValueError(f"必須環境変数 '{env_var}' が設定されてないわよ！")

    all_json_keys = []
    
    try:
        all_json_keys = list_json_files_from_s3()
        
        if not all_json_keys:
            print(f"S3バケット '{S3_BUCKET_NAME}' のプレフィックス '{S3_INPUT_PREFIX}' にJSONファイルが見つからなかったわ。")
            return {
                "status": "SUCCESS",
                "message": "インデックスすべきJSONファイルがS3に見つからなかったわ。"
            }

        print(f"合計 {len(all_json_keys)} 個のJSONファイルが見つかったわ。処理を開始するわよ。")
        
        es_client = get_elasticsearch_client()
        total_reports_indexed = 0
        total_files_processed = 0

        for s3_key in all_json_keys:
            print(f"S3オブジェクト '{s3_key}' を読み込み中よ。")
            try:
                response = s3_client.get_object(Bucket=S3_BUCKET_NAME, Key=s3_key)
                file_content = response['Body'].read().decode('utf-8')
                raw_reports_in_file = json.loads(file_content) # Rawデータを読み込む

                if not isinstance(raw_reports_in_file, list):
                    print(f"警告: ファイル '{s3_key}' はJSONリスト形式じゃないみたい。スキップするわ。")
                    continue
                
                if not raw_reports_in_file:
                    print(f"ファイル '{s3_key}' に処理すべきレポートが見つからなかったわ。")
                    continue

                successful_indexes_in_file = 0
                for sp_raw_item in raw_reports_in_file: # Rawデータを一つずつ処理
                    try:
                        processed_item = {}

                        # 1. 基本フィールドの抽出 (Raw JSONから取得)
                        processed_item['Title'] = sp_raw_item.get('Title', 'N/A')
                        processed_item['ID'] = str(sp_raw_item.get('ID', 'N/A'))
                        processed_item['mrtApprovedDate'] = sp_raw_item.get('mrtApprovedDate', '')
                        # URLとFileLeafRefはRawデータに含まれている想定
                        processed_item['URL'] = f"{os.environ.get('SITE_URL', '')}/Lists/For%20Global/DispForm.aspx?ID={processed_item['ID']}" # SITE_URLも環境変数から
                        processed_item['FileLeafRef'] = sp_raw_item.get('FileLeafRef', f"SharePoint_Item_{processed_item['ID']}.txt")

                        # SharePointの本文HTMLフィールド mrtBody からテキストを抽出 (これが「詳細」の全文)
                        extracted_body_text = extract_text_from_html(sp_raw_item.get('mrtBody', ''))
                        processed_item['詳細'] = extracted_body_text 

                        # 2. 概要と詳細要約をBedrockで生成
                        processed_item['概要'] = sp_raw_item.get('mrtSummary', 'N/A') # Raw JSONの既存概要を使用

                        # 「詳細要約」をBedrockで生成
                        summary_text = summarize_text_with_bedrock(processed_item['詳細'])
                        if not summary_text:
                            print(f"警告: レポート '{processed_item['Title']}' の詳細要約生成に失敗したためスキップするわ。")
                            continue
                        processed_item['詳細要約'] = summary_text 

                        # 得意先参加者、村田同行者はRaw JSONのフィールドから直接取得
                        processed_item['得意先参加者'] = sp_raw_item.get('mrtCustomerParticipant', 'N/A')
                        processed_item['村田同行者'] = sp_raw_item.get('mrtMurataParticipant', 'N/A')


                        # 3. 埋め込みベクトル生成 (2種類)
                        full_embedding_text = (
                            f"タイトル: {processed_item['Title']}\n"
                            f"概要: {processed_item['概要']}\n"
                            f"詳細: {processed_item['詳細']}"
                        )
                        processed_item['全文ベクトル'] = get_embedding_from_bedrock(full_embedding_text)
                        if processed_item['全文ベクトル'] is None:
                            print(f"警告: レポート '{processed_item['Title']}' の全文ベクトル生成に失敗したため、このレポートはスキップするわ。")
                            continue

                        summary_embedding_text = (
                            f"タイトル: {processed_item['Title']}\n"
                            f"概要: {processed_item['概要']}\n"
                            f"詳細要約: {processed_item['詳細要約']}"
                        )
                        processed_item['全文要約ベクトル'] = get_embedding_from_bedrock(summary_embedding_text)
                        if processed_item['全文要約ベクトル'] is None:
                            print(f"警告: レポート '{processed_item['Title']}' の全文要約ベクトル生成に失敗したため、このレポートはスキップするわ。")
                            continue
                        
                        # Elasticsearchにインデックス
                        # index_data_to_elasticsearchは最終的なESのキー名に合わせる
                        es_doc = {
                            "タイトル": processed_item.get('Title'),
                            "訪問日": processed_item.get('mrtApprovedDate'), # Raw JSONのフィールド名をそのまま使う
                            "得意先参加者": processed_item.get('得意先参加者'),
                            "村田同行者": processed_item.get('村田同行者'),
                            "概要": processed_item.get('概要'),
                            "詳細": processed_item.get('詳細'),
                            "詳細要約": processed_item.get('詳細要約'), 
                            "全文ベクトル": processed_item['全文ベクトル'], 
                            "全文要約ベクトル": processed_item['全文要約ベクトル'], 
                            "URL": processed_item.get('URL'), 
                            "source_sharepoint_file_id": processed_item['ID'],
                            "source_sharepoint_filename": processed_item.get('FileLeafRef')
                        }
                        
                        if index_data_to_elasticsearch(es_client, es_doc): # 加工済みデータを渡す
                            successful_indexes_in_file += 1

                    except Exception as e:
                        print(f"ファイル '{s3_key}' 内のレポート処理中にエラーが発生したわ: {e}")
                        print(traceback.format_exc())
                        continue # このレポートはスキップし、次のレポートへ
                
                total_reports_indexed += successful_indexes_in_file
                total_files_processed += 1
                print(f"ファイル '{s3_key}' から {successful_indexes_in_file} 件のレポートをインデックスしたわ。")

            except json.JSONDecodeError as e:
                print(f"エラー: ファイル '{s3_key}' のJSON解析に失敗したわ: {e}")
                traceback.print_exc()
                continue 
            except Exception as e:
                print(f"ファイル '{s3_key}' の読み込みまたは処理中に予期せぬエラーが発生したわ: {e}")
                traceback.print_exc()
                continue 

        print(f"全ての処理が完了したわ。合計 {total_files_processed} 個のファイルから {total_reports_indexed} 件のレポートをElasticsearchにインデックスしたわ。")
        
        return {
            "status": "SUCCESS",
            "message": f"S3の全過去データインデックスが完了したわ！合計 {total_reports_indexed} 件インデックス済み。"
        }

    except Exception as e:
        print(f"S3からのファイルリストまたは処理中に致命的なエラーが発生したわ: {e}")
        print(traceback.format_exc())
        raise # エラー発生時はジョブを失敗させる

# --- スクリプトのエントリポイント (AWS Batchジョブとして実行) ---
if __name__ == "__main__":
    # AWS Batchで引数は渡されないが、環境変数を読み込む
    try:
        result = process_s3_data_and_index_es()
        if result and result.get("status") == "SUCCESS":
            print(f"ジョブ成功: {result.get('message')}")
            exit(0)
        else:
            print(f"ジョブ失敗（データなしまたは警告）: {result.get('message')}")
            exit(1)
    except Exception as e:
        print(f"処理中に致命的なエラーが発生し、ジョブが失敗したわ: {e}")
        exit(1)