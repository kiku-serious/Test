# Lambda関数名: ProcessSingleFileSimpleLambda
# ランタイム: Python 3.9 またはそれ以降

import json

def lambda_handler(event, context):
    print(f"Received a batch containing {len(event)} files for processing.")
    
    processed_files_count = 0
    
    # event はファイルのリスト（バッチ）として渡されることを想定
    for file_info in event:
        s3_bucket = file_info.get('Bucket')
        s3_key = file_info.get('Key')

        if not s3_bucket or not s3_key:
            print(f"Skipping malformed file_info in batch: {file_info}")
            continue

        # ここではS3からのファイル読み込みや外部連携は行いません
        print(f"--- Successfully 'processed' (dummy) S3 file: s3://{s3_bucket}/{s3_key} ---")
        processed_files_count += 1

    print(f"Finished processing batch. Successfully 'processed' {processed_files_count} files in this batch.")

    return {
        'statusCode': 200,
        'body': json.dumps(f'Successfully processed {processed_files_count} files in batch.')
    }
