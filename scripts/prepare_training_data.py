"""
수집된 VOD 채팅 데이터를 LoRA 학습용 포맷으로 변환

사용법:
  python scripts/prepare_training_data.py
  python scripts/prepare_training_data.py --input data/vod_chats/my_chats --output data/training_data.jsonl
  python scripts/prepare_training_data.py --max-laugh-ratio 0.2  # ㅋ 반응 비율 제한
"""

import argparse
import json
import random
import re
from pathlib import Path
from collections import Counter


SYSTEM_PROMPT = (
    "너는 한국 인터넷 방송 채팅 유저야. "
    "채팅방의 분위기에 맞게 자연스럽게 반응해. "
    "짧고 간결하게, 이모티콘과 인터넷 신조어를 자유롭게 써."
)


def is_laugh_only(text):
    """순수 ㅋㅎ 반응인지 판별"""
    cleaned = text.replace(" ", "")
    return bool(cleaned) and all(c in "ㅋㅎ" for c in cleaned)


def is_emote_only(text):
    """치지직 이모티콘만 있는 메시지인지 판별"""
    cleaned = re.sub(r"\{:[^}]+:\}", "", text).strip()
    return not cleaned


def convert_item_to_conversation(item, max_context=5):
    """수집 데이터 1건을 Qwen3 conversation 형식으로 변환"""
    context = item["context"]
    response = item["response"]

    msg = response["message"].strip()
    if not msg:
        return None

    # 맥락 구성 (최근 N개)
    recent = context[-max_context:]
    context_lines = []
    for c in recent:
        m = c["message"].strip()
        if m:
            context_lines.append(f'{c["nickname"]}: {m}')

    if not context_lines:
        return None

    context_str = "\n".join(context_lines)

    return {
        "conversations": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"[채팅방]\n{context_str}"},
            {"role": "assistant", "content": msg},
        ]
    }


def load_and_convert(input_dir, max_context=5):
    """JSONL 파일들을 로드하여 학습 데이터로 변환"""
    input_dir = Path(input_dir)
    jsonl_files = list(input_dir.rglob("*.jsonl"))

    if not jsonl_files:
        print(f"JSONL 파일을 찾을 수 없습니다: {input_dir}")
        return []

    all_items = []
    for f in jsonl_files:
        print(f"  로딩: {f.relative_to(input_dir)}")
        for line in f.read_text(encoding="utf-8").strip().split("\n"):
            if line.strip():
                all_items.append(json.loads(line))

    print(f"  원본 데이터: {len(all_items)}개")

    conversations = []
    for item in all_items:
        conv = convert_item_to_conversation(item, max_context)
        if conv:
            conversations.append(conv)

    print(f"  변환 완료: {len(conversations)}개")
    return conversations


def balance_dataset(conversations, max_laugh_ratio=0.25):
    """ㅋ 반응의 비율을 제한하여 데이터 밸런싱"""
    laugh_items = []
    other_items = []

    for conv in conversations:
        response = conv["conversations"][-1]["content"]
        if is_laugh_only(response):
            laugh_items.append(conv)
        else:
            other_items.append(conv)

    print(f"\n데이터 분포:")
    print(f"  ㅋㅎ 반응: {len(laugh_items)}개")
    print(f"  기타 반응: {len(other_items)}개")

    # ㅋ 반응 수 제한
    max_laugh = int(len(other_items) * max_laugh_ratio / (1 - max_laugh_ratio))
    if len(laugh_items) > max_laugh:
        random.seed(42)
        # 다양한 길이의 ㅋ를 골고루 샘플링
        laugh_lengths = Counter(len(c["conversations"][-1]["content"]) for c in laugh_items)
        sampled = random.sample(laugh_items, min(max_laugh, len(laugh_items)))
        print(f"  ㅋㅎ 반응 샘플링: {len(laugh_items)} → {len(sampled)}개 (최대 {max_laugh_ratio*100:.0f}%)")
        laugh_items = sampled

    balanced = other_items + laugh_items
    random.seed(42)
    random.shuffle(balanced)

    print(f"  밸런싱 후: {len(balanced)}개")
    return balanced


def main():
    parser = argparse.ArgumentParser(description="학습 데이터 준비")
    parser.add_argument("--input", default="data/vod_chats/my_chats", help="입력 디렉토리")
    parser.add_argument("--output", default="data/training_data.jsonl", help="출력 파일")
    parser.add_argument("--max-context", type=int, default=5, help="맥락 메시지 수 (기본 5)")
    parser.add_argument("--max-laugh-ratio", type=float, default=0.25, help="ㅋ 반응 최대 비율 (기본 0.25)")
    parser.add_argument("--no-balance", action="store_true", help="밸런싱 비활성화")
    args = parser.parse_args()

    print("=== 학습 데이터 준비 ===\n")

    conversations = load_and_convert(args.input, args.max_context)
    if not conversations:
        return

    if not args.no_balance:
        conversations = balance_dataset(conversations, args.max_laugh_ratio)

    # 저장
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        for conv in conversations:
            f.write(json.dumps(conv, ensure_ascii=False) + "\n")

    print(f"\n저장 완료: {output} ({len(conversations)}개)")

    # 미리보기
    print("\n=== 미리보기 (3개) ===")
    for i, conv in enumerate(conversations[:3]):
        msgs = conv["conversations"]
        print(f"\n--- Example {i+1} ---")
        print(f"[system] {msgs[0]['content'][:50]}...")
        print(f"[user] {msgs[1]['content'][:80]}...")
        print(f"[assistant] {msgs[2]['content']}")


if __name__ == "__main__":
    main()
