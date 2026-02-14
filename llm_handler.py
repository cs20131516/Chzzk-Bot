import requests
import json
from collections import deque
from config import Config


class LLMHandler:
    """Ollama 기반 LLM 처리 클래스"""

    def __init__(self, model_name=None, host=None, context_size=5):
        """
        Args:
            model_name: Ollama 모델 이름
            host: Ollama 서버 호스트
            context_size: 유지할 대화 컨텍스트 크기
        """
        self.model_name = model_name or Config.OLLAMA_MODEL
        self.host = host or Config.OLLAMA_HOST
        self.api_url = f"{self.host}/api/generate"
        self.context = deque(maxlen=context_size)
        self.system_prompt = self._get_system_prompt()

    def _get_system_prompt(self):
        """시스템 프롬프트 생성"""
        return """You are a fun Korean viewer participating in Chzzk streaming chat.
Respond naturally and entertainingly to what the streamer says.

CRITICAL RULES - MUST FOLLOW:
- ALWAYS respond in KOREAN ONLY (한글로만 대답)
- Keep it short (under 50 characters)
- Use Korean emoticons (ㅋㅋㅋ, ㅎㅎ, ㄷㄷ, etc.)
- Use casual speech (반말)
- Don't over-praise
- Be natural, not spammy
- Return ONLY the chat message, no explanations

Examples:
Streamer: "오늘 날씨 진짜 좋네요"
Response: "인정ㅋㅋ 날씨 개꿀"

Streamer: "이거 어떻게 깨지?"
Response: "왼쪽으로 가보세요!"

Streamer: "오늘 방송 재미있나요?"
Response: "넵 재밌어요 ㅎㅎ"

Streamer: "쇼 쇼 쇼"
Response: "쇼 하시는구나 ㅋㅋ"

Remember: KOREAN ONLY! Never use English in your response.
"""

    def check_connection(self):
        """Ollama 서버 연결 확인"""
        try:
            response = requests.get(f"{self.host}/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get('models', [])
                model_names = [m['name'] for m in models]

                if self.model_name in model_names or any(self.model_name in name for name in model_names):
                    print(f"Ollama 연결 성공 (모델: {self.model_name})")
                    return True
                else:
                    print(f"모델 '{self.model_name}'을 찾을 수 없습니다.")
                    print(f"사용 가능한 모델: {', '.join(model_names)}")
                    return False
            return False
        except requests.exceptions.RequestException as e:
            print(f"Ollama 서버 연결 실패: {e}")
            print(f"Ollama가 실행 중인지 확인하세요: {self.host}")
            return False

    def add_to_context(self, role, text):
        """
        대화 컨텍스트에 추가

        Args:
            role: 역할 (streamer, bot)
            text: 발화 내용
        """
        self.context.append({"role": role, "text": text})

    def _build_prompt(self, streamer_speech, chat_context=""):
        """
        컨텍스트를 포함한 프롬프트 생성

        Args:
            streamer_speech: 스트리머 발언
            chat_context: 최근 채팅 메시지들

        Returns:
            str: 완성된 프롬프트
        """
        prompt_parts = [self.system_prompt]

        # 최근 채팅 컨텍스트 (다른 시청자들의 채팅)
        if chat_context:
            prompt_parts.append("\n현재 채팅창 분위기:")
            prompt_parts.append(chat_context)

        # 대화 히스토리
        prompt_parts.append("\n대화 히스토리:")
        for item in self.context:
            role_name = "스트리머" if item["role"] == "streamer" else "나"
            prompt_parts.append(f"{role_name}: {item['text']}")

        # 현재 스트리머 발언 추가
        prompt_parts.append(f"\n스트리머: {streamer_speech}")
        prompt_parts.append("\n응답: ")

        return "\n".join(prompt_parts)

    def generate_response(self, streamer_speech, chat_context=""):
        """
        스트리머 발언에 대한 응답 생성

        Args:
            streamer_speech: 스트리머 발언

        Returns:
            str: 생성된 응답 (실패 시 None)
        """
        if not streamer_speech or not streamer_speech.strip():
            return None

        try:
            # 프롬프트 생성
            prompt = self._build_prompt(streamer_speech, chat_context)

            # Ollama API 호출
            payload = {
                "model": self.model_name,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.8,
                    "top_p": 0.9,
                    "max_tokens": 100
                }
            }

            response = requests.post(
                self.api_url,
                json=payload,
                timeout=30
            )

            if response.status_code == 200:
                result = response.json()
                generated_text = result.get("response", "").strip()

                # 응답 후처리
                generated_text = self._postprocess_response(generated_text)

                if generated_text:
                    # 컨텍스트에 추가
                    self.add_to_context("streamer", streamer_speech)
                    self.add_to_context("bot", generated_text)

                return generated_text
            else:
                print(f"LLM 응답 실패: {response.status_code}")
                return None

        except requests.exceptions.Timeout:
            print("LLM 응답 시간 초과")
            return None
        except Exception as e:
            print(f"LLM 응답 생성 실패: {e}")
            return None

    def _postprocess_response(self, text):
        """
        생성된 응답 후처리

        Args:
            text: 원본 응답

        Returns:
            str: 처리된 응답
        """
        if not text:
            return None

        # 줄바꿈 제거
        text = text.replace("\n", " ").strip()

        # 너무 긴 응답 자르기 (50자 제한)
        if len(text) > 50:
            text = text[:50]

        # 따옴표 제거
        text = text.strip('"\'')

        # 빈 응답 체크
        if not text or len(text) < 2:
            return None

        return text

    def clear_context(self):
        """대화 컨텍스트 초기화"""
        self.context.clear()


def test_llm():
    """LLM 연결 및 응답 생성 테스트"""
    handler = LLMHandler()

    print("Ollama 연결 테스트 중...")
    if not handler.check_connection():
        print("\n테스트 실패: Ollama에 연결할 수 없습니다.")
        return

    print("\n응답 생성 테스트:")
    print("=" * 50)

    test_speeches = [
        "오늘 날씨 진짜 좋네요",
        "이거 어떻게 깨지?",
        "오늘 방송 재미있나요?",
    ]

    for speech in test_speeches:
        print(f"\n스트리머: {speech}")
        response = handler.generate_response(speech)
        if response:
            print(f"봇: {response}")
        else:
            print("응답 생성 실패")

    print("\n" + "=" * 50)
