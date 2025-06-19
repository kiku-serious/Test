承知いたしました。会社のネットワーク制約（AWS CLIおよびDocker Desktopの利用不可）を考慮し、AWSマネジメントコンソールとAWS CloudShellのみを利用したチャットボットアプリケーションの全体構築手順を最初から最後までご案内します。

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

## 1. バックエンド (Lambda + API Gateway) の構築

まず、チャットボットの応答ロジックを実装し、それを呼び出すAPIエンドポイントを設定します。

### 1.1. Lambda 関数の作成

1.  **IAM ロールの作成:**
    * AWSマネジメントコンソールにサインインし、**IAM** サービスに移動します。
    * 左側のナビゲーションペインで「**ロール**」を選択し、「**ロールを作成**」をクリックします。
    * 「信頼済みエンティティを選択」で「**AWS サービス**」を選択し、「ユースケース」で「**Lambda**」を選択します。
    * 「**次へ**」をクリックします。
    * 「許可を追加」のページで、検索バーに「`AWSLambdaBasicExecutionRole`」と入力し、表示されたポリシーにチェックを入れます。これはLambda関数がCloudWatch Logsにログを書き込むための基本的な権限です。
    * 「**次へ**」をクリックし、必要であればタグを追加します。
    * 「ロール名」に「`lambda-chatbot-role`」と入力し、「**ロールを作成**」をクリックします。
    * 作成されたロールのARN（例: `arn:aws:iam::xxxxxxxxxxxx:role/lambda-chatbot-role`）を控えておきます。これは後でLambda関数を作成する際に必要です。

2.  **Lambda 関数の作成:**
    * AWSマネジメントコンソールで **Lambda** サービスに移動します。
    * 「**関数の作成**」をクリックします。
    * 「関数の作成」ページで以下を設定します。
        * 「一から作成」を選択します。
        * 「関数名」に「`ChatbotBackendFunction`」と入力します。
        * 「ランタイム」で「**Python 3.9**」を選択します。
        * 「アーキテクチャ」は「`x86_64`」のままにします。
        * 「実行ロール」セクションで「**既存のロールを使用する**」を選択し、ドロップダウンから先ほど作成した「`lambda-chatbot-role`」を選択します。
    * 「**関数の作成**」をクリックします。
    * 関数が作成されたら、コードエディタが表示されます。ここに以下のコードをコピー＆ペーストします。

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

### 1.2. API Gateway の設定

1.  **REST API の作成:**
    * AWSマネジメントコンソールで **API Gateway** サービスに移動します。
    * 「REST API」の下にある「**構築**」をクリックします（または、すでにAPIがある場合は「API を作成」をクリックし、「REST API」を選択して「構築」をクリックします）。
    * 「API の作成」ページで以下を設定します。
        * 「新しい API」を選択します。
        * 「API 名」に「`ChatbotApi`」と入力します。
        * 「API を作成」をクリックします。

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
    * Lambda関数のパーミッションを追加するかどうか尋ねられたら、「**OK**」をクリックします。これにより、API GatewayがLambda関数を呼び出す権限が自動的に追加されます。

4.  **CORS 設定の確認:**
    * 「`/chat`」リソースを選択した状態であることを確認します。
    * 「**アクション**」ドロップダウンから「**CORS の有効化**」を選択します。
    * デフォルトの設定のまま「**はい、既存の CORS ヘッダーを上書きします**」をクリックします。これにより、OPTIONSメソッドが自動的に追加され、CORSヘッダーが適切に設定されます。

5.  **API のデプロイ:**
    * 左側のナビゲーションペインでAPI名（`ChatbotApi`）が選択されていることを確認します。
    * 「**アクション**」ドロップダウンから「**API のデプロイ**」を選択します。
    * 「デプロイされるステージ」で「**新しいステージ**」を選択し、「ステージ名」に「`prod`」と入力します。
    * 「**デプロイ**」をクリックします。
    * デプロイが完了すると、「ステージエディタ」に「**呼び出し URL**」が表示されます。`https://xxxxxxxxxx.execute-api.ap-northeast-1.amazonaws.com/prod/chat` のような形式になります。**この URL を控えておきます。これはフロントエンドからバックエンドを呼び出す際に必要です。**

---

## 2. フロントエンド (Streamlit on ECS Fargate) の構築

StreamlitアプリケーションをDockerコンテナとしてECRにプッシュし、ECS Fargateで実行します。

### 2.1. Docker イメージのビルドと ECR へのプッシュ (AWS CloudShell を使用)

このステップでは、ブラウザベースの **AWS CloudShell** を使用してDockerイメージを作成し、ECRにアップロードします。

1.  **AWS CloudShell の起動:**
    * AWSマネジメントコンソールにサインインし、画面上部のナビゲーションバーにある **CloudShell アイコン**（`>_` のようなマーク）をクリックします。
    * CloudShell 環境が起動するまで数秒から数十秒かかります。ブラウザの下部にターミナルウィンドウが開きます。

2.  **必要なファイルの作成:**
    CloudShell ターミナルで以下のコマンドを実行して、`app.py`、`requirements.txt`、`Dockerfile` を作成します。

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

    # Dockerfile の作成
    cat << EOF > Dockerfile
    # ベースイメージ
    FROM python:3.9-slim-buster

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
    * AWSマネジメントコンソールで **ECR** サービスに移動します。
    * 左側のナビゲーションペインで「**リポジトリ**」を選択し、「**リポジトリを作成**」をクリックします。
    * 「可視性設定」で「**プライベート**」を選択します。
    * 「リポジトリ名」に「`chatbot-frontend`」と入力します。
    * 「**リポジトリを作成**」をクリックします。
    * 作成されたリポジトリの「**URI**」（例: `xxxxxxxxxxxx.dkr.ecr.ap-northeast-1.amazonaws.com/chatbot-frontend`）を控えておきます。

4.  **Docker イメージのビルドとプッシュ (CloudShell ターミナルで実行):**
    CloudShell ターミナルで `chatbot-frontend` ディレクトリにいることを確認し、以下のコマンドを順番に実行します。

    ```bash
    # ECR にログイン
    # <YOUR_ECR_REPOSITORY_URI_PREFIX> は、ECRリポジトリURIの「dkr.ecr.」より前の部分です。
    # 例: 123456789012.dkr.ecr.ap-northeast-1.amazonaws.com の場合、123456789012.dkr.ecr.ap-northeast-1.amazonaws.com
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

    これにより、DockerイメージがECRにプッシュされ、ECSから利用可能になります。

### 2.2. ECS Fargate へのデプロイ (AWS マネジメントコンソール)

StreamlitのDockerイメージをECS Fargateで実行するための設定を行います。

1.  **IAM ロールの作成 (ECS タスク実行ロールとタスクロール):**
    ECSタスクがECRからイメージをプルしたり、CloudWatch Logsにログを書き込んだりするために必要です。

    * **ECS タスク実行ロール:**
        * **IAM** サービスに移動し、「**ロールを作成**」をクリック。
        * 「信頼済みエンティティを選択」で「**AWS サービス**」を選択し、「ユースケース」で「**Elastic Container Service**」の「**Elastic Container Service Task**」を選択。
        * 「**次へ**」をクリック。
        * 「許可を追加」で「`AmazonECSTaskExecutionRolePolicy`」を検索して選択し、チェックを入れます。
        * ロール名に「`ecsTaskExecutionRole`」（既存でなければ）と入力し、「**ロールを作成**」。ARNを控えておく。
    * **ECS タスクロール (オプションですが推奨):**
        * **IAM** サービスに移動し、「**ロールを作成**」をクリック。
        * 「信頼済みエンティティを選択」で「**AWS サービス**」を選択し、「ユースケース」で「**Elastic Container Service**」の「**Elastic Container Service Task**」を選択。
        * 「**次へ**」をクリック。
        * 今回は追加のAWSサービス連携は不要なため、ポリシーはアタッチせず進めます。
        * ロール名に「`ecsTaskRole`」（既存でなければ）と入力し、「**ロールを作成**」。ARNを控えておく。

2.  **VPC とサブネットの確認:**
    * AWSマネジメントコンソールで **VPC** サービスに移動します。
    * 使用するVPCのIDと、少なくとも2つのアベイラビリティゾーンにまたがるサブネットIDを控えておきます。通常、デフォルトVPCが利用可能です。

3.  **セキュリティグループの作成:**
    * AWSマネジメントコンソールで **EC2** サービスに移動し、左側のナビゲーションペインで「**セキュリティグループ**」を選択します。
    * 「**セキュリティグループを作成**」をクリックします。
    * 「セキュリティグループ名」に「`ChatbotFrontendSG`」と入力し、「説明」も入力します。
    * 「VPC」で、使用するVPCを選択します。
    * 「**インバウンドルール**」で「**ルールを追加**」をクリックします。
        * タイプ: 「**カスタム TCP**」
        * ポート範囲: `8501`
        * ソース: 「**どこでも (IPv4)**」(`0.0.0.0/0`)
    * 「**セキュリティグループを作成**」をクリックします。作成されたセキュリティグループIDを控えておきます。

4.  **ECS クラスターの作成:**
    * AWSマネジメントコンソールで **ECS** サービスに移動します。
    * 左側のナビゲーションペインで「**クラスター**」を選択し、「**クラスターの作成**」をクリックします。
    * 「クラスターテンプレートを選択」で「**Fargate (サーバーレス)**」を選択し、「**次のステップ**」をクリックします。
    * 「クラスター名」に「`ChatbotFrontendCluster`」と入力します。
    * その他の設定はデフォルトのまま「**作成**」をクリックします。

5.  **タスク定義の作成:**
    * ECSサービスに戻り、左側のナビゲーションペインで「**タスク定義**」を選択し、「**新しいタスク定義の作成**」をクリックします。
    * 「起動タイプ」で「**Fargate**」を選択し、「**次のステップ**」をクリックします。
    * 「タスク定義名」に「`chatbot-frontend-task`」と入力します。
    * 「タスクロール」で、先ほど作成した「`ecsTaskRole`」（または既存の適切なタスクロール）を選択します。
    * 「タスク実行ロール」で、先ほど作成した「`ecsTaskExecutionRole`」を選択します。
    * 「タスクのサイズ」を設定します。
        * 「タスクメモリ (MiB)」: `512`
        * 「タスク CPU (vCPU)」: `0.25 vCPU` (256 unit)
    * 「**コンテナの追加**」をクリックします。
        * 「コンテナ名」に「`chatbot-frontend`」と入力します。
        * 「イメージ」に、ECRからプッシュしたイメージのURIを入力します（例: `xxxxxxxxxxxx.dkr.ecr.ap-northeast-1.amazonaws.com/chatbot-frontend:latest`）。
        * 「ポートマッピング」に `8501` と入力します。
        * 「**追加**」をクリックします。
    * 一番下までスクロールし、「**作成**」をクリックします。

6.  **ECS サービスの作成:**
    * ECSサービスに戻り、左側のナビゲーションペインで「**クラスター**」を選択し、先ほど作成した「`ChatbotFrontendCluster`」をクリックします。
    * 「**サービス**」タブを選択し、「**作成**」をクリックします。
    * 「サービスの作成」ページで以下を設定します。
        * 「起動タイプ」で「**Fargate**」を選択します。
        * 「タスク定義」で、作成した「`chatbot-frontend-task`」と最新のリビジョンを選択します。
        * 「サービス名」に「`ChatbotFrontendService`」と入力します。
        * 「必要なタスク」に `1` を入力します。
        * 「**次のステップ**」をクリックします。
    * **ネットワーク設定:**
        * 「VPC」で、使用するVPCを選択します。
        * 「サブネット」で、ECSタスクを配置する2つ以上のサブネットを選択します。
        * 「セキュリティグループ」で、「**既存のセキュリティグループを選択**」を選択し、先ほど作成した「`ChatbotFrontendSG`」を選択します。
        * 「パブリック IP」で「**ENABLED**」を選択します。
    * 「**次のステップ**」を2回クリックし（ロードバランシングは今回はスキップします）、最後の画面で内容を確認し、「**サービスの作成**」をクリックします。

### 2.3. 動作確認

1.  ECSサービスが起動するまで数分かかります。ECSクラスターの「サービス」タブで、`ChatbotFrontendService` のステータスが「**ACTIVE**」になり、「実行中のタスク」が `1` になるまで待ちます。
2.  「**タスク**」タブに移動し、実行中のタスクのIDをクリックします。
3.  タスクの詳細ページで「**ネットワーク**」セクションを見つけ、「**パブリック IP**」をコピーします。
4.  ブラウザで `http://<パブリックIP>:8501` にアクセスすると、Streamlitのチャットボットアプリケーションが表示されます。メッセージを入力して、Lambdaバックエンドからの応答が返ってくることを確認してください。

---

## トラブルシューティングのヒント

* **Lambdaログの確認:** Lambda関数がエラーを返した場合、**CloudWatch Logs** でLambda関数のロググループ（`/aws/lambda/ChatbotBackendFunction`）を確認してください。
* **API Gatewayログの確認:** API Gatewayの統合エラーは、**CloudWatch Logs** のAPI Gatewayロググループで確認できます。API Gatewayのステージ設定でログ記録を有効にすることが推奨されます。
* **ECSタスクログの確認:** ECSタスクが起動しない、またはエラーになる場合、**CloudWatch Logs** でECRコンテナのロググループ（`/ecs/chatbot-frontend`）を確認してください。タスク定義で指定したロググループです。
* **セキュリティグループの確認:** 各コンポーネント間の通信が正しく許可されているか、セキュリティグループのインバウンド/アウトバウンドルールを確認してください。特にStreamlitへのアクセス（8501ポート）が許可されているか重要です。
* **API Gateway URLの確認:** `app.py` に記述したAPI GatewayのURLが正しいか、再度確認してください。末尾の`/`も重要です。

この詳細な手順で、会社のネットワーク制約下でもAWS上でチャットボットアプリケーションを構築し、慣れていくことができるはずです。もし途中で不明な点があれば、お気軽にご質問ください。
