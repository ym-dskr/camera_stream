#!/usr/bin/env python3
from flask import Flask, Response, render_template
import time
import io
import threading
import os
import picamera2
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__)

# グローバル変数
frame_buffer = None
buffer_lock = threading.Lock()
stop_thread = False

def setup_camera():
    """Picamera2のセットアップ"""
    try:
        from picamera2 import Picamera2
        from libcamera import controls
        
        # Picamera2の初期化
        picam2 = Picamera2()
        
        # ビデオ設定を作成（以前はstill_configurationを使用）
        config = picam2.create_video_configuration(
            main={"size": (640, 480), "format": "RGB888"},
            lores={"size": (320, 240), "format": "YUV420"},
            display="lores"
        )
        picam2.configure(config)
        
        # 自動フォーカス設定
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
    """フレームをキャプチャしてバッファに保存するスレッド"""
    global frame_buffer, stop_thread
    
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
        # カメラを開始
        picam2.start()
        print("カメラの起動に成功しました")
        
        # エンコーダは一度だけ初期化
        encoder = JpegEncoder(q=90)
        
        while not stop_thread:
            # 一時的なストリームを作成
            stream = io.BytesIO()
            
            # キャプチャして直接JPEGとして保存（修正部分）
            picam2.capture_file(stream, format='jpeg')
            
            # ストリームの位置を先頭に戻す
            stream.seek(0)
            
            # バッファに保存
            with buffer_lock:
                frame_buffer = stream.getvalue()
            
            # フレームレート調整
            time.sleep(0.033)  # ~30fps
            
    except Exception as e:
        print(f"フレームキャプチャ中にエラーが発生しました: {e}")
    finally:
        if picam2:
            picam2.close()
        print("カメラキャプチャスレッドを終了します")

def gen_frames():
    """フレームジェネレーター関数"""
    global frame_buffer
    
    # フレームバッファが初期化されるまで待機
    wait_count = 0
    while frame_buffer is None:
        time.sleep(0.5)
        wait_count += 1
        if wait_count > 20:  # 10秒待機
            # 静的エラー画像を生成
            try:
                img = Image.new('RGB', (640, 480), color=(0, 0, 0))
                d = ImageDraw.Draw(img)
                d.text((100, 240), "カメラに接続できません", fill=(255, 255, 255))
                
                img_bytes = io.BytesIO()
                img.save(img_bytes, format='JPEG')
                img_bytes = img_bytes.getvalue()
                
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + img_bytes + b'\r\n')
                return
            except Exception as e:
                print(f"エラー画像の生成に失敗しました: {e}")
                return
    
    # フレームを送信
    while True:
        with buffer_lock:
            if frame_buffer is not None:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_buffer + b'\r\n')
        
        time.sleep(0.033)  # ~30fps

@app.route('/')
def index():
    """メインページを表示"""
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
          // 接続エラーを処理
          function handleImageError() {
            document.getElementById('status').innerHTML = '<span style="color:red">カメラからの映像を取得できません。5秒後に再試行します...</span>';
            setTimeout(function() {
              var img = document.getElementById('stream');
              img.src = '/video_feed?t=' + new Date().getTime();
            }, 5000);
          }
          
          // 定期的に接続状態を更新
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
    """ビデオフィードをストリーミング"""
    return Response(gen_frames(),
                   mimetype='multipart/x-mixed-replace; boundary=frame')

def check_picamera2():
    """picamera2がインストールされているか確認"""
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
    # picamera2の確認
    if not check_picamera2():
        print("picamera2がインストールされていないため、OpenCVを使ったストリーミングに切り替えます")
        try:
            import subprocess
            subprocess.run(["python3", "rtsp_stream.py"])
        except Exception as e:
            print(f"OpenCVストリーミングの起動に失敗しました: {e}")
        exit(0)
    
    # カメラキャプチャスレッドを開始
    camera_thread = threading.Thread(target=capture_frames)
    camera_thread.daemon = True
    camera_thread.start()
    
    print("Raspberry Piカメラストリーミングサーバーを起動します...")
    print("ブラウザで http://<IPアドレス>:5000/ にアクセスしてください")
    
    try:
        app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
    except KeyboardInterrupt:
        print("サーバーを終了します...")
    finally:
        # スレッドを停止
        stop_thread = True
        camera_thread.join(timeout=1.0)
        print("カメラスレッドを終了しました") 