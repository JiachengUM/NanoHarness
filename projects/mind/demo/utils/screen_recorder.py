import threading
from typing import List
import numpy as np

class ScreenRecorder:
    """
    屏幕录制器类
    
    负责捕获屏幕内容，生成视频文件
    
    属性：
    - is_recording: bool - 录屏状态标志
    - recording_thread: Optional[threading.Thread] - 录屏线程
    - screenshot_interval: float - 截图间隔时间（秒）
    - recording_frames: List[np.ndarray] - 录制的视频帧
    """
    def __init__(self, screenshot_interval: float = 0.1):
        """
        初始化屏幕录制器
        
        参数：
        - screenshot_interval: float - 截图间隔时间（秒），默认 0.1 秒（10fps）
        """
        self.is_recording = False
        self.recording_thread = None
        self.screenshot_interval = screenshot_interval  # 10fps
        self.recording_frames: List[np.ndarray] = []

    def start_recording(self):
        """
        开始录屏
        """
        print("🎬 尝试开始录屏...")
        if not self.is_recording:
            self.is_recording = True
            self.recording_frames = []
            print("🎬 创建录屏线程...")
            self.recording_thread = threading.Thread(target=self._record_terminal)
            self.recording_thread.daemon = True
            self.recording_thread.start()
            print("🎬 录屏线程已启动")
        else:
            print("🎬 录屏已经在进行中")

    def stop_recording(self):
        """
        停止录屏并生成视频
        """
        if self.is_recording:
            self.is_recording = False
            if self.recording_thread:
                self.recording_thread.join(timeout=2)
            self._generate_video()
            print("🎬 录屏完成，视频已生成")

    def _record_terminal(self):
        """
        录制整个屏幕
        """
        import mss
        import cv2
        import numpy as np
        import time
        
        print("🎬 开始录制整个屏幕...")
        
        with mss.mss() as sct:
            # 获取主屏幕
            monitor = sct.monitors[1]
            screen_width = monitor["width"]
            screen_height = monitor["height"]
            print(f"🎬 屏幕分辨率: {screen_width}x{screen_height}")
            
            while self.is_recording:
                try:
                    # 截图整个屏幕
                    screenshot = sct.grab(monitor)
                    frame = np.array(screenshot)
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                    
                    # 保存帧
                    self.recording_frames.append(frame)
                    
                    # 控制帧率
                    time.sleep(self.screenshot_interval)
                except Exception as e:
                    print(f"❌ 录屏错误: {e}")
                    break
        
        print(f"🎬 录制结束，共捕获 {len(self.recording_frames)} 帧")

    def _generate_video(self):
        """
        生成视频文件
        """
        if not self.recording_frames:
            print("❌ 没有录制到帧")
            return
        
        import cv2
        from datetime import datetime
        
        # 生成文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"terminal_demo_{timestamp}.mp4"
        
        # 获取帧大小
        height, width, _ = self.recording_frames[0].shape
        
        # 创建视频 writer
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")  # type: ignore
        out = cv2.VideoWriter(output_file, fourcc, 10, (width, height))
        
        # 写入帧
        for frame in self.recording_frames:
            out.write(frame)
        
        # 释放资源
        out.release()
        
        print(f"🎬 视频已保存为: {output_file}")
