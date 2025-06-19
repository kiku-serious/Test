Current time is Thursday, June 19, 2025 at 7:49:13 PM JST.

承知いたしました！サービス別に必要なIAMポリシーのJSON例を順に提示していきますね。

まずは、前回の S3 読み取り権限に続き、**Amazon Bedrock (InvokeModel)**、**CloudWatch Logs**、そして **ECR (イメージプル)** のためのポリシーをそれぞれ独立して提供します。

---

## サービス別 IAM ポリシー (JSON 例)

### 1. Amazon S3 (読み取り専用)

このポリシーは、AWS Batch ジョブが指定された S3 バケットから JSON ファイルを読み取るために必要な最小限の権限を提供します。

**ポリシー名:** `S3ReadOnlyAccessForBedrockBatch` (任意)

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "s3:GetObject",
                "s3:ListBucket"
            ],
            "Resource": [
                "arn:aws:s3:::your-s3-bucket-name",
                "arn:aws:s3:::your-s3-bucket-name/*"
            }
        ]
    }
}
```

**[重要]** `"your-s3-bucket-name"` の部分を、**実際にJSONファイルが保存されているS3バケットの正確な名前**に置き換えてください。

---

### 2. Amazon Bedrock (InvokeModel)

このポリシーは、Python スクリプトが Amazon Bedrock の埋め込みモデルを呼び出すために必要な権限を提供します。

**ポリシー名:** `BedrockInvokeModelPolicyForBatch` (任意)

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "bedrock:InvokeModel"
            ],
            "Resource": "arn:aws:bedrock:your-aws-region::foundation-model/your-embedding-model-id"
        }
    ]
}
```

**[重要]**
* `"your-aws-region"` の部分を、**Bedrock を利用する AWS リージョン** (例: `us-east-1`, `ap-northeast-1`) に置き換えてください。
* `"your-embedding-model-id"` の部分を、**使用する Bedrock 埋め込みモデルの正確な ID** に置き換えてください。一般的な埋め込みモデル ID の例は以下の通りです:
    * `amazon.titan-embed-text-v1`
    * `cohere.embed-english-v3`
    * `cohere.embed-multilingual-v3`

特定のモデル ID を指定することで、**最小権限の原則**に沿ったよりセキュアな設定になります。

---

### 3. Amazon CloudWatch Logs (ログ出力)

このポリシーは、AWS Batch ジョブが CloudWatch Logs に標準出力やエラーログを書き込むために必要です。

**ポリシー名:** `CloudWatchLogsAccessForBatchJobs` (任意)

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

**[重要]**
* `"your-aws-region"` の部分を、**AWS Batch ジョブを実行する AWS リージョン** に置き換えてください。
* `"your-account-id"` の部分を、**ご自身の AWS アカウント ID** に置き換えてください。

---

### 4. Amazon ECR (イメージプル)

このポリシーは、AWS Batch が Docker イメージを実行するために、ECR からイメージをプル（ダウンロード）するために必要です。

**ポリシー名:** `ECRImagePullAccessForBatch` (任意)

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

**[重要]**
* `"your-aws-region"` の部分を、**ECR リポジトリが存在する AWS リージョン** に置き換えてください。
* `"your-account-id"` の部分を、**ご自身の AWS アカウント ID** に置き換えてください。
* `"repository/s3-to-es-indexer"` は、CloudShell で作成・プッシュした ECR リポジトリ名です。

---

### 次のステップ

これらのポリシーをそれぞれ作成したら、次にこれらのポリシーを Batch ジョブを実行する **IAM ロール (`BatchJobExecutionRoleForS3ToOnPremES`) にアタッチ**することになります。

各ポリシーの作成は、AWS コンソールで **IAM** サービスに移動し、「**ポリシー**」->「**ポリシーの作成**」->「**JSON**」タブで行ってください。

他に何か必要なポリシーはありますか？それとも、次のステップに進みましょうか？
