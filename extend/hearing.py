"""

"""
import os
import threading
import tempfile
import wave
import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel

from pyaudio import paInt16, PyAudio

class BaseHearing:
    def __init__(self, sample_rate: int = 16000, chunk_size: int = 1024):
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.client = PyAudio()

    def start(self):
        self.stream = self.client.open(
            format=paInt16,
            channels=1,
            rate=self.sample_rate,
            input=True,
            frames_per_buffer=self.chunk_size
        )

    def stop(self):
        self.stream.stop_stream()
        self.stream.close()
        self.client.terminate()

    def recognize(self, audio_data: bytes):
        raise NotImplementedError("请在子类中实现 recognize 方法")

    def run(self):
        self.start()
        try:
            while True:
                audio_data = self.stream.read(self.chunk_size, exception_on_overflow=False)
                result = self.recognize(audio_data)
                if result:
                    print(f"识别结果: {result}")
        except KeyboardInterrupt:
            print("🛑 停止识别")
        finally:
            self.stop()


class HearingUsingONNX(BaseHearing):
    def __init__(self, model_path: str, sample_rate: int = 16000, chunk_size: int = 1024):
        super().__init__(model_path, sample_rate, chunk_size)
        pass

    def recognize(self, audio_data):
        """
        使用ONNX模型识别音频数据
        """
        input_data = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
        input_data = input_data.reshape(1, -1)  # 调整形状以适应模型输入
        inputs = {self.session.get_inputs()[0].name: input_data}
        outputs = self.session.run(None, inputs)
        return outputs[0]  # 返回第一个输出结果


class HearingUsingWhisper(BaseHearing):
    def __init__(self, model_size="small", language="zh", beam_size=5,
                 device="cuda", compute_type="int8",
                 sample_rate=16000, chunk_size=1024,
                 block_duration=2):
        super().__init__(sample_rate, chunk_size)
        self.model = WhisperModel(model_size, device=device, compute_type=compute_type)
        self.language = language
        self.beam_size = beam_size
        self.block_duration = block_duration
        self.frames = []
        self.lock = threading.Lock()

    def recognize_block(self, audio_block: np.ndarray):
        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)

        try:
            with wave.open(path, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.sample_rate)
                wf.writeframes((audio_block * 32767).astype(np.int16).tobytes())

            segments, _ = self.model.transcribe(
                path,
                beam_size=self.beam_size,
                language=self.language
            )
            return " ".join([segment.text for segment in segments])
        finally:
            os.remove(path)

    def recognize(self, audio_data: bytes):
        int_data = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
        with self.lock:
            self.frames.append(int_data)

        required_samples = int(self.sample_rate * self.block_duration)
        current_samples = int(sum(len(f) for f in self.frames))

        if current_samples >= required_samples:
            with self.lock:
                block = np.concatenate(self.frames)[:required_samples]
                self.frames = []  # 清空缓存
            return self.recognize_block(block)
        return None
