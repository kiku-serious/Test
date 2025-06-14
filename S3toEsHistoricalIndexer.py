import json
import boto3 # S3は使わないけど、boto3はBedrockで使うので残す可能性あり
import os
import traceback
from elasticsearch import Elasticsearch, ConnectionError

# --- 環境変数の設定 ---
# これらの環境変数は、ローカルPCで実行する前に設定すること！
# 例: export ELASTICSEARCH_HOST="your-onprem-elasticsearch-ip"
ELASTICSEARCH_HOST = os.environ.get("ELASTICSEARCH_HOST") # Elasticsearchのエンドポイント (必須)
ELASTICSEARCH_INDEX_NAME = os.environ.get("ELASTICSEARCH_INDEX_NAME") # Elasticsearchのインデックス名 (必須)
AWS_REGION = os.environ.get("AWS_REGION", "ap-northeast-1") # Bedrockを使うなら必要

# --- AWSクライアントの初期化 (このスクリプトではS3は使わない) ---
# S3クライアントは使わないので削除。Bedrockを使う場合は別途Bedrockクライアントが必要になる。
# 今回のインデクサーはElasticsearchに投入するだけなので、Bedrockは不要。
# s3_client = boto3.client('s3', region_name=AWS_REGION)

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
        
        # S3から読み込んだJSONの形式がElasticsearchのマッピングに合っていることを前提とする
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

# --- メイン処理関数 ---
def index_local_data_to_elasticsearch(local_file_path: str):
    print(f"ローカルファイル '{local_file_path}' のデータをElasticsearchにインデックスするわ。")

    # 環境変数の必須チェック
    required_envs = ['ELASTICSEARCH_HOST', 'ELASTICSEARCH_INDEX_NAME']
    for env_var in required_envs:
        if not os.environ.get(env_var):
            raise ValueError(f"必須環境変数 '{env_var}' が設定されてないわよ！")

    if not os.path.exists(local_file_path):
        raise FileNotFoundError(f"ファイル '{local_file_path}' が見つからないわよ！")

    try:
        # ローカルからJSONファイルを読み込む
        with open(local_file_path, 'r', encoding='utf-8') as f:
            reports_from_file = json.load(f)

        if not reports_from_file:
            print(f"ファイル '{local_file_path}' に処理すべきレポートが見つからなかったわ。")
            return None # データがない場合は処理終了

        es_client = get_elasticsearch_client()

        successful_indexes = 0
        for report in reports_from_file:
            if index_data_to_elasticsearch(es_client, report):
                successful_indexes += 1
            
        if successful_indexes == len(reports_from_file):
            print(f"ファイル '{local_file_path}' の全ての{successful_indexes}件のレポートをElasticsearchにインデックスしたわ。")
        else:
            print(f"警告: ファイル '{local_file_path}' の{len(reports_from_file)}件中{successful_indexes}件のレポートしかElasticsearchにインデックスできなかったわ。")
            raise Exception("一部のレポートのElasticsearchへのインデックスに失敗したわ。")
                
        print("全ての処理が完了したわ。")

    except Exception as e:
        print(f"処理中に致命的なエラーが発生したわ: {e}")
        print(traceback.format_exc())
        raise # エラー発生時は処理を中断する

# --- スクリプトのエントリポイント ---
if __name__ == "__main__":
    # コマンドライン引数からローカルファイルのパスを取得
    # 例: python S3toEsHistoricalIndexer.py processed_sharepoint_reports/2023-01-01_to_2023-01-31_reports.json
    import sys
    if len(sys.argv) != 2:
        print("使い方： python S3toEsHistoricalIndexer.py <ローカル_JSONファイルパス>")
        sys.exit(1)
    
    local_json_file_path = sys.argv[1]
    
    try:
        index_local_data_to_elasticsearch(local_json_file_path)
    except Exception as e:
        print(f"Elasticsearchへのインデックス中にエラーが発生したわ: {e}")
        sys.exit(1)