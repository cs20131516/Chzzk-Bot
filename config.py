import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """애플리케이션 설정 관리"""

    # 치지직 API 설정
    CHZZK_CLIENT_ID = os.getenv("CHZZK_CLIENT_ID")
    CHZZK_CLIENT_SECRET = os.getenv("CHZZK_CLIENT_SECRET")
    CHZZK_CHANNEL_ID = os.getenv("CHZZK_CHANNEL_ID")

    # Ollama 설정
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama2")
    OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")

    # Whisper 설정
    WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")

    # 오디오 설정
    AUDIO_SAMPLE_RATE = int(os.getenv("AUDIO_SAMPLE_RATE", "16000"))
    AUDIO_CHUNK_DURATION = int(os.getenv("AUDIO_CHUNK_DURATION", "5"))

    # 채팅 설정
    MIN_SPEECH_LENGTH = int(os.getenv("MIN_SPEECH_LENGTH", "3"))
    RESPONSE_COOLDOWN = int(os.getenv("RESPONSE_COOLDOWN", "10"))

    @classmethod
    def validate(cls):
        """필수 설정값 검증"""
        errors = []

        if not cls.CHZZK_CLIENT_ID:
            errors.append("CHZZK_CLIENT_ID가 설정되지 않았습니다.")

        if not cls.CHZZK_CLIENT_SECRET:
            errors.append("CHZZK_CLIENT_SECRET이 설정되지 않았습니다.")

        if not cls.CHZZK_CHANNEL_ID:
            errors.append("CHZZK_CHANNEL_ID가 설정되지 않았습니다.")

        if errors:
            error_message = "\n".join(errors)
            raise ValueError(f"설정 오류:\n{error_message}\n\n.env 파일을 확인하세요.")

        return True

    @classmethod
    def display(cls):
        """현재 설정 표시 (민감한 정보는 마스킹)"""
        print("=" * 50)
        print("현재 설정:")
        print("=" * 50)
        print(f"Ollama 모델: {cls.OLLAMA_MODEL}")
        print(f"Ollama 호스트: {cls.OLLAMA_HOST}")
        print(f"Whisper 모델: {cls.WHISPER_MODEL}")
        print(f"오디오 샘플레이트: {cls.AUDIO_SAMPLE_RATE}Hz")
        print(f"오디오 청크 길이: {cls.AUDIO_CHUNK_DURATION}초")
        print(f"최소 발화 길이: {cls.MIN_SPEECH_LENGTH}초")
        print(f"응답 쿨다운: {cls.RESPONSE_COOLDOWN}초")
        print(f"치지직 채널 ID: {cls.CHZZK_CHANNEL_ID}")
        print(f"API 자격증명: {'설정됨' if cls.CHZZK_CLIENT_ID else '미설정'}")
        print("=" * 50)
