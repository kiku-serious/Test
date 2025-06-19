承知いたしました！これまでの全ての議論、特に CloudShell でのファイル操作の挙動、Docker イメージのベース、`bullseye` タグの選定理由、AWS Batch のコンピューティング環境で EC2 を選択する理由、そして IAM ポリシーのサービス別分割、Lambda ログが出ない場合のトラブルシューティングまで、全ての情報を網羅した、**完全かつ最新、最も正確な `README.md` 形式の手順**をここに提示します。

オンプレミス Elasticsearch への接続確認と、将来的な Bedrock を利用した埋め込み処理も考慮した内容になっています。

-----

# AWS Batch を利用した S3 からオンプレミス Elasticsearch への接続確認（兼 Bedrock 埋め込み準備）

このプロジェクトは、AWS Batch を利用して Amazon S3 に保存された JSON データを読み込み（動作確認のため）、オンプレミス環境の Elasticsearch へ接続確認（ping）を行うための手順を説明します。さらに、将来的に Amazon Bedrock の埋め込みモデルを呼び出すための IAM 権限も事前に設定します。これにより、AWS 環境からオンプレミス Elasticsearch へのネットワーク接続、IAM 権限、および基本的な設定が適切であることを検証できます。

**変更点ハイライト:**

  * AWS リソースの操作は**全て AWS コンソール**から行います。
  * Docker イメージのビルドと ECR へのプッシュは **AWS CloudShell** を使用します。
  * Elasticsearch はオンプレミスの IP アドレスに直接接続します。
  * Python 3.12 を使用し、**Docker Official Images の Python 3.12 `bullseye` ベースイメージ**を Docker のベースとします。
  * Elasticsearch ライブラリは 8.4.3 を使用します。
  * Python スクリプトは、まず Elasticsearch への接続（ping）のみを確認します。
  * IAM ポリシーをサービス別に分割し、より明確な権限管理を行います。

-----

## 目次

1.  [概要](https://www.google.com/search?q=%231-%E6%A6%82%E8%A6%81)
2.  [前提条件](https://www.google.com/search?q=%232-%E5%89%8D%E6%8F%90%E6%9D%A1%E4%BB%B6)
3.  [アーキテクチャ](https://www.google.com/search?q=%233-%E3%82%A2%E3%83%BC%E3%82%AD%E3%83%86%E3%82%AF%E3%83%81%E3%83%A3)
4.  [セットアップ手順](https://www.google.com/search?q=%234-%E3%82%BB%E3%83%83%E3%83%88%E3%82%A2%E3%83%83%E3%83%97%E6%89%8B%E9%A0%86)
      * [4.1. オンプレミス Elasticsearch の準備](https://www.google.com/search?q=%2341-%E3%82%AA%E3%83%B3%E3%83%97%E3%83%AC%E3%83%9F%E3%82%B9-elasticsearch-%E3%81%AE%E6%BA%96%E5%82%99)
      * [4.2. IAM ポリシーの作成 (サービス別)](https://www.google.com/search?q=%2342-iam-%E3%83%9D%E3%83%AA%E3%82%B7%E3%83%BC%E3%81%AE%E4%BD%9C%E6%88%90-%E3%82%B5%E3%83%BC%E3%83%93%E3%82%B9%E5%88%A5)
          * [4.2.1. Amazon S3 (読み書き両用)](https://www.google.com/search?q=%23421-amazon-s3-%E8%AA%AD%E3%81%BF%E6%9B%B8%E3%81%8D%E4%B8%A1%E7%94%A8)
          * [4.2.2. Amazon Bedrock (InvokeModel)](https://www.google.com/search?q=%23422-amazon-bedrock-invokemodel)
          * [4.2.3. Amazon CloudWatch Logs (ログ出力)](https://www.google.com/search?q=%23423-amazon-cloudwatch-logs-%E3%83%AD%E3%82%B0%E5%87%BA%E5%8A%9B)
          * [4.2.4. Amazon ECR (イメージプル)](https://www.google.com/search?q=%23424-amazon-ecr-%E3%82%A4%E3%83%A1%E3%83%BC%E3%82%B8%E3%83%97%E3%83%AB)
          * [4.2.5. CloudShell ユーザー/ロールのためのポリシー (ECR プッシュ権限)](https://www.google.com/search?q=%23425-cloudshell-%E3%83%A6%E3%83%BC%E3%82%B6%E3%83%BC%E3%83%AD%E3%83%BC%E3%83%AB%E3%81%AE%E3%81%9F%E3%82%81%E3%81%AE%E3%83%9D%E3%83%AA%E3%82%B7%E3%83%BC-ecr-%E3%83%97%E3%83%83%E3%82%B7%E3%83%A5%E6%A8%A9%E9%99%90)
      * [4.3. IAM ロールの作成とポリシーのアタッチ](https://www.google.com/search?q=%2343-iam-%E3%83%AD%E3%83%BC%E3%83%AB%E3%81%AE%E4%BD%9C%E6%88%90%E3%81%A8%E3%83%9D%E3%83%AA%E3%82%B7%E3%83%BC%E3%81%AE%E3%82%A2%E3%82%BF%E3%83%83%E3%83%81)
      * [4.4. Python スクリプトと Dockerfile の準備](https://www.google.com/search?q=%2344-python-%E3%82%B9%E3%82%AF%E3%83%AA%E3%83%97%E3%83%88%E3%81%A8-dockerfile-%E3%81%AE%E6%BA%96%E5%82%99)
      * [4.5. AWS CloudShell を使った Docker イメージの作成と ECR へのプッシュ](https://www.google.com/search?q=%2345-aws-cloudshell-%E3%82%92%E4%BD%BF%E3%81%A3%E3%81%9F-docker-%E3%82%A4%E3%83%A1%E3%83%BC%E3%82%B8%E3%81%AE%E4%BD%9C%E6%88%90%E3%81%A8-ecr-%E3%81%B8%E3%81%AE%E3%83%97%E3%83%83%E3%82%B7%E3%83%A5)
      * [4.6. AWS Batch の設定](https://www.google.com/search?q=%2346-aws-batch-%E3%81%AE%E8%A8%AD%E5%AE%9A)
          * [4.6.1. コンピューティング環境の作成](https://www.google.com/search?q=%23461-%E3%82%B3%E3%83%B3%E3%83%94%E3%83%A5%E3%83%BC%E3%83%86%E3%82%A3%E3%83%B3%E3%82%B0%E7%92%B0%E5%A2%83%E3%81%AE%E4%BD%9C%E6%88%90)
          * [4.6.2. ジョブキューの作成](https://www.google.com/search?q=%23462-%E3%82%B8%E3%83%A7%E3%83%96%E3%82%AD%E3%83%A5%E3%83%BC%E3%81%AE%E4%BD%9C%E6%88%90)
          * [4.6.3. ジョブ定義の作成](https://www.google.com/search?q=%23463-%E3%82%B8%E3%83%A7%E3%83%96%E5%AE%9A%E7%BE%A9%E3%81%AE%E4%BD%9C%E6%88%90)
5.  [実行手順](https://www.google.com/search?q=%235-%E5%AE%9F%E8%A1%8C%E6%89%8B%E9%A0%86)
6.  [トラブルシューティング](https://www.google.com/search?q=%236-%E3%83%88%E3%83%A9%E3%83%96%E3%83%AB%E3%82%B7%E3%83%A5%E3%83%BC%E3%83%86%E3%82%A3%E3%83%B3%E3%82%B0)
7.  [クリーンアップ](https://www.google.com/search?q=%237-%E3%82%AF%E3%83%AA%E3%83%BC%E3%83%B3%E3%82%A2%E3%83%83%E3%83%97)

-----

## 1\. 概要

このプロジェクトでは、以下のワークフローを AWS Batch を使用して自動化し、オンプレミス Elasticsearch への接続確認を行います。

1.  **Amazon S3:** JSON 形式のデータが保存されます（スクリプトは読み込みを試みますが、ESへのデータ投入は行いません）。
2.  **AWS Batch:** S3 から JSON データを読み込み、オンプレミスの Elasticsearch へ接続確認（ping）を行うカスタムスクリプトを実行します。同時に、将来的な Bedrock モデル呼び出しに必要な権限設定も検証します。
3.  **オンプレミス Elasticsearch:** 接続が成功するかどうかをログに出力します。

これにより、AWS とオンプレミス環境間のネットワーク接続、IAM 権限、および Elasticsearch の基本的な接続設定が適切であることを効率的に検証できます。

-----

## 2\. 前提条件

  * **AWS アカウント**があること。
  * **全ての AWS リソース操作は AWS コンソール経由で行います。** AWS CLI は CloudShell 内でのみ使用します。
  * オンプレミス Elasticsearch インスタンスへのネットワーク接続が、AWS Batch が実行される EC2 インスタンスから可能であること (**AWS VPC とオンプレミス間の VPN または AWS Direct Connect の接続**が既に確立されている必要があります)。
  * 基本的な AWS サービス (S3, IAM, Batch, EC2, ECR, CloudShell) の知識があること。
  * オンプレミス Elasticsearch の接続情報 (IP アドレス、ポート、認証情報など) を把握していること。
  * **Amazon Bedrock の利用開始のための「モデルアクセス」リクエストが完了していること。** (Bedrock コンソール -\> 左メニュー「Model access」から、利用したい埋め込みモデルにアクセスを許可しておく必要があります。例: Titan Embeddings G1 - Text)。

-----

## 3\. アーキテクチャ

```
+----------------+       +-------------------+       +------------------------+
|    Amazon S3   |       |    AWS Batch      |       | On-Premises            |
| (JSON Data)    +------>+ (Docker Container)|+----->+ Elasticsearch          |
+----------------+       |   (Python Script) |       | (Connection Check)     |
                         +-------------------+       +------------------------+
                                   ^                            ^
                                   |                            |
                                   +------- EC2 Instance        |
                                   | (Managed by Batch)         |
                                   |                            |
                                   +----------------------------+
                                     (VPC, VPN/Direct Connect)
```

-----

## 4\. セットアップ手順

### 4.1. オンプレミス Elasticsearch の準備

オンプレミスの Elasticsearch 環境が稼働しており、AWS Batch が実行される VPC からネットワーク的に到達可能であることを確認してください。

  * **ネットワーク接続:** AWS Batch が実行される VPC とオンプレミス環境間で、VPN または AWS Direct Connect を介したネットワーク接続が確立されている必要があります。
  * **セキュリティグループ/ファイアウォール:** AWS Batch のコンピューティング環境で使用される EC2 インスタンスの**セキュリティグループ**から、オンプレミス Elasticsearch の IP アドレスとポートへのアウトバウンド通信が許可されていることを確認してください。また、オンプレミス側の**ファイアウォール**でも、AWS からのインバウンド接続を許可する必要があります。
  * **認証:** Elasticsearch が認証を必要とする場合、その認証情報 (ユーザー名、パスワード) を安全な方法でスクリプトに渡す準備をします。

-----

### 4.2. IAM ポリシーの作成 (サービス別)

AWS Batch ジョブ実行ロール (`BatchJobExecutionRoleForS3ToOnPremES`) と、CloudShell から ECR にプッシュするための IAM ユーザー/ロールにアタッチするポリシーを、サービスごとに作成します。**全ての操作は AWS コンソールから行います。**

AWS コンソールで **IAM** サービスに移動し、「**ポリシー**」-\>「**ポリシーの作成**」-\>「**JSON**」タブで以下の JSON をそれぞれ貼り付けてポリシーを作成してください。`your-aws-region`、`your-account-id`、`your-s3-bucket-name`、`your-embedding-model-id` はご自身の環境に合わせて置き換えてください。

#### 4.2.1. Amazon S3 (読み書き両用)

このポリシーは、指定された S3 バケットに対して、オブジェクトの読み取り、一覧表示、および書き込み（アップロード）を許可します。

**ポリシー名:** `S3ReadWriteAccessForBatchJobs`

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "s3:GetObject",
                "s3:ListBucket",
                "s3:PutObject"
            ],
            "Resource": [
                "arn:aws:s3:::your-s3-bucket-name",
                "arn:aws:s3:::your-s3-bucket-name/*"
            }
        ]
    }
}
```

#### 4.2.2. Amazon Bedrock (InvokeModel)

このポリシーは、Python スクリプトが Amazon Bedrock の埋め込みモデルを呼び出すために必要な権限を提供します。複数のモデルを呼び出す可能性がある場合は、ARN をリスト形式で記述します。

**ポリシー名:** `BedrockInvokeModelsPolicyForBatch`

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "bedrock:InvokeModel"
            ],
            "Resource": [
                "arn:aws:bedrock:your-aws-region::foundation-model/amazon.titan-embed-text-v1",
                "arn:aws:bedrock:your-aws-region::foundation-model/cohere.embed-english-v3",
                "arn:aws:bedrock:your-aws-region::foundation-model/cohere.embed-multilingual-v3"
                // 必要に応じて、さらに他の埋め込みモデルのARNを追加してください
            ]
        }
    ]
}
```

#### 4.2.3. Amazon CloudWatch Logs (ログ出力)

このポリシーは、AWS Batch ジョブが CloudWatch Logs に標準出力やエラーログを書き込むために必要です。

**ポリシー名:** `CloudWatchLogsAccessForBatchJobs`

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents"
            ],
            "Resource": "arn:aws:logs:your-aws-region:your-account-id:log-group:/aws/batch/job:*"
        }
    ]
}
```

#### 4.2.4. Amazon ECR (イメージプル)

このポリシーは、AWS Batch が Docker イメージを実行するために、ECR からイメージをプル（ダウンロード）するために必要です。

**ポリシー名:** `ECRImagePullAccessForBatch`

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": "ecr:GetAuthorizationToken",
            "Resource": "*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "ecr:BatchCheckLayerAvailability",
                "ecr:GetDownloadUrlForLayer",
                "ecr:BatchGetImage"
            ],
            "Resource": "arn:aws:ecr:your-aws-region:your-account-id:repository/s3-to-es-indexer"
        }
    ]
}
```

#### 4.2.5. CloudShell ユーザー/ロールのためのポリシー (ECR プッシュ権限)

CloudShell を利用する IAM ユーザーまたはロールに、ECR に Docker イメージをプッシュするための権限が付与されている必要があります。

**ポリシー名:** `ECRImagePushAccessForCloudShell`

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "ecr:GetAuthorizationToken",
                "ecr:BatchCheckLayerAvailability",
                "ecr:InitiateLayerUpload",
                "ecr:UploadLayerPart",
                "ecr:CompleteLayerUpload",
                "ecr:PutImage"
            ],
            "Resource": "arn:aws:ecr:your-aws-region:your-account-id:repository/s3-to-es-indexer"
        }
    ]
}
```

*このポリシーは、CloudShell を起動するユーザーまたはロールに直接アタッチします。*

-----

### 4.3. IAM ロールの作成とポリシーのアタッチ

上記で作成したポリシーを、AWS Batch ジョブが実行時に使用する IAM ロールにアタッチします。

1.  **新しい IAM ロールを作成します。**
      * AWS コンソールで **IAM** サービスに移動します。
      * 左側のナビゲーションペインで「**ロール**」をクリックします。
      * 「**ロールを作成**」をクリックします。
      * **信頼されたエンティティの種類:** 「**AWS のサービス**」を選択します。
      * **ユースケース:** 「**Batch**」を選択します。
      * 「**次へ**」をクリックします。
      * **許可の追加:** 検索ボックスに以下の作成済みポリシー名をそれぞれ入力して選択し、アタッチします。
          * `S3ReadWriteAccessForBatchJobs`
          * `BedrockInvokeModelsPolicyForBatch`
          * `CloudWatchLogsAccessForBatchJobs`
          * `ECRImagePullAccessForBatch`
      * また、AWS Batch コンピューティング環境の EC2 インスタンスが ECS コンテナインスタンスとして動作するために必要な `AmazonEC2ContainerServiceforEC2Role` も検索して選択し、アタッチします（もし既になければ）。
      * 「**次へ**」をクリックし、タグを追加（任意）、「**次へ**」をクリックします。
      * **ロール名:** `BatchJobExecutionRoleForS3ToOnPremES` (推奨、分かりやすい名前をつけます)
      * 「**ロールの作成**」をクリックします。

-----

### 4.4. Python スクリプトと Dockerfile の準備

まず、以下の3つのファイルを作成し、**ローカルPCに保存**します。

1.  **`check_es_connection.py`** (Python スクリプト): Elasticsearch への接続確認のみを行います。

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

2.  **`requirements.txt`** (Python 依存関係ファイル):

    ```
    boto3
    elasticsearch==8.4.3
    ```

3.  **`Dockerfile`** (Docker イメージの定義ファイル): **Docker Official Images の Python 3.12 `bullseye` ベースイメージ**を使用します。

    ```dockerfile
    # Docker Official Images の Python 3.12 bullseye イメージを使用
    FROM public.ecr.aws/docker/library/python:3.12-bullseye

    WORKDIR /app

    # 依存関係のインストール
    COPY requirements.txt .
    RUN pip install --no-cache-dir -r requirements.txt

    # アプリケーションコードのコピー
    COPY check_es_connection.py .

    # コンテナ起動時に実行されるコマンド
    CMD ["python", "check_es_connection.py"]
    ```

-----

### 4.5. AWS CloudShell を使った Docker イメージの作成と ECR へのプッシュ

ローカル Docker を使用できないため、AWS CloudShell 環境内で Docker イメージをビルドし、ECR にプッシュします。

**手順:**

1.  **ECR リポジトリの作成:**

      * AWS コンソールで **ECR** サービスに移動します。
      * 「**リポジトリ**」-\>「**リポジトリを作成**」をクリックします。
      * 「可視性設定」で「プライベート」を選択します。
      * **リポジトリ名:** `s3-to-es-indexer` と入力し、「**リポジトリを作成**」をクリックします。

2.  **CloudShell の起動:**

      * AWS コンソールの右上にある CloudShell アイコンをクリックして CloudShell を起動します。

3.  **作業ディレクトリの作成:**

      * CloudShell のターミナルで作業ディレクトリを作成します。
        ```bash
        mkdir s3-to-es-project
        ```

4.  **各ファイルをホームディレクトリ（`/home/cloudshell-user/`）にアップロード:**

      * CloudShell 画面上部の「**アクション**」メニューから「**ファイルのアップロード**」を選択し、ローカルPCに保存した以下のファイルをそれぞれアップロードします。
          * `check_es_connection.py`
          * `requirements.txt`
          * `Dockerfile`
      * **重要:** この操作では、どのディレクトリにいるかに関わらず、ファイルは必ず `/home/cloudshell-user/` にアップロードされます。

5.  **アップロードしたファイルを作業ディレクトリに移動:**

      * まずホームディレクトリにいることを確認します。
        ```bash
        cd ~
        ```
      * アップロードしたファイルを作業ディレクトリ `s3-to-es-project` へ移動します。
        ```bash
        mv Dockerfile s3-to-es-project/
        mv check_es_connection.py s3-to-es-project/
        mv requirements.txt s3-to-es-project/
        ```
      * これで、必要なファイルがすべて `s3-to-es-project` ディレクトリに移動されました。

6.  **作業ディレクトリに移動し、ファイルが揃っていることを確認:**

    ```bash
    cd s3-to-es-project/
    ls -l
    ```

    ここで `Dockerfile`、`check_es_connection.py`、`requirements.txt` が表示されていればOKです。

7.  **Docker イメージのビルド:**

      * `s3-to-es-project` ディレクトリ内にいることを確認した上で、以下のコマンドを実行します。
        ```bash
        docker build -t s3-to-es-indexer .
        ```
      * **もしここで `not found` エラーが発生した場合:**
          * CloudShell で `public.ecr.aws/docker/library/python:3.12-bullseye` が本当に存在するか、直接 `docker pull public.ecr.aws/docker/library/python:3.12-bullseye` を試してみてください。これで成功すれば Dockerfile のパス以外の問題の可能性は低いです。
          * それでも失敗する場合は、ECR Public Gallery (`https://gallery.ecr.aws/docker/library/python`) で確認できる別のタグ（例: `3.12-slim` や `3.11-bullseye` など）を `Dockerfile` で試してみてください。

8.  **ECR にログイン:**

      * 以下のコマンドを実行し、ECR にログインするための認証情報を取得します。
        ```bash
        aws ecr get-login-password --region your-aws-region | docker login --username AWS --password-stdin your-account-id.dkr.ecr.your-aws-region.amazonaws.com
        ```
          * `your-aws-region` と `your-account-id` はご自身の環境に合わせて置き換えてください。

9.  **Docker イメージにタグを付け、ECR にプッシュ:**

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

### 4.6. AWS Batch の設定

**全ての操作は AWS コンソールから行います。**

#### 4.6.1. コンピューティング環境の作成

1.  AWS コンソールで **Batch** サービスに移動します。
2.  「**コンピューティング環境**」-\>「**コンピューティング環境を作成**」をクリックします。
3.  **環境タイプ:** `マネージド`
4.  **オーケストレーションタイプ:** **Amazon EC2** を選択します。
      * **理由:** オンプレミス Elasticsearch へのネットワーク接続（VPN/Direct Connect）を利用するには、EC2 ベースのコンピューティング環境で特定の VPC、サブネット、セキュリティグループを指定する必要があるためです。Fargate は抽象化が高いため、これらの詳細なネットワーク制御には向きません。
5.  **プロビジョニングモデル:** `オンデマンド` または `スポット` (コストに応じて選択)
6.  **インスタンスタイプ:** ジョブの要件に合わせて選択 (例: `m5.large`, `c5.xlarge`)。オンプレミス ES への接続を考慮し、十分なネットワーク帯域があるタイプを検討してください。
7.  **ネットワーク設定:**
      * **VPC:** オンプレミス ES に接続可能な **VPC** を選択します。
      * **サブネット:** オンプレミス ES への接続が可能な **サブネット** を選択します。
      * **セキュリティグループ:** アウトバウンドでオンプレミス ES の IP アドレスとポートへのアクセスを許可する**セキュリティグループ**を作成し、割り当てます。
8.  **インスタンスロール:** 前述の「IAM ロールの作成とポリシーのアタッチ」で作成した **`BatchJobExecutionRoleForS3ToOnPremES`** (またはそれと同等の権限を持つロール) を指定します。
9.  その他設定 (最小/最大 vCPU、希望 vCPU) を適切に設定し、「**コンピューティング環境を作成**」をクリックします。

#### 4.6.2. ジョブキューの作成

1.  AWS コンソールで **Batch** サービスに移動します。
2.  「**ジョブキュー**」-\>「**ジョブキューを作成**」をクリックします。
3.  **名前:** `s3-to-onprem-es-queue` (任意)
4.  **優先度:** `1` (任意)
5.  **関連付けるコンピューティング環境:** 先ほど作成したコンピューティング環境を選択し、「**関連付ける**」をクリックします。
6.  「**ジョブキューを作成**」をクリックします。

#### 4.6.3. ジョブ定義の作成

1.  AWS コンソールで **Batch** サービスに移動します。
2.  「**ジョブ定義**」-\>「**ジョブ定義を作成**」をクリックします。
3.  **名前:** `s3-to-onprem-es-indexer-job-definition` (任意)
4.  **プラットフォームの機能:** `EC2`
5.  **実行ロール:** 前述の「IAM ロールの作成とポリシーのアタッチ」で作成した **`BatchJobExecutionRoleForS3ToOnPremES`** を指定します。
6.  **コンテナイメージ:** ECR にプッシュしたイメージの URI (例: `your-account-id.dkr.ecr.your-aws-region.amazonaws.com/s3-to-es-indexer:latest`) を入力します。
7.  **コマンド:** 指定なし (Dockerfile の `CMD` が使用されます)。
8.  **環境変数:**
      * `S3_BUCKET`: インデックス対象の S3 バケット名 (空でも可だが、Batch の動作確認のため何か指定することが推奨されます)
      * `S3_KEY`: インデックス対象の JSON ファイルのパス (空でも可)
      * `ES_HOST`: オンプレミス Elasticsearch の IP アドレスまたはホスト名
      * `ES_PORT`: オンプレミス Elasticsearch のポート (例: `9200`)
      * `ES_USERNAME`: Elasticsearch のユーザー名 (認証が必要な場合のみ)
      * `ES_PASSWORD`: Elasticsearch のパスワード (認証が必要な場合のみ)
      * `ES_VERIFY_CERTS`: HTTPS 証明書を検証するかどうか (例: `true` または `false`)
      * `ES_USE_SSL`: SSL を使用するかどうかを明示的に指定 (例: `true` または `false`)
9.  **リソース:**
      * **vCPU:** 必要な vCPU 数
      * **メモリ:** 必要なメモリ量 (MB)
10. **実行タイムアウト:** `300` 秒 (5分) を推奨。
11. **ジョブの試行回数:** `2` 回を推奨。
12. 「**ジョブ定義を作成**」をクリックします。

-----

## 5\. 実行手順

1.  **S3 にテスト用の JSON データファイルをアップロード (オプション):**
    Elasticsearch へのインデックスは行いませんが、S3 アクセス権限の確認のため、任意のJSONファイルを指定したS3バケットとキーにアップロードしても良いでしょう。
    例: `s3://your-s3-bucket-name/data/test_data.json`

2.  **AWS Batch ジョブの送信:**

      * AWS コンソールで **Batch** サービスに移動します。
      * 「**ジョブ**」-\>「**新しいジョブを送信**」をクリックします。
      * **名前:** ジョブのユニークな名前 (例: `my-es-connection-check-job`)
      * **ジョブ定義:** 先ほど作成したジョブ定義 (`s3-to-onprem-es-indexer-job-definition`) を選択します。
      * **ジョブキュー:** 先ほど作成したジョブキュー (`s3-to-onprem-es-queue`) を選択します。
      * **環境変数のオーバーライド:**
          * `ES_HOST`, `ES_PORT` は必ずオンプレミスの Elasticsearch の正しい情報を設定してください。
          * 必要に応じて `S3_BUCKET`, `S3_KEY`, `ES_USERNAME`, `ES_PASSWORD`, `ES_VERIFY_CERTS`, `ES_USE_SSL` を設定します。
      * 「**ジョブを送信**」をクリックします。

3.  **ジョブの監視:**
    AWS Batch コンソールでジョブのステータス (**PENDING**, **RUNNING**, **SUCCEEDED**, **FAILED**) を監視します。ジョブの詳細画面から **CloudWatch Logs** へのリンクをたどり、スクリプトの出力を確認してください。Elasticsearch への接続成功/失敗メッセージが表示されます。

-----

## 6\. トラブルシューティング

  * **IAM 権限エラー:**
      * Batch ジョブ実行ロール (`BatchJobExecutionRoleForS3ToOnPremES`) に、**S3 の読み書き、Bedrock の InvokeModel、CloudWatch Logs への書き込み、ECR のイメージプル**の各権限が正しく付与されているか確認してください。
      * CloudShell で Docker イメージをプッシュする際、CloudShell を起動した IAM ユーザー/ロールに **ECR へのプッシュ権限** (`ECRImagePushAccessForCloudShell` に相当する権限) があるか確認してください。
      * **Bedrock モデルアクセスリクエストが完了しているか**、Bedrock コンソールの「Model access」ページで確認してください。
  * **Elasticsearch 接続エラー:**
      * **最も重要な点:** AWS Batch のコンピューティング環境が起動する VPC とサブネットから、オンプレミス Elasticsearch の IP アドレスとポートへのネットワーク接続が確立されているか（VPN/Direct Connect、ルーティング、ファイアウォールなど）を最優先で確認してください。
      * Batch のコンピューティング環境で使用されている EC2 インスタンスの**セキュリティグループ**で、オンプレミス ES へのアウトバウンド通信が許可されているか確認してください。
      * オンプレミス ES 側の**ファイアウォール**で、AWS からのインバウンド接続が許可されているか確認してください。
      * `ES_HOST` と `ES_PORT` 環境変数が正しいか確認してください。
      * `ES_USERNAME` と `ES_PASSWORD` が正しく設定されているか確認してください (認証が必要な場合)。
      * HTTPS を使用している場合、`ES_VERIFY_CERTS` と `ES_USE_SSL` の設定が環境に合っているか確認してください。自己署名証明書の場合は `ES_VERIFY_CERTS` を `false` に設定する必要があるかもしれません (非推奨、テスト環境のみ)。
  * **Docker イメージの問題:**
      * CloudShell での `docker build` および `docker push` コマンドの出力にエラーがないか確認してください。
      * `Dockerfile` の `FROM` 行にあるイメージパスとタグが、**ECR Public Gallery (`https://gallery.ecr.aws/docker/library/python`)** で確認できる正確なものと一致しているか、特に注意して確認してください。
      * ECR リポジトリへのパスがジョブ定義で正しいか確認してください。
      * `requirements.txt` に必要なライブラリ (特に `elasticsearch==8.4.3`) がすべて含まれているか確認してください。
  * **JSON フォーマットエラー (S3 読み込み確認時):**
      * S3 にアップロードされた JSON データが有効な形式であることを確認してください。スクリプトは各行が独立した JSON オブジェクトである JSONL 形式、または単一のJSON配列を想定しています。
  * **Batch ジョブログの確認:**
      * ジョブが失敗した場合、**CloudWatch Logs** に出力されるログを必ず確認してください。エラーの詳細が記載されています。

-----

## 7\. クリーンアップ

不要なリソースは削除して、AWS の料金が発生し続けないようにしてください。**全ての操作は AWS コンソールから行います。**

1.  AWS Batch ジョブ定義、ジョブキュー、コンピューティング環境を削除します。
2.  ECR リポジトリから Docker イメージを削除し、リポジトリ自体も削除します。
3.  S3 バケット内のアップロードした JSON データファイルを削除します (必要であればバケットも)。
4.  作成した IAM ロールとポリシーを削除します。

-----

この手順で、全ての懸念事項を網羅した、より明確かつ正確な内容になったかと思います。この手順でうまくいけば幸いです。
