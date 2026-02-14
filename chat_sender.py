import time
import pyperclip
import pyautogui

# pyautogui 안전 설정
pyautogui.FAILSAFE = True  # 마우스를 좌상단 모서리로 이동하면 긴급 중지
pyautogui.PAUSE = 0.1


class ChatSender:
    """치지직 채팅창에 자동으로 메시지를 입력하는 클래스

    동작 방식:
    1. 사용자가 브라우저에서 치지직 방송 페이지를 열어둠
    2. 채팅 입력창 위치를 기억
    3. 클립보드 + 붙여넣기로 한글 메시지 입력
    """

    def __init__(self):
        self.chat_input_pos = None  # (x, y) 채팅 입력창 좌표
        self.last_send_time = 0
        self.is_authenticated = False

    def authenticate(self):
        """채팅 입력창 위치 설정"""
        print("\n" + "=" * 50)
        print("채팅 입력창 위치를 설정합니다.")
        print("=" * 50)
        print()
        print("방법: 브라우저에서 치지직 방송 페이지를 열고,")
        print("      채팅 입력창을 클릭할 준비를 하세요.")
        print()
        input("준비되면 Enter를 누르세요...")
        print()
        print("5초 후 마우스 위치를 기록합니다.")
        print("채팅 입력창 위에 마우스를 올려두세요!")
        print()

        for i in range(5, 0, -1):
            print(f"  {i}...")
            time.sleep(1)

        self.chat_input_pos = pyautogui.position()
        print(f"\n채팅 입력창 위치 저장: ({self.chat_input_pos.x}, {self.chat_input_pos.y})")
        self.is_authenticated = True

        # 테스트 클릭
        pyautogui.click(self.chat_input_pos)
        print("위치 설정 완료!")
        return True

    def send_message(self, text, retry=3):
        """채팅 메시지 전송 (클립보드 + 붙여넣기)"""
        if not self.is_authenticated or not self.chat_input_pos:
            print("채팅 입력창 위치가 설정되지 않았습니다.")
            return False

        if not text or not text.strip():
            return False

        # 레이트 리밋 (최소 2초 간격)
        current_time = time.time()
        time_since_last = current_time - self.last_send_time
        if time_since_last < 2.0:
            time.sleep(2.0 - time_since_last)

        try:
            # 1. 채팅 입력창 클릭
            pyautogui.click(self.chat_input_pos)
            time.sleep(0.2)

            # 2. 클립보드에 텍스트 복사 (한글 입력을 위해 붙여넣기 사용)
            pyperclip.copy(text)

            # 3. Ctrl+V로 붙여넣기
            pyautogui.hotkey('ctrl', 'v')
            time.sleep(0.2)

            # 4. Enter로 전송
            pyautogui.press('enter')

            self.last_send_time = time.time()
            print(f"✓ 채팅 전송: {text}")
            return True

        except Exception as e:
            print(f"채팅 전송 실패: {e}")
            return False

    def is_connected(self):
        return self.is_authenticated

    def disconnect(self):
        self.is_authenticated = False
        print("채팅 전송 종료")


class MockChatSender(ChatSender):
    """테스트용 Mock"""

    def __init__(self):
        super().__init__()
        print("MockChatSender 사용 중 (실제 메시지는 전송되지 않음)")

    def authenticate(self):
        print("Mock 인증 성공")
        self.is_authenticated = True
        return True

    def send_message(self, text, retry=3):
        if not text or not text.strip():
            return False
        print(f"[MOCK 전송] {text}")
        self.last_send_time = time.time()
        return True


if __name__ == "__main__":
    import sys
    use_mock = "--mock" in sys.argv

    if use_mock:
        sender = MockChatSender()
    else:
        sender = ChatSender()

    sender.authenticate()

    test_messages = ["안녕하세요!", "테스트 ㅎㅎ", "잘 되나요?"]
    for msg in test_messages:
        sender.send_message(msg)
        time.sleep(2)

    sender.disconnect()
