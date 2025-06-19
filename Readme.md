# AWS Batch を利用した S3 からオンプレミス Elasticsearch へのデータインデックス

AWS Batch を利用して Amazon S3 に保存された JSON データを取得し、オンプレミス環境の Elasticsearch にインデックスするための手順を説明します。


## 目次

1.  [概要](https://www.google.com/search?q=%231-%E6%A6%82%E8%A6%81)
2.  [前提条件](https://www.google.com/search?q=%232-%E5%89%8D%E6%8F%90%E6%9D%A1%E4%BB%B6)
3.  [アーキテクチャ](https://www.google.com/search?q=%233-%E3%82%A2%E3%83%BC%E3%82%AD%E3%83%86%E3%82%AF%E3%83%81%E3%83%A3)
4.  [セットアップ手順](https://www.google.com/search?q=%234-%E3%82%BB%E3%83%83%E3%83%88%E3%82%A2%E3%83%83%E3%83%97%E6%89%8B%E9%A0%86)
      * [4.1. オンプレミス Elasticsearch の準備](https://www.google.com/search?q=%2341-%E3%82%AA%E3%83%B3%E3%83%97%E3%83%AC%E3%83%9F%E3%82%B9-elasticsearch-%E3%81%AE%E6%BA%96%E5%82%99)
      * [4.2. IAM ロールの作成](https://www.google.com/search?q=%2342-iam-%E3%83%AD%E3%83%BC%E3%83%AB%E3%81%AE%E4%BD%9C%E6%88%90)
      * [4.3. Python スクリプトの準備](https://www.google.com/search?q=%2343-python-%E3%82%B9%E3%82%AF%E3%83%AA%E3%83%97%E3%83%88%E3%81%AE%E6%BA%96%E5%82%99)
      * [4.4. AWS CloudShell を使った Docker イメージの作成と ECR へのプッシュ](https://www.google.com/search?q=%2344-aws-cloudshell-%E3%82%92%E4%BD%BF%E3%81%A3%E3%81%9F-docker-%E3%82%A4%E3%83%A1%E3%83%BC%E3%82%B8%E3%81%AE%E4%BD%9C%E6%88%90%E3%81%A8-ecr-%E3%81%B8%E3%81%AE%E3%83%97%E3%83%83%E3%82%B7%E3%83%A5)
      * [4.5. AWS Batch の設定](https://www.google.com/search?q=%2345-aws-batch-%E3%81%AE%E8%A8%AD%E5%AE%9A)
          * [4.5.1. コンピューティング環境の作成](https://www.google.com/search?q=%23451-%E3%82%B3%E3%83%B3%E3%83%94%E3%83%A5%E3%83%BC%E3%83%86%E3%82%A3%E3%83%B3%E3%82%B0%E7%92%B0%E5%A2%83%E3%81%AE%E4%BD%9C%E6%88%90)
          * [4.5.2. ジョブキューの作成](https://www.google.com/search?q=%23452-%E3%82%B8%E3%83%A7%E3%83%96%E3%82%AD%E3%83%A5%E3%83%BC%E3%81%AE%E4%BD%9C%E6%88%90)
          * [4.5.3. ジョブ定義の作成](https://www.google.com/search?q=%23453-%E3%82%B8%E3%83%A7%E3%83%96%E5%AE%9A%E7%BE%A9%E3%81%AE%E4%BD%9C%E6%88%90)
5.  [実行手順](https://www.google.com/search?q=%235-%E5%AE%9F%E8%A1%8C%E6%89%8B%E9%A0%86)
6.  [トラブルシューティング](https://www.google.com/search?q=%236-%E3%83%88%E3%83%A9%E3%83%96%E3%83%AB%E3%82%B7%E3%83%A5%E3%83%BC%E3%83%86%E3%82%A3%E3%83%B3%E3%82%B0)
7.  [クリーンアップ](https://www.google.com/search?q=%237-%E3%82%AF%E3%83%AA%E3%83%BC%E3%83%B3%E3%82%A2%E3%83%83%E3%83%97)

## 1\. 概要

このプロジェクトでは、以下のワークフローを AWS Batch を使用して自動化します。

1.  **S3:** JSON 形式のデータが保存されます。
2.  **AWS Batch:** S3 から JSON データを読み込み、オンプレミスの Elasticsearch にインデックスするカスタムスクリプトを実行します。
3.  **オンプレミス Elasticsearch:** インデックスされたデータを保存します。

これにより、大量のデータを効率的かつスケーラブルに処理し、オンプレミス ES に取り込むことができます。特に、AWS とオンプレミス環境間のデータ連携において、スケーラブルな処理基盤を提供します。

## 2\. 前提条件

  * AWS アカウント
  * **全ての AWS リソース操作は AWS コンソール経由で行います。**
  * オンプレミス Elasticsearch インスタンスへのネットワーク接続が AWS Batch が実行される EC2 インスタンスから可能であること (VPC と VPN/Direct Connect の設定が必要です)。
  * 基本的な AWS サービス (S3, IAM, Batch, EC2, ECR, CloudShell) の知識
  * オンプレミス Elasticsearch の接続情報 (IP アドレス、ポート、認証情報など)

## 3\. アーキテクチャ

```
+----------------+       +-------------------+       +------------------------+
|    Amazon S3   |       |    AWS Batch      |       | On-Premises            |
| (JSON Data)    +------>+ (Docker Container)|+----->+ Elasticsearch          |
+----------------+       |   (Python Script) |       | (Data Indexing)        |
                         +-------------------+       +------------------------+
                                   ^                            ^
                                   |                            |
                                   +------- EC2 Instance        |
                                   | (Managed by Batch)         |
                                   |                            |
                                   +----------------------------+
                                     (VPC, VPN/Direct Connect)
```

## 4\. セットアップ手順

### 4.1. オンプレミス Elasticsearch の準備

オンプレミスの Elasticsearch 環境が稼働しており、AWS Batch が実行される VPC からネットワーク的に到達可能であることを確認してください。

  * **ネットワーク接続:** AWS Batch が実行される VPC とオンプレミス環境間で、VPN または AWS Direct Connect を介したネットワーク接続が確立されている必要があります。
  * **セキュリティグループ/ファイアウォール:** AWS Batch のコンピューティング環境で使用される EC2 インスタンスのセキュリティグループから、オンプレミス Elasticsearch の IP アドレスとポートへのアウトバウンド通信が許可されていることを確認してください。また、オンプレミス側のファイアウォールでも、AWS からのインバウンド接続を許可する必要があります。
  * **認証:** Elasticsearch が認証を必要とする場合、その認証情報 (ユーザー名、パスワード) を安全な方法でスクリプトに渡す準備をします。

### 4.2. IAM ロールの作成

AWS Batch が S3 にアクセスするために必要な権限を持つ IAM ロールを作成します。**全ての操作は AWS コンソールから行います。**

1.  **AWS Batch ジョブ実行ロール:**
      * **信頼エンティティ:** `ec2.amazonaws.com` と `batch.amazonaws.com`
      * **アクセス権限:**
          * **S3 読み取り権限:** `AmazonS3ReadOnlyAccess` ポリシーをアタッチするか、特定の S3 バケットへの読み取りアクセスを許可するカスタムポリシーを作成します。
              * AWS コンソールで IAM サービスに移動し、「ポリシー」-\>「ポリシーの作成」で JSON を編集して作成します。
              * `"Resource"` には対象の S3 バケット ARN を指定します。
          * **Elasticsearch (オンプレミス) へのアクセス権限:** オンプレミスの Elasticsearch へは直接 IP で接続するため、IAM 認証は不要です。しかし、VPC 内からのネットワークアクセス権限が適切に設定されている必要があります。
          * **AWS Batch サービスロール:** AWS Batch が EC2 インスタンスを起動するために必要な `AWSServiceRoleForBatch` は通常、Batch の設定時に自動的に作成されます。Batch コンピューティング環境にアタッチされるインスタンスプロファイルには、最低限 `AmazonEC2ContainerServiceforEC2Role` またはそれに相当する権限が必要です。
      * このロールの名前を控えておきます (例: `BatchJobExecutionRoleForS3ToOnPremES`)。

### 4.3. Python スクリプトの準備

S3 から JSON データを読み込み、オンプレミス Elasticsearch にインデックスする Python スクリプトを作成します。

`index_data.py`:

```python
import os
import json
import boto3
from elasticsearch import Elasticsearch, ConnectionError, TransportError
import time # リトライ処理のため

# 環境変数から設定を取得
S3_BUCKET = os.environ.get('S3_BUCKET')
S3_KEY = os.environ.get('S3_KEY') # S3 オブジェクトのパス
ES_HOST = os.environ.get('ES_HOST') # オンプレミス Elasticsearch の IP アドレスまたはホスト名
ES_PORT = int(os.environ.get('ES_PORT', 9200)) # Elasticsearch のポート
ES_INDEX = os.environ.get('ES_INDEX', 'my-index')
ES_USERNAME = os.environ.get('ES_USERNAME') # Elasticsearch 認証ユーザー名 (Optional)
ES_PASSWORD = os.environ.get('ES_PASSWORD') # Elasticsearch 認証パスワード (Optional)
ES_VERIFY_CERTS = os.environ.get('ES_VERIFY_CERTS', 'false').lower() == 'true' # HTTPS 証明書検証 (Optional, デフォルトはfalse)

# Elasticsearch クライアントの初期化
# オンプレミスなので AWS4Auth は不要
auth_args = {}
if ES_USERNAME and ES_PASSWORD:
    auth_args['basic_auth'] = (ES_USERNAME, ES_PASSWORD)

# HTTPS を使用する場合、ポートが 443 でなくても use_ssl=True にする
# verify_certs は環境に応じて適切に設定する
es = Elasticsearch(
    hosts=[{'host': ES_HOST, 'port': ES_PORT}],
    use_ssl=True if ES_PORT == 443 or os.environ.get('ES_USE_SSL', 'false').lower() == 'true' else False, # ポートが443か、ES_USE_SSLがtrueならSSLを有効
    verify_certs=ES_VERIFY_CERTS,
    **auth_args
)

s3 = boto3.client('s3')

def process_s3_json():
    if not S3_BUCKET or not S3_KEY or not ES_HOST:
        print("エラー: S3_BUCKET, S3_KEY, ES_HOST 環境変数が設定されていません。")
        raise ValueError("必須の環境変数が不足しています。")

    print(f"S3 からデータを取得中: s3://{S3_BUCKET}/{S3_KEY}")
    try:
        obj = s3.get_object(Bucket=S3_BUCKET, Key=S3_KEY)
        data = obj['Body'].read().decode('utf-8')

        # JSONL (各行が1つのJSONオブジェクト) または単一のJSON配列を想定
        lines = data.strip().split('\n')

        # Elasticsearch 接続確認
        try:
            if not es.ping():
                raise ConnectionError("Elasticsearch への接続に失敗しました。")
            print("Elasticsearch への接続に成功しました。")
        except ConnectionError as e:
            print(f"Elasticsearch への接続エラー: {e}")
            raise

        for i, line in enumerate(lines):
            if not line:
                continue
            try:
                doc = json.loads(line)
                # ドキュメントIDを明示的に指定する場合（例: `id`フィールドがあればそれを使用）
                doc_id = doc.get('id', None)

                print(f"インデックス中 (行 {i+1}): {doc_id if doc_id else '新しいドキュメント'}")
                response = es.index(index=ES_INDEX, id=doc_id, document=doc, refresh=True) # Elasticsearch 8.x では body ではなく document を使用
                print(f"インデックス成功: {response['result']} (ID: {response['_id']})")
            except json.JSONDecodeError as e:
                print(f"JSONデコードエラー (行 {i+1}): {e} - 行データ: {line[:100]}...")
            except (ConnectionError, TransportError) as e:
                print(f"Elasticsearch へのインデックスエラー (ネットワーク/接続): {e} - 行データ: {line[:100]}...")
                # リトライロジックなどをここに追加することも可能
                raise # 再スローしてジョブを失敗させるか、リトライするかは要件次第
            except Exception as e:
                print(f"予期せぬエラー (行 {i+1}): {e} - ドキュメント: {doc.get('id', 'N/A')}")
                raise # ジョブを失敗させる

    except Exception as e:
        print(f"S3 からのデータ取得または主要な処理中にエラーが発生しました: {e}")
        raise

if __name__ == '__main__':
    try:
        process_s3_json()
    except Exception as e:
        print(f"スクリプト実行中に致命的なエラーが発生しました: {e}")
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
COPY index_data.py .

# コンテナ起動時に実行されるコマンド
CMD ["python", "index_data.py"]
```

### 4.4. AWS CloudShell を使った Docker イメージの作成と ECR へのプッシュ

ローカル Docker や CodeBuild を使用できないため、AWS CloudShell 環境内で Docker イメージをビルドし、ECR にプッシュします。

**手順:**

1.  **ECR リポジトリの作成:**

      * AWS コンソールで **ECR** サービスに移動します。
      * 「リポジトリ」-\>「リポジトリを作成」をクリックします。
      * 「可視性設定」で「プライベート」を選択します。
      * **リポジトリ名:** `s3-to-es-indexer` と入力し、「リポジトリを作成」をクリックします。

2.  **CloudShell の起動:**

      * AWS コンソールの右上にある CloudShell アイコンをクリックして CloudShell を起動します。

3.  **作業ディレクトリの作成とファイル転送:**

      * CloudShell のターミナルで作業ディレクトリを作成します。
        ```bash
        mkdir s3-to-es-project
        cd s3-to-es-project
        ```
      * `index_data.py`, `requirements.txt`, `Dockerfile` の各ファイルを、CloudShell のメニューからアップロードします。
          * CloudShell 画面上部の「アクション」メニューから「**ファイルのアップロード**」を選択し、各ファイルをアップロードします。
          * または、S3 にアップロードしておき、CloudShell 内で `aws s3 cp` コマンドでダウンロードすることも可能です。
            ```bash
            # 例: S3 にアップロード済みの場合
            aws s3 cp s3://your-s3-bucket/path/to/index_data.py .
            aws s3 cp s3://your-s3-bucket/path/to/requirements.txt .
            aws s3 cp s3://your-s3-bucket/path/to/Dockerfile .
            ```

4.  **Docker イメージのビルド:**

      * CloudShell 環境は Docker がプリインストールされています。
      * `s3-to-es-project` ディレクトリ内で以下のコマンドを実行します。
        ```bash
        docker build -t s3-to-es-indexer .
        ```

5.  **ECR にログイン:**

      * 以下のコマンドを実行し、ECR にログインするための認証情報を取得します。
        ```bash
        aws ecr get-login-password --region your-aws-region | docker login --username AWS --password-stdin your-account-id.dkr.ecr.your-aws-region.amazonaws.com
        ```
          * `your-aws-region` と `your-account-id` はご自身の環境に合わせて置き換えてください。

6.  **Docker イメージにタグを付け、ECR にプッシュ:**

      * イメージに ECR リポジトリのURIでタグを付けます。
        ```bash
        docker tag s3-to-es-indexer:latest your-account-id.dkr.ecr.your-aws-region.amazonaws.com/s3-to-es-indexer:latest
        ```
      * ECR にイメージをプッシュします。
        ```bash
        docker push your-account-id.dkr.ecr.your-aws-region.amazonaws.com/s3-to-es-indexer:latest
        ```
      * これで Docker イメージが ECR に格納されました。CloudShell は一時的な環境ですが、ECR にプッシュされたイメージは永続的に保存されます。

-----

### 4.5. AWS Batch の設定

**全ての操作は AWS コンソールから行います。**

#### 4.5.1. コンピューティング環境の作成

1.  AWS コンソールで **Batch** サービスに移動します。
2.  「コンピューティング環境」-\>「コンピューティング環境を作成」をクリックします。
3.  **環境タイプ:** `マネージド`
4.  **プロビジョニングモデル:** `オンデマンド` または `スポット` (コストに応じて選択)
5.  **インスタンスタイプ:** ジョブの要件に合わせて選択 (例: `m5.large`, `c5.xlarge`)。オンプレミス ES への接続を考慮し、十分なネットワーク帯域があるタイプを検討してください。
6.  **ネットワーク設定:**
      * **VPC:** オンプレミス ES に接続可能な VPC を選択します。
      * **サブネット:** オンプレミス ES への接続が可能なサブネットを選択します。
      * **セキュリティグループ:** アウトバウンドでオンプレミス ES の IP アドレスとポートへのアクセスを許可するセキュリティグループを作成し、割り当てます。
7.  **インスタンスロール:** 前述の「IAM ロールの作成」で作成した **`BatchJobExecutionRoleForS3ToOnPremES`** (またはそれと同等の権限を持つロール) を指定します。
8.  その他設定 (最小/最大 vCPU、希望 vCPU) を適切に設定し、「コンピューティング環境を作成」をクリックします。

#### 4.5.2. ジョブキューの作成

1.  AWS コンソールで **Batch** サービスに移動します。
2.  「ジョブキュー」-\>「ジョブキューを作成」をクリックします。
3.  **名前:** `s3-to-onprem-es-queue` (任意)
4.  **優先度:** `1` (任意)
5.  **関連付けるコンピューティング環境:** 先ほど作成したコンピューティング環境を選択し、「関連付ける」をクリックします。
6.  「ジョブキューを作成」をクリックします。

#### 4.5.3. ジョブ定義の作成

1.  AWS コンソールで **Batch** サービスに移動します。
2.  「ジョブ定義」-\>「ジョブ定義を作成」をクリックします。
3.  **名前:** `s3-to-onprem-es-indexer-job-definition` (任意)
4.  **プラットフォームの機能:** `EC2`
5.  **実行ロール:** 前述の「IAM ロールの作成」で作成した **`BatchJobExecutionRoleForS3ToOnPremES`** を指定します。
6.  **コンテナイメージ:** ECR にプッシュしたイメージの URI (例: `your-account-id.dkr.ecr.your-aws-region.amazonaws.com/s3-to-es-indexer:latest`) を入力します。
7.  **コマンド:** 指定なし (Dockerfile の `CMD` が使用されます)。
8.  **環境変数:**
      * `S3_BUCKET`: インデックス対象の S3 バケット名
      * `S3_KEY`: インデックス対象の JSON ファイルのパス
      * `ES_HOST`: オンプレミス Elasticsearch の IP アドレスまたはホスト名
      * `ES_PORT`: オンプレミス Elasticsearch のポート (例: `9200`)
      * `ES_INDEX`: インデックスする Elasticsearch インデックス名
      * `ES_USERNAME`: Elasticsearch のユーザー名 (認証が必要な場合のみ)
      * `ES_PASSWORD`: Elasticsearch のパスワード (認証が必要な場合のみ)
      * `ES_VERIFY_CERTS`: HTTPS 証明書を検証するかどうか (例: `true` または `false`)
      * `ES_USE_SSL`: SSL を使用するかどうかを明示的に指定 (例: `true` または `false`)
9.  **リソース:**
      * **vCPU:** 必要な vCPU 数
      * **メモリ:** 必要なメモリ量 (MB)
10. 「ジョブ定義を作成」をクリックします。

-----

## 5\. 実行手順

1.  **S3 に JSON データファイルをアップロード:**
    インデックスしたい JSON データファイルを指定した S3 バケットとキーにアップロードします。
    例: `s3://your-s3-bucket-name/data/your_data.json`

2.  **AWS Batch ジョブの送信:**

      * AWS コンソールで **Batch** サービスに移動します。
      * 「ジョブ」-\>「新しいジョブを送信」をクリックします。
      * **名前:** ジョブのユニークな名前 (例: `my-s3-to-onprem-es-job`)
      * **ジョブ定義:** 先ほど作成したジョブ定義 (`s3-to-onprem-es-indexer-job-definition`) を選択します。
      * **ジョブキュー:** 先ほど作成したジョブキュー (`s3-to-onprem-es-queue`) を選択します。
      * **環境変数のオーバーライド:**
          * 必要に応じて、`S3_BUCKET`, `S3_KEY`, `ES_HOST`, `ES_PORT`, `ES_INDEX`, `ES_USERNAME`, `ES_PASSWORD`, `ES_VERIFY_CERTS`, `ES_USE_SSL` などの環境変数を上書きします。これにより、同じジョブ定義で異なるファイルや Elasticsearch インデックスにデータをインデックスできます。
      * 「ジョブを送信」をクリックします。

3.  **ジョブの監視:**
    AWS Batch コンソールでジョブのステータス (PENDING, RUNNING, SUCCEEDED, FAILED) を監視します。ジョブの詳細画面から CloudWatch Logs へのリンクをたどり、スクリプトの出力を確認できます。

4.  **Elasticsearch でデータの確認:**
    ジョブが `SUCCEEDED` になったら、オンプレミスの Kibana や Elasticsearch API を使用して、データが正しくインデックスされているか確認します。

-----

## 6\. トラブルシューティング

  * **IAM 権限エラー:**
      * Batch ジョブ実行ロール (`BatchJobExecutionRoleForS3ToOnPremES`) に S3 への読み取り権限が正しく付与されているか確認してください。
      * CloudShell で Docker イメージをプッシュする際、CloudShell を起動した IAM ユーザー/ロールに ECR へのプッシュ権限 (上記「4.2. IAM ロールの作成」で説明したような権限) があるか確認してください。
  * **Elasticsearch 接続エラー:**
      * **最も重要な点:** AWS Batch のコンピューティング環境が起動する VPC とサブネットから、オンプレミス Elasticsearch の IP アドレスとポートへのネットワーク接続が確立されているか（VPN/Direct Connect、ルーティング、ファイアウォールなど）を最優先で確認してください。
      * Batch のコンピューティング環境で使用されている EC2 インスタンスのセキュリティグループで、オンプレミス ES へのアウトバウンド通信が許可されているか確認してください。
      * オンプレミス ES 側のファイアウォールで、AWS からのインバウンド接続が許可されているか確認してください。
      * `ES_HOST` と `ES_PORT` 環境変数が正しいか確認してください。
      * `ES_USERNAME` と `ES_PASSWORD` が正しく設定されているか確認してください (認証が必要な場合)。
      * HTTPS を使用している場合、`ES_VERIFY_CERTS` と `ES_USE_SSL` の設定が環境に合っているか確認してください。自己署名証明書の場合は `ES_VERIFY_CERTS` を `false` に設定する必要があるかもしれません (非推奨、テスト環境のみ)。
  * **Docker イメージの問題:**
      * CloudShell での `docker build` および `docker push` コマンドの出力にエラーがないか確認してください。
      * ECR リポジトリへのパスがジョブ定義で正しいか確認してください。
      * `requirements.txt` に必要なライブラリ (特に `elasticsearch==8.4.3`) がすべて含まれているか確認してください。
  * **JSON フォーマットエラー:**
      * S3 にアップロードされた JSON データが有効な形式であることを確認してください。スクリプトは各行が独立した JSON オブジェクトである JSONL 形式、または単一のJSON配列を想定しています。
  * **Batch ジョブログの確認:**
      * ジョブが失敗した場合、CloudWatch Logs に出力されるログを必ず確認してください。エラーの詳細が記載されています。

-----

## 7\. クリーンアップ

不要なリソースは削除して、AWS の料金が発生し続けないようにしてください。**全ての操作は AWS コンソールから行います。**

1.  AWS Batch ジョブ定義、ジョブキュー、コンピューティング環境を削除します。
2.  ECR リポジトリから Docker イメージを削除し、リポジトリ自体も削除します。
3.  S3 バケット内のアップロードした JSON データファイルを削除します (必要であればバケットも)。
4.  作成した IAM ロールとポリシーを削除します。

-----
