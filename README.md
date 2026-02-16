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
│  │ Qwen3-ASR    │                 │                              │
│  │ (음성→텍스트) │                 │                              │
│  └──────┬───────┘                 │                              │
│         │                         │                              │
│         │ streamer_speech         │                              │
│         ▼                         ▼                              │
│  ┌─────────────────────────────────────┐                         │
│  │           LLM (Ollama)              │                         │
│  │                                     │                         │
│  │  입력:                               │                         │
│  │   - 스트리머 발언 (Qwen3-ASR)       │                         │
│  │   - 채팅 분위기 (ChatReader)         │                         │
│  │   - 대화 히스토리                     │                         │
│  │   - 메모리 (스트리머/채팅/내 응답)    │                         │
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
│  │  m=모드 전환           │                                       │
│  └──────────┬───────────┘                                        │
│             │                                                    │
│             ▼                                                    │
│  ┌──────────────────────┐                                        │
│  │  ChatSender           │                                       │
│  │  (chzzkpy WebSocket)  │                                       │
│  └───────────────────────┘                                       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 데이터 흐름 요약

```
브라우저 오디오 ──→ soundcard 루프백 ──→ Qwen3-ASR ──→ 텍스트
                                                          │
치지직 WebSocket ──→ ChatReader ──→ 최근 채팅 ─────────────┤
                                                          │
채널별 메모리 (JSON) ──→ 스트리머/채팅/내 응답 패턴 ────────┤
                                                          ▼
                                                    Ollama LLM
                                                          │
                                                     응답 생성
                                                          │
                                                   수동 승인/자동
                                                          │
                                                chzzkpy WebSocket
                                                          │
                                                    채팅 API 전송
```

## 시스템 요구사항

- Python 3.9 이상
- 최소 8GB RAM (ASR 모델 실행용)
- GPU 권장 (CUDA, RTX 3090 등)
- Windows (WASAPI 루프백)
- Ollama 설치 필요

## 프로젝트 구조

```
chzzk-bot/
├── main.py                  # 메인 실행 (통합 제어)
├── config.py                # 환경 변수 설정 관리
├── audio_capture.py         # 시스템 오디오 루프백 캡처 (soundcard)
├── speech_recognition.py    # 음성 인식 (Qwen3-ASR)
├── llm_handler.py           # LLM 응답 생성 (Ollama)
├── chat_reader.py           # 실시간 채팅 수집 (chzzkpy WebSocket)
├── chat_sender.py           # 채팅 전송 (chzzkpy WebSocket + 네이버 쿠키)
├── memory/                  # 메모리 시스템
│   ├── memory_store.py      # JSON 파일 기반 메모리 저장소
│   └── memory_manager.py    # LLM 기반 메모리 자동 업데이트
├── data/                    # 채널별 메모리 데이터 (gitignore)
│   └── {channel_id}/
│       ├── streamer_memory.json
│       ├── chat_memory.json
│       └── my_chat_memory.json
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
ollama pull qwen3:8b    # 한국어 지원 모델 (권장, 4b는 instruction 미준수)

# Ollama 서버 실행
ollama serve
```

### 3. 환경 변수 설정

```bash
cp .env.example .env
```

`.env` 파일 편집:
```env
# 치지직 채널 설정
CHZZK_CHANNEL_ID=target_channel_id

# Ollama 설정
OLLAMA_MODEL=qwen3:8b
OLLAMA_HOST=http://localhost:11434
OLLAMA_KEEP_ALIVE=10m

# LLM 생성 설정
LLM_MAX_TOKENS=200
LLM_NUM_CTX=2048

# ASR 설정
ASR_MODEL=Qwen/Qwen3-ASR-0.6B

# 오디오 설정
AUDIO_SAMPLE_RATE=48000
AUDIO_CHUNK_DURATION=5

# 채팅 설정
RESPONSE_COOLDOWN=10
RESPONSE_CHANCE=1.0
RESPONSE_MODE=ai        # ai (LLM 응답) / mimic (채팅 따라하기)
WARMUP_SECONDS=0         # 시작 후 관찰만 하는 시간 (초)

# 네이버 로그인 쿠키 (채팅 전송 + 성인인증 채널용)
# 크롬 F12 → Application → Cookies → chzzk.naver.com 에서 복사
NID_AUT=
NID_SES=
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
- `m` = 모드 전환 (AI ↔ 따라하기)

> **참고**: AI 모드는 하이브리드로 동작합니다. 최근 채팅 10개 중 단순 반응(ㅋㅋㅋ, ㅎㅎ 등)이 4개 이상이면 분위기를 타고 따라치고, 그 외엔 LLM으로 응답합니다. 따라치기 시 반복 문자 개수를 랜덤하게 변형하여 봇처럼 보이지 않게 합니다.

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
3. 채널별 메모리 로드 (기존 데이터가 있으면 자동 로드)
4. 채팅 리더 연결 (WebSocket으로 실시간 채팅 수집)
5. ASR 모델 로딩
6. Ollama 연결 확인
7. 오디오 출력 장치 선택 (브라우저 소리가 나오는 스피커)
8. 네이버 로그인 인증 (쿠키 or 브라우저 자동 로그인)
9. 봇 동작 시작 (ASR/LLM/Mimic 워커 스레드 병렬 실행)
10. `Ctrl+C`로 종료 (메모리 자동 저장)

## 메모리 시스템

봇은 채널별로 3가지 메모리를 JSON 파일로 유지합니다:

| 메모리 | 내용 | 최대 |
|--------|------|------|
| 스트리머 메모리 | 스트리머의 특징, 말투, 게임 장르 등 | 5개 |
| 채팅 메모리 | 채팅 분위기, 자주 쓰는 밈/이모티콘 등 | 4개 |
| 내 채팅 메모리 | 봇의 응답 패턴, 자주 쓰는 표현 등 | 4개 |

- 5회 상호작용마다 LLM이 자동으로 메모리를 요약/갱신
- 채널마다 별도 저장 (`data/{channel_id}/`)
- 같은 채널 재접속 시 기존 메모리 자동 로드
- 종료 시 메모리 자동 저장

## 모듈 설명

| 모듈 | 역할 | 핵심 기술 |
|------|------|----------|
| `audio_capture.py` | 시스템 오디오 루프백 캡처 | soundcard, WASAPI |
| `speech_recognition.py` | 음성 → 텍스트 변환 | Qwen3-ASR |
| `llm_handler.py` | 자연스러운 채팅 응답 생성 | Ollama (qwen3:8b) |
| `chat_reader.py` | 실시간 채팅 메시지 수집 | chzzkpy WebSocket |
| `chat_sender.py` | 채팅 WebSocket 전송 | chzzkpy + selenium |
| `config.py` | 환경 변수 관리 | python-dotenv |
| `memory/memory_store.py` | 메모리 저장/로드 | JSON 파일 |
| `memory/memory_manager.py` | 메모리 자동 갱신 | Ollama LLM |

## 설정 커스터마이징

### ASR 모델 (음성 인식)

| 모델 | 크기 | 한국어 | 특징 |
|------|------|--------|------|
| Qwen/Qwen3-ASR-0.6B | 0.6B | 지원 (권장) | 가볍고 빠름 |
| Qwen/Qwen3-ASR-1.7B | 1.7B | 지원 | 더 높은 정확도 |

> **대안 모델**: [Voxtral-Mini-4B](https://huggingface.co/mistralai/Voxtral-Mini-4B-Realtime-2602) - 실시간 스트리밍 ASR, 한국어 지원, VRAM 16GB+ 필요 (vLLM 필수)

### Ollama 모델

| 모델 | 한국어 | 속도 | 비고 |
|------|--------|------|------|
| qwen3:8b | 매우 좋음 (권장) | 보통 | instruction 준수 우수 |
| exaone3.5:7.8b | 매우 좋음 | 보통 | LG AI, 한국어 특화 |
| exaone3.5:2.4b | 좋음 | 빠름 | 경량 한국어 모델 |
| qwen3:4b | 보통 | 빠름 | 영어로 응답하는 경우 있음 |

## 트러블슈팅

### 음성이 감지되지 않음
- 오디오 장치 선택 시 브라우저 소리가 나오는 스피커를 선택했는지 확인
- 브라우저에서 방송 소리가 실제로 나오고 있는지 확인

### ASR 인식 품질이 낮음
- `ASR_MODEL=Qwen/Qwen3-ASR-1.7B`로 더 큰 모델 사용
- GPU 사용 설정 (CUDA)

### LLM이 영어로 응답함
- `OLLAMA_MODEL=qwen3:8b` 이상 사용 권장 (`ollama pull qwen3:8b`)
- qwen3:4b는 instruction을 따르지 않아 영어로 응답하는 경우가 많음
- EXAONE 3.5도 한국어 응답에 강함 (`ollama pull exaone3.5:7.8b`)

### 채팅 전송이 안 됨
- `.env`에 `NID_AUT`, `NID_SES` 쿠키가 올바른지 확인 (크롬 F12 → Application → Cookies → chzzk.naver.com)
- 쿠키 미설정 시 브라우저 자동 로그인이 뜹니다 (네이버 로그인 필요)
- 치지직 채팅이 로그인 사용자만 가능한 채널인지 확인

### "Adult verification" 오류
- 성인인증 채널은 NID_AUT/NID_SES 쿠키 필수 (채팅 읽기/전송 모두 필요)
- 첫 실행 시 브라우저 로그인하면 자동 저장되어 이후 자동 인증

## 주의사항

- 이 봇은 교육 및 개인 사용 목적입니다
- 스팸 방지를 위해 쿨다운이 설정되어 있습니다
- 치지직 이용 약관을 준수하세요
- 봇 사용으로 인한 제재는 사용자 책임입니다

## 라이선스

MIT License
