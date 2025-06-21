# Streamlit-ECS-Lambda-Chatbot-Quickstart

このガイドは、AWSのデフォルトVPCとパブリックなAPI Gatewayエンドポイントを使用し、Python 3.12で開発環境（`dev` ステージ）に簡易チャットボットをデプロイするためのものです。AWS CLIやDocker DesktopをローカルPCにインストールすることなく、AWSマネジメントコンソールとAWS CloudShellのみで作業が完結します。

---

## 全体像と作業の目的

このシステムは、大きく分けて**バックエンド**と**フロントエンド**の2つの主要な部分で構成されます。

* **バックエンド (AWS Lambda + Amazon API Gateway):**
    * **Lambda**: ユーザーからのメッセージを受け取り、それに応じた返答を生成するPythonコードが動きます。サーバーを管理する必要がなく、コードが実行された分だけ料金がかかります。
    * **API Gateway**: フロントエンドからのリクエストを受け取り、Lambdaに渡して実行させ、その結果をフロントエンドに返します。インターネットからアクセスできるURLを提供します。
* **フロントエンド (Streamlit on Amazon ECS Fargate):**
    * **Streamlit**: Webブラウザで表示される対話画面を提供します。Pythonコードで簡単にユーザーインターフェースが作れます。
    * **ECS Fargate**: Streamlitアプリを動かす実行環境です。コンテナ化されたアプリを、基盤となるサーバーの管理なしで動かすことができます。
    * **ECR**: StreamlitアプリのDockerイメージを保管する場所です。
    * **CloudShell**: Dockerイメージを作成してECRにアップロードするために使います。

---

## 1. バックエンド (Lambda + API Gateway - パブリックエンドポイント) の構築

ユーザーのメッセージを受け取り、応答を返す仕組みを作ります。

### 1.1. Lambda 関数の作成（チャットボットの頭脳）

**作業の意味**: メッセージを受け取って応答するPythonコードをAWS上に配置します。

1.  **IAM ロールの作成**:
    * **目的**: Lambda関数がAWSの他のサービス（ログ記録など）にアクセスするための権限を与えます。
    * AWSマネジメントコンソールにサインインし、**IAM** サービスへ移動します。
    * 左メニューから「**ロール**」を選び、「**ロールを作成**」をクリックします。
    * 「信頼済みエンティティを選択」で「**AWS サービス**」を選択し、「ユースケース」で「**Lambda**」を選んで「**次へ**」をクリックします。
    * 「許可を追加」のページで、検索ボックスに「`AWSLambdaBasicExecutionRole`」と入力し、表示されたポリシーに**チェック**を入れます。これがLambdaがCloudWatch Logsにログを書き込むための基本的な権限です。
    * 「**次へ**」をクリックし、必要であればタグを追加します。
    * 「ロール名」に「**`lambda-chatbot-role-dev`**」と入力し、「**ロールを作成**」をクリックします。
    * 作成されたロールの **ARN** を控えておきましょう。これは後でLambda関数を作成する際に必要になります。

2.  **Lambda 関数の作成**:
    * **目的**: 実際に実行されるPythonコードをサンプルとして配置します。
    * AWSマネジメントコンソールで **Lambda** サービスへ移動します。
    * 「**関数の作成**」をクリックします。
    * 「関数の作成」ページで以下を設定します。
        * 「一から作成」を選択します。
        * 「関数名」に「**`ChatbotBackendFunctionDev`**」と入力します。
        * 「ランタイム」で「**Python 3.12**」を選択します。
        * 「アーキテクチャ」は「`x86_64`」のままにします。
        * 「実行ロール」セクションで「**既存のロールを使用する**」を選択し、ドロップダウンから先ほど作成した「`lambda-chatbot-role-dev`」を選択します。
        * **「高度な設定」は展開せず、そのまま「関数の作成」をクリックします**。
    * 関数が作成されたら、コードエディタが表示されます。ここに以下のPythonコードを貼り付けます。

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

---

### 1.2. API Gateway の設定（チャットボットの窓口）

**作業の意味**: インターネットからアクセス可能なURLを作成し、そのURLへのリクエストをLambda関数に橋渡しするように設定します。ウェブブラウザからのアクセスを許可するCORS設定も行います。

1.  **REST API の作成**:
    * AWSマネジメントコンソールで **API Gateway** サービスへ移動します。
    * 「REST API」の下にある「**構築**」をクリックします。
    * 「API の作成」ページで以下を設定します。
        * 「新しい API」を選択します。
        * 「API 名」に「**`ChatbotApiDev`**」と入力します。
        * 「エンドポイントタイプ」は「エッジ最適化」または「リージョン」（デフォルトでOK）のまま、「**API を作成**」をクリックします。

2.  **既存のルートリソース (`/`) の確認**:
    * **目的**: API作成時に自動的に生成されるルートリソース (`/`) を利用します。このリソースに対して直接メソッドを定義します。
    * 左メニューで作成したAPI名（`ChatbotApiDev`）が選択された状態であることを確認します。

3.  **POST メソッドの作成 (ルートリソース `/` に対して)**:
    * **目的**: APIのルートパス（`/`）へのPOSTリクエストをLambdaに転送する設定をします。
    * **現在、リソースツリーでルートリソース「`/`」が選択されていることを確認します。**
    * その状態で、「**アクション**」ドロップダウンから「**メソッドの作成**」を選択します。
    * ドロップダウンリストから「**POST**」を選び、右のチェックマークをクリックします。
    * 「メソッドリクエストの設定」の各項目は、基本的に**デフォルトのまま変更なし**で進めます。
        * **認可**: **`なし (NONE)`** を選択します。
        * **リクエストバリデーター**: **`なし`** （リクエストの形式検証は不要なため）
        * **API キーは必須です**: **`チェックなし`** （APIキーによる認証は不要なため）
        * その他、URLクエリ文字列パラメータ、HTTPリクエストヘッダー、リクエスト本文も変更不要です。
    * 「統合タイプ」で「**Lambda プロキシ統合**」を選択します。
    * 「Lambda リージョン」で、Lambda関数を作成したリージョンを選択します。
    * 「Lambda 関数」に「`ChatbotBackendFunctionDev`」と入力し始めると、候補が表示されるので選択します。
    * 「**保存**」をクリックします。Lambda関数のパーミッション追加を求められたら「**OK**」をクリックします。

4.  **CORS 設定の確認と修正 (ルートリソース `/` に対して)**:
    * **目的**: Streamlitのようなウェブアプリケーションが異なるドメインからAPIにアクセスできるようにします。
    * **現在、リソースツリーでルートリソース「`/`」が選択されていることを確認します。**
    * その状態で、右側にある「**CORS を有効にする**」**ボタン**をクリックします。
    * 表示される「CORS の設定」画面で、以下に**チェックが入っていることを確認またはチェックを入れます**。
        * **ゲートウェイのレスポンス**:
            * `DEFAULT 4XX`：**チェックを入れる** (4xx系のエラーレスポンスにもCORSヘッダーを含めるため)
            * `DEFAULT 5XX`：**チェックを入れる** (5xx系のエラーレスポンスにもCORSヘッダーを含めるため)
        * **Access-Control-Allow-Methods**:
            * `OPTIONS`：**チェックを入れる** (CORSプリフライトリクエストに必須)
            * `POST`：**チェックを入れる** (あなたのアプリケーションが実際にPOSTリクエストを送信するため)
        * **Access-Control-Allow-Origin**: 「`*`」（ワイルドカード）が入力されていることを確認します。
    * 上記の設定が完了したら、画面下部の「**CORS を有効にする**」ボタンをクリックして設定を保存します。

5.  **API のデプロイ**:
    * **目的**: 設定したAPIをインターネットからアクセスできるように公開します。
    * 左メニューでAPI名（`ChatbotApiDev`）を選択します。
    * 「**アクション**」ドロップダウンから「**API のデプロイ**」を選択します。
    * 「デプロイされるステージ」で「新しいステージ」を選択し、「ステージ名」に「**`dev`**」と入力します。
    * 「**デプロイ**」をクリックします。
    * デプロイ完了後、「ステージエディタ」に表示される「**呼び出し URL**」（例: `https://xxxxxxxxxx.execute-api.ap-northeast-1.amazonaws.com/dev/` のように `/dev/` で終わるURLになります）を控えておきましょう。これはフロントエンドからAPIを呼び出すためのURLです。

---

## 2. フロントエンド (Streamlit on ECS Fargate) の構築

StreamlitアプリケーションをDockerコンテナとして動かし、それを公開します。

### 2.1. ECR リポジトリの作成

**作業の意味**: DockerイメージをAWS上で保管するための場所を確保します。

1.  **目的**: DockerイメージをAWS上に保存するためのプライベートなリポジトリを作成します。
2.  AWSマネジメントコンソールで **ECR** サービスへ移動します。
3.  左メニューから「**リポジトリ**」を選び、「**リポジトリを作成**」をクリックします。
4.  「可視性設定」で「**プライベート**」を選択し、「リポジトリ名」に「**`chatbot-frontend-dev`**」と入力します。
5.  「**リポジトリを作成**」をクリックします。
6.  作成されたリポジトリの **URI** （例: `xxxxxxxxxxxx.dkr.ecr.ap-northeast-1.amazonaws.com/chatbot-frontend-dev`）を控えておきましょう。このURIはCloudShellでのDockerコマンドで使用します。

### 2.2. アプリケーションファイルの準備とDockerイメージの作成・プッシュ (ローカルPC + CloudShell)

**作業の意味**: Streamlitアプリのコードと設定ファイルをローカルPCで作成し、CloudShellにアップロードしてDockerイメージをビルド、ECRにプッシュします。ローカルPCにDocker環境は不要です。

1.  **ローカルPCでアプリケーションファイルを作成**:
    * **目的**: Streamlitアプリのコード、必要なライブラリ、Dockerイメージ作成の指示書をローカルで準備します。
    * ローカルPCの任意の場所に `chatbot-frontend-dev` という新しいフォルダを作成します。
    * そのフォルダ内に、以下の3つのファイルを作成し、それぞれの内容を正確にコピー＆ペーストして保存します。
    * **重要**: `app.py` の `API_GATEWAY_URL` は、バックエンド構築の手順1.2.5で控えたAPI Gatewayの「呼び出し URL」に置き換えてください。 （例: `https://xxxxxxxxxx.execute-api.ap-northeast-1.amazonaws.com/dev`）

    * **`app.py`**
        ```python
        import streamlit as st
        import requests
        import json

        # API GatewayのエンドポイントURLを設定 (パブリックエンドポイントのURL)
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
        ```

    * **`requirements.txt`**
        ```
        streamlit==1.36.0
        requests==2.32.3
        ```

    * **`Dockerfile`**
        ```dockerfile
        # ベースイメージ
        FROM public.ecr.aws/docker/library/python:3.12-bullseye

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
        ```

2.  **AWS CloudShell を起動し、作業ディレクトリを作成**:
    * **目的**: Dockerイメージ作成のための開発環境をブラウザ上で準備し、ファイルをアップロードする場所を作ります。
    * AWSマネジメントコンソールの画面上部にある **CloudShell アイコン**（`>_`）をクリックして起動します。
    * CloudShell ターミナルで、作業ディレクトリを作成します。
        ```bash
        mkdir chatbot-frontend-dev
        ```

3.  **CloudShell にアプリケーションファイルをアップロード**:
    * **目的**: ローカルで作成したファイルを、CloudShell内の目的のディレクトリに直接転送します。
    * CloudShellのターミナルウィンドウの右上にある「**アクション**」メニューをクリックし、「**ファイルをアップロード**」を選択します。
    * ダイアログが表示されたら、ローカルPCの「`chatbot-frontend-dev`」フォルダを開き、**`app.py`**, **`requirements.txt`**, **`Dockerfile`** の3つのファイルすべてを選択します。
    * 「**アップロード先のディレクトリ**」には、先ほどCloudShellで作成したディレクトリ名「**`chatbot-frontend-dev`**」を入力します（または、参照して選択します）。
    * 「**アップロード**」ボタンをクリックします。

4.  **CloudShell で作業ディレクトリに移動し、Dockerイメージのビルドとプッシュ**:
    * **目的**: アップロードされたファイルを使ってDockerイメージを作成し、ECRにアップロードします。
    * 以下のDockerコマンドを順番に実行します。
        * `<あなたのAWSリージョン>` は、`ap-northeast-1` のようにご自身のリージョンに置き換えます。
        * `<YOUR_ECR_REPOSITORY_URI>` は、手順2.1.4で控えたECRリポジトリのURI全体（例: `xxxxxxxxxxxx.dkr.ecr.ap-northeast-1.amazonaws.com/chatbot-frontend-dev`）です。

    ```bash
    # ディレクトリ移動 
    cd chatbot-frontend-dev
    
    #アップロードしたファイルを移動する
    mv ~/app.py ~/chatbot-frontend-dev
    mv ~/Dockerfile ~/chatbot-frontend-dev
    mv ~/requirements.txt ~/chatbot-frontend-dev
      
    # ECR にログイン (CloudShell はAWS認証情報が設定済みなので直接実行できます)
    aws ecr get-login-password --region <あなたのAWSリージョン> | docker login --username AWS --password-stdin <YOUR_ECR_REPOSITORY_URI>

    # Docker イメージをビルド
    docker build -t chatbot-frontend-dev .

    # タグ付け
    docker tag chatbot-frontend-dev:latest <YOUR_ECR_REPOSITORY_URI>:latest

    # ECR にプッシュ
    docker push <YOUR_ECR_REPOSITORY_URI>:latest
    ```

---

### 2.3. ECS Fargate へのデプロイ (AWS マネジメントコンソール)

**作業の意味**: アップロードしたDockerイメージを使ってStreamlitアプリをAWS上で動かし、インターネットからアクセスできるようにします。

1.  **IAM ロールの作成 (ECS タスク実行ロールとタスクロール)**:
    * **目的**: ECSがDockerイメージをECRから取得したり、ログをCloudWatchに送信したりするための権限を与えます。
    * **ECS タスク実行ロール (`ecsTaskExecutionRole`)**:
        * IAMサービスで「**ロールを作成**」します。
        * 「AWSサービス」で「Elastic Container Service Task」を選択し、「**次へ**」をクリックします。
        * 「`AmazonECSTaskExecutionRolePolicy`」を検索し、**チェック**を入れて「**次へ**」をクリックします。
        * ロール名に「**`ecsTaskExecutionRole`**」と入力し、「**ロールを作成**」します。ARNを控えておきましょう。
    * **ECS タスクロール (`ecsTaskRole` - オプション)**:
        * IAMサービスで「**ロールを作成**」します。
        * 「AWSサービス」で「Elastic Container Service Task」を選択し、「**次へ**」をクリックします。
        * ポリシーは**何もアタッチせずに**「**次へ**」をクリックします。
        * ロール名に「**`ecsTaskRole`**」と入力し、「**ロールを作成**」します。ARNを控えておきましょう。

2.  **フロントエンド用セキュリティグループの作成 (`streamlit-fargate-sg-dev`)**:
    * **目的**: Fargateで動くStreamlitアプリへの通信を許可する仮想ファイアウォールを設定します。今回は簡易デプロイのため、**インターネットからのアクセスを許可します。**
    * AWSマネジメントコンソールで **EC2** サービスへ移動します。左メニューから「**セキュリティグループ**」を選択します。
    * 「**セキュリティグループを作成**」をクリックします。
    * 「セキュリティグループ名」に「**`streamlit-fargate-sg-dev`**」と入力します。
    * 「VPC」で「**デフォルトVPC**」を選択します。
    * **インバウンドルール**: 「**ルールを追加**」をクリックします。
        * タイプ: 「**カスタム TCP**」
        * ポート範囲: `8501` (Streamlitが使用するポート)
        * ソース: 「**Anywhere IPv4** (`0.0.0.0/0`)」を選択します。（**注意**: 本番環境ではセキュリティリスクが高いため、特定のIPアドレスに制限すべきです）
    * **アウトバウンドルール**: デフォルトの「すべてのトラフィックを許可」のままでOKです。
    * 「**セキュリティグループを作成**」をクリックします。作成されたセキュリティグループIDを控えておきましょう。

3.  **ECS クラスターの作成**:
    * **目的**: Fargateタスクを実行するための論理的なグループを作成します。
    * AWSマネジメントコンソールで **ECS** サービスへ移動します。左メニューから「**クラスター**」を選択します。
    * 「**クラスターの作成**」をクリックし、「Fargate (サーバーレス)」を選択して「**次のステップ**」をクリックします。
    * 「クラスター名」に「**`ChatbotFrontendClusterDev`**」と入力し、「**作成**」をクリックします。

4.  **タスク定義の作成**:
    * **目的**: ECSでコンテナを動かすための「設計図」を作成します。どのDockerイメージを使うか、CPUやメモリをどれだけ割り当てるかなどを定義します。
    * ECSサービスで左メニューから「**タスク定義**」を選択します。
    * 「**新しいタスク定義の作成**」をクリックします。
    * 表示された画面で、以下の設定を行います。

        * **タスク定義ファミリー情報**
            * 「タスク定義ファミリー名」: `chatbot-frontend-task-dev`

        * **インフラストラクチャの要件**
            * 「起動タイプ」: 「**AWS Fargate**」を選択します。
            * 「オペレーティングシステム/アーキテクチャ」: 「`Linux/X86_64`」のままにします。
            * 「ネットワークモード」: 「`awsvpc`」のままにします。
            * **タスクサイズ**
                * 「CPU」: 「**`0.25 vCPU`**」（または `256` units）を選択します。
                * 「メモリ」: 「**`0.5 GB`**」（または `512 MiB`）を選択します。

        * **タスクロール**
            * 「タスクロール」: プルダウンから、手順2.3.1で作成した「**`ecsTaskRole`**」を選択します。（もし不要な場合は「なし」でも可ですが、推奨です）
            * 「タスク実行ロール」: プルダウンから、手順2.3.1で作成した「**`ecsTaskExecutionRole`**」を選択します。

        * **コンテナ - 1**
            * 「**コンテナを追加**」ボタンをクリックします。
            * 表示されたコンテナ設定ダイアログで、以下の設定を行います。
                * 「名前」: `chatbot-frontend-dev`
                * 「イメージ URI」: 手順2.2.4でプッシュしたイメージの **URI** （例: `xxxxxxxxxxxx.dkr.ecr.ap-northeast-1.amazonaws.com/chatbot-frontend-dev:latest`）を入力します。
                * 「必須コンテナ」: 「はい」のままにします。
                * **ポートマッピング**
                    * 「コンテナポート」: `8501` (Streamlitが使用するポート)
                    * 「プロトコル」: `TCP` のままにします。
                    * 「ポート名」: 空白のままで構いません。
                    * 「アプリケーションプロトコル」: `HTTP` のままにします。
                * **リソース割り当て制限**
                    * 「CPU」: **空欄のままにする**か、`0.25` vCPU を設定します。
                    * 「GPU」: 空欄のままにします。
                    * 「メモリのハード制限」: **`0.5` GB**（または `512` MiB）を設定します。
                    * 「メモリのソフト制限」: **`0.5` GB**（または `512` MiB）を設定します。
                * **ログ記録**
                    * 「ログ収集の使用」: 「**Amazon CloudWatch**」が選択されていることを確認します。
                    * 「ログ設定オプションを追加」セクションで、デフォルトでロググループとリージョンが自動的に設定されるはずです。特に変更の必要はありません。
                * その他のオプション（読み取り専用ルートファイルシステム、環境変数、再起動ポリシー、HealthCheckなど）は、デフォルトのまま変更しません。
            * 設定後、コンテナ設定ダイアログの「**追加**」ボタンをクリックします。

        * **ストレージ - オプション**
            * 「エフェメラルストレージ」など、その他のストレージ設定はデフォルトのまま変更しません。

        * **モニタリング - オプション**
            * デフォルトのまま変更しません。

        * **タグ (オプション)**
            * 必要に応じてタグを追加できますが、必須ではありません。

    * すべての設定が完了したら、画面下部にある「**作成**」ボタンをクリックします。

5.  **ECS サービスの作成**:
    * **目的**: 作成したタスク定義に基づいて、ECSクラスタ内でアプリケーションを継続的に実行・管理します。
    * AWSマネジメントコンソールで **ECS** サービスへ移動します。左メニューから「**クラスター**」を選び、「`ChatbotFrontendClusterDev`」をクリックします。
    * 「**サービス**」タブを選択し、「**作成**」をクリックします。
    * 「サービスの作成」ページで以下を設定します。

        * **サービスの詳細**
            * 「タスク定義ファミリー」: プルダウンから「**`chatbot-frontend-task-dev`**」を選択します。
            * 「タスク定義のリビジョン」: 「**最新**」のままでOKです。
            * 「サービス名」に「**`ChatbotFrontendServiceDev`**」と入力します。

        * **環境**
            * 「AWS Fargate」: 選択されていることを確認します。
            * 「既存のクラスター」: 「`ChatbotFrontendClusterDev`」が選択されていることを確認します。

        * **コンピューティング設定 (アドバンスト)**
            * **コンピューティングオプション**:
                * 「キャパシティープロバイダー戦略」: 「**カスタムを使用 (アドバンスト)**」が選択されていることを確認します。
                * 「キャパシティープロバイダー」: 「**FARGATE**」が選択されていることを確認します。
                * 「ベース」: `0` のままでOKです。
                * 「ウェイト」: `1` のままでOKです。
                * **理由**: Fargate起動タイプを使用する場合、この設定がECSサービスのFargateタスク割り当て方法のデフォルトであり、適切です。
            * 「プラットフォームバージョン」: 「**LATEST**」のままでOKです。
                * **理由**: 最新のプラットフォームバージョンを使用することで、AWSが提供する最新の機能、セキュリティパッチ、バグ修正の恩恵を受けられます。

        * **デプロイ設定**
            * 「サービスタイプ」: 「レプリカ」を選択します。
                * **理由**: 指定した数のタスクを維持する一般的なWebサービスに適しています。デーモンは各コンテナインスタンスに1つずつ配置するタイプなので、Fargateでは通常使用しません。
            * 「必要なタスク」: `1` と入力します。
            * 「アベイラビリティーゾーンの再調整」: 「有効にする」はチェックなしでOKです。（本番環境でAZの均等配置を厳密に管理したい場合に検討しますが、今回は簡易設定のため不要です。）
            * 「ヘルスチェックの猶予期間」: 空欄のままでOKです。（タスクが起動してからヘルスチェックが始まるまでの猶予期間ですが、今回は簡易デプロイなのでデフォルトで問題ありません。）
            * **デプロイオプション**
                * 「デプロイタイプ」: 「**ローリングアップデート**」を選択します。
                * **理由**: サービスを停止せずに新しいバージョンに更新する一般的なデプロイ方法です。ブルー/グリーンデプロイはCodeDeployとの連携が必要で複雑です。
                * 「最小実行タスク %」: **`50`** （デフォルト値のまま）
                * 「最大実行タスク %」: **`200`** （デフォルト値のまま）
                * **理由**: デプロイ中のタスクの数を制御し、サービス停止を避けるための設定です。
            * **デプロイ不具合の検出**
                * 「Amazon ECS デプロイサーキットブレーカーを使用する」: **チェックを入れる**。
                * 「失敗時のロールバック」: **チェックを入れる**。
                * **理由**: デプロイが失敗した際に自動的にロールバックしてくれるため、サービスへの影響を最小限に抑えられます。
                * 「CloudWatch アラームを使用」: チェックなしでOKです。（カスタムアラームを使った高度なデプロイ失敗検出ですが、今回は不要です。）

        * **ネットワーキング**
            * 「VPC」: プルダウンから「**デフォルトVPC**」（`vpc-xxxxxxxxxxxxxxxxxx` のようなもの）を選択します。
            * 「サブネット」: ECSタスクを配置する**デフォルトVPC内のパブリックサブネットを複数選択**します。（通常、デフォルトVPCには各AZにパブリックサブネットが存在します。例: `subnet-xxxxxxxxxx (ap-northeast-1a)` など）
            * 「セキュリティグループ」: 「既存のセキュリティグループを使用」を選択し、プルダウンから先ほど作成した「**`streamlit-fargate-sg-dev`**」を選択します。
            * 「パブリック IP」で「**オンになっています**」（ENABLED）を選択します。

        * **Service Connect - オプション**：チェックなしでOKです。（ECS内部でのサービスディスカバリやルーティングを簡素化する機能ですが、今回は単一のフロントエンドサービスなので不要です。）
        * **サービス検出 - オプション**：チェックなしでOKです。（Route 53を使った高度なサービスディスカバリ機能ですが、今回はパブリックIPで直接アクセスするため不要です。）
        * **ロードバランシング - オプション**：チェックなしでOKです。（Application Load Balancer (ALB) を使用したロードバランシング設定ですが、今回は簡易デプロイでパブリックIPで直接アクセスするため不要です。本番環境では必須です。）
        * **VPC Lattice - オプション**：チェックなしでOKです。（VPC間の高度な接続サービスですが、今回は不要です。）
        * **サービスの自動スケーリング - オプション**：チェックなしでOKです。（今回は希望するタスク数を `1` に固定するため、自動スケーリングは設定しません。）
        * **ボリューム - オプション**：チェックなしでOKです。（タスク内で永続的なストレージが必要な場合に設定しますが、今回は不要です。）
        * **タグ (オプション)**：必要に応じてタグを追加できますが、必須ではありません。

    * すべての設定が完了したら、画面下部にある「**作成**」ボタンをクリックします。

### 2.4. 動作確認

**作業の意味**: デプロイしたチャットボットが正しく動いているか、ブラウザからアクセスして確認します。

1.  ECSサービスが起動するまで数分待ちます。ECSクラスターの「サービス」タブで、`ChatbotFrontendServiceDev` のステータスが「**ACTIVE**」になり、「実行中のタスク」が `1` になるまで待ちます。
2.  「**タスク**」タブに移動し、実行中のタスクの **ID** をクリックします。
3.  タスクの詳細ページで「**ネットワーク**」セクションの「**パブリック IP**」をコピーします。
4.  ブラウザで `http://<コピーしたパブリックIP>:8501` にアクセスすると、Streamlitのチャットボットアプリケーションが表示されるはずです。メッセージを入力して、Lambdaバックエンドからの応答が返ってくることを確認してください。
