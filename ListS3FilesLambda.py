# Lambda関数名: ListS3FilesLambda
# ランタイム: Python 3.9 またはそれ以降
# 環境変数:
#   - S3_BUCKET_NAME: ご主人様のS3バケット名（例: hikakinmania）
#   - S3_PREFIX: JSONファイルを保存するプレフィックス（例: test/）
#   - BATCH_SIZE: 1回のLambda呼び出しで処理するファイルの数（例: 50） ★ 新しく追加

import os
import json
import boto3

s3_client = boto3.client('s3')

def lambda_handler(event, context):
    s3_bucket_name = os.environ.get('S3_BUCKET_NAME')
    s3_prefix = os.environ.get('S3_PREFIX')
    
    # --- 新しく追加・修正 ---
    batch_size_str = os.environ.get('BATCH_SIZE', '50') # デフォルトは50個
    try:
        batch_size = int(batch_size_str)
    except ValueError:
        print(f"Warning: Invalid BATCH_SIZE environment variable: {batch_size_str}. Using default 50.")
        batch_size = 50
    # --- ここまで追加・修正 ---

    if not s3_bucket_name or not s3_prefix:
        print("Error: S3_BUCKET_NAME or S3_PREFIX environment variables are not set.")
        return {
            'statusCode': 500,
            'errorMessage': 'Configuration error: S3 bucket or prefix not set.'
        }

    all_files = []
    paginator = s3_client.get_paginator('list_objects_v2')
    pages = paginator.paginate(Bucket=s3_bucket_name, Prefix=s3_prefix)

    try:
        for page in pages:
            if 'Contents' in page:
                for obj in page['Contents']:
                    if obj['Key'].endswith('.json') and obj['Size'] > 0:
                        all_files.append({
                            'Bucket': s3_bucket_name,
                            'Key': obj['Key']
                        })
        
        print(f"Found {len(all_files)} JSON files in S3 prefix: s3://{s3_bucket_name}/{s3_prefix}")
        
        # --- ここからバッチ処理のロジックを追加 ---
        batched_file_lists = [
            all_files[i:i + batch_size] for i in range(0, len(all_files), batch_size)
        ]
        
        print(f"Divided into {len(batched_file_lists)} batches of size {batch_size}.")

        return {
            'batches': batched_file_lists, # 'files' の代わりに 'batches' というキーでバッチリストを返す
            'statusCode': 200
        }
        # --- ここまでバッチ処理のロジックを追加 ---

    except Exception as e:
        print(f"Error listing S3 files: {e}")
        return {
            'statusCode': 500,
            'errorMessage': f"Error listing S3 files: {str(e)}"
        }