承知いたしました。AWS Batch のジョブ実行に必要な IAM ロールと、CloudShell から ECR にプッシュする IAM ユーザー/ロールに付与すべきポリシーの JSON 例を記載します。

会社のネットワーク制限により AWS CLI を使えないとのことですので、これらの JSON を AWS コンソールの IAM サービスで「ポリシーの作成」時に「JSON」タブに貼り付けて作成してください。

---

## 4.2. IAM ロールの作成 (JSON 例)

AWS Batch が S3 にアクセスし、CloudShell から ECR にプッシュするために必要な権限を持つ IAM ロールを作成します。**全ての操作は AWS コンソールから行います。**

### 4.2.1. AWS Batch ジョブ実行ロール (`BatchJobExecutionRoleForS3ToOnPremES`) のためのポリシー

このポリシーは、AWS Batch ジョブが S3 からデータを読み込み、CloudWatch Logs にログを書き込むためのものです。Elasticsearch への接続はネットワークレベルで行われるため、IAM ポリシーでは直接制御しません。

1.  **新しい IAM ポリシーを作成します。**
    * AWS コンソールで **IAM** サービスに移動します。
    * 左側のナビゲーションペインで「**ポリシー**」をクリックします。
    * 「**ポリシーの作成**」をクリックします。
    * 「JSON」タブを選択し、以下の JSON を貼り付けます。
    * `your-s3-bucket-name` と `your-aws-region`、`your-account-id` はご自身の環境に合わせて置き換えてください。

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
                ]
            },
            {
                "Effect": "Allow",
                "Action": [
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents"
                ],
                "Resource": "arn:aws:logs:your-aws-region:your-account-id:log-group:/aws/batch/job:*"
            },
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
    * 「次へ」をクリックし、タグを追加（任意）、「次へ」をクリックします。
    * **ポリシー名:** `S3ToEsIndexerBatchJobPolicy` (任意、分かりやすい名前をつけます)
    * 「ポリシーの作成」をクリックします。

2.  **新しい IAM ロールを作成し、上記のポリシーをアタッチします。**
    * AWS コンソールで **IAM** サービスに移動します。
    * 左側のナビゲーションペインで「**ロール**」をクリックします。
    * 「**ロールを作成**」をクリックします。
    * **信頼されたエンティティの種類:** 「**AWS のサービス**」を選択します。
    * **ユースケース:** 「**Batch**」を選択します。
    * 「次へ」をクリックします。
    * **許可の追加:** 検索ボックスに先ほど作成したポリシー名 (`S3ToEsIndexerBatchJobPolicy`) を入力して選択します。
    * 通常、Batch 用途のロールには `AmazonEC2ContainerServiceforEC2Role` もアタッチする必要があります。これも検索して選択してください（もし既になければ）。これは EC2 インスタンスが ECS コンテナインスタンスとして動作するために必要です。
    * 「次へ」をクリックし、タグを追加（任意）、「次へ」をクリックします。
    * **ロール名:** `BatchJobExecutionRoleForS3ToOnPremES` (任意、分かりやすい名前をつけます)
    * 「ロールの作成」をクリックします。

### 4.2.2. CloudShell ユーザー/ロールのためのポリシー (ECR プッシュ権限)

CloudShell は、現在ログインしている IAM ユーザーまたは引き受けている IAM ロールの権限で動作します。そのため、CloudShell で Docker イメージを ECR にプッシュするためには、そのユーザー/ロールに以下の ECR プッシュ権限が付与されている必要があります。

1.  **新しい IAM ポリシーを作成します。**
    * AWS コンソールで **IAM** サービスに移動します。
    * 左側のナビゲーションペインで「**ポリシー**」をクリックします。
    * 「**ポリシーの作成**」をクリックします。
    * 「JSON」タブを選択し、以下の JSON を貼り付けます。
    * `your-aws-region` と `your-account-id` はご自身の環境に合わせて置き換えてください。

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
    * 「次へ」をクリックし、タグを追加（任意）、「次へ」をクリックします。
    * **ポリシー名:** `ECRImagePushPolicyForCloudShell` (任意、分かりやすい名前をつけます)
    * 「ポリシーの作成」をクリックします。

2.  **このポリシーを、CloudShell を利用する IAM ユーザーまたは引き受ける IAM ロールにアタッチします。**
    * AWS コンソールで **IAM** サービスに移動します。
    * 左側のナビゲーションペインで「**ユーザー**」または「**ロール**」をクリックします。
    * CloudShell を利用する対象の IAM ユーザーまたは IAM ロールを選択します。
    * 「**アクセス権限を追加**」をクリックし、「**ポリシーをアタッチ**」を選択します。
    * 検索ボックスに先ほど作成したポリシー名 (`ECRImagePushPolicyForCloudShell`) を入力して選択し、「アクセス権限を追加」をクリックします。

---
