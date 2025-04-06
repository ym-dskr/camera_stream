# Raspberry Pi カメラストリーミングサーバー

このプロジェクトは、Raspberry PiカメラモジュールからのビデオをウェブブラウザにリアルタイムでストリーミングするためのFlaskベースのウェブアプリケーションです。

## 機能

- ブラウザベースのライブビデオストリーミング
- Picamera2ライブラリを使用した高効率なキャプチャ
- マルチスレッド処理によるパフォーマンス向上
- レスポンシブなウェブインターフェース
- エラーハンドリングとリトライメカニズム
- systemdを使用した自動起動設定

## 必要条件

- Raspberry Pi (推奨: Raspberry Pi 3 Model B以上)
- Raspberry Piカメラモジュール (V1, V2, または互換カメラ)
- Raspberry Pi OS (以前のRaspbian) Bullseye以上
- Python 3.6以上

## 必要なライブラリ

以下のPythonライブラリが必要です：

```bash
sudo apt update
sudo apt install -y python3-pip python3-picamera2 python3-opencv
pip3 install flask pillow numpy
```

## インストール方法

1. このリポジトリをクローンします：

```bash
git clone https://github.com/yourusername/camera-streaming.git
cd camera-streaming
```

2. 必要なライブラリをインストールします：

```bash
sudo apt update
sudo apt install -y python3-pip python3-picamera2 python3-opencv
pip3 install flask pillow numpy
```

## 使用方法

### 手動起動

以下のコマンドでサーバーを起動します：

```bash
python3 picamera_stream.py
```

サーバーが起動したら、ウェブブラウザで以下のURLにアクセスします： 