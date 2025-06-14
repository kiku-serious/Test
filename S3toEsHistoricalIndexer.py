import json
import os
import traceback
from elasticsearch import Elasticsearch, ConnectionError

# --- 環境変数の設定 ---
# これらの環境変数は、ローカルPCで実行する前に設定すること！
# 例: export ELASTICSEARCH_HOST="your-onprem-elasticsearch-ip"
ELASTICSEARCH_HOST = os.environ.get("ELASTICSEARCH_HOST") # Elasticsearchのエンドポイント (必須)
ELASTICSEARCH_INDEX_NAME = os.environ.get("ELASTICSEARCH_INDEX_NAME") # Elasticsearchのインデックス名 (必須)
AWS_REGION = os.environ.get("AWS_REGION", "ap-northeast-1") # AWS認証情報取得用（boto3用）

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
        
        # S3toEsHistoricalIndexer.py で整形された形式をそのまま利用
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
def index_local_directory_to_elasticsearch(local_directory_path: str):
    print(f"ローカルディレクトリ '{local_directory_path}' 内のデータをElasticsearchにインデックスするわ。")

    # 環境変数の必須チェック
    required_envs = ['ELASTICSEARCH_HOST', 'ELASTICSEARCH_INDEX_NAME']
    for env_var in required_envs:
        if not os.environ.get(env_var):
            raise ValueError(f"必須環境変数 '{env_var}' が設定されてないわよ！")

    if not os.path.isdir(local_directory_path):
        raise FileNotFoundError(f"ディレクトリ '{local_directory_path}' が見つからないか、ディレクトリじゃないわよ！")

    es_client = get_elasticsearch_client()
    total_indexed_files = 0
    total_indexed_reports = 0

    try:
        # ディレクトリ内の全てのファイルとフォルダをリスト
        for filename in os.listdir(local_directory_path):
            if filename.endswith('.json'): # .jsonで終わるファイルだけを対象にする
                file_path = os.path.join(local_directory_path, filename)
                print(f"ファイル '{file_path}' を読み込み中よ。")

                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        reports_from_file = json.load(f)

                    if not isinstance(reports_from_file, list):
                        print(f"警告: ファイル '{file_path}' はJSONリスト形式じゃないみたい。スキップするわ。")
                        continue
                    
                    if not reports_from_file:
                        print(f"ファイル '{file_path}' に処理すべきレポートが見つからなかったわ。")
                        continue

                    successful_indexes_in_file = 0
                    for report in reports_from_file:
                        if index_data_to_elasticsearch(es_client, report):
                            successful_indexes_in_file += 1
                        
                    total_indexed_reports += successful_indexes_in_file
                    total_indexed_files += 1
                    print(f"ファイル '{file_path}' から {successful_indexes_in_file} 件のレポートをインデックスしたわ。")

                except json.JSONDecodeError as e:
                    print(f"エラー: ファイル '{file_path}' のJSON解析に失敗したわ: {e}")
                    traceback.print_exc()
                    continue # 次のファイルへ
                except Exception as e:
                    print(f"ファイル '{file_path}' の処理中に予期せぬエラーが発生したわ: {e}")
                    traceback.print_exc()
                    continue # 次のファイルへ

        if total_indexed_files == 0:
            print("指定されたディレクトリにインデックスすべきJSONファイルが見つからなかったわ。")
        else:
            print(f"全ての処理が完了したわ。合計 {total_indexed_files} 個のファイルから {total_indexed_reports} 件のレポートをElasticsearchにインデックスしたわ。")

    except Exception as e:
        print(f"メイン処理中に致命的なエラーが発生したわ: {e}")
        traceback.print_exc()
        raise # エラー発生時は処理を中断する

# --- スクリプトのエントリポイント ---
if __name__ == "__main__":
    # コマンドライン引数からローカルディレクトリのパスを取得
    # 例: python S3toEsHistoricalIndexer.py processed_sharepoint_reports/
    import sys
    if len(sys.argv) != 2:
        print("使い方： python S3toEsHistoricalIndexer.py <ローカル_JSONディレクトリパス>")
        sys.exit(1)
    
    local_directory_path = sys.argv[1]
    
    try:
        index_local_directory_to_elasticsearch(local_directory_path)
    except Exception as e:
        print(f"Elasticsearchへのインデックス中にエラーが発生したわ: {e}")
        sys.exit(1)