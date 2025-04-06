#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Raspberry Piカメラストリーミングプログラム

このスクリプトは、Raspberry PiカメラモジュールからのビデオストリームをWebブラウザに
リアルタイムで配信するFlaskウェブアプリケーションです。Picamera2ライブラリを使用して
カメラからの映像をキャプチャし、MJPEGストリームとしてブラウザに送信します。

主な機能:
- Picamera2を使用したカメラストリーミング
- マルチスレッドによる効率的な処理
- エラー処理とフォールバックメカニズム
- レスポンシブなWebインターフェース

必要なライブラリ:
- Flask: Webアプリケーションフレームワーク
- Picamera2: Raspberry Piカメラ用ライブラリ
- PIL (Pillow): 画像処理ライブラリ
- OpenCV: コンピュータビジョンライブラリ（バックアップ用）

作成者: yutapi3
作成日: 20250407
"""
from flask import Flask, Response, render_template
import time
import io
import threading
import os
import picamera2  # Picamera2ライブラリをインポート
import cv2  # OpenCVライブラリをインポート（エラー画像生成用）
import numpy as np
from PIL import Image, ImageDraw, ImageFont  # 画像処理用ライブラリ

# Flaskアプリケーションの初期化
app = Flask(__name__)

# グローバル変数
frame_buffer = None  # カメラからのフレームを保存するバッファ
buffer_lock = threading.Lock()  # マルチスレッドでのバッファアクセスを同期するためのロック
stop_thread = False  # スレッド停止用フラグ

def setup_camera():
    """
    Picamera2カメラをセットアップする関数
    
    この関数は以下の処理を行います:
    1. Picamera2ライブラリを初期化
    2. カメラの解像度とフォーマット設定
    3. 自動フォーカス設定（サポートされている場合）
    
    戻り値:
        Picamera2オブジェクト: 初期化に成功した場合
        None: 初期化に失敗した場合
    """
    try:
        # 必要なモジュールをインポート
        from picamera2 import Picamera2
        from libcamera import controls
        
        # Picamera2オブジェクトの初期化
        picam2 = Picamera2()
        
        # ビデオ設定を作成
        # main: 高解像度ストリーム (640x480, RGB888形式)
        # lores: 低解像度ストリーム (320x240, YUV420形式) - 表示用
        config = picam2.create_video_configuration(
            main={"size": (640, 480), "format": "RGB888"},
            lores={"size": (320, 240), "format": "YUV420"},
            display="lores"
        )
        picam2.configure(config)
        
        # 自動フォーカス設定（カメラがサポートしている場合）
        try:
            picam2.set_controls({"AfMode": controls.AfModeEnum.Continuous})
        except Exception as e:
            print(f"自動フォーカス設定中にエラーが発生しました: {e}")
            print("お使いのカメラは自動フォーカスをサポートしていないかもしれません")
        
        return picam2
    except Exception as e:
        print(f"Picamera2の初期化中にエラーが発生しました: {e}")
        return None

def capture_frames():
    """
    カメラからフレームを継続的にキャプチャし、グローバルバッファに保存するスレッド関数
    
    このスレッド関数は以下の処理を行います:
    1. Picamera2ライブラリの確認とインポート
    2. カメラのセットアップと起動
    3. 連続的なフレームのキャプチャ（JPEG形式）
    4. バッファへの保存（スレッドセーフな方法で）
    5. エラー処理とクリーンアップ
    
    グローバル変数:
        frame_buffer: キャプチャしたフレームを保存するバッファ
        stop_thread: スレッド停止用のフラグ
    """
    global frame_buffer, stop_thread
    
    # 必要なライブラリがインストールされているか確認
    try:
        from picamera2 import Picamera2
        from picamera2.encoders import JpegEncoder
        from picamera2.outputs import FileOutput
    except ImportError:
        print("picamera2がインストールされていません。以下のコマンドでインストールしてください:")
        print("sudo apt install -y python3-picamera2")
        return
    
    print("カメラキャプチャスレッドを開始します...")
    
    # カメラのセットアップ
    picam2 = setup_camera()
    if picam2 is None:
        print("カメラの初期化に失敗しました")
        return
    
    try:
        # カメラを起動
        picam2.start()
        print("カメラの起動に成功しました")
        
        # JPEGエンコーダを初期化（品質90%）
        encoder = JpegEncoder(q=90)
        
        # メインループ - stop_threadフラグがTrueになるまで実行
        while not stop_thread:
            # 一時的なバイトストリームを作成
            stream = io.BytesIO()
            
            # 現在のフレームをJPEG形式でキャプチャし、ストリームに保存
            picam2.capture_file(stream, format='jpeg')
            
            # ストリームの読み取り位置を先頭に戻す
            stream.seek(0)
            
            # スレッドセーフにバッファを更新
            with buffer_lock:
                frame_buffer = stream.getvalue()
            
            # フレームレートを約30fpsに制限（0.033秒のスリープ）
            time.sleep(0.033)
            
    except Exception as e:
        print(f"フレームキャプチャ中にエラーが発生しました: {e}")
    finally:
        # カメラリソースのクリーンアップ
        if picam2:
            picam2.close()
        print("カメラキャプチャスレッドを終了します")

def gen_frames():
    """
    ビデオストリーム用のフレームジェネレーター関数
    
    この関数は以下の処理を行います:
    1. カメラバッファからフレームを取得
    2. MJPEGストリーム形式に変換
    3. カメラが利用できない場合のエラー画像生成
    
    戻り値:
        generator: multipart/x-mixed-replace形式のMJPEGストリームデータ
    """
    global frame_buffer
    
    # フレームバッファが初期化されるまで待機
    wait_count = 0
    while frame_buffer is None:
        time.sleep(0.5)  # 0.5秒待機
        wait_count += 1
        if wait_count > 20:  # 10秒経過してもバッファが初期化されない場合
            # エラーメッセージを含む静的イメージを生成
            try:
                # 黒い背景画像を作成
                img = Image.new('RGB', (640, 480), color=(0, 0, 0))
                d = ImageDraw.Draw(img)
                # エラーメッセージを描画
                d.text((100, 240), "カメラに接続できません", fill=(255, 255, 255))
                
                # 画像をJPEG形式のバイトデータに変換
                img_bytes = io.BytesIO()
                img.save(img_bytes, format='JPEG')
                img_bytes = img_bytes.getvalue()
                
                # MJPEG形式でエラー画像を返す
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + img_bytes + b'\r\n')
                return
            except Exception as e:
                print(f"エラー画像の生成に失敗しました: {e}")
                return
    
    # メインストリーミングループ - 継続的にフレームを送信
    while True:
        # スレッドセーフにバッファからフレームを取得
        with buffer_lock:
            if frame_buffer is not None:
                # MJPEG形式でフレームを返す
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_buffer + b'\r\n')
        
        # フレームレートを約30fpsに制限
        time.sleep(0.033)

@app.route('/')
def index():
    """
    メインページを表示するルートハンドラ
    
    HTML, CSS, JavaScriptを含むWebページを返します。
    このページには以下の機能があります:
    - ビデオストリームの表示
    - レスポンシブなデザイン
    - 接続エラー処理とリトライロジック
    - ストリーミング状態の表示
    
    戻り値:
        string: HTMLコンテンツ
    """
    html = """
    <!DOCTYPE html>
    <html>
      <head>
        <title>Raspberry Piカメラストリーミング</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
          body { font-family: Arial, sans-serif; margin: 0; padding: 20px; text-align: center; background-color: #f5f5f5; }
          h1 { color: #333; }
          .video-container { margin: 20px auto; max-width: 800px; background-color: #000; padding: 10px; border-radius: 5px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
          img { width: 100%; border: 1px solid #ddd; }
          .status { color: #666; margin-top: 10px; background-color: #fff; padding: 5px; border-radius: 3px; }
          .info-panel { margin: 20px 0; text-align: left; background-color: #fff; padding: 15px; border-radius: 5px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        </style>
        <script>
          // 接続エラーを処理するJavaScript関数
          function handleImageError() {
            document.getElementById('status').innerHTML = '<span style="color:red">カメラからの映像を取得できません。5秒後に再試行します...</span>';
            setTimeout(function() {
              var img = document.getElementById('stream');
              img.src = '/video_feed?t=' + new Date().getTime();
            }, 5000);
          }
          
          // 定期的に接続状態表示を更新するタイマー
          setInterval(function() {
            var status = document.getElementById('status');
            var dotCount = (status.innerText.match(/\./g) || []).length;
            if (dotCount > 5) {
              status.innerText = 'カメラストリーミング中';
            } else {
              status.innerText = status.innerText + '.';
            }
          }, 1000);
        </script>
      </head>
      <body>
        <h1>Raspberry Piカメラストリーミング</h1>
        <div class="video-container">
          <img id="stream" src="/video_feed" alt="カメラストリーム" onerror="handleImageError()">
        </div>
        <p id="status" class="status">カメラストリーミング中</p>
      </body>
    </html>
    """
    return html

@app.route('/video_feed')
def video_feed():
    """
    ビデオフィードをストリーミングするルートハンドラ
    
    gen_frames()ジェネレーター関数からのMJPEGストリームを返します。
    
    戻り値:
        Response: multipart/x-mixed-replace形式のストリームレスポンス
    """
    return Response(gen_frames(),
                   mimetype='multipart/x-mixed-replace; boundary=frame')

def check_picamera2():
    """
    picamera2ライブラリが利用可能かどうかを確認する関数
    
    戻り値:
        bool: picamera2が利用可能な場合はTrue、そうでない場合はFalse
    """
    try:
        from picamera2 import Picamera2
        print(f"picamera2 が正常にインポートされました")
        return True
    except ImportError:
        print("picamera2 がインストールされていません")
        print("以下のコマンドでインストールしてください:")
        print("sudo apt install -y python3-picamera2")
        return False

if __name__ == '__main__':
    """
    メインエントリーポイント
    
    以下の処理を行います:
    1. picamera2の可用性チェック
    2. カメラキャプチャスレッドの起動
    3. Flaskウェブサーバーの起動
    4. クリーンアップ処理
    """
    # picamera2ライブラリの確認
    if not check_picamera2():
        print("picamera2がインストールされていないため、OpenCVを使ったストリーミングに切り替えます")
        try:
            # 代替のRTSPストリーミングスクリプトを実行
            import subprocess
            subprocess.run(["python3", "rtsp_stream.py"])
        except Exception as e:
            print(f"OpenCVストリーミングの起動に失敗しました: {e}")
        exit(0)
    
    # カメラキャプチャスレッドを開始（デーモンスレッドとして実行）
    camera_thread = threading.Thread(target=capture_frames)
    camera_thread.daemon = True
    camera_thread.start()
    
    print("Raspberry Piカメラストリーミングサーバーを起動します...")
    print("ブラウザで http://<IPアドレス>:5000/ にアクセスしてください")
    
    try:
        # Flaskウェブサーバーを起動（すべてのネットワークインターフェースでリッスン）
        app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
    except KeyboardInterrupt:
        # Ctrl+Cで停止した場合
        print("サーバーを終了します...")
    finally:
        # スレッドを停止して終了処理
        stop_thread = True
        camera_thread.join(timeout=1.0)
        print("カメラスレッドを終了しました") 