# Chzzk Bot - 치지직 음성인식 자동 채팅 봇

치지직(Chzzk) 스트리밍 플랫폼에서 스트리머의 음성을 실시간으로 인식하고, 채팅 분위기를 파악하여 로컬 LLM으로 자연스러운 채팅 메시지를 자동 생성하는 봇입니다.

## 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                        Chzzk Bot                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  [사용자 입력]                                                   │
│       │                                                         │
│       │  방송 URL 입력                                           │
│       ▼                                                         │
│  ┌──────────────┐     채널 ID 추출                               │
│  │ extract_      │─────────────────┐                             │
│  │ channel_id()  │                 │                             │
│  └──────────────┘                  │                             │
│       │                            │                             │
│       ▼                            ▼                             │
│  ┌──────────────┐          ┌──────────────┐                      │
│  │ AudioCapture │          │  ChatReader   │                     │
│  │ (soundcard)  │          │  (chzzkpy)    │                     │
│  │              │          │              │                      │
│  │ 시스템 오디오 │          │ WebSocket     │                     │
│  │ 루프백 캡처   │          │ 실시간 채팅   │                     │
│  └──────┬───────┘          └──────┬───────┘                      │
│         │                         │                              │
│         │ audio_data              │ chat_context                 │
│         ▼                         │                              │
│  ┌──────────────┐                 │                              │
│  │ Whisper STT  │                 │                              │
│  │ (음성→텍스트) │                 │                              │
│  │              │                 │                              │
│  │ "오늘 날씨   │                 │                              │
│  │  좋네요"     │                 │                              │
│  └──────┬───────┘                 │                              │
│         │                         │                              │
│         │ streamer_speech         │                              │
│         ▼                         ▼                              │
│  ┌─────────────────────────────────────┐                         │
│  │           LLM (Ollama)              │                         │
│  │                                     │                         │
│  │  입력:                               │                         │
│  │   - 스트리머 발언 (Whisper)          │                         │
│  │   - 채팅 분위기 (ChatReader)         │                         │
│  │   - 대화 히스토리                     │                         │
│  │                                     │                         │
│  │  출력: "인정ㅋㅋ 날씨 개꿀"           │                         │
│  └──────────────┬──────────────────────┘                         │
│                 │                                                │
│                 │ response                                       │
│                 ▼                                                │
│  ┌──────────────────────┐                                        │
│  │  수동 승인 (기본)     │                                        │
│  │  Enter=전송           │                                        │
│  │  s=스킵 / e=수정      │                                        │
│  └──────────┬───────────┘                                        │
│             │                                                    │
│             ▼                                                    │
│  ┌──────────────────────┐                                        │
│  │  ChatSender           │                                       │
│  │  (pyautogui)          │                                       │
│  │                       │                                       │
│  │  클립보드 복사         │                                       │
│  │  → 채팅창 클릭        │                                        │
│  │  → Ctrl+V 붙여넣기    │                                       │
│  │  → Enter 전송         │                                        │
│  └───────────────────────┘                                       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 데이터 흐름 요약

```
브라우저 오디오 ──→ soundcard 루프백 ──→ Whisper STT ──→ 텍스트
                                                          │
치지직 WebSocket ──→ ChatReader ──→ 최근 채팅 ─────────────┤
                                                          ▼
                                                    Ollama LLM
                                                          │
                                                     응답 생성
                                                          │
                                                   수동 승인/자동
                                                          │
                                                  pyautogui 입력
                                                          │
                                                    채팅창 전송
```

## 시스템 요구사항

- Python 3.9 이상
- 최소 8GB RAM (Whisper 모델 실행용)
- GPU 권장 (CUDA, RTX 3090 등)
- Windows (WASAPI 루프백)
- Ollama 설치 필요

## 프로젝트 구조

```
chzzk-bot/
├── main.py                  # 메인 실행 (통합 제어)
├── config.py                # 환경 변수 설정 관리
├── audio_capture.py         # 시스템 오디오 루프백 캡처 (soundcard)
├── speech_recognition.py    # 음성 인식 (Whisper STT)
├── llm_handler.py           # LLM 응답 생성 (Ollama)
├── chat_reader.py           # 실시간 채팅 수집 (chzzkpy WebSocket)
├── chat_sender.py           # 채팅 자동 입력 (pyautogui)
├── requirements.txt         # 의존성 패키지
├── .env                     # 환경 변수 (gitignore)
├── .env.example             # 환경 변수 템플릿
└── README.md                # 이 파일
```

## 설치 가이드

### 1. Python 환경 설정

```bash
# conda 환경 생성 (권장)
conda create -n chzzk-bot python=3.10
conda activate chzzk-bot

# 또는 venv
python -m venv venv
venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt
```

### 2. Ollama 설치

```bash
# https://ollama.ai/download 에서 설치 후
ollama pull gemma2    # 한국어 지원 모델 (권장)

# Ollama 서버 실행
ollama serve
```

### 3. 환경 변수 설정

```bash
cp .env.example .env
```

`.env` 파일 편집:
```env
CHZZK_CLIENT_ID=your_client_id
CHZZK_CLIENT_SECRET=your_client_secret
CHZZK_CHANNEL_ID=target_channel_id

OLLAMA_MODEL=gemma2
WHISPER_MODEL=base

AUDIO_SAMPLE_RATE=48000
AUDIO_CHUNK_DURATION=5
RESPONSE_COOLDOWN=10
```

## 사용 방법

### 기본 실행 (수동 승인 모드)

```bash
python main.py
```

메시지 전송 전 사용자 확인을 거칩니다:
- `Enter` = 전송
- `s` = 스킵
- `e` = 수정 후 전송

### 자동 전송 모드

```bash
python main.py --auto
```

### Mock 모드 (테스트용)

실제 채팅을 전송하지 않고 콘솔에만 출력:

```bash
python main.py --mock
```

### 실행 순서

1. 프로그램 시작
2. 방송 URL 입력 (예: `https://chzzk.naver.com/live/채널ID`)
3. 채팅 리더 연결 (WebSocket으로 실시간 채팅 수집)
4. Whisper 모델 로딩
5. Ollama 연결 확인
6. 오디오 출력 장치 선택 (브라우저 소리가 나오는 스피커)
7. 채팅 입력창 마우스 위치 설정 (5초 카운트다운)
8. 봇 동작 시작
9. `Ctrl+C`로 종료

## 모듈 설명

| 모듈 | 역할 | 핵심 기술 |
|------|------|----------|
| `audio_capture.py` | 시스템 오디오 루프백 캡처 | soundcard, WASAPI |
| `speech_recognition.py` | 음성 → 텍스트 변환 | OpenAI Whisper |
| `llm_handler.py` | 자연스러운 채팅 응답 생성 | Ollama (gemma2) |
| `chat_reader.py` | 실시간 채팅 메시지 수집 | chzzkpy WebSocket |
| `chat_sender.py` | 채팅창 자동 입력 | pyautogui + pyperclip |
| `config.py` | 환경 변수 관리 | python-dotenv |

## 설정 커스터마이징

### Whisper 모델

| 모델 | 크기 | 속도 | 정확도 |
|------|------|------|--------|
| tiny | 39M | 매우 빠름 | 낮음 |
| base | 74M | 빠름 | 보통 |
| small | 244M | 보통 | 좋음 |
| medium | 769M | 느림 | 매우 좋음 |

### Ollama 모델

| 모델 | 한국어 | 속도 |
|------|--------|------|
| gemma2 | 좋음 (권장) | 보통 |
| mistral | 보통 | 빠름 |
| llama2 | 나쁨 | 보통 |

## 트러블슈팅

### 음성이 감지되지 않음
- 오디오 장치 선택 시 브라우저 소리가 나오는 스피커를 선택했는지 확인
- 브라우저에서 방송 소리가 실제로 나오고 있는지 확인

### Whisper 인식 품질이 낮음
- `WHISPER_MODEL`을 `small` 또는 `medium`으로 변경
- GPU 사용 설정 (CUDA)

### LLM이 영어로 응답함
- `OLLAMA_MODEL=gemma2`로 변경 (`ollama pull gemma2` 필요)
- llama2는 한국어 지원이 부족함

### 채팅 입력이 안 됨
- 채팅 입력창 위치 설정 시 정확한 위치에 마우스를 올려둘 것
- 긴급 중지: 마우스를 화면 좌상단 모서리로 이동

## 주의사항

- 이 봇은 교육 및 개인 사용 목적입니다
- 스팸 방지를 위해 쿨다운이 설정되어 있습니다
- 치지직 이용 약관을 준수하세요
- 봇 사용으로 인한 제재는 사용자 책임입니다

## 라이선스

MIT License
