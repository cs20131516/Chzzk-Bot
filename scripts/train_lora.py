"""
LoRA 파인튜닝 스크립트 - Qwen3 채팅 스타일 학습

PEFT + TRL을 사용하여 수집한 본인 채팅 데이터로 QLoRA 학습 후
LoRA 어댑터를 저장합니다.

설치 (별도 venv 권장):
  pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
  pip install peft trl datasets accelerate bitsandbytes transformers sentencepiece

사용법:
  # 1단계: 데이터 준비
  python scripts/prepare_training_data.py

  # 2단계: 학습
  python scripts/train_lora.py

  # 3단계: Ollama에 등록 (llama.cpp로 GGUF 변환 필요)
  #   방법은 학습 완료 후 출력되는 안내 참고
"""

import argparse
import json
import sys
from pathlib import Path


def load_training_data(path):
    """JSONL 학습 데이터를 로드"""
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def main():
    parser = argparse.ArgumentParser(description="LoRA 파인튜닝")
    parser.add_argument("--data", default="data/training_data.jsonl", help="학습 데이터 경로")
    parser.add_argument("--base-model", default="Qwen/Qwen3-8B",
                        help="베이스 모델 (기본: Qwen3-8B)")
    parser.add_argument("--output-dir", default="outputs/qwen3-chat-lora", help="출력 디렉토리")
    parser.add_argument("--epochs", type=int, default=3, help="학습 에포크 (기본 3)")
    parser.add_argument("--lr", type=float, default=5e-5, help="학습률 (기본 5e-5)")
    parser.add_argument("--rank", type=int, default=32, help="LoRA rank (기본 32)")
    parser.add_argument("--batch-size", type=int, default=2, help="배치 크기 (기본 2)")
    args = parser.parse_args()

    data_path = Path(args.data)
    if not data_path.exists():
        print(f"학습 데이터를 찾을 수 없습니다: {data_path}")
        print("먼저 prepare_training_data.py를 실행하세요.")
        sys.exit(1)

    records = load_training_data(data_path)
    print(f"학습 데이터: {len(records)}개")

    if len(records) < 10:
        print("학습 데이터가 너무 적습니다 (최소 10개 이상 권장).")
        sys.exit(1)

    # ──────────────────── 임포트 ────────────────────
    print("\n라이브러리 로딩중...")
    import torch
    from datasets import Dataset
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from trl import SFTTrainer, SFTConfig

    # ──────────────────── 모델 로딩 (4bit 양자화) ────────────────────
    print(f"모델 로딩: {args.base_model} (4-bit QLoRA)")

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16,
        bnb_4bit_use_double_quant=True,
    )

    tokenizer = AutoTokenizer.from_pretrained(args.base_model, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )

    model = prepare_model_for_kbit_training(model)

    # ──────────────────── LoRA 설정 ────────────────────
    print(f"LoRA 설정 (rank={args.rank})")

    lora_config = LoraConfig(
        r=args.rank,
        lora_alpha=args.rank,  # alpha = rank
        lora_dropout=0.05,
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
        bias="none",
        task_type="CAUSAL_LM",
    )

    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # ──────────────────── 데이터셋 준비 ────────────────────
    dataset = Dataset.from_list(records)

    def format_conversations(examples):
        texts = []
        for convos in examples["conversations"]:
            text = tokenizer.apply_chat_template(
                convos,
                tokenize=False,
                add_generation_prompt=False,
                enable_thinking=False,
            )
            texts.append(text)
        return {"text": texts}

    dataset = dataset.map(format_conversations, batched=True)
    print(f"데이터셋 준비 완료: {len(dataset)}개")

    # 토큰 길이 통계
    lengths = [len(tokenizer.encode(t)) for t in dataset["text"]]
    print(f"  토큰 길이 - 평균: {sum(lengths)/len(lengths):.0f}, "
          f"최대: {max(lengths)}, 최소: {min(lengths)}")

    # ──────────────────── 학습 설정 ────────────────────
    total_steps = (len(dataset) // (args.batch_size * 4)) * args.epochs
    warmup_steps = max(5, total_steps // 20)

    training_config = SFTConfig(
        output_dir=args.output_dir,
        dataset_text_field="text",
        max_length=2048,
        packing=False,

        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=4,

        learning_rate=args.lr,
        warmup_steps=warmup_steps,
        num_train_epochs=args.epochs,

        optim="adamw_8bit",
        weight_decay=0.05,
        lr_scheduler_type="cosine",

        logging_steps=5,
        save_strategy="epoch",
        gradient_checkpointing=True,

        seed=42,
        fp16=not torch.cuda.is_bf16_supported(),
        bf16=torch.cuda.is_bf16_supported(),
    )

    # ──────────────────── 학습 ────────────────────
    trainer = SFTTrainer(
        model=model,
        processing_class=tokenizer,
        train_dataset=dataset,
        args=training_config,
    )

    print(f"\n학습 시작 (epochs={args.epochs}, lr={args.lr}, batch={args.batch_size}x4)")
    print(f"  예상 총 스텝: ~{total_steps}")
    stats = trainer.train()
    print(f"\n학습 완료! Final loss: {stats.training_loss:.4f}")

    # ──────────────────── 저장 ────────────────────
    output_dir = Path(args.output_dir)

    # LoRA 어댑터 저장
    adapter_dir = output_dir / "adapter"
    model.save_pretrained(str(adapter_dir))
    tokenizer.save_pretrained(str(adapter_dir))
    print(f"\nLoRA 어댑터 저장: {adapter_dir}")

    print(f"\n{'='*60}")
    print("학습 완료!")
    print(f"어댑터 위치: {adapter_dir}")
    print()
    print("Ollama에서 사용하려면 GGUF 변환이 필요합니다:")
    print("  1. llama.cpp의 convert_lora_to_gguf.py로 변환")
    print("  2. Modelfile에 ADAPTER로 지정")
    print()
    print("또는 transformers에서 직접 사용:")
    print(f"  from peft import PeftModel")
    print(f"  model = PeftModel.from_pretrained(base_model, '{adapter_dir}')")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
