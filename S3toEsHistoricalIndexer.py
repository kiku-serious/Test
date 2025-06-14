import json
import os
import traceback
from elasticsearch import Elasticsearch, ConnectionError
import boto3

# --- 環境変数の設定 ---
# これらの環境変数はLambdaの環境変数として設定される
ELASTICSEARCH_HOST = os.environ.get("ELASTICSEARCH_HOST") # Elasticsearchのエンドポイント (必須)
ELASTICSEARCH_INDEX_NAME = os.environ.get("ELASTICSEARCH_INDEX_NAME") # Elasticsearchのインデックス名 (必須)
S3_BUCKET_NAME = os.environ.get("S3_BUCKET_NAME") # S3バケット名 (必須)
S3_INPUT_PREFIX = os.environ.get("S3_INPUT_PREFIX", "processed_historical_reports/") # 処理対象S3ファイルのプレフィックス (必須)
AWS_REGION = os.environ.get("AWS_REGION", "ap-northeast-1") # S3クライアント初期化用リージョン

# --- AWSクライアントの初期化 ---
s3_client = boto3.client('s3', region_name=AWS_REGION)

# --- Elasticsearchのクライアント取得ヘルパー関数 ---
def get_elasticsearch_client():
    if not ELASTICSEARCH_HOST:
        raise ValueError("ELASTICSEARCH_HOST環境変数が設定されてないわよ！")
    
    es_client_instance = Elasticsearch(hosts=[ELASTICSEARCH_HOST])
    if not es_client_instance.ping():
        raise ConnectionError(f"Elasticsearchホスト {ELASTICSEARCH_HOST} への接続に失敗したわ！")
    return es_client_instance

# --- S3からJSONファイルをリストアップする関数 (あんたの提供コードを統合) ---
def list_json_files():
    if not S3_BUCKET_NAME:
        raise ValueError("S3_BUCKET_NAME環境変数が設定されてないわよ！")

    # input_prefix は環境変数 S3_INPUT_PREFIX から取得
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

    # ファイル名 (Key) だけを抽出し、.json で終わるものに絞る
    # list_objects_v2 が返すのはオブジェクト全体の情報 (辞書) なので、obj['Key'] を使う
    json_keys = [obj['Key'] for obj in files if obj['Key'].endswith('.json')]
    return json_keys


# --- Elasticsearchへのインデックス関数 ---
def index_data_to_elasticsearch(es_client, report_data: dict):
    if not ELASTICSEARCH_INDEX_NAME:
        raise ValueError("ELASTICSEARCH_INDEX_NAME環境変数が設定されてないわよ！")

    try:
        document_id = report_data['source_sharepoint_file_id']
        
        if report_data.get("全文ベクトル") is None:
            print(f"警告: レポート '{report_data.get('タイトル', 'N/A')}' の '全文ベクトル' がないわ。インデックスをスキップするわよ。")
            return False
        if report_data.get("全文要約ベクトル") is None:
            print(f"警告: レポート '{report_data.get('タイトル', 'N/A')}' の '全文要約ベクトル' がないわ。インデックスをスキップするわよ。")
            return False
        
        doc = {
            "タイトル": report_data.get('タイトル'),
            "訪問日": report_data.get('訪問日'),
            "得意先参加者": report_data.get('得意先参加者'),
            "村田同行者": report_data.get('村田同行者'),
            "概要": report_data.get('概要'),
            "詳細": report_data.get('詳細'),
            "詳細要約": report_data.get('詳細要約'), 
            "全文ベクトル": report_data['全文ベクトル'], 
            "全文要約ベクトル": report_data['全文要約ベクトル'], 
            "URL": report_data.get('URL'),
            "source_sharepoint_file_id": report_data['source_sharepoint_file_id'],
            "source_sharepoint_filename": report_data.get('source_sharepoint_filename')
        }
        
        response = es_client.index(index=ELASTICSEARCH_INDEX_NAME, id=document_id, body=doc)
        print(f"Elasticsearchにストアしたわ！ Document ID: {document_id}. Status: {response['result']}")
        return True
    except Exception as e:
        print(f"Elasticsearchへのインデックス中にエラーが発生したわ: {e}", exc_info=True)
        return False

# --- メインのLambdaハンドラー関数 ---
def lambda_handler(event, context):
    print("Lambda関数が実行されたわ。")
    
    # 環境変数の必須チェック
    required_envs = ['ELASTICSEARCH_HOST', 'ELASTICSEARCH_INDEX_NAME', 'S3_BUCKET_NAME', 'S3_INPUT_PREFIX']
    for env_var in required_envs:
        if not os.environ.get(env_var):
            raise ValueError(f"必須環境変数 '{env_var}' が設定されてないわよ！")

    print(f"S3バケット '{S3_BUCKET_NAME}' のプレフィックス '{S3_INPUT_PREFIX}' からJSONファイルをリストするわ。")
    
    all_json_keys = []
    
    try:
        # あんたの list_json_files() 関数を使ってS3オブジェクトキーを取得
        all_json_keys = list_json_files()
        
        if not all_json_keys:
            print(f"S3バケット '{S3_BUCKET_NAME}' のプレフィックス '{S3_INPUT_PREFIX}' にJSONファイルが見つからなかったわ。")
            return {
                "statusCode": 200,
                "body": json.dumps("インデックスすべきJSONファイルがS3に見つからなかったわ。")
            }

        print(f"合計 {len(all_json_keys)} 個のJSONファイルが見つかったわ。")
        
        es_client = get_elasticsearch_client()
        total_reports_indexed = 0
        total_files_processed = 0

        for s3_key in all_json_keys:
            print(f"S3オブジェクト '{s3_key}' を読み込み中よ。")
            try:
                response = s3_client.get_object(Bucket=S3_BUCKET_NAME, Key=s3_key)
                file_content = response['Body'].read().decode('utf-8')
                reports_in_file = json.loads(file_content)

                if not isinstance(reports_in_file, list):
                    print(f"警告: ファイル '{s3_key}' はJSONリスト形式じゃないみたい。スキップするわ。")
                    continue
                
                if not reports_in_file:
                    print(f"ファイル '{s3_key}' に処理すべきレポートが見つからなかったわ。")
                    continue

                successful_indexes_in_file = 0
                for report in reports_in_file:
                    if index_data_to_elasticsearch(es_client, report):
                        successful_indexes_in_file += 1
                
                total_reports_indexed += successful_indexes_in_file
                total_files_processed += 1
                print(f"ファイル '{s3_key}' から {successful_indexes_in_file} 件のレポートをインデックスしたわ。")

            except json.JSONDecodeError as e:
                print(f"エラー: ファイル '{s3_key}' のJSON解析に失敗したわ: {e}")
                traceback.print_exc()
                continue 
            except Exception as e:
                print(f"ファイル '{s3_key}' の処理中に予期せぬエラーが発生したわ: {e}")
                traceback.print_exc()
                continue 

        print(f"全ての処理が完了したわ。合計 {total_files_processed} 個のファイルから {total_reports_indexed} 件のレポートをElasticsearchにインデックスしたわ。")
        
        return {
            "statusCode": 200,
            "body": json.dumps(f"S3の全過去データインデックスが完了したわ！合計 {total_reports_indexed} 件インデックス済み。")
        }

    except Exception as e:
        print(f"S3からのファイルリストまたは処理中に致命的なエラーが発生したわ: {e}")
        print(traceback.format_exc())
        return {
            "statusCode": 500,
            "body": json.dumps(f"処理中にエラーが発生したわ: {str(e)}")
        }