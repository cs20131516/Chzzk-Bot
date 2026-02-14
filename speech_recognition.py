import whisper
import numpy as np
from config import Config


class SpeechRecognizer:
    """Whisper 기반 음성 인식 클래스"""

    def __init__(self, model_name=None):
        """
        Args:
            model_name: Whisper 모델 이름 (tiny, base, small, medium, large)
        """
        self.model_name = model_name or Config.WHISPER_MODEL
        self.model = None
        self.is_loaded = False

    def load_model(self):
        """Whisper 모델 로딩"""
        if self.is_loaded:
            return

        print(f"Whisper 모델 로딩 중... (모델: {self.model_name})")
        print("처음 실행 시 모델 다운로드로 시간이 걸릴 수 있습니다.")

        try:
            self.model = whisper.load_model(self.model_name)
            self.is_loaded = True
            print("Whisper 모델 로딩 완료")
        except Exception as e:
            print(f"Whisper 모델 로딩 실패: {e}")
            raise

    def transcribe(self, audio_data, language="ko"):
        """
        오디오 데이터를 텍스트로 변환

        Args:
            audio_data: numpy array 형태의 오디오 데이터
            language: 언어 코드 (기본값: ko)

        Returns:
            str: 인식된 텍스트 (실패 시 None)
        """
        if not self.is_loaded:
            self.load_model()

        if audio_data is None or len(audio_data) == 0:
            return None

        try:
            # 오디오 데이터 전처리
            # sounddevice는 (samples, channels) 형태로 반환하므로 flatten 필요
            if len(audio_data.shape) > 1:
                audio_data = audio_data.flatten()

            # float32로 변환 및 정규화
            audio_data = audio_data.astype(np.float32)

            # Whisper는 [-1, 1] 범위를 기대
            max_val = np.abs(audio_data).max()
            if max_val > 0:
                audio_data = audio_data / max_val

            # Whisper 실행
            result = self.model.transcribe(
                audio_data,
                language=language,
                fp16=False,  # CPU에서는 fp16=False 사용
                verbose=False
            )

            text = result["text"].strip()
            return text if text else None

        except Exception as e:
            print(f"음성 인식 실패: {e}")
            return None

    def is_valid_speech(self, text):
        """
        인식된 텍스트가 의미 있는 발화인지 검증

        Args:
            text: 인식된 텍스트

        Returns:
            bool: 유효한 발화 여부
        """
        if not text:
            return False

        # 너무 짧은 텍스트 제외
        if len(text.strip()) < 2:
            return False

        # 반복되는 짧은 소리 제외 (예: "아 아 아", "음 음 음")
        words = text.split()
        if len(words) <= 3 and len(set(words)) == 1:
            return False

        # Whisper가 인식 실패 시 자주 반환하는 패턴 제외
        ignore_patterns = [
            "자막",
            "번역",
            "구독",
            "좋아요",
            "알람",
            "[",
            "]",
            "(",
            ")",
        ]

        for pattern in ignore_patterns:
            if pattern in text:
                return False

        return True

    def __del__(self):
        """소멸자"""
        if self.model:
            del self.model


def test_transcribe(audio_file_path):
    """
    오디오 파일로 음성 인식 테스트

    Args:
        audio_file_path: 테스트할 오디오 파일 경로
    """
    recognizer = SpeechRecognizer()
    recognizer.load_model()

    print(f"\n테스트 파일: {audio_file_path}")

    # 오디오 로드
    import soundfile as sf
    audio_data, sample_rate = sf.read(audio_file_path)

    print(f"샘플레이트: {sample_rate}Hz")
    print(f"오디오 길이: {len(audio_data) / sample_rate:.2f}초")

    # 음성 인식
    print("\n음성 인식 중...")
    text = recognizer.transcribe(audio_data)

    if text:
        print(f"\n인식 결과: {text}")
        print(f"유효성: {'유효' if recognizer.is_valid_speech(text) else '무효'}")
    else:
        print("인식 실패")
