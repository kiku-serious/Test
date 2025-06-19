---

## 全体像

このチャットボットアプリケーションは、以下のコンポーネントで構成されます。

* **バックエンド (AWS Lambda + Amazon API Gateway):**
    * **AWS Lambda:** チャットボットの応答ロジックを処理するサーバーレス関数です。
    * **Amazon API Gateway:** フロントエンドからのHTTPリクエストを受け取り、Lambda関数にルーティングするAPIエンドポイントを提供します。
* **フロントエンド (Streamlit on Amazon ECS Fargate):**
    * **Streamlit:** Pythonで記述されたWebアプリケーションフレームワークで、チャットボットのユーザーインターフェースを提供します。
    * **Amazon ECS (Elastic Container Service) Fargate:** Streamlitアプリケーションをコンテナとして実行するためのサーバーレスなコンテナオーケストレーションサービスです。基盤となるEC2インスタンスの管理は不要です。
    * **Amazon ECR (Elastic Container Registry):** StreamlitアプリケーションのDockerイメージを保存するリポジトリです。
    * **AWS CloudShell:** DockerイメージのビルドとECRへのプッシュを行うための、ブラウザベースのターミナル環境です。

---


### 1. バックエンド (Lambda + API Gateway) の構築

Lambda 関数のランタイムを Python 3.12 に変更します。

#### 1.1. Lambda 関数の作成

1.  **IAM ロールの作成:**
    この手順は前回と変更ありません。
    * AWSマネジメントコンソールにサインインし、**IAM** サービスに移動します。
    * 左側のナビゲーションペインで「**ロール**」を選択し、「**ロールを作成**」をクリックします。
    * 「信頼済みエンティティを選択」で「**AWS サービス**」を選択し、「ユースケース」で「**Lambda**」を選択します。
    * 「**次へ**」をクリックします。
    * 「許可を追加」のページで、検索バーに「`AWSLambdaBasicExecutionRole`」と入力し、表示されたポリシーにチェックを入れます。
    * 「**次へ**」をクリックし、必要であればタグを追加します。
    * 「ロール名」に「`lambda-chatbot-role`」と入力し、「**ロールを作成**」をクリックします。
    * 作成されたロールのARN（例: `arn:aws:iam::xxxxxxxxxxxx:role/lambda-chatbot-role`）を控えておきます。

2.  **Lambda 関数の作成:**
    * AWSマネジメントコンソールで **Lambda** サービスに移動します。
    * 「**関数の作成**」をクリックします。
    * 「関数の作成」ページで以下を設定します。
        * 「一から作成」を選択します。
        * 「関数名」に「`ChatbotBackendFunction`」と入力します。
        * 「ランタイム」で「**Python 3.12**」を選択します。
        * 「アーキテクチャ」は「`x86_64`」のままにします。
        * 「実行ロール」セクションで「**既存のロールを使用する**」を選択し、ドロップダウンから先ほど作成した「`lambda-chatbot-role`」を選択します。
    * 「**関数の作成**」をクリックします。
    * 関数が作成されたら、コードエディタが表示されます。ここに以下のコードをコピー＆ペーストします。**コード自体は Python 3.9 と互換性があるため変更ありません。**

    ```python
    import json

    def lambda_handler(event, context):
        """
        チャットボットのバックエンドロジックを処理するLambda関数
        """
        print(f"Received event: {json.dumps(event)}")

        try:
            # API Gatewayからのリクエストボディを解析
            body = json.loads(event['body'])
            user_message = body.get('message', '')

            # ここにチャットボットの実際のロジックを記述します。
            # 例: キーワードに応じて応答を変える、外部APIを呼び出すなど
            if "こんにちは" in user_message:
                bot_response = "こんにちは！何かお手伝いできることはありますか？"
            elif "ありがとう" in user_message:
                bot_response = "どういたしまして！"
            elif "天気" in user_message:
                bot_response = "今日の天気は晴れです！"
            else:
                bot_response = f"「{user_message}」についてですね。申し訳ありません、まだそのトピックについては学習していません。"

            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*', # CORS対応のため
                    'Access-Control-Allow-Methods': 'OPTIONS,POST,GET',
                    'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'
                },
                'body': json.dumps({'response': bot_response})
            }
        except Exception as e:
            print(f"Error: {e}")
            return {
                'statusCode': 500,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': 'OPTIONS,POST,GET',
                    'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'
                },
                'body': json.dumps({'error': 'Internal server error', 'details': str(e)})
            }
    ```
    * コードを貼り付けたら、画面右上の「**Deploy**」ボタンをクリックしてコードを保存・デプロイします。

#### 1.2. API Gateway の設定

この手順は前回と変更ありません。

1.  **REST API の作成:**
    * AWSマネジメントコンソールで **API Gateway** サービスに移動します。
    * 「REST API」の下にある「**構築**」をクリックします（または、すでにAPIがある場合は「API を作成」をクリックし、「REST API」を選択して「構築」をクリックします）。
    * 「新しい API」を選択し、「API 名」に「`ChatbotApi`」と入力します。
    * 「**API を作成**」をクリックします。

2.  **リソースの作成 (/chat):**
    * 左側のナビゲーションペインで、作成したAPI名（`ChatbotApi`）が選択されていることを確認します。
    * 「**アクション**」ドロップダウンから「**リソースの作成**」を選択します。
    * 「リソース名」に「`chat`」と入力し、「リソースパス」も自動的に「`chat`」になります。
    * 「**CORS を有効にする**」にチェックを入れます。
    * 「**リソースの作成**」をクリックします。

3.  **POST メソッドの作成:**
    * 作成された「`/chat`」リソースを選択した状態であることを確認します。
    * 「**アクション**」ドロップダウンから「**メソッドの作成**」を選択します。
    * ドロップダウンリストから「**POST**」を選択し、右のチェックマークをクリックします。
    * 「`/chat - POST - セットアップ`」ページで以下を設定します。
        * 「統合タイプ」で「**Lambda プロキシ統合**」を選択します。
        * 「Lambda リージョン」で、Lambda関数を作成したリージョン（例: `ap-northeast-1`）を選択します。
        * 「Lambda 関数」に「`ChatbotBackendFunction`」と入力し始めると、候補が表示されるので選択します。
    * 「**保存**」をクリックします。
    * Lambda関数のパーミッションを追加するかどうか尋ねられたら、「**OK**」をクリックします。

4.  **CORS 設定の確認:**
    * 「`/chat`」リソースを選択した状態であることを確認します。
    * 「**アクション**」ドロップダウンから「**CORS の有効化**」を選択します。
    * デフォルトの設定のまま「**はい、既存の CORS ヘッダーを上書きします**」をクリックします。

5.  **API のデプロイ:**
    * 左側のナビゲーションペインでAPI名（`ChatbotApi`）が選択されていることを確認します。
    * 「**アクション**」ドロップダウンから「**API のデプロイ**」を選択します。
    * 「デプロイされるステージ」で「**新しいステージ**」を選択し、「ステージ名」に「`prod`」と入力します。
    * 「**デプロイ**」をクリックします。
    * デプロイが完了すると、「ステージエディタ」に「**呼び出し URL**」が表示されます。`https://xxxxxxxxxx.execute-api.ap-northeast-1.amazonaws.com/prod/chat` のような形式になります。**この URL を控えておきます。**

---

### 2. フロントエンド (Streamlit on ECS Fargate) の構築

Streamlitアプリケーションの Dockerfile のベースイメージを Python 3.12 に変更します。

#### 2.1. Docker イメージのビルドと ECR へのプッシュ (AWS CloudShell を使用)

1.  **AWS CloudShell の起動:**
    この手順は前回と変更ありません。
    * AWSマネジメントコンソールにサインインし、画面上部のナビゲーションバーにある **CloudShell アイコン**（`>_` のようなマーク）をクリックします。

2.  **必要なファイルの作成:**
    CloudShell ターミナルで以下のコマンドを実行して、`app.py`、`requirements.txt`、`Dockerfile` を作成します。**Dockerfile の `FROM` 行が `python:3.12-slim-buster` に変更されています。**

    ```bash
    mkdir chatbot-frontend
    cd chatbot-frontend

    # app.py の作成 (YOUR_API_GATEWAY_URL は手順1.2の最後に控えたURLに置き換える)
    cat << EOF > app.py
    import streamlit as st
    import requests
    import json

    # API GatewayのエンドポイントURLを設定
    API_GATEWAY_URL = "YOUR_API_GATEWAY_URL"

    st.title("簡易チャットボット")

    # チャット履歴をセッションステートに保持
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # 履歴を表示
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # ユーザーからの入力を受け取る
    if prompt := st.chat_input("メッセージを入力してください"):
        # ユーザーメッセージを履歴に追加して表示
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # API Gatewayを介してLambdaにメッセージを送信
        try:
            response = requests.post(
                API_GATEWAY_URL,
                data=json.dumps({"message": prompt}),
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status() # HTTPエラーがあれば例外を発生させる
            bot_response = response.json().get('response', 'エラーが発生しました。')
        except requests.exceptions.RequestException as e:
            bot_response = f"通信エラーが発生しました: {e}"
        except json.JSONDecodeError:
            bot_response = "バックエンドからの応答を解析できませんでした。"
        except Exception as e:
            bot_response = f"予期せぬエラーが発生しました: {e}"

        # ボットの応答を履歴に追加して表示
        st.session_state.messages.append({"role": "assistant", "content": bot_response})
        with st.chat_message("assistant"):
            st.markdown(bot_response)
    EOF

    # requirements.txt の作成
    cat << EOF > requirements.txt
    streamlit==1.36.0
    requests==2.32.3
    EOF

    # Dockerfile の作成 (Python 3.12 に変更)
    cat << EOF > Dockerfile
    # ベースイメージ
    FROM python:3.12-slim-buster

    # 作業ディレクトリを設定
    WORKDIR /app

    # 依存関係をインストール
    COPY requirements.txt .
    RUN pip install --no-cache-dir -r requirements.txt

    # アプリケーションコードをコピー
    COPY app.py .

    # Streamlitのポート (8501) を公開
    EXPOSE 8501

    # Streamlitアプリケーションを実行
    CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
    EOF
    ```
    **重要:** `app.py` の `API_GATEWAY_URL` を、手順1.2の最後に控えたAPI GatewayのURLに**必ず置き換えてください**。

3.  **ECR リポジトリの作成:**
    この手順は前回と変更ありません。
    * AWSマネジメントコンソールで **ECR** サービスに移動します。
    * 「**リポジトリを作成**」をクリックします。
    * 「可視性設定」で「**プライベート**」を選択します。
    * 「リポジトリ名」に「`chatbot-frontend`」と入力します。
    * 「**リポジトリを作成**」をクリックします。
    * 作成されたリポジトリの「**URI**」（例: `xxxxxxxxxxxx.dkr.ecr.ap-northeast-1.amazonaws.com/chatbot-frontend`）を控えておきます。

4.  **Docker イメージのビルドとプッシュ (CloudShell ターミナルで実行):**
    CloudShell ターミナルで `chatbot-frontend` ディレクトリにいることを確認し、以下のコマンドを順番に実行します。

    ```bash
    # ECR にログイン
    # <YOUR_ECR_REPOSITORY_URI_PREFIX> は、ECRリポジトリURIの「dkr.ecr.」より前の部分です。
    aws ecr get-login-password --region <あなたのAWSリージョン> | docker login --username AWS --password-stdin <YOUR_ECR_REPOSITORY_URI_PREFIX>

    # Docker イメージをビルド
    docker build -t chatbot-frontend .

    # タグ付け
    # <YOUR_ECR_REPOSITORY_URI> は、ECRで作成したリポジトリのURI全体です。
    docker tag chatbot-frontend:latest <YOUR_ECR_REPOSITORY_URI>:latest

    # ECR にプッシュ
    docker push <YOUR_ECR_REPOSITORY_URI>:latest
    ```
    * `<あなたのAWSリージョン>` は、例えば `ap-northeast-1` のようにご自身のリージョンに置き換えてください。
    * `<YOUR_ECR_REPOSITORY_URI_PREFIX>` は、ECRリポジトリURIの `dkr.ecr.` より前の部分（例: `123456789012.dkr.ecr.ap-northeast-1.amazonaws.com`）に置き換えてください。
    * `<YOUR_ECR_REPOSITORY_URI>` は、ECRで作成したリポジトリのURI全体（例: `123456789012.dkr.ecr.ap-northeast-1.amazonaws.com/chatbot-frontend`）に置き換えてください。

#### 2.2. ECS Fargate へのデプロイ (AWS マネジメントコンソール)

この手順は前回と変更ありません。

1.  **IAM ロールの作成 (ECS タスク実行ロールとタスクロール):**
    * **ECS タスク実行ロール:**
        * IAMサービスで「`ecsTaskExecutionRole`」という名前でロールを作成し、「`AmazonECSTaskExecutionRolePolicy`」ポリシーをアタッチします。
    * **ECS タスクロール (オプション):**
        * IAMサービスで「`ecsTaskRole`」という名前でロールを作成します（ポリシーはアタッチ不要）。

2.  **VPC とサブネットの確認:**
    * AWSマネジメントコンソールで **VPC** サービスに移動し、使用するVPCのIDと、少なくとも2つのアベイラビリティゾーンにまたがるサブネットIDを控えておきます。

3.  **セキュリティグループの作成:**
    * AWSマネジメントコンソールで **EC2** サービスに移動し、「**セキュリティグループ**」を選択します。
    * 「`ChatbotFrontendSG`」という名前でセキュリティグループを作成し、使用するVPCを選択します。
    * **インバウンドルール**として、タイプ「**カスタム TCP**」、ポート範囲「`8501`」、ソース「**どこでも (IPv4)** (`0.0.0.0/0`)」を追加します。作成されたセキュリティグループIDを控えておきます。

4.  **ECS クラスターの作成:**
    * AWSマネジメントコンソールで **ECS** サービスに移動します。
    * 「**クラスターの作成**」をクリックし、「**Fargate (サーバーレス)**」を選択。
    * 「クラスター名」に「`ChatbotFrontendCluster`」と入力し、「**作成**」します。

5.  **タスク定義の作成:**
    * ECSサービスで「**タスク定義**」を選択し、「**新しいタスク定義の作成**」をクリックします。
    * 「起動タイプ」で「**Fargate**」を選択します。
    * 「タスク定義名」に「`chatbot-frontend-task`」と入力します。
    * 「タスクロール」と「タスク実行ロール」に、手順2.2.1で作成したロールを選択します。
    * 「タスクのサイズ」で「タスクメモリ (MiB)」を `512`、「タスク CPU (vCPU)」を `0.25 vCPU` (256 unit) に設定します。
    * 「**コンテナの追加**」をクリックします。
        * 「コンテナ名」に「`chatbot-frontend`」と入力します。
        * 「イメージ」に、ECRからプッシュしたイメージのURI（例: `xxxxxxxxxxxx.dkr.ecr.ap-northeast-1.amazonaws.com/chatbot-frontend:latest`）を入力します。
        * 「ポートマッピング」に `8501` と入力します。
        * 「**追加**」をクリックします。
    * 「**作成**」をクリックします。

6.  **ECS サービスの作成:**
    * ECSサービスに戻り、「**クラスター**」を選択し、「`ChatbotFrontendCluster`」をクリックします。
    * 「**サービス**」タブを選択し、「**作成**」をクリックします。
    * 「起動タイプ」で「**Fargate**」を選択します。
    * 「タスク定義」で、作成した「`chatbot-frontend-task`」と最新のリビジョンを選択します。
    * 「サービス名」に「`ChatbotFrontendService`」と入力し、「必要なタスク」に `1` を入力します。
    * 「**次のステップ**」をクリックします。
    * **ネットワーク設定:**
        * 「VPC」で、使用するVPCを選択します。
        * 「サブネット」で、ECSタスクを配置する2つ以上のサブネットを選択します。
        * 「セキュリティグループ」で、「**既存のセキュリティグループを選択**」を選択し、先ほど作成した「`ChatbotFrontendSG`」を選択します。
        * 「パブリック IP」で「**ENABLED**」を選択します。
    * 「**次のステップ**」を2回クリックし（ロードバランシングは今回スキップ）、最後の画面で内容を確認し、「**サービスの作成**」をクリックします。

#### 2.3. 動作確認

1.  ECSサービスが起動するまで数分かかります。ECSクラスターの「サービス」タブで、`ChatbotFrontendService` のステータスが「**ACTIVE**」になり、「実行中のタスク」が `1` になるまで待ちます。
2.  「**タスク**」タブに移動し、実行中のタスクのIDをクリックします。
3.  タスクの詳細ページで「**ネットワーク**」セクションを見つけ、「**パブリック IP**」をコピーします。
4.  ブラウザで `http://<パブリックIP>:8501` にアクセスすると、Streamlitのチャットボットアプリケーションが表示されます。メッセージを入力して、Lambdaバックエンドからの応答が返ってくることを確認してください。

---
