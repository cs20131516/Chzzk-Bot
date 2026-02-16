"""치지직 채팅 전송 모듈 (chzzkpy unofficial ChatClient 사용)

네이버 로그인 쿠키(NID_AUT, NID_SES)로 인증하여
WebSocket을 통해 채팅 메시지를 전송합니다.
"""
import asyncio
import os
import time
import threading
from typing import Any

from chzzkpy.unofficial.chat import ChatClient

from config import Config

ENV_FILE = os.path.join(os.path.dirname(__file__), ".env")


class ChatSender:
    """치지직 채팅 전송 클래스 (쿠키 인증)

    동작 방식:
    1. 네이버 쿠키(NID_AUT, NID_SES)로 ChatClient 생성
    2. WebSocket 연결 후 send_chat()으로 메시지 전송
    """

    def __init__(self):
        self._client: Any = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self.is_authenticated = False
        self._running = False
        self.last_send_time = 0
        self._channel_id = ""
        self._nid_aut = ""
        self._nid_ses = ""

    @staticmethod
    def _login_via_browser() -> tuple[str, str]:
        """브라우저로 네이버 로그인 → 쿠키 자동 캡처"""
        try:
            import undetected_chromedriver as uc
        except ImportError:
            print("undetected-chromedriver가 필요합니다: pip install undetected-chromedriver")
            return "", ""

        print("\n네이버 로그인 창을 여는 중...")
        print("로그인 완료 후 자동으로 쿠키를 가져옵니다.\n")

        # Chrome 버전 자동 감지 (PowerShell로 exe 파일 버전 읽기)
        chrome_path = uc.find_chrome_executable()
        ver = None
        import subprocess
        try:
            out = subprocess.check_output(
                ["powershell", "-Command",
                 f"(Get-Item '{chrome_path}').VersionInfo.FileVersion"],
                text=True,
            )
            ver = int(out.strip().split(".")[0])
            print(f"Chrome {ver} 감지됨")
        except Exception:
            pass

        import tempfile
        tmp_profile = os.path.join(tempfile.gettempdir(), "chzzk_bot_chrome")
        os.makedirs(tmp_profile, exist_ok=True)
        driver = uc.Chrome(
            headless=False,
            version_main=ver,
            user_data_dir=tmp_profile,
        )
        nid_aut = ""
        nid_ses = ""

        try:
            # 1단계: 네이버 로그인 페이지로 이동
            driver.get("https://nid.naver.com/nidlogin.login?url=https://chzzk.naver.com/")
            time.sleep(2)

            # 2단계: 로그인 완료 대기 (로그인 페이지를 벗어날 때까지)
            from selenium.webdriver.support.ui import WebDriverWait
            if "nidlogin" in driver.current_url:
                print("네이버 로그인을 완료해주세요 (최대 3분 대기)...")
                WebDriverWait(driver, 180).until(
                    lambda d: "nidlogin" not in d.current_url
                )

            # 3단계: chzzk.naver.com으로 이동해서 쿠키 추출
            driver.get("https://chzzk.naver.com/")
            time.sleep(2)

            cookies = driver.get_cookies()
            for c in cookies:
                if c["name"] == "NID_AUT":
                    nid_aut = c["value"]
                elif c["name"] == "NID_SES":
                    nid_ses = c["value"]

            if nid_aut and nid_ses:
                print("로그인 성공! 쿠키를 가져왔습니다.")
        except Exception as e:
            print(f"로그인 실패: {e}")
        finally:
            driver.quit()

        return nid_aut, nid_ses

    @staticmethod
    def _save_cookies_to_env(nid_aut: str, nid_ses: str):
        """쿠키를 .env 파일에 저장 (다음 실행 시 자동 사용)"""
        if not os.path.exists(ENV_FILE):
            return
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()

        new_lines = []
        for line in lines:
            if line.startswith("NID_AUT="):
                new_lines.append(f"NID_AUT={nid_aut}\n")
            elif line.startswith("NID_SES="):
                new_lines.append(f"NID_SES={nid_ses}\n")
            else:
                new_lines.append(line)

        with open(ENV_FILE, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
        print(".env에 쿠키 저장 완료 (다음부터 자동 로그인)")

    def _try_connect(self, channel_id: str, nid_aut: str, nid_ses: str) -> bool:
        """ChatClient WebSocket 연결 시도 (최대 20초 대기)"""
        self._channel_id = channel_id
        self._nid_aut = nid_aut
        self._nid_ses = nid_ses

        self._client = ChatClient(
            channel_id=channel_id,
            authorization_key=nid_aut,
            session_key=nid_ses,
        )
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run, name="ChatSender", daemon=True
        )
        self._thread.start()

        # 연결 대기 (최대 20초)
        for _ in range(200):
            time.sleep(0.1)
            if self._client.is_connected:
                self.is_authenticated = True
                print("채팅 전송 연결 성공!")
                return True
        return False

    def authenticate(self, channel_id: str) -> bool:
        """쿠키 인증 + WebSocket 연결

        Args:
            channel_id: 치지직 채널 ID (방송 URL에서 추출)
        """
        nid_aut = Config.NID_AUT
        nid_ses = Config.NID_SES

        # .env에 없으면 Selenium으로 로그인
        if not nid_aut or not nid_ses:
            nid_aut, nid_ses = self._login_via_browser()
            if not nid_aut or not nid_ses:
                print("로그인에 실패했습니다.")
                return False
            self._save_cookies_to_env(nid_aut, nid_ses)

        # 1차 시도: 저장된 쿠키로 연결
        if self._try_connect(channel_id, nid_aut, nid_ses):
            return True

        # 2차 시도: 쿠키 만료 가능성 → 재로그인
        print("연결 실패. 쿠키가 만료되었을 수 있습니다. 재로그인 시도...")
        self.is_authenticated = False
        nid_aut, nid_ses = self._login_via_browser()
        if not nid_aut or not nid_ses:
            print("재로그인 실패")
            return False
        self._save_cookies_to_env(nid_aut, nid_ses)

        if self._try_connect(channel_id, nid_aut, nid_ses):
            return True

        print("채팅 전송 연결 실패 (방송이 라이브 중인지 확인하세요)")
        return False

    def _run(self):
        """별도 스레드에서 ChatClient 실행 (자동 재연결)"""
        assert self._loop is not None
        asyncio.set_event_loop(self._loop)
        retry_delay = 3
        self._running = True
        while self._running:
            try:
                self._loop.run_until_complete(self._client.start())
            except Exception as e:
                if not self._running:
                    break
                print(f"채팅 전송 연결 오류: {e} ({retry_delay}초 후 재연결...)")
                # 기존 클라이언트/루프 정리 (Unclosed client session 방지)
                try:
                    self._loop.run_until_complete(self._client.close())
                except Exception:
                    pass
                try:
                    self._loop.close()
                except Exception:
                    pass
                time.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 30)
                # 새 이벤트 루프 + 클라이언트로 재연결
                try:
                    self._loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(self._loop)
                    self._client = ChatClient(
                        channel_id=self._channel_id,
                        authorization_key=self._nid_aut,
                        session_key=self._nid_ses,
                    )
                except Exception:
                    break

    def send_message(self, text: str, retry: int = 3) -> bool:
        """채팅 메시지 전송"""
        if not self.is_authenticated or not self._client or not self._loop:
            print("채팅 전송이 연결되지 않았습니다.")
            return False
        if not text or not text.strip():
            return False

        # 레이트 리밋 (최소 2초 간격)
        current_time = time.time()
        elapsed = current_time - self.last_send_time
        if elapsed < 2.0:
            time.sleep(2.0 - elapsed)

        try:
            future = asyncio.run_coroutine_threadsafe(
                self._client.send_chat(text), self._loop
            )
            future.result(timeout=5)
            self.last_send_time = time.time()
            print(f"채팅 전송: {text}")
            return True
        except Exception as e:
            print(f"채팅 전송 실패: {e}")
            return False

    def is_connected(self) -> bool:
        return self.is_authenticated and bool(
            self._client and self._client.is_connected
        )

    def disconnect(self):
        self._running = False
        self.is_authenticated = False
        if self._client and self._loop and self._loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(
                    self._client.close(), self._loop
                ).result(timeout=3)
            except Exception:
                pass
        print("채팅 전송 종료")


class MockChatSender(ChatSender):
    """테스트용 Mock"""

    def __init__(self):
        self._client = None
        self._loop = None
        self._thread = None
        self.is_authenticated = False
        self.last_send_time = 0
        print("MockChatSender 사용 중 (실제 메시지는 전송되지 않음)")

    def authenticate(self, channel_id: str = "") -> bool:
        print("Mock 인증 성공")
        self.is_authenticated = True
        return True

    def send_message(self, text: str, retry: int = 3) -> bool:
        if not text or not text.strip():
            return False
        print(f"[MOCK 전송] {text}")
        self.last_send_time = time.time()
        return True

    def disconnect(self):
        self.is_authenticated = False
        print("Mock 채팅 종료")


if __name__ == "__main__":
    import sys
    use_mock = "--mock" in sys.argv

    if use_mock:
        sender = MockChatSender()
        sender.authenticate()
    else:
        channel_url = input("방송 URL: ").strip()
        cid = channel_url.rstrip("/").split("/")[-1]
        sender = ChatSender()
        if not sender.authenticate(cid):
            sys.exit(1)

    test_messages = ["안녕하세요!", "테스트 ㅎㅎ", "잘 되나요?"]
    for msg in test_messages:
        sender.send_message(msg)
        time.sleep(2)

    sender.disconnect()
