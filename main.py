import os
import time
import signal
import sys
import queue
import random
import threading
from difflib import SequenceMatcher
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

    파이프라인 (각 단계가 독립 스레드로 동작):
    1. AudioCapture 스레드: 시스템 오디오 루프백 → audio_queue
    2. ASR Worker 스레드: audio_queue → 음성인식 → speech_queue
    3. LLM Worker 스레드: speech_queue → 응답 생성 → response_queue
    4. Main 스레드: response_queue → 승인/전송/메모리
    5. ChatReader 스레드: WebSocket → 실시간 채팅 수집
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

        # 파이프라인 큐
        self.speech_queue = queue.Queue()    # ASR → LLM
        self.response_queue = queue.Queue()  # LLM → Main

        # 스레드 제어
        self._stop_event = threading.Event()
        self._asr_thread = None
        self._llm_thread = None

        # 쿨다운 (LLM worker + main thread 공유)
        self.last_response_time = 0
        self._cooldown_lock = threading.Lock()

        self.use_mock = use_mock
        self.auto_send = auto_send

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

        # [3] ASR + Ollama 체크
        print("\n[3/5] ASR 모델 로딩...")
        try:
            self.speech_recognizer.load_model()
        except Exception as e:
            print(f"ASR 모델 로딩 실패: {e}")
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
        print("  봇 시작! (동시성 파이프라인)")
        print("  ASR ─→ LLM ─→ 전송 각각 독립 동작")
        print("  Ctrl+C로 종료")
        if not self.use_mock:
            print("  긴급 중지: 마우스를 화면 좌상단 모서리로")
        print("=" * 60 + "\n")

        self.stats["start_time"] = time.time()
        self._stop_event.clear()

        # 오디오 캡처 시작 (기존 스레드)
        self.audio_capture.start()

        # 워커 스레드 시작
        self._asr_thread = threading.Thread(
            target=self._asr_worker, name="ASR-Worker", daemon=True
        )
        self._llm_thread = threading.Thread(
            target=self._llm_worker, name="LLM-Worker", daemon=True
        )
        self._asr_thread.start()
        self._llm_thread.start()

        # 메인 스레드에서 응답 처리
        try:
            self._response_handler()
        except KeyboardInterrupt:
            print("\n\n종료...")
        finally:
            self.stop()

    def _is_tts_donation(self, text, threshold=0.4):
        """ASR 결과가 도네 TTS인지 도네이션/채팅 내용과 비교하여 판단

        Args:
            text: ASR로 인식된 텍스트
            threshold: 유사도 임계값 (0.0~1.0, 기본 0.4)

        Returns:
            bool: TTS 도네이션이면 True
        """
        if not self.chat_reader:
            return False

        text_clean = text.strip().lower()

        # 1차: 도네이션 메시지와 비교 (on_donation 이벤트로 수집)
        donations = self.chat_reader.get_recent_donations(20)
        for msg in donations:
            donate_text = msg["content"].strip().lower()
            if len(donate_text) < 3:
                continue
            ratio = SequenceMatcher(None, text_clean, donate_text).ratio()
            if ratio > threshold:
                print(f"[ASR] TTS 도네 감지 (도네 유사도 {ratio:.0%}): {donate_text[:30]}")
                return True
            # 부분 포함 체크 (ASR이 도네 텍스트의 일부만 인식한 경우)
            if len(donate_text) >= 10 and donate_text in text_clean:
                print(f"[ASR] TTS 도네 감지 (부분 일치): {donate_text[:30]}")
                return True
            if len(text_clean) >= 10 and text_clean in donate_text:
                print(f"[ASR] TTS 도네 감지 (부분 일치): {donate_text[:30]}")
                return True

        # 2차: 일반 채팅과도 비교 (도네가 채팅에도 표시되는 경우)
        recent = self.chat_reader.get_recent_messages(20)
        for msg in recent:
            chat_text = msg["content"].strip().lower()
            if len(chat_text) < 5:
                continue
            ratio = SequenceMatcher(None, text_clean, chat_text).ratio()
            if ratio > 0.5:
                print(f"[ASR] TTS 도네 감지 (채팅 유사도 {ratio:.0%}): {chat_text[:30]}")
                return True
        return False

    def _asr_worker(self):
        """ASR 워커 스레드: 오디오 → 음성인식 → speech_queue"""
        while not self._stop_event.is_set():
            try:
                # 1. 오디오 청크 수집
                audio_data = self.audio_capture.get_audio_chunk(timeout=1.0)
                if audio_data is None:
                    continue

                # 2. 소리 감지
                if not self.audio_capture.is_speech_present(audio_data):
                    continue

                print("\n[ASR] 음성 감지됨, 인식 중...")

                # 3. 음성 인식
                text = self.speech_recognizer.transcribe(audio_data)
                if not text:
                    print("[ASR] 인식 실패")
                    continue

                print(f"[ASR] 스트리머: {text}")

                # 4. 유효성 검증
                if not self.speech_recognizer.is_valid_speech(text):
                    print("[ASR] 무효한 발화 (무시)")
                    continue

                # 5. TTS 도네이션 필터
                if self._is_tts_donation(text):
                    continue

                # 6. speech_queue에 전달
                self.speech_queue.put(text)

            except Exception as e:
                if not self._stop_event.is_set():
                    print(f"\n[ASR] 오류: {e}")
                    time.sleep(1)

    def _drain_speech_queue(self):
        """speech_queue에서 가장 최신 텍스트만 가져오고 나머지는 버림"""
        text = self.speech_queue.get(timeout=1.0)
        skipped = 0
        while not self.speech_queue.empty():
            try:
                text = self.speech_queue.get_nowait()
                skipped += 1
            except queue.Empty:
                break
        if skipped > 0:
            print(f"[LLM] {skipped}개 이전 발화 스킵, 최신 처리: {text[:20]}")
        return text

    def _llm_worker(self):
        """LLM 워커 스레드: speech_queue → LLM 응답 → response_queue"""
        while not self._stop_event.is_set():
            try:
                # 1. 최신 음성 인식 결과만 가져오기 (오래된 것 버림)
                try:
                    text = self._drain_speech_queue()
                except queue.Empty:
                    continue

                # 2. 쿨다운 체크
                with self._cooldown_lock:
                    current_time = time.time()
                    if current_time - self.last_response_time < Config.RESPONSE_COOLDOWN:
                        remaining = Config.RESPONSE_COOLDOWN - (current_time - self.last_response_time)
                        print(f"[LLM] 쿨다운 ({remaining:.1f}초) - 스킵: {text[:20]}")
                        continue

                # 3. 응답 확률 체크
                if Config.RESPONSE_CHANCE < 1.0 and random.random() > Config.RESPONSE_CHANCE:
                    print(f"[LLM] 확률 스킵 ({Config.RESPONSE_CHANCE:.0%}): {text[:20]}")
                    continue

                # 4. 채팅 컨텍스트 가져오기
                chat_context = ""
                if self.chat_reader:
                    chat_context = self.chat_reader.get_chat_context(10)
                    if chat_context != "(채팅 없음)":
                        print(f"[LLM] 채팅 컨텍스트: {len(self.chat_reader.messages)}개")

                # 5. 스마트 응답 (켜져 있으면 LLM이 응답할지 판단)
                if Config.SMART_RESPONSE:
                    if not self.llm_handler.should_respond(text, chat_context):
                        print(f"[LLM] 스마트 스킵: {text[:30]}")
                        continue

                self.stats["processed_speeches"] += 1

                # 6. LLM 응답 생성
                print("[LLM] 응답 생성 중...")
                response = self.llm_handler.generate_response(
                    text, chat_context,
                    streamer_memory=self.streamer_memory.get_facts_as_prompt(),
                    chat_memory=self.chat_memory.get_facts_as_prompt(),
                    my_chat_memory=self.my_chat_memory.get_facts_as_prompt()
                )
                if not response:
                    print("[LLM] 응답 생성 실패")
                    continue

                print(f"[LLM] 응답: {response}")

                # 7. response_queue에 전달
                self.response_queue.put((text, response, chat_context))

            except Exception as e:
                if not self._stop_event.is_set():
                    print(f"\n[LLM] 오류: {e}")
                    time.sleep(1)

    def _response_handler(self):
        """메인 스레드: response_queue → 승인/전송/메모리"""
        while not self._stop_event.is_set():
            try:
                # 1. 응답 대기
                try:
                    text, response, chat_context = self.response_queue.get(timeout=1.0)
                except queue.Empty:
                    continue

                # 2. 채팅 전송 (수동 승인 or 자동)
                if self.auto_send:
                    success = self.chat_sender.send_message(response)
                else:
                    choice = input(f"  [{response}] Enter=전송 / s=스킵 / e=수정: ").strip().lower()
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
                    with self._cooldown_lock:
                        self.last_response_time = time.time()
                    self.memory_manager.record_interaction(
                        text, response, chat_context
                    )

            except Exception as e:
                if not self._stop_event.is_set():
                    print(f"\n오류: {e}")
                    time.sleep(1)

    def stop(self):
        """종료"""
        self._stop_event.set()

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

        # 워커 스레드 종료 대기
        if self._asr_thread and self._asr_thread.is_alive():
            self._asr_thread.join(timeout=3)
        if self._llm_thread and self._llm_thread.is_alive():
            self._llm_thread.join(timeout=3)

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
