承知いたしました。Elasticsearchへのインデックス処理は行わず、単に接続確認（ping）だけを行うPythonスクリプトのサンプルコードを提示します。

---

## 4.3. Python スクリプトの準備 (Ping 確認のみ)

S3 から JSON データを読み込む処理はそのまま残しますが、Elasticsearch へのインデックス処理は行わず、接続（ping）確認のみを行う Python スクリプトを作成します。

`check_es_connection.py`:

```python
import os
import json
import boto3
from elasticsearch import Elasticsearch, ConnectionError, TransportError
import time

# 環境変数から設定を取得
S3_BUCKET = os.environ.get('S3_BUCKET')
S3_KEY = os.environ.get('S3_KEY') # S3 オブジェクトのパス (今回は使用しないが、Batchジョブ定義の互換性のため残す)
ES_HOST = os.environ.get('ES_HOST') # オンプレミス Elasticsearch の IP アドレスまたはホスト名
ES_PORT = int(os.environ.get('ES_PORT', 9200)) # Elasticsearch のポート
ES_USERNAME = os.environ.get('ES_USERNAME') # Elasticsearch 認証ユーザー名 (Optional)
ES_PASSWORD = os.environ.get('ES_PASSWORD') # Elasticsearch 認証パスワード (Optional)
ES_VERIFY_CERTS = os.environ.get('ES_VERIFY_CERTS', 'false').lower() == 'true' # HTTPS 証明書検証 (Optional, デフォルトはfalse)
ES_USE_SSL = os.environ.get('ES_USE_SSL', 'false').lower() == 'true' # SSL を明示的に使用するかどうか

# Elasticsearch クライアントの初期化
auth_args = {}
if ES_USERNAME and ES_PASSWORD:
    auth_args['basic_auth'] = (ES_USERNAME, ES_PASSWORD)

es = Elasticsearch(
    hosts=[{'host': ES_HOST, 'port': ES_PORT}],
    use_ssl=ES_USE_SSL, # 環境変数 ES_USE_SSL に従う
    verify_certs=ES_VERIFY_CERTS,
    **auth_args
)

s3 = boto3.client('s3')

def check_es_connection():
    if not ES_HOST or not ES_PORT:
        print("エラー: ES_HOST または ES_PORT 環境変数が設定されていません。")
        raise ValueError("必須の環境変数が不足しています。")

    print(f"Elasticsearch {ES_HOST}:{ES_PORT} への接続を試行中...")
    try:
        if es.ping():
            print(f"Elasticsearch {ES_HOST}:{ES_PORT} への接続に成功しました！")
            # S3からデータを読み込む処理（今回はping確認が主なので、読み込んだデータを活用しない）
            if S3_BUCKET and S3_KEY:
                print(f"S3 からデータを取得中 (確認のみ): s3://{S3_BUCKET}/{S3_KEY}")
                try:
                    obj = s3.get_object(Bucket=S3_BUCKET, Key=S3_KEY)
                    # データを実際に処理する必要がないため、読み込んだ後は特に何もしない
                    _ = obj['Body'].read().decode('utf-8')
                    print("S3 からのデータ読み込みに成功しました。")
                except Exception as e:
                    print(f"S3 からのデータ読み込み中にエラーが発生しました: {e}")
                    raise
            else:
                print("S3_BUCKET または S3_KEY が設定されていないため、S3 の読み込みはスキップされます。")

        else:
            print(f"エラー: Elasticsearch {ES_HOST}:{ES_PORT} への接続 (ping) に失敗しました。")
            raise ConnectionError("Elasticsearch ping failed.")

    except ConnectionError as e:
        print(f"Elasticsearch への接続エラー: {e}")
        raise
    except Exception as e:
        print(f"予期せぬエラーが発生しました: {e}")
        raise

if __name__ == '__main__':
    try:
        check_es_connection()
        print("スクリプトが正常に完了しました。")
    except Exception as e:
        print(f"スクリプト実行中にエラーが発生しました: {e}")
        exit(1)

```

`requirements.txt`:

```
boto3
elasticsearch==8.4.3
```

`Dockerfile`:

```dockerfile
# AWS 公式の Python 3.12 イメージを使用
FROM public.ecr.aws/python/python:3.12-slim-bullseye

WORKDIR /app

# 依存関係のインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションコードのコピー
COPY check_es_connection.py .

# コンテナ起動時に実行されるコマンド
CMD ["python", "check_es_connection.py"]
```

---

### このコードのポイント

* **`es.ping()` の使用**: Elasticsearch クライアントの `ping()` メソッドは、指定されたホストに接続し、Elasticsearch クラスターが応答しているかどうかを確認します。これは認証を含む基本的な接続テストに非常に有効です。
* **インデックス処理の削除**: `es.index()` や関連するデータ処理ロジックは全て削除されています。
* **S3 読み込み処理の残存**: `S3_BUCKET` と `S3_KEY` 環境変数は引き続き Batch ジョブ定義で設定しますが、スクリプト内では S3 からのデータ読み込み自体は行いますが、そのデータを Elasticsearch に送ることはありません。これにより、S3 へのアクセス権限も同時に確認できます。
* **エラーハンドリング**: 接続に失敗した場合やその他のエラーが発生した場合に、適切なメッセージを出力し、スクリプトがエラー終了するように `exit(1)` を使用しています。

このスクリプトを使えば、実際にデータを投入することなく、AWS Batch とオンプレミス Elasticsearch 間の基本的な接続性と権限設定が正しく機能しているかを確認できます。
