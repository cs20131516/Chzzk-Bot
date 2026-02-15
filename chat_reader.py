"""치지직 채팅 읽기 모듈 (chzzkpy unofficial ChatClient 사용)

로그인 없이 READ 모드로 채팅을 수신합니다.
채널 ID만 있으면 실시간 채팅 메시지를 수집할 수 있습니다.
"""
import time
import asyncio
import threading
from collections import deque

from chzzkpy.unofficial.chat import ChatClient, ChatMessage, DonationMessage


class ChatReader:
    """치지직 채팅 읽기 클래스

    별도 스레드에서 비동기 ChatClient를 실행하여
    실시간 채팅 메시지를 수집합니다.
    """

    def __init__(self, channel_id: str, max_messages: int = 20):
        """
        Args:
            channel_id: 치지직 채널 ID (방송 URL에서 추출)
            max_messages: 보관할 최근 메시지 수
        """
        self.channel_id = channel_id
        self.messages = deque(maxlen=max_messages)
        self.donations = deque(maxlen=max_messages)
        self._thread = None
        self._loop = None
        self._client = None
        self._running = False

    def start(self):
        """채팅 리더 시작 (별도 스레드)"""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_client, daemon=True)
        self._thread.start()
        print(f"채팅 리더 시작 (채널: {self.channel_id})")

    def _run_client(self):
        """별도 스레드에서 ChatClient 실행"""
        try:
            self._client = ChatClient(channel_id=self.channel_id)

            @self._client.event
            async def on_chat(message: ChatMessage):
                nickname = message.profile.nickname if message.profile else "???"
                self.messages.append({
                    "nickname": nickname,
                    "content": message.content,
                    "time": time.time(),
                })

            @self._client.event
            async def on_donation(message: DonationMessage):
                nickname = message.profile.nickname if message.profile else "???"
                content = message.content or ""
                if content:
                    self.donations.append({
                        "nickname": nickname,
                        "content": content,
                    })

            @self._client.event
            async def on_connect():
                print("채팅 연결 성공! 메시지 수신 중...")

            # run()은 내부적으로 asyncio.run()을 호출
            self._client.run()

        except Exception as e:
            if self._running:
                print(f"채팅 리더 오류: {e}")

    def get_recent_messages(self, count: int = 10) -> list[dict]:
        """최근 채팅 메시지 반환"""
        messages = list(self.messages)
        return messages[-count:]

    def get_recent_donations(self, count: int = 10) -> list[dict]:
        """최근 도네이션 메시지 반환"""
        donations = list(self.donations)
        return donations[-count:]

    def get_chat_rate(self, window: int = 30) -> float:
        """최근 N초 동안의 채팅 속도 (메시지/분)"""
        now = time.time()
        cutoff = now - window
        recent = [m for m in self.messages if m.get("time", 0) > cutoff]
        return len(recent) / (window / 60)

    def get_chat_context(self, count: int = 10) -> str:
        """LLM 프롬프트용 채팅 컨텍스트 문자열 반환"""
        messages = self.get_recent_messages(count)
        if not messages:
            return "(채팅 없음)"

        lines = []
        for msg in messages:
            lines.append(f"{msg['nickname']}: {msg['content']}")
        return "\n".join(lines)

    def stop(self):
        """채팅 리더 종료"""
        self._running = False
        # ChatClient는 내부적으로 asyncio.run을 사용하므로
        # 스레드가 자연스럽게 종료되길 기다림
        if self._thread:
            self._thread.join(timeout=5)
        print("채팅 리더 종료")


def extract_channel_id(url: str) -> str:
    """치지직 URL에서 채널 ID 추출

    예: https://chzzk.naver.com/live/d0888e44767fbc1ee86bbba49c6cd848
    → d0888e44767fbc1ee86bbba49c6cd848
    """
    url = url.strip().rstrip("/")
    # /live/CHANNEL_ID 또는 /CHANNEL_ID 형태
    parts = url.split("/")
    return parts[-1]


if __name__ == "__main__":
    import time

    url = input("방송 URL 입력: ").strip()
    channel_id = extract_channel_id(url)
    print(f"채널 ID: {channel_id}")

    reader = ChatReader(channel_id)
    reader.start()

    try:
        while True:
            time.sleep(5)
            print(f"\n--- 최근 채팅 ({len(reader.messages)}개 수집) ---")
            print(reader.get_chat_context(5))
            print("---")
    except KeyboardInterrupt:
        reader.stop()
