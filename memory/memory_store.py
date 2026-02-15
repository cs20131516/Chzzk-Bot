import json
import os
from datetime import datetime


class MemoryStore:
    """JSON 파일 기반 메모리 저장소"""

    def __init__(self, file_path, max_facts=5):
        self.file_path = file_path
        self.max_facts = max_facts
        self.data = self._load()

    def _load(self):
        """JSON 파일에서 메모리 로드"""
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {"version": 1, "updated_at": None, "facts": []}

    def save(self):
        """JSON 파일에 메모리 저장"""
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        self.data["updated_at"] = datetime.now().isoformat()
        with open(self.file_path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def get_facts(self):
        """모든 fact 텍스트 리스트 반환"""
        return [f["text"] for f in self.data["facts"]]

    def get_facts_as_prompt(self):
        """프롬프트에 삽입할 형식으로 반환"""
        facts = self.get_facts()
        if not facts:
            return ""
        return "\n".join(f"- {fact}" for fact in facts)

    def replace_all_facts(self, new_facts_texts):
        """전체 fact 목록을 교체"""
        now = datetime.now().isoformat()
        self.data["facts"] = []
        for i, text in enumerate(new_facts_texts[:self.max_facts]):
            self.data["facts"].append({
                "id": i + 1,
                "text": text.strip(),
                "created_at": now,
                "updated_at": now
            })
        self.save()

    def is_empty(self):
        return len(self.data["facts"]) == 0
