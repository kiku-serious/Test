# Lambda関数名: GenerateDummyS3FilesLambda
# ランタイム: Python 3.9 またはそれ以降
# IAMロール: S3への putObject 権限が必要です (s3:PutObject)
# 環境変数:
#   - TARGET_S3_BUCKET: ご主人様のS3バケット名（例: my-test-data-bucket）
#   - TARGET_S3_PREFIX: JSONファイルを保存するプレフィックス（例: input_json_files/）
#   - NUM_FILES_TO_GENERATE: 生成するファイルの数（例: 2500）

import os
import json
import boto3
import uuid # ユニークなIDを生成するために使います

s3_client = boto3.client('s3')

def lambda_handler(event, context):
    target_bucket = os.environ.get('TARGET_S3_BUCKET')
    target_prefix = os.environ.get('TARGET_S3_PREFIX')
    num_files_str = os.environ.get('NUM_FILES_TO_GENERATE')

    if not target_bucket or not target_prefix or not num_files_str:
        print("Error: Required environment variables are not set.")
        return {
            'statusCode': 500,
            'body': json.dumps('Configuration error: Missing environment variables.')
        }

    try:
        num_files_to_generate = int(num_files_str)
    except ValueError:
        print("Error: NUM_FILES_TO_GENERATE is not a valid number.")
        return {
            'statusCode': 400,
            'body': json.dumps('Invalid NUM_FILES_TO_GENERATE value.')
        }

    print(f"Starting to generate {num_files_to_generate} dummy JSON files into s3://{target_bucket}/{target_prefix}")

    generated_files = []
    for i in range(num_files_to_generate):
        file_id = str(uuid.uuid4()) # ユニークなIDを生成
        file_name = f"data_{i:04d}_{file_id}.json" # 連番とIDを組み合わせたファイル名
        s3_key = f"{target_prefix}{file_name}"

        # 約20KBのダミーJSONデータを作成
        # ダミーのテキストと、適当な数値のリスト（ベクトルを模倣）
        dummy_data = {
            "id": file_id,
            "sequence_number": i,
            "title": f"Dummy Data for File {i}",
            "description": "This is a dummy description for testing purposes. " * 30, # 長めのテキストで約20KBに近づける
            "vector": [float(j) / 1000 for j in range(256)], # 256次元のダミーベクトル
            "timestamp": context.get_remaining_time_in_millis() # タイムスタンプ
        }
        
        json_content = json.dumps(dummy_data, indent=2, ensure_ascii=False) # 見やすいように整形

        try:
            s3_client.put_object(
                Bucket=target_bucket,
                Key=s3_key,
                Body=json_content,
                ContentType='application/json'
            )
            generated_files.append(s3_key)
            if (i + 1) % 100 == 0: # 100ファイルごとに進捗表示
                print(f"Generated {i + 1}/{num_files_to_generate} files...")

        except Exception as e:
            print(f"Error uploading {s3_key} to S3: {e}")
            # エラーが発生しても、残りのファイルの生成を続行するか、ここで中断するかはご判断ください。
            # 今回は続行する形にしています。
            continue

    print(f"Successfully generated {len(generated_files)} dummy JSON files.")
    return {
        'statusCode': 200,
        'body': json.dumps({'generated_files_count': len(generated_files)})
    }