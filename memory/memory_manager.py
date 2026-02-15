import requests
import json
import time
import threading
from config import Config


class MemoryManager:
    """메모리 업데이트 관리자

    N번의 상호작용마다 별도 LLM 호출로 메모리를 갱신합니다.
    """

    def __init__(self, streamer_memory, chat_memory, my_chat_memory):
        self.streamer_memory = streamer_memory
        self.chat_memory = chat_memory
        self.my_chat_memory = my_chat_memory

        self.interaction_buffer = []
        self.chat_context_buffer = []
        self._buffer_lock = threading.Lock()
        self.update_interval = 5
        self.interaction_count = 0

        self.api_url = f"{Config.OLLAMA_HOST}/api/generate"
        self.model_name = Config.OLLAMA_MODEL

    def record_interaction(self, streamer_speech, bot_response, chat_context=""):
        """상호작용 기록"""
        with self._buffer_lock:
            self.interaction_buffer.append({
                "streamer": streamer_speech,
                "bot": bot_response,
                "time": time.time()
            })
            if chat_context:
                self.chat_context_buffer.append(chat_context)

            if len(self.interaction_buffer) > 10:
                self.interaction_buffer = self.interaction_buffer[-10:]
            if len(self.chat_context_buffer) > 5:
                self.chat_context_buffer = self.chat_context_buffer[-5:]

        self.interaction_count += 1

        if self.interaction_count % self.update_interval == 0:
            thread = threading.Thread(target=self._update_all_memories, daemon=True)
            thread.start()

    def _update_all_memories(self):
        """모든 메모리 업데이트"""
        print("\n[메모리] 메모리 업데이트 중...")

        interactions_text = self._format_interactions()
        chat_text = self._format_chat_contexts()

        self._update_streamer_memory(interactions_text)
        self._update_chat_memory(chat_text)
        self._update_my_chat_memory(interactions_text)

        print("[메모리] 업데이트 완료")

    def _format_interactions(self):
        """상호작용 버퍼를 텍스트로 변환"""
        with self._buffer_lock:
            buffer_copy = list(self.interaction_buffer)
        lines = []
        for item in buffer_copy:
            lines.append(f"스트리머: {item['streamer']}")
            lines.append(f"봇: {item['bot']}")
        return "\n".join(lines)

    def _format_chat_contexts(self):
        """채팅 컨텍스트 버퍼를 텍스트로 변환"""
        with self._buffer_lock:
            contexts = list(self.chat_context_buffer[-3:])
        return "\n---\n".join(contexts)

    def _update_streamer_memory(self, interactions_text):
        """스트리머 메모리 업데이트"""
        current_facts = self.streamer_memory.get_facts_as_prompt()
        prompt = f"""다음은 스트리머의 최근 발언입니다:
{interactions_text}

기존 스트리머 정보:
{current_facts if current_facts else "(없음)"}

위 내용을 바탕으로 스트리머에 대한 핵심 특징을 최대 5개 한국어 문장으로 정리하세요.
각 문장은 20자 이내로 짧게 작성하세요.
JSON 배열로만 응답하세요. 예: ["특징1", "특징2"]"""

        facts = self._call_llm_for_facts(prompt)
        if facts:
            self.streamer_memory.replace_all_facts(facts)

    def _update_chat_memory(self, chat_text):
        """채팅 메모리 업데이트"""
        if not chat_text:
            return
        current_facts = self.chat_memory.get_facts_as_prompt()
        prompt = f"""다음은 최근 채팅 내용입니다:
{chat_text}

기존 채팅 분위기 정보:
{current_facts if current_facts else "(없음)"}

채팅 분위기의 핵심 특징을 최대 4개 한국어 문장으로 정리하세요.
각 문장은 20자 이내로 짧게 작성하세요.
JSON 배열로만 응답하세요. 예: ["특징1", "특징2"]"""

        facts = self._call_llm_for_facts(prompt)
        if facts:
            self.chat_memory.replace_all_facts(facts)

    def _update_my_chat_memory(self, interactions_text):
        """내 채팅 메모리 업데이트"""
        current_facts = self.my_chat_memory.get_facts_as_prompt()
        prompt = f"""다음은 봇의 최근 응답들입니다:
{interactions_text}

기존 봇 응답 패턴 정보:
{current_facts if current_facts else "(없음)"}

봇의 응답 패턴/특징을 최대 4개 한국어 문장으로 정리하세요.
각 문장은 20자 이내로 짧게 작성하세요.
JSON 배열로만 응답하세요. 예: ["특징1", "특징2"]"""

        facts = self._call_llm_for_facts(prompt)
        if facts:
            self.my_chat_memory.replace_all_facts(facts)

    def _call_llm_for_facts(self, prompt):
        """LLM을 호출하여 fact 리스트 추출"""
        try:
            payload = {
                "model": self.model_name,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.3,
                    "max_tokens": 200
                }
            }
            response = requests.post(self.api_url, json=payload, timeout=30)
            if response.status_code == 200:
                text = response.json().get("response", "").strip()
                return self._parse_json_array(text)
        except Exception as e:
            print(f"[메모리] LLM 호출 실패: {e}")
        return None

    def _parse_json_array(self, text):
        """LLM 응답에서 JSON 배열 파싱"""
        text = text.strip()

        # 마크다운 코드블록 제거
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1])

        # [ ... ] 추출
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass

        # 폴백: 줄 단위 추출
        lines = [l.strip().strip("-").strip() for l in text.split("\n") if l.strip()]
        return lines[:5] if lines else None

    def force_update(self):
        """강제 메모리 업데이트 (동기)"""
        if self.interaction_buffer:
            self._update_all_memories()

    def save_all(self):
        """모든 메모리를 디스크에 저장"""
        self.streamer_memory.save()
        self.chat_memory.save()
        self.my_chat_memory.save()
