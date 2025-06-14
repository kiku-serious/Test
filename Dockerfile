# ベースイメージはPython公式イメージを使用します
FROM python:3.9-slim-buster

# 作業ディレクトリを設定
WORKDIR /app

# 依存関係をインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 新しい要約用の依存関係（必要なら）
# elasticsearchライブラリは sceRagProcessor.py と同じものを使うはずなので、requirements.txt に既に含まれているはず
# requests-ntlm, BeautifulSoup4, urllib3 なども追加する

# Pythonスクリプトをコピー
COPY S3toEsHistoricalIndexer.py .

# スクリプトを実行するコマンドを設定
# このCMDは、Step FunctionsからtaskOverridesで環境変数S3_OBJECT_KEYを渡されることを想定
CMD ["python", "S3toEsHistoricalIndexer.py"]