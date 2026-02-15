import os
import time
import signal
import sys
from config import Config
from audio_capture import AudioCapture, select_speaker
from speech_recognition import SpeechRecognizer
from llm_handler import LLMHandler
from chat_sender import ChatSender, MockChatSender
from chat_reader import ChatReader, extract_channel_id
from memory.memory_store import MemoryStore
from memory.memory_manager import MemoryManager


class ChzzkVoiceBot:
    """치지직 음성인식 자동 채팅 봇

    흐름:
    1. 방송 URL 입력
    2. 채팅 리더: 실시간 채팅 메시지 수집
    3. 오디오 캡처: 스트리머 음성 → Whisper → 텍스트
    4. LLM: 스트리머 발언 + 채팅 분위기 → 응답 생성
    5. pyautogui: 채팅창에 자동 입력
    """

    def __init__(self, use_mock=False, auto_send=False):
        self.audio_capture = None
        self.speech_recognizer = SpeechRecognizer()
        self.llm_handler = LLMHandler()
        self.chat_sender = MockChatSender() if use_mock else ChatSender()
        self.chat_reader = None

        # 메모리 시스템 (initialize에서 channel_id 확정 후 초기화)
        self.streamer_memory = None
        self.chat_memory = None
        self.my_chat_memory = None
        self.memory_manager = None

        self.is_running = False
        self.last_response_time = 0
        self.use_mock = use_mock
        self.auto_send = auto_send  # False면 수동 승인 모드

        self.stats = {
            "processed_speeches": 0,
            "sent_messages": 0,
            "start_time": None
        }

    def initialize(self):
        """초기화"""
        print("\n" + "=" * 60)
        print("  치지직 음성인식 자동 채팅 봇")
        print("=" * 60)

        # [1] 방송 URL 입력
        print("\n[1/5] 방송 URL 입력")
        url = input("치지직 방송 URL: ").strip()
        if not url:
            print("URL이 입력되지 않았습니다.")
            return False

        channel_id = extract_channel_id(url)
        print(f"채널 ID: {channel_id}")

        # 채널별 메모리 초기화
        data_dir = os.path.join(os.path.dirname(__file__), "data", channel_id)
        self.streamer_memory = MemoryStore(
            os.path.join(data_dir, "streamer_memory.json"), max_facts=5
        )
        self.chat_memory = MemoryStore(
            os.path.join(data_dir, "chat_memory.json"), max_facts=4
        )
        self.my_chat_memory = MemoryStore(
            os.path.join(data_dir, "my_chat_memory.json"), max_facts=4
        )
        self.memory_manager = MemoryManager(
            self.streamer_memory, self.chat_memory, self.my_chat_memory
        )
        if not self.streamer_memory.is_empty():
            print(f"  기존 메모리 로드됨 (스트리머: {len(self.streamer_memory.get_facts())}개)")

        # [2] 채팅 리더 시작 (실시간 채팅 수집)
        print("\n[2/5] 채팅 리더 시작...")
        self.chat_reader = ChatReader(channel_id)
        self.chat_reader.start()
        time.sleep(3)  # 연결 대기

        # [3] Whisper + Ollama 체크
        print("\n[3/5] Whisper 모델 로딩...")
        try:
            self.speech_recognizer.load_model()
        except Exception as e:
            print(f"Whisper 로딩 실패: {e}")
            return False

        print("\n[4/5] Ollama 연결 확인...")
        if not self.llm_handler.check_connection():
            return False

        # [4] 스피커 선택
        print("\n[5/5] 오디오 + 채팅 설정...")
        print("브라우저에서 방송 소리가 나오고 있어야 합니다!")
        speaker = select_speaker()
        self.audio_capture = AudioCapture(speaker=speaker)

        # [5] 채팅 입력창 위치 (Mock이 아닐 때만)
        if not self.use_mock:
            if not self.chat_sender.authenticate():
                return False

        print("\n초기화 완료!")
        return True

    def start(self):
        """봇 실행"""
        if not self.initialize():
            print("\n초기화 실패.")
            return

        print("\n" + "=" * 60)
        print("  봇 시작!")
        print("  스트리머 음성 + 채팅 분위기를 보고 자동 채팅합니다.")
        print("  Ctrl+C로 종료")
        if not self.use_mock:
            print("  긴급 중지: 마우스를 화면 좌상단 모서리로")
        print("=" * 60 + "\n")

        self.is_running = True
        self.stats["start_time"] = time.time()
        self.audio_capture.start()

        try:
            self.main_loop()
        except KeyboardInterrupt:
            print("\n\n종료...")
        finally:
            self.stop()

    def main_loop(self):
        """메인 처리 루프"""
        while self.is_running:
            try:
                # 1. 오디오 캡처
                audio_data = self.audio_capture.get_audio_chunk(timeout=1.0)
                if audio_data is None:
                    continue

                # 2. 소리 감지
                if not self.audio_capture.is_speech_present(audio_data):
                    continue

                print("\n음성 감지됨, 인식 중...")

                # 3. 음성 인식
                text = self.speech_recognizer.transcribe(audio_data)
                if not text:
                    print("  인식 실패")
                    continue

                print(f"  스트리머: {text}")

                # 4. 유효성 검증
                if not self.speech_recognizer.is_valid_speech(text):
                    print("  무효한 발화 (무시)")
                    continue

                # 5. 쿨다운
                current_time = time.time()
                if current_time - self.last_response_time < Config.RESPONSE_COOLDOWN:
                    remaining = Config.RESPONSE_COOLDOWN - (current_time - self.last_response_time)
                    print(f"  쿨다운 ({remaining:.1f}초)")
                    continue

                self.stats["processed_speeches"] += 1

                # 6. 채팅 컨텍스트 가져오기
                chat_context = ""
                if self.chat_reader:
                    chat_context = self.chat_reader.get_chat_context(10)
                    if chat_context != "(채팅 없음)":
                        print(f"  채팅 컨텍스트: {len(self.chat_reader.messages)}개")

                # 7. LLM 응답 생성 (음성 + 채팅 컨텍스트 + 메모리)
                print("  응답 생성 중...")
                response = self.llm_handler.generate_response(
                    text, chat_context,
                    streamer_memory=self.streamer_memory.get_facts_as_prompt(),
                    chat_memory=self.chat_memory.get_facts_as_prompt(),
                    my_chat_memory=self.my_chat_memory.get_facts_as_prompt()
                )
                if not response:
                    print("  응답 생성 실패")
                    continue

                print(f"  응답: {response}")

                # 8. 채팅 전송 (수동 승인 or 자동)
                if self.auto_send:
                    success = self.chat_sender.send_message(response)
                else:
                    choice = input("  [Enter=전송 / s=스킵 / e=수정]: ").strip().lower()
                    if choice == 's':
                        print("  스킵됨")
                        continue
                    elif choice == 'e':
                        new_text = input("  수정 메시지: ").strip()
                        if not new_text:
                            print("  스킵됨")
                            continue
                        response = new_text
                    success = self.chat_sender.send_message(response)

                if success:
                    self.stats["sent_messages"] += 1
                    self.last_response_time = current_time
                    self.memory_manager.record_interaction(
                        text, response, chat_context
                    )

            except Exception as e:
                print(f"\n오류: {e}")
                time.sleep(1)

    def stop(self):
        """종료"""
        self.is_running = False

        # 메모리 저장
        if self.memory_manager:
            print("메모리 저장 중...")
            self.memory_manager.force_update()
            self.memory_manager.save_all()
            print("메모리 저장 완료")

        if self.audio_capture:
            self.audio_capture.stop()
        if self.chat_reader:
            self.chat_reader.stop()
        if self.chat_sender:
            self.chat_sender.disconnect()

        if self.stats["start_time"]:
            runtime = time.time() - self.stats["start_time"]
            print(f"\n  실행: {time.strftime('%H:%M:%S', time.gmtime(runtime))}")
            print(f"  처리: {self.stats['processed_speeches']}개")
            print(f"  전송: {self.stats['sent_messages']}개")


def main():
    signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))

    use_mock = "--mock" in sys.argv
    auto_send = "--auto" in sys.argv

    if use_mock:
        print("\n[Mock 모드] 채팅은 콘솔에만 출력됩니다.\n")
    if not auto_send:
        print("[수동 모드] 메시지 전송 전 확인합니다. (--auto로 자동 전송)\n")

    bot = ChzzkVoiceBot(use_mock=use_mock, auto_send=auto_send)
    bot.start()


if __name__ == "__main__":
    main()
