import json
import boto3
import os
import traceback
from elasticsearch import Elasticsearch, ConnectionError

# --- 環境変数の設定 ---
# これらの環境変数はFargateタスクの定義で設定されるか、タスク起動時に渡される
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

# --- Elasticsearchへのインデックス関数（既存コードから流用・調整） ---
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
        
        # Elasticsearchマッピングに合わせた doc を構築 (KEY_MAPはここでは不要、前のLambdaで適用済み)
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

# --- メイン処理関数 (Fargateタスクのエントリポイントになる) ---
def process_s3_object_and_index(s3_key: str):
    print(f"S3からオブジェクト '{s3_key}' を読み込み中よ。")

    # 環境変数の必須チェック
    required_envs = ['ELASTICSEARCH_HOST', 'ELASTICSEARCH_INDEX_NAME', 'S3_BUCKET_NAME']
    for env_var in required_envs:
        if not os.environ.get(env_var):
            raise ValueError(f"必須環境変数 '{env_var}' が設定されてないわよ！")

    try:
        # S3からJSONファイルを読み込む
        response = s3_client.get_object(Bucket=S3_BUCKET_NAME, Key=s3_key)
        file_content = response['Body'].read().decode('utf-8')
        reports_from_s3 = json.loads(file_content)

        if not reports_from_s3:
            print(f"S3オブジェクト '{s3_key}' に処理すべきレポートが見つからなかったわ。")
            return {
                "status": "SUCCESS",
                "message": "処理すべきレポートがなかったわ。"
            }

        # Elasticsearchクライアントを取得
        es_client = get_elasticsearch_client()

        # Elasticsearchにインデックス
        successful_indexes = 0
        for report in reports_from_s3:
            if index_data_to_elasticsearch(es_client, report):
                successful_indexes += 1
            
        if successful_indexes == len(reports_from_s3):
            print(f"S3オブジェクト '{s3_key}' の全ての{successful_indexes}件のレポートをElasticsearchにインデックスしたわ。")
        else:
            print(f"警告: S3オブジェクト '{s3_key}' の{len(reports_from_s3)}件中{successful_indexes}件のレポートしかElasticsearchにインデックスできなかったわ。")
            raise Exception("一部のレポートのElasticsearchへのインデックスに失敗したわ。")
                
        print("全ての処理が完了したわ。")
        return {
            "status": "SUCCESS",
            "message": f"S3オブジェクト '{s3_key}' の過去データインデックスが完了したわ！"
        }

    except Exception as e:
        print(f"Fargateタスクの実行中に致命的なエラーが発生したわ: {e}")
        print(traceback.format_exc())
        raise # Fargateタスクは失敗したらエラーを投げる

# --- スクリプトのエントリポイント ---
if __name__ == "__main__":
    # このスクリプトはStep FunctionsからFargateタスクとして起動されることを想定
    # Step Functionsは 'taskOverrides' で環境変数やコマンド引数を渡せる
    # ここでは、環境変数 'S3_OBJECT_KEY' から処理対象のS3キーを取得する
    s3_object_key_from_env = os.environ.get('S3_OBJECT_KEY')
    
    if not s3_object_key_from_env:
        print("エラー: 環境変数 'S3_OBJECT_KEY' が設定されてないわよ！")
        exit(1) # エラー終了

    try:
        process_s3_object_and_index(s3_object_key_from_env)
    except Exception as e:
        print(f"Fargateタスクのメイン処理中にエラーが発生したわ: {e}")
        exit(1) # エラー終了