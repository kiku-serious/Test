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

---

## 目次

1.  [概要](#1-概要)
2.  [前提条件](#2-前提条件)
3.  [アーキテクチャ](#3-アーキテクチャ)
4.  [セットアップ手順](#4-セットアップ手順)
    * [4.1. オンプレミス Elasticsearch の準備](#41-オンプレミス-elasticsearch-の準備)
    * [4.2. IAM ポリシーの作成 (サービス別)](#42-iam-ポリシーの作成-サービス別)
        * [4.2.1. Amazon S3 (読み書き両用)](#421-amazon-s3-読み書き両用)
        * [4.2.2. Amazon Bedrock (InvokeModel)](#422-amazon-bedrock-invokemodel)
        * [4.2.3. Amazon CloudWatch Logs (ログ出力)](#423-amazon-cloudwatch-logs-ログ出力)
        * [4.2.4. Amazon ECR (イメージプル)](#424-amazon-ecr-イメージプル)
        * [4.2.5. CloudShell ユーザー/ロールのためのポリシー (ECR プッシュ権限)](#425-cloudshell-ユーザーロールのためのポリシー-ecr-プッシュ権限)
    * [4.3. IAM ロールの作成とポリシーのアタッチ](#43-iam-ロールの作成とポリシーのアタッチ)
    * [4.4. Python スクリプトと Dockerfile の準備](#44-python-スクリプトと-dockerfile-の準備)
    * [4.5. AWS CloudShell を使った Docker イメージの作成と ECR へのプッシュ](#45-aws-cloudshell-を使った-docker-イメージの作成と-ecr-へのプッシュ)
    * [4.6. AWS Batch の設定](#46-aws-batch-の設定)
        * [4.6.1. コンピューティング環境の作成](#461-コンピューティング環境の作成)
        * [4.6.2. ジョブキューの作成](#462-ジョブキューの作成)
        * [4.6.3. ジョブ定義の作成](#463-ジョブ定義の作成)
5.  [実行手順](#5-実行手順)
6.  [トラブルシューティング](#6-トラブルシューティング)
7.  [クリーンアップ](#7-クリーンアップ)

---

## 1. 概要

このプロジェクトでは、以下のワークフローを AWS Batch を使用して自動化し、オンプレミス Elasticsearch への接続確認を行います。

1.  **Amazon S3:** JSON 形式のデータが保存されます（スクリプトは読み込みを試みますが、ESへのデータ投入は行いません）。
2.  **AWS Batch:** S3 から JSON データを読み込み、オンプレミスの Elasticsearch へ接続確認（ping）を行うカスタムスクリプトを実行します。同時に、将来的な Bedrock モデル呼び出しに必要な権限設定も検証します。
3.  **オンプレミス Elasticsearch:** 接続が成功するかどうかをログに出力します。

これにより、AWS とオンプレミス環境間のネットワーク接続、IAM 権限、および Elasticsearch の基本的な接続設定が適切であることを効率的に検証できます。

---

## 2. 前提条件

* **AWS アカウント**があること。
* **全ての AWS リソース操作は AWS コンソール経由で行います。** AWS CLI は CloudShell 内でのみ使用します。
* オンプレミス Elasticsearch インスタンスへのネットワーク接続が、AWS Batch が実行される EC2 インスタンスから可能であること (**AWS VPC とオンプレミス間の VPN または AWS Direct Connect の接続**が既に確立されている必要があります)。
* 基本的な AWS サービス (S3, IAM, Batch, EC2, ECR, CloudShell) の知識があること。
* オンプレミス Elasticsearch の接続情報 (IP アドレス、ポート、認証情報など) を把握していること。
* **Amazon Bedrock の利用開始のための「モデルアクセス」リクエストが完了していること。** (Bedrock コンソール -> 左メニュー「Model access」から、利用したい埋め込みモデルにアクセスを許可しておく必要があります。例: Titan Embeddings G1 - Text)。

---

## 3. アーキテクチャ
