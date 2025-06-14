import json
import os
import traceback
from elasticsearch import Elasticsearch, ConnectionError
import boto3

# --- 環境変数の設定 ---
# これらの環境変数はLambdaの環境変数として設定される
ELASTICSEARCH_HOST = os.environ.get("ELASTICSEARCH_HOST") # Elasticsearchのエンドポイント (必須)
ELASTICSEARCH_INDEX_NAME = os.environ.get("ELASTICSEARCH_INDEX_NAME") # Elasticsearchのインデックス名 (必須)
S3_BUCKET_NAME = os.environ.get("BUCKET_NAME") # S3バケット名 (必須)
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
    required_envs = ['ELASTICSEARCH_HOST', 'ELASTICSEARCH_INDEX_NAME', 'S3_BUCKET_NAME']
    for env_var in required_envs:
        if not os.environ.get(env_var):
            raise ValueError(f"必須環境変数 '{env_var}' が設定されてないわよ！")

    s3_key = None
    # S3イベントトリガーの場合、event['Records']からs3_keyを取得
    if 'Records' in event: 
        for record in event['Records']:
            if 's3' in record:
                s3_key = record['s3']['object']['key']
                break
    elif 's3_key' in event: # Step Functionsから直接keyが渡された場合
        s3_key = event['s3_key']

    if not s3_key:
        raise ValueError("S3オブジェクトキーがイベントまたはペイロードで指定されてないわよ！")
    
    print(f"S3からオブジェクト '{s3_key}' を読み込み中よ。")

    try:
        response = s3_client.get_object(Bucket=S3_BUCKET_NAME, Key=s3_key)
        file_content = response['Body'].read().decode('utf-8')
        reports_from_s3 = json.loads(file_content)

        if not reports_from_s3:
            print(f"S3オブジェクト '{s3_key}' に処理すべきレポートが見つからなかったわ。")
            return {
                "statusCode": 200,
                "body": json.dumps("処理すべきレポートがなかったわ。")
            }

        es_client = get_elasticsearch_client()

        successful_indexes = 0
        for report in reports_from_s3:
            if index_data_to_elasticsearch(es_client, report):
                successful_indexes += 1
            
        if successful_indexes == len(reports_from_s3):
            print(f"S3オブジェクト '{s3_key}' の全ての{successful_indexes}件のレポートをElasticsearchにインデックスしたわ。")
        else:
            print(f"警告: S3オブジェクト '{s3_key}' の{len(reports_from_s3)}件中{successful_indexes}件のレポートしかElasticsearchにインデックスできなかったわ。")
            # 部分的な失敗でも、Lambdaは成功とみなすか、エラーとするか、ポリシーによる
            # 今回はエラーとして再試行を促す
            raise Exception("一部のレポートのElasticsearchへのインデックスに失敗したわ。")
                
        print("全ての処理が完了したわ。")
        return {
            "statusCode": 200,
            "body": json.dumps(f"S3オブジェクト '{s3_key}' の過去データインデックスが完了したわ！")
        }

    except Exception as e:
        print(f"Lambda関数の実行中に致命的なエラーが発生したわ: {e}")
        print(traceback.format_exc())
        return {
            "statusCode": 500,
            "body": json.dumps(f"Lambda関数の実行中にエラーが発生したわ: {str(e)}")
        }