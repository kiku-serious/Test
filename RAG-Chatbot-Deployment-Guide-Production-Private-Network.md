-----

# RAG-Chatbot-Deployment-Guide-Production-Private-Network

このガイドは、企業内のプライベートネットワーク環境での本番運用を想定したRAG（Retrieval Augmented Generation）チャットシステムのデプロイ手順です。既存のVPC、サブネット、セキュリティグループ、NAT Gateway、およびVPCエンドポイントの利用を前提とし、複数ユーザーの同時使用に対応するため、Application Load Balancer (ALB) とECSサービスオートスケーリングを導入します。

-----

## 全体像と作業の目的

このシステムは、**フロントエンド**と**バックエンド**の2つの主要な部分で構成され、企業内プライベートネットワークでのセキュアな運用を前提とします。

  * **フロントエンド (Streamlit on Amazon ECS Fargate with ALB):**

      * **Streamlit**: ユーザーインターフェースを提供します。
      * **Application Load Balancer (ALB)**: 複数のユーザーからのトラフィックを分散し、ECS Fargateタスクへ安全にルーティングします。**パブリックサブネットに配置されますが、社内ネットワークからのアクセスのみを許可**します。
      * **ECS Fargate**: Streamlitアプリの実行環境。複数ユーザーに対応するため、必要に応じてタスクが自動で増減（オートスケーリング）します。**完全にプライベートサブネットに配置され、パブリックIPは持ちません**。
      * **ECR**: StreamlitアプリのDockerイメージ保管庫。
      * **CloudShell**: DockerイメージのビルドとECRへのプッシュに使用。

  * **バックエンド (AWS Lambda + Amazon API Gateway - プライベートエンドポイント):**

      * **Lambda**: 実際のRAG処理ロジック（Elasticsearch検索、Bedrock呼び出し、DynamoDB操作、CloudWatch Logs記録）を実行します。**プライベートサブネットに配置**され、NAT GatewayやVPCエンドポイント経由で外部サービスにアクセスします。
      * **API Gateway (プライベートエンドポイント)**: フロントエンドからのリクエストをLambdaへ中継します。**VPCエンドポイント経由でのみアクセス可能**となり、インターネットからの直接アクセスをブロックします。

  * **既存ネットワークインフラストラクチャ**:

      * **既存VPC**: 全てのコンポーネントがこのVPC内にデプロイされます。
      * **サブネット**: パブリックサブネット（ALB配置用）とプライベートサブネット（ECSタスク、Lambda、VPCエンドポイント用）を適切に使い分けます。
      * **NAT Gateway**: プライベートサブネットからインターネット上のAWSサービス（Bedrockなど）やオンプレミスElasticsearchへ安全にアウトバウンド接続するために必要です。
      * **VPCエンドポイント**: AWSサービス（API Gateway, Bedrock, DynamoDB, CloudWatch Logs）へのプライベートな接続を提供し、インターネット経由のトラフィックを回避します。

-----

## 構築前の準備 (既存ネットワークインフラストラクチャの確認と情報収集)

このシステムは既存VPC内に構築されるため、まず以下の情報を正確に把握しておきましょう。

1.  **VPC ID**:
      * RAGチャットシステムが配置される**既存のVPC ID**を控えます。
2.  **サブネット ID**:
      * 上記VPC内の「**パブリックサブネット**」（ALB配置用）と「**プライベートサブネット**」（ECSタスク、Lambda、VPCエンドポイント配置用）のIDをそれぞれ複数（推奨: 各2つ以上）控えます。異なるアベイラビリティーゾーンに配置することで高可用性を確保します。
3.  **会社のプライベートIPアドレスレンジ**:
      * 社内ネットワークからのアクセスを許可するために使用する、会社のプライベートIPアドレスレンジ（例: `192.168.0.0/16`, `172.16.0.0/12`, `10.0.0.0/8` など）を把握しておきます。
4.  **オンプレミスElasticsearchのIPアドレス範囲**:
      * Lambdaからのアクセスを許可するために使用する、オンプレミスElasticsearchのIPアドレス範囲を把握しておきます。
5.  **既存のNAT Gateway**:
      * プライベートサブネットからのインターネットへのアウトバウンド通信（ECRからのイメージプル、BedrockなどAWSサービスへのアクセス）のために、**プライベートサブネットのルートテーブルがNAT Gatewayにルーティングされていること**を確認します。NAT Gatewayがパブリックサブネットに配置され、Elastic IPが関連付けられていることを確認してください。もし存在しなければ、別途作成が必要です。
6.  **既存のVPCエンドポイントと関連セキュリティグループ**:
      * API Gatewayプライベートエンドポイント用 (`com.amazonaws.<region>.execute-api` サービス)。
      * Bedrock用（`com.amazonaws.<region>.bedrock` または `com.amazonaws.<region>.bedrock-runtime` サービス）。
      * DynamoDB用（`com.amazonaws.<region>.dynamodb` サービス）。
      * CloudWatch Logs用（`com.amazonaws.<region>.logs` サービス）。
      * これらのVPCエンドポイントのIDと、関連付けられているセキュリティグループIDを控えます。もし存在しなければ、構築時に別途作成が必要です。

-----

## 1\. バックエンド (Lambda + API Gateway - プライベートエンドポイント) の構築

RAG処理の心臓部となるLambdaと、社内からのアクセスのみを許可するAPI Gatewayを設定します。

### 1.1. IAM ロールの作成

**作業の意味**: Lambda関数がAWSの他のサービスにアクセスし、ECSタスクがECRからイメージをプルしたりログを送信したりするための権限を付与します。

1.  **Lambda 実行ロール (`lambda-rag-processor-role-prod`)**:
      * **目的**: Lambda関数がRAG処理に必要なAWSサービス（Bedrock, DynamoDB）、VPC内のリソース、CloudWatch Logsにアクセスするための権限を与えます。
      * AWSマネジメントコンソールにサインインし、**IAM** サービスへ移動します。
      * 左メニューから「**ロール**」を選び、「**ロールを作成**」をクリックします。
      * 「信頼済みエンティティを選択」で「**AWS サービス**」を選択し、「ユースケース」で「**Lambda**」を選んで「**次へ**」をクリックします。
      * 「許可を追加」で以下を検索し、**チェック**を入れて「**次へ**」。
          * `AWSLambdaBasicExecutionRole` (CloudWatch Logsへの基本権限)
          * `AmazonBedrockFullAccess` (Bedrockへのアクセス権限 - **本番では必要最小限に絞るべき**)
          * `AmazonDynamoDBFullAccess` (DynamoDBへのアクセス権限 - **本番では必要最小限に絞るべき**)
          * **`AWSLambdaVPCAccessExecutionRole`** (LambdaがVPC内のリソースにアクセスするために必要な権限)
      * 「ロール名」に「**`lambda-rag-processor-role-prod`**」と入力し、「**ロールを作成**」をクリックします。
      * 作成されたロールの **ARN** を控えておきましょう。
2.  **ECS タスク実行ロール (`ecs-task-execution-role-sg`)**:
      * **目的**: ECSがDockerイメージをECRから取得したり、ログをCloudWatchに送信したりするための権限を与えます。
      * IAMサービスで「**ロールを作成**」。
      * 「AWSサービス」で「Elastic Container Service Task」を選択し、「**次へ**」。
      * 「`AmazonECSTaskExecutionRolePolicy`」を検索し、**チェック**を入れて「**次へ**」。
      * 「ロール名」に「**`ecs-task-execution-role-sg`**」と入力し、「**ロールを作成**」。ARNを控えておきましょう。
3.  **ECS タスクロール (`ecs-task-role-sg`)**:
      * **目的**: ECSタスク内のコンテナ（Streamlitアプリ）が、ALBやAPI GatewayといったAWSサービスにアクセスするための権限を与えます。（今回はAPI Gatewayへのアウトバウンドがメインですが、ALBからのアクセスもこのロール経由で制御されます。）
      * IAMサービスで「**ロールを作成**」。
      * 「AWSサービス」で「Elastic Container Service Task」を選択し、「**次へ**」。
      * 今回は追加のAWSサービス連携は不要なため、ポリシーは**何もアタッチせずに**「**次へ**」。
      * 「ロール名」に「**`ecs-task-role-sg`**」と入力し、「**ロールを作成**」。ARNを控えておきましょう。

-----

### 1.2. セキュリティグループの作成 (ALB, ECSタスク, API Gateway, Lambda連携用)

**作業の意味**: 各コンポーネント間のトラフィックを制御するための仮想ファイアウォールルールを定義します。**以下の順序で作成することで、後続のセキュリティグループが依存するIDを先に取得できます。**

1.  **ALB 用セキュリティグループ (`chatbot-alb-sg`) の作成**:

      * **目的**: 社内ネットワークからALBへのアクセスと、ALBからECSタスクへのアクセスを制御します。
      * AWSマネジメントコンソールで **EC2** へ。左メニュー「**セキュリティグループ**」。
      * 「**セキュリティグループを作成**」をクリック。
      * 「セキュリティグループ名」に「**`chatbot-alb-sg`**」と入力し、「VPC」で**既存のVPC ID**を選択。
      * **インバウンドルール**:
          * タイプ: 「**HTTP**」、ポート範囲: `80`
          * ソース: 「**カスタム**」を選択し、**会社の社内プライベートIPアドレスレンジ**（例: `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`）を許可。
          * 必要であれば、タイプ: 「**HTTPS**」、ポート範囲: `443` も同様に許可。（SSL/TLS終端をALBで行う場合）
      * **アウトバウンドルール**: 後でECSタスク用SGのIDを指定するため、一旦デフォルトの「すべてのトラフィックを許可」のままで「**セキュリティグループを作成**」。（**後でこのアウトバウンドルールを修正します**）
      * 作成されたセキュリティグループIDを控えておきましょう。

2.  **ECS タスク用セキュリティグループ (`streamlit-fargate-task-sg`) の作成**:

      * **目的**: ECS FargateタスクへのアクセスをALBからのみに制限し、バックエンドへのアウトバウンド通信を許可します。
      * AWSマネジメントコンソールで **EC2** へ。左メニュー「**セキュリティグループ**」。
      * 「**セキュリティグループを作成**」をクリック。
      * 「セキュリティグループ名」に「**`streamlit-fargate-task-sg`**」と入力し、「VPC」で**既存のVPC ID**を選択。
      * **インバウンドルール**:
          * タイプ: 「**カスタム TCP**」、ポート範囲: `8080` (Streamlitがリッスンするポート)
          * ソース: 「**カスタム**」を選択し、**`chatbot-alb-sg` のセキュリティグループID**を許可。（ALBからのアクセスのみ許可）
      * **アウトバウンドルール**: 後でAPI GatewayとCloudWatch LogsのVPCエンドポイント用SGのIDを指定するため、一旦デフォルトの「すべてのトラフィックを許可」のままで「**セキュリティグループを作成**」。（**後でこのアウトバウンドルールを修正します**）
      * 作成されたセキュリティグループIDを控えておきましょう。

3.  **API Gateway プライベートエンドポイント用セキュリティグループ (`api-gateway-endpoint-sg`) の確認/作成**:

      * **目的**: API GatewayのVPCエンドポイントへのアクセス元を制御します。ALB用SGからのアクセスのみを許可します。
      * このSGは通常、API GatewayのVPCエンドポイント作成時に自動生成されるか、既にあるVPCエンドポイントに紐付けられています。そのIDを控えておきます。
      * もし存在しない場合は、EC2サービスで「セキュリティグループを作成」し、以下のルールを設定します。
          * 「セキュリティグループ名」に「**`api-gateway-endpoint-sg`**」と入力し、「VPC」で**既存のVPC ID**を選択。
          * **インバウンドルール**:
              * タイプ: 「**HTTPS**」、ポート範囲: `443`
              * 送信元: **`chatbot-alb-sg` のセキュリティグループID**を許可。（ALBからのアクセスのみ許可）
          * **アウトバウンドルール**: デフォルトの「すべてのトラフィックを許可」で「**セキュリティグループを作成**」。
      * 作成されたセキュリティグループIDを控えておきましょう。

4.  **Lambda 関数のセキュリティグループ (`lambda-rag-processor-sg`) の作成**:

      * **目的**: Lambdaがプライベートサブネット内で動作し、オンプレミスElasticsearchやAWSサービス（VPCエンドポイント経由）にアウトバウンド接続できるようにします。
      * AWSマネジメントコンソールで **EC2** へ。左メニュー「**セキュリティグループ**」。
      * 「**セキュリティグループを作成**」をクリック。
      * 「セキュリティグループ名」に「**`lambda-rag-processor-sg`**」と入力し、「VPC」で**既存のVPC ID**を選択。
      * **インバウンドルール**: 通常、特別なインバウンドルールは不要です（API Gatewayからプライベートに呼び出されるため）。デフォルトのまま（ルールなし）でOKです。
      * **アウトバウンドルール**:
          * 「**ルールを追加**」をクリック。
          * オンプレミスElasticsearchへ:
              * タイプ: 「**カスタム TCP**」、ポート範囲: `9200`
              * 送信先: 「**カスタム**」を選択し、**オンプレミスElasticsearchのIPアドレス範囲**を許可。
          * AWSサービスVPCエンドポイントへ（Bedrock, DynamoDB, CloudWatch Logsなど）:
              * タイプ: 「**HTTPS**」、ポート範囲: `443`
              * 送信先: 各AWSサービス（例: `sg-bedrock-vpce`, `sg-dynamodb-vpce`, `sg-cloudwatch-logs-vpce`）の**VPCエンドポイントのセキュリティグループID**をそれぞれ追加。
      * 「**セキュリティグループを作成**」。作成されたセキュリティグループIDを控えておきましょう。

5.  **セキュリティグループのアウトバウンドルールを修正**:

      * **目的**: 依存関係を解決した後に、`chatbot-alb-sg` と `streamlit-fargate-task-sg` のアウトバウンドルールを正確に設定します。
      * **`chatbot-alb-sg` の修正**:
          * EC2コンソールで `chatbot-alb-sg` を選択し、「**アウトバウンドルール**」タブをクリックし、「**ルールを編集**」をクリック。
          * デフォルトで許可されていた「すべてのトラフィック」のルールを**削除**し、「**ルールを追加**」をクリック。
          * タイプ: 「**カスタム TCP**」、ポート範囲: `8080`
          * 送信先: 「**カスタム**」を選択し、**`streamlit-fargate-task-sg` のセキュリティグループID**を許可。
          * 「**変更を保存**」。
      * **`streamlit-fargate-task-sg` の修正**:
          * EC2コンソールで `streamlit-fargate-task-sg` を選択し、「**アウトバウンドルール**」タブをクリックし、「**ルールを編集**」をクリック。
          * デフォルトで許可されていた「すべてのトラフィック」のルールを**削除**し、「**ルールを追加**」をクリック。
          * タイプ: 「**HTTPS**」、ポート範囲: `443`
          * 送信先: 「**カスタム**」を選択し、**`api-gateway-endpoint-sg` のセキュリティグループID**を許可。
          * タイプ: 「**HTTPS**」、ポート範囲: `443`
          * 送信先: **CloudWatch Logs VPCエンドポイントのセキュリティグループID**（`sg-cloudwatch-logs-vpce`）を許可。
          * 「**変更を保存**」。

-----

### 1.3. Lambda 関数の作成（実際のRAG処理ロジック）

**作業の意味**: 実際のRAG処理を実行するLambda関数を、プライベートネットワーク内に配置し、必要な外部サービスに安全に接続できるようにします。

1.  **Lambda 関数の作成**:

      * AWSマネジメントコンソールで **Lambda** サービスへ移動。
      * 「**関数の作成**」をクリック。
      * 「一から作成」を選び、「関数名」に「**`ChatbotBackendFunctionProd`**」と入力。
      * 「ランタイム」で「**Python 3.12**」を選択。
      * 「アーキテクチャ」は「`x86_64`」。
      * 「実行ロール」セクションで「**既存のロールを使用する**」を選択し、先ほど作成した「**`lambda-rag-processor-role-prod`**」を選択。
      * 「**高度な設定**」を展開し、「**VPC**」セクションを設定します。
          * 「VPC」で、**既存のVPC ID**を選択。
          * 「サブネット」で、**プライベートサブネットのIDを複数選択**。
          * 「セキュリティグループ」で、先ほど作成した「**`lambda-rag-processor-sg`**」を選択。
      * 「**関数の作成**」。
      * 関数が作成されたら、コードエディタに以下のPythonコードを貼り付けます。

    <!-- end list -->

    ```python
    import json
    import os
    import requests # Elasticsearch/API Gateway呼び出し用
    # import boto3 # Bedrock, DynamoDBなどにアクセスする場合

    # 環境変数からAPI GatewayのURLを取得 (ALBからAPI Gatewayへの呼び出し)
    # 実際のAPI Gateway URLは、VPCエンドポイント経由の内部FQDNになります
    # 例: https://vpce-xxxxxxxxxxxxxxxxx-<api-id>.execute-api.<region>.amazonaws.com/prod/
    API_GATEWAY_URL = os.environ.get("API_GATEWAY_URL_FOR_LAMBDA", "https://your-private-api-gateway-endpoint.execute-api.your-region.amazonaws.com/prod/")
    # 注意: 上記のURLはAPI Gatewayの「ステージ」画面で確認できるURLとは異なります。
    # VPCエンドポイントのDNS名とAPI Gatewayのカスタムドメイン名（もしあれば）を組み合わせた形になります。
    # 例: https://{vpce-id}-{api-id}.execute-api.{region}.amazonaws.com/prod/


    # Elasticsearchクライアントの初期化 (例)
    # ES_HOST = os.environ.get("ES_HOST", "your-onprem-es-ip:9200")
    # es_client = requests.Session() # requestsを使う場合の簡易例

    def lambda_handler(event, context):
        print(f"Received event: {json.dumps(event)}")

        try:
            body = json.loads(event['body'])
            user_message = body.get('message', '')
            session_id = body.get('session_id', 'default_session') # 会話履歴のためのセッションID

            bot_response = ""

            # --- ここにRAG処理の実際のロジックを記述します ---
            # 1. Elasticsearchでの検索 (例)
            # es_query_result = es_client.post(f"http://{ES_HOST}/_search", json={"query": {"match": {"text": user_message}}}).json()
            # context_data = es_query_result.get("hits", {}).get("hits", [])[0].get("_source", {}).get("content", "") if es_query_result else ""

            # 2. BedrockのLLM呼び出し (例)
            # bedrock_client = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "ap-northeast-1"))
            # prompt = f"ユーザーの質問: {user_message}\n関連情報: {context_data}\n回答:"
            # response = bedrock_client.invoke_model(
            #     body=json.dumps({"prompt": prompt, "max_tokens_to_sample": 200}),
            #     modelId="anthropic.claude-v2",
            #     contentType="application/json",
            #     accept="application/json"
            # )
            # llm_response_body = json.loads(response.get("body").read())
            # bot_response = llm_response_body.get("completion", "LLMからの応答なし")

            # 3. DynamoDBに会話履歴を保存 (例)
            # dynamodb = boto3.resource('dynamodb', region_name=os.environ.get("AWS_REGION", "ap-northeast-1"))
            # table = dynamodb.Table(os.environ.get("DYNAMODB_TABLE_NAME", "ChatHistory"))
            # table.put_item(Item={'session_id': session_id, 'timestamp': str(context.get_remaining_time_in_millis()), 'user_message': user_message, 'bot_response': bot_response})

            # ダミーの応答 (実際のRAG処理を実装するまで)
            if "こんにちは" in user_message:
                bot_response = "こんにちは！何かお手伝いできることはありますか？ (本番環境)"
            elif "ありがとう" in user_message:
                bot_response = "どういたしまして！ (本番環境)"
            elif "天気" in user_message:
                bot_response = "今日の天気は晴れです！ (本番環境)"
            else:
                bot_response = f"「{user_message}」についてですね。申し訳ありません、まだそのトピックについては学習していません。 (本番環境)"

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
            print(f"Error in Lambda: {e}")
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
      * **環境変数**タブで、`API_GATEWAY_URL_FOR_LAMBDA`、`ES_HOST`、`DYNAMODB_TABLE_NAME`、`AWS_REGION` などの環境変数を設定します（実際のRAG処理で必要に応じて）。

-----

### 1.4. API Gateway (プライベートエンド点) の設定

**作業の意味**: 社内からのアクセスのみを許可するAPIエンドポイントを作成し、Lambda関数に連携します。

1.  **API Gateway 用 VPC エンドポイントの確認/作成**:

      * **目的**: API Gatewayへのプライベート接続を確立します。
      * AWSマネジメントコンソールで **VPC** サービスへ移動。
      * 左メニュー「**エンドポイント**」を選択し、「**エンドポイントを作成**」をクリック。
      * 表示された「エンドポイントを作成」画面で、以下の設定を行います。
          * 「名前タグ - オプション」: `api-gateway-vpce-prod` (任意の分かりやすい名前)
          * 「タイプ」: 「**AWS のサービス**」が選択されていることを確認します。
          * 「サービス」の検索バーに「`execute-api`」と入力し、「**`com.amazonaws.<region>.execute-api`**」を探して選択します。（例: `com.amazonaws.ap-northeast-1.execute-api`）
          * 「VPC」: プルダウンから**既存のVPC ID**を選択します。
          * 「サブネット」: **プライベートサブネットのIDを複数選択**します。
          * 「セキュリティグループ」: 「既存のセキュリティグループを選択」を選択し、プルダウンから\*\*手順1.2.3で作成した「`api-gateway-endpoint-sg`」\*\*を選択します。
          * 「ポリシー」: デフォルトの「**フルアクセス**」のまま（「すべてへのフルアクセスを許可」）で問題ありません。
      * すべて設定が完了したら、画面下部にある「**エンドポイントを作成**」をクリックします。
      * 作成されたVPCエンドポイントのID（`vpce-xxxxxxxxxxxxxxxxx`）を控えておきましょう。

2.  **REST API の作成 (プライベートエンドポイント)**:

      * AWSマネジメントコンソールで **API Gateway** サービスへ移動。
      * 「REST APIプライベート」の下にある「**構築**」をクリック。
      * 「API の作成」ページで以下を設定。
          * 「新しい API」を選択。
          * 「API 名」：「**`ChatbotApiProd`**」と入力。
          * 「エンドポイントタイプ」：「**プライベート**」を選択。
          * 「VPC エンドポイント」：プルダウンから先ほど作成/確認したAPI Gateway用VPCエンドポイントのIDを選択。
      * 「**API を作成**」をクリック。

3.  **既存のルートリソース (`/`) の確認**:

      * 左メニューで作成されたAPI名（`ChatbotApiProd`）が選択された状態であることを確認します。
      * リソースツリーにルートリソース「`/`」が存在することを確認。

4.  **POST メソッドの作成 (ルートリソース `/` に対して)**:

      * **現在、リソースツリーでルートリソース「`/`」が選択されていることを確認。**
      * 「**アクション**」ドロップダウンから「**メソッドの作成**」を選択。
      * ドロップダウンリストから「**POST**」を選び、チェックマークをクリック。
      * 「メソッドリクエストの設定」は全て**デフォルト（なし/チェックなし）**。
          * **認可**: **`なし (NONE)`**
          * **リクエストバリデーター**: **`なし`**
          * **API キーは必須です**: **`チェックなし`**
      * 「統合タイプ」で「**Lambda プロキシ統合**」を選択。
      * 「Lambda リージョン」で、Lambda関数を作成したリージョンを選択。
      * 「Lambda 関数」に「**`ChatbotBackendFunctionProd`**」と入力し、候補が表示されるので選択。
      * 「**保存**」。パーミッション追加を求められたら「**OK**」。

5.  **CORS 設定の確認と修正 (ルートリソース `/` に対して)**:

      * **現在、リソースツリーでルートリソース「`/`」が選択されていることを確認。**
      * 右側にある「**CORS を有効にする**」**ボタン**をクリック。
      * 表示される「CORS の設定」画面で、以下に**チェックが入っていることを確認またはチェックを入れます**。
          * **ゲートウェイのレスポンス**: `DEFAULT 4XX`、`DEFAULT 5XX` にチェック。
          * **Access-Control-Allow-Methods**: `OPTIONS`、`POST` にチェック。
          * **Access-Control-Allow-Origin**: 「`*`」（ワイルドカード）が入力されていることを確認。
      * 「**CORS を有効にする**」ボタンをクリックして設定を保存。

6.  **リソースポリシーの設定 (重要)**:

      * **目的**: API Gatewayへのアクセスを、特定のVPCエンドポイント経由のみに制限します。
      * 左メニューでAPI名（`ChatbotApiProd`）を選択。
      * 「**リソースポリシー**」を選択。
      * 以下のポリシーをコピー＆ペーストし、`<region>`, `<account-id>`, `<api-id>`, `<YOUR_VPC_ENDPOINT_ID>` を適切に置き換えます。

    <!-- end list -->

    ```json
    {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Deny",
                "Principal": "*",
                "Action": "execute-api:Invoke",
                "Resource": "arn:aws:execute-api:<region>:<account-id>:<api-id>/*",
                "Condition": {
                    "StringNotEquals": {
                        "aws:SourceVpce": "<YOUR_VPC_ENDPOINT_ID>"
                    }
                }
            },
            {
                "Effect": "Allow",
                "Principal": "*",
                "Action": "execute-api:Invoke",
                "Resource": "arn:aws:execute-api:<region>:<account-id>:<api-id>/*"
            }
        ]
    }
    ```

      * 「**ポリシーを保存**」。

7.  **API のデプロイ**:

      * 左メニューでAPI名（`ChatbotApiProd`）を選択。
      * 「**アクション**」ドロップダウンから「**API のデプロイ**」を選択。
      * 「デプロイされるステージ」で「新しいステージ」を選択し、「ステージ名」に「**`prod`**」と入力。
      * 「**デプロイ**」。
      * デプロイ完了後、表示される「**呼び出し URL**」を控えます。これはALBからアクセスするためのURLです。

-----

## 2\. フロントエンド (Streamlit on ECS Fargate) の構築

StreamlitアプリケーションをDockerコンテナとして動かし、ALB経由で社内公開します。

### 2.1. ECR リポジトリの作成

**作業の意味**: DockerイメージをAWS上で保管するための場所を先に確保します。これにより、後のCloudShellでの操作がスムーズになります。

1.  **目的**: DockerイメージをAWS上に保存するためのプライベートなリポジトリを作成します。
2.  AWSマネジメントコンソールで **ECR** サービスへ移動します。
3.  左メニューから「**リポジトリ**」を選び、「**リポジトリを作成**」をクリックします。
4.  「可視性設定」で「**プライベート**」を選択し、「リポジトリ名」に「**`chatbot-frontend-prod`**」と入力します。
5.  「**リポジトリを作成**」をクリックします。
6.  作成されたリポジトリの **URI** （例: `xxxxxxxxxxxx.dkr.ecr.ap-northeast-1.amazonaws.com/chatbot-frontend-prod`）を**控えておきましょう**。このURIはCloudShellでのDockerコマンドで使用します。

### 2.2. アプリケーションファイルの準備とDockerイメージの作成・プッシュ (ローカルPC + CloudShell)

**作業の意味**: Streamlitアプリのコードと設定ファイルをローカルPCで作成し、CloudShellにアップロードしてDockerイメージをビルド、ECRにプッシュします。ローカルPCにDocker環境は不要です。

1.  **ローカルPCでアプリケーションファイルを作成**:

      * **目的**: Streamlitアプリのコード、必要なライブラリ、Dockerイメージ作成の指示書をローカルで準備します。

      * ローカルPCの任意の場所に `chatbot-frontend-prod` という新しいフォルダを作成します。

      * そのフォルダ内に、以下の3つのファイルを作成し、それぞれの内容を正確にコピー＆ペーストして保存します。

      * **重要**: `app.py` の `API_GATEWAY_URL` は、API Gatewayデプロイ後に取得する**プライベートAPI Gatewayの呼び出し URL**に正確に置き換えてください。これはパブリックなURLではなく、VPCエンドポイントのDNS名を含んだ形式になります。（例: `https://vpce-xxxxxxxxxxxxxxxxx-<api-id>.execute-api.<region>.amazonaws.com/prod/` のような形式です）

      * **`app.py`**

        ```python
        import streamlit as st
        import requests
        import json

        # API GatewayのエンドポイントURLを設定 (プライベートエンドポイントのURL)
        API_GATEWAY_URL = "YOUR_PRIVATE_API_GATEWAY_URL" 

        st.title("RAG チャットボット (本番環境)")

        # チャット履歴をセッションステートに保持
        if "messages" not in st.session_state:
            st.session_state.messages = []

        # 履歴を表示
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

        # ユーザーからの入力を受け取る
        if prompt := st.chat_input("質問を入力してください"):
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

        # StreamlitのポートをECS内部でアクセスされるポート (例: 8080) に変更
        EXPOSE 8080

        # Streamlitアプリケーションを実行
        # --server.port を ALB がヘルスチェックするポート (例: 8080) に合わせる
        CMD ["streamlit", "run", "app.py", "--server.port=8080", "--server.address=0.0.0.0"]
        ```

2.  **AWS CloudShell を起動し、作業ディレクトリを作成**:

      * **目的**: Dockerイメージ作成のための開発環境をブラウザ上で準備し、ファイルをアップロードする場所を作ります。
      * AWSマネジメントコンソールの画面上部にある **CloudShell アイコン**（`>_`）をクリックして起動します。
      * CloudShell ターミナルで、作業ディレクトリを作成します。
        ```bash
        mkdir chatbot-frontend-prod
        ```
        **注**: この時点ではまだこのディレクトリには移動しません。

3.  **CloudShell にアプリケーションファイルをアップロード**:

      * **目的**: ローカルで作成したファイルを、CloudShell内の目的のディレクトリに直接転送します。
      * CloudShellのターミナルウィンドウの右上にある「**アクション**」メニューをクリックし、「**ファイルをアップロード**」を選択します。
      * ダイアログが表示されたら、ローカルPCの「`chatbot-frontend-prod`」フォルダを開き、**`app.py`**, **`requirements.txt`**, **`Dockerfile`** の3つのファイルすべてを選択します。
      * 「**アップロード先のディレクトリ**」には、先ほどCloudShellで作成したディレクトリ名「**`chatbot-frontend-prod`**」を入力します（または、参照して選択します）。
      * 「**アップロード**」ボタンをクリックします。

4.  **CloudShell で作業ディレクトリに移動し、Dockerイメージのビルドとプッシュ**:

      * **目的**: アップロードされたファイルを使ってDockerイメージを作成し、ECRにアップロードします。
      * CloudShell ターミナルで、アップロードしたファイルがあるディレクトリに移動します。
        ```bash
        cd chatbot-frontend-prod
        ```
      * 以下のDockerコマンドを順番に実行します。
          * `<あなたのAWSリージョン>` は、`ap-northeast-1` のようにご自身のリージョンに置き換えます。
          * `<YOUR_ECR_REPOSITORY_URI>` は、手順2.1.6で控えたECRリポジトリのURI全体（例: `xxxxxxxxxxxx.dkr.ecr.ap-northeast-1.amazonaws.com/chatbot-frontend-prod`）です。

    <!-- end list -->

    ```bash
    # ECR にログイン (CloudShell はAWS認証情報が設定済みなので直接実行できます)
    # YOUR_ECR_REPOSITORY_URIは、ECRコンソールでリポジトリを選択し、「プッシュコマンドの表示」をクリックすると表示されるログインコマンドの最後の引数 (レジストリURI全体) を使用してください。
    aws ecr get-login-password --region <あなたのAWSリージョン> | docker login --username AWS --password-stdin <YOUR_ECR_REPOSITORY_URI>

    # Docker イメージをビルド
    docker build -t chatbot-frontend-prod .

    # タグ付け
    docker tag chatbot-frontend-prod:latest <YOUR_ECR_REPOSITORY_URI>:latest

    # ECR にプッシュ
    docker push <YOUR_ECR_REPOSITORY_URI>:latest
    ```

-----

### 2.3. ALB (Application Load Balancer) の作成と設定

**作業の意味**: 複数のユーザーからのトラフィックをECSタスクに分散し、セキュリティ層を追加します。

1.  **ALB の作成**:
      * AWSマネジメントコンソールで **EC2** サービスへ移動。左メニューから「**ロードバランサー**」。
      * 「**ロードバランサーを作成**」をクリックし、「**Application Load Balancer**」の「**作成**」をクリック。
      * **「基本設定」**:
          * 「ロードバランサー名」: `chatbot-alb-prod`
          * 「スキーム」: `internal` を選択（社内ネットワークからのみアクセス可能にするため）。
          * 「IPアドレスタイプ」: `ipv4`
          * 「VPC」: **既存のVPC ID**を選択。
          * 「マッピング」: **パブリックサブネットを複数選択**（ALBをパブリックサブネットに配置することで、社内からのアクセスポイントとします）。
      * **「セキュリティグループ」**:
          * 既存のセキュリティグループから「**`chatbot-alb-sg`**」を選択。
      * **「リスナーとルーティング」**:
          * 「プロトコル」: `HTTP`、ポート: `80` (社内からのアクセスを許可するポート)
          * 「デフォルトアクション」: 「**ターゲットグループを作成**」を選択。
          * **ターゲットグループの作成**:
              * 「ターゲットグループ名」: `chatbot-tg-prod`
              * 「ターゲットタイプ」: 「**IPアドレス**」を選択。（FargateタスクはIPアドレスとして登録されるため）
              * 「プロトコル」: `HTTP`、ポート: `8080` (ECSタスクがStreamlitをリッスンするポート)
              * 「VPC」: **既存のVPC ID**を選択。
              * 「ヘルスチェック」:
                  * 「プロトコル」: `HTTP`
                  * 「パス」: `/` (Streamlitがデフォルトで応答するパス)
                  * 「詳細設定」で「正常しきい値」を `2`、「異常しきい値」を `2`、「タイムアウト」を `5`、「間隔」を `30` 秒に設定。
              * ターゲットグループを作成したら、前のALB作成画面に戻り、作成したターゲットグループを「デフォルトアクション」で選択。
      * **「タグ」**: 必要に応じて追加。
      * 「**ロードバランサーを作成**」をクリック。

-----

### 2.4. ECS クラスターの作成

**作業の意味**: Fargateタスクを実行するための論理的なグループを作成します。

1.  **目的**: Fargateタスクを実行するための論理的なグループを作成します。
2.  AWSマネジメントコンソールで **ECS** サービスへ移動します。左メニューから「**クラスター**」を選択します。
3.  「**クラスターの作成**」をクリックし、「Fargate (サーバーレス)」を選択して「**次のステップ**」をクリックします。
4.  「クラスター名」に「**`ChatbotFrontendClusterProd`**」と入力し、「**作成**」をクリックします。

### 2.5. タスク定義の作成

**作業の意味**: ECSでコンテナを動かすための「設計図」を作成します。CPUやメモリ、Dockerイメージ、コンテナのリッスンポートなどを定義します。

1.  **目的**: ECSでコンテナを動かすための「設計図」を作成します。

2.  ECSサービスで左メニューから「**タスク定義**」を選択します。

3.  「**新しいタスク定義の作成**」をクリックします。

4.  表示された画面で、以下の設定を行います。

      * **タスク定義ファミリー情報**

          * 「タスク定義ファミリー名」: `chatbot-frontend-task-prod`

      * **インフラストラクチャの要件**

          * 「起動タイプ」: 「**AWS Fargate**」を選択します。
          * 「オペレーティングシステム/アーキテクチャ」: 「`Linux/X86_64`」のままにします。
          * 「ネットワークモード」: 「`awsvpc`」のままにします。
          * **タスクサイズ**
              * 「CPU」: 「**`0.25 vCPU`**」（または `256` units）を選択します。（複数ユーザー対応のため、後でタスク数やCPUを増やす検討も必要）
              * 「メモリ」: 「**`0.5 GB`**」（または `512 MiB`）を選択します。

      * **タスクロール**

          * 「タスクロール」: プルダウンから、手順1.1.2で作成した「**`ecs-task-role-sg`**」を選択します。（推奨）
          * 「タスク実行ロール」: プルダウンから、手順1.1.2で作成した「**`ecs-task-execution-role-sg`**」を選択します。

      * **コンテナ - 1**

          * 「**コンテナを追加**」ボタンをクリックします。
          * 表示されたコンテナ設定ダイアログで、以下の設定を行います。
              * 「名前」: `chatbot-frontend-prod`
              * 「イメージ URI」: 手順2.2.4でプッシュしたイメージの **URI** （例: `xxxxxxxxxxxx.dkr.ecr.ap-northeast-1.amazonaws.com/chatbot-frontend-prod:latest`）を入力します。
              * 「必須コンテナ」: 「はい」のままにします。
              * **ポートマッピング**
                  * 「コンテナポート」: `8080` (Streamlitがリッスンし、ALBがトラフィックを転送するポート)
                  * 「プロトコル」: `TCP` のままにします。
                  * 「ポート名」: 空白のままで構いません。
                  * 「アプリケーションプロトコル」: `HTTP` のままにします。
              * **リソース割り当て制限**
                  * 「CPU」: **空欄のままにする**か、`0.25` vCPU を設定します。
                  * 「GPU」: 空欄のままにします。
                  * 「メモリのハード制限」: **`0.5` GB**（または `512` MiB）を設定します。
                  * 「メモリのソフト制限\*\*: **`0.5` GB**（または `512` MiB）を設定します。
              * **ログ記録**
                  * 「ログ収集の使用」: 「**Amazon CloudWatch**」が選択されていることを確認します。
                  * 「ログ設定オプションを追加」セクションで、デフォルトでロググループとリージョンが自動的に設定されるはずです。特に変更の必要はありません。
              * その他のオプション（読み取り専用ルートファイルシステム、環境変数、再起動ポリシー、HealthCheckなど）は、**デフォルトのまま変更しません**。
          * 設定後、コンテナ設定ダイアログの「**追加**」ボタンをクリックします。

      * **ストレージ - オプション**

          * 「エフェメラルストレージ」など、その他のストレージ設定は**デフォルトのまま変更しません**。

      * **モニタリング - オプション**

          * **デフォルトのまま変更しません**。

      * **タグ (オプション)**

          * 必要に応じてタグを追加できますが、必須ではありません。

      * すべて設定が完了したら、画面下部にある「**作成**」ボタンをクリックします。

### 2.6. ECS サービスの作成 (ALBとの連携とプライベートサブネットへの配置)

**作業の意味**: 作成したタスク定義に基づいて、ECSクラスタ内でアプリケーションを継続的に実行・管理します。ALBと連携させ、プライベートサブネットに配置することで、セキュリティとスケーラビリティを確保します。

1.  **目的**: 作成したタスク定義に基づいて、ECSクラスタ内でアプリケーションを継続的に実行・管理します。

2.  AWSマネジメントコンソールで **ECS** サービスへ移動します。左メニューから「**クラスター**」を選び、「`ChatbotFrontendClusterProd`」をクリックします。

3.  「**サービス**」タブを選択し、「**作成**」をクリックします。

4.  「サービスの作成」ページで以下を設定します。

      * **サービスの詳細**

          * 「タスク定義ファミリー」: プルダウンから「**`chatbot-frontend-task-prod`**」を選択します。
          * 「タスク定義のリビジョン」: 「**最新**」のままでOKです。
          * 「サービス名」に「**`ChatbotFrontendServiceProd`**」と入力します。

      * **環境**

          * 「AWS Fargate」: 選択されていることを確認します。
          * 「既存のクラスター」: 「`ChatbotFrontendClusterProd`」が選択されていることを確認します。

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

          * 「サービスタイプ」: 「**レプリカ**」を選択します。
              * **理由**: 指定した数のタスクを維持する一般的なWebサービスに適しています。デーモンは各コンテナインスタンスに1つずつ配置するタイプなので、Fargateでは通常使用しません。
          * 「必要なタスク」: `1` と入力します。（**これは初期値です。後でオートスケーリングを設定します。**）
          * 「アベイラビリティーゾーンの再調整」: **「有効にする」をチェック**します。（本番環境ではAZ間の均等配置が推奨されます。）
          * 「ヘルスチェックの猶予期間」: **`60`** 秒程度に設定します。（Streamlitアプリの起動にかかる時間を考慮）
          * **デプロイオプション**
              * 「デプロイタイプ」: 「**ローリングアップデート**」を選択します。
              * **理由**: サービスを停止せずに新しいバージョンに更新する一般的なデプロイ方法です。ブルー/グリーンデプロイはCodeDeployとの連携が必要で複雑です。
              * 「最小実行タスク %」: **`100`** （デフォルト値のまま。デプロイ中も全タスクを維持）
              * 「最大実行タスク %」: **`200`** （デフォルト値のまま。デプロイ中にタスクを一時的に倍増）
          * **デプロイ不具合の検出**
              * 「Amazon ECS デプロイサーキットブレーカーを使用する」: **チェックを入れる**。
              * 「失敗時のロールバック」: **チェックを入れる**。
              * **理由**: デプロイが失敗した際に自動的にロールバックしてくれるため、サービスへの影響を最小限に抑えられます。
              * 「CloudWatch アラームを使用」: **チェックなし**でOKです。（カスタムアラームを使った高度なデプロイ失敗検出ですが、今回は不要です。）

      * **ネットワーキング**

          * 「VPC」: プルダウンから**既存のVPC ID**を選択します。
          * 「サブネット」: ECSタスクを配置する**プライベートサブネットを複数選択**します。（重要: パブリックIPは持ちません）
          * 「セキュリティグループ」: 「既存のセキュリティグループを使用」を選択し、プルダウンから先ほど作成した「**`streamlit-fargate-task-sg`**」を選択します。
          * 「パブリック IP」で「**オフになっています**」（DISABLED）を選択します。（重要: パブリックIPを割り当てません）

      * **Service Connect - オプション**：**チェックなし**でOKです。（ECS内部でのサービスディスカバリやルーティングを簡素化する機能ですが、今回は単一のフロントエンドサービスなので不要です。）

      * **サービス検出 - オプション**：**チェックなし**でOKです。（Route 53を使った高度なサービスディスカバリ機能ですが、今回はALBを使用するため不要です。）

      * **ロードバランシング - オプション**

          * 「**ロードバランシングを使用**」に**チェックを入れます**。
          * 「ロードバランサーのタイプ」: 「**Application Load Balancer**」を選択。
          * 「ロードバランサー名」: プルダウンから、手順2.3.1で作成した「**`chatbot-alb-prod`**」を選択。
          * 「コンテナ名」: 「`chatbot-frontend-prod`」が選択されていることを確認。
          * 「ポート」: `8080` が表示されていることを確認（Dockerfileの `EXPOSE` と一致）。
          * 「ロードバランサーに追加」をクリック。
          * 「プロダクションリスナー」: プルダウンから、ALBで作成した `80:HTTP` リスナーを選択。（HTTPSを使用する場合は `443:HTTPS` リスナーも）
          * 「ターゲットグループ名」: プルダウンから、ALBで作成した「**`chatbot-tg-prod`**」を選択。
          * 「プロダクションリスナーのロードバランサーでトラフィックをリダイレクトする」: **チェックなし**でOKです。

      * **VPC Lattice - オプション**：**チェックなし**でOKです。（VPC間の高度な接続サービスですが、今回は不要です。）

      * **サービスの自動スケーリング - オプション**

          * **「サービスの自動スケーリングを使用」にチェックを入れます**。
          * 「最小タスク」: `1` （常に1つは起動し、コールドスタートを避ける）
          * 「希望するタスク」: `1`
          * 「最大タスク」: `5` など、同時ユーザー数や負荷に応じて適切な値を設定します。（**複数ユーザー同時使用の考慮点**：この値が同時ユーザー数に対応します。必要に応じて調整してください。）
          * 「**スケーリングポリシーの追加**」をクリック。
              * ポリシータイプ: 「ターゲット追跡スケーリングポリシー」
              * ポリシー名: `CpuUtilizationScaling`
              * メトリクス: 「ECS CPU Utilization」
              * ターゲット値: `70` (%) など、CPU使用率がこの値を超えたらスケールアウトするように設定。（**複数ユーザー同時使用の考慮点**：高負荷時にタスク数を増やすトリガーです。）
              * クールダウン (スケールアウト): `60` 秒
              * クールダウン (スケールイン): `300` 秒
              * 「**作成**」をクリック。
          * 必要に応じて、「**スケジュールされたスケーリングアクション**」を追加し、業務時間帯に最小タスク数を増やす（例: 8:00-18:00は最小2タスクなど）ことで、ピーク時のレスポンスを向上させることも可能です。

      * **ボリューム - オプション**：**チェックなし**でOKです。（タスク内で永続的なストレージが必要な場合に設定しますが、今回は不要です。）

      * **タグ (オプション)**：必要に応じてタグを追加できますが、必須ではありません。

5.  すべての設定が完了したら、画面下部にある「**作成**」ボタンをクリックします。

-----

### 2.7. 動作確認

**作業の意味**: デプロイしたチャットボットが正しく動いているか、社内ネットワークからALBのDNS名を使ってアクセスして確認します。

1.  ALB がプロビジョニングされ、ECS サービスがタスクを起動するまで数分かかります。
2.  AWSマネジメントコンソールで **EC2** サービスへ移動。左メニューから「**ロードバランサー**」。
3.  作成したALB (`chatbot-alb-prod`) の **DNS名** をコピーします。（例: `internal-chatbot-alb-prod-xxxxxxxxxx.ap-northeast-1.elb.amazonaws.com` のような形式）
4.  **社内ネットワークに接続されたPCから**、ブラウザで `http://<コピーしたALBのDNS名>` にアクセスします。（HTTPSを設定した場合は `https://`）
5.  Streamlitのチャットボットアプリケーションが表示されるはずです。メッセージを入力して、Lambdaバックエンドからの応答が返ってくることを確認してください。

<!-- end list -->

```
```
