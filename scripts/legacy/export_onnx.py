"""Qwen3-ASR 추론 최적화 스크립트

torch.compile로 오디오 인코더를 최적화하거나,
ONNX 변환을 시도합니다.

Qwen3-ASR 인코더는 동적 청킹/패딩을 사용하여
직접 ONNX export가 어렵습니다. torch.compile이 권장됩니다.

사용법:
    python scripts/export_onnx.py                    # torch.compile 벤치마크
    python scripts/export_onnx.py --model Qwen/Qwen3-ASR-1.7B
    python scripts/export_onnx.py --try-onnx         # ONNX 변환 시도
"""
import argparse
import sys
import time
from pathlib import Path

import numpy as np
import torch

# 프로젝트 루트를 path에 추가
SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_DIR))

DEFAULT_MODEL = "Qwen/Qwen3-ASR-0.6B"


def load_model(model_name: str):
    """qwen_asr 모델 로드"""
    from qwen_asr import Qwen3ASRModel

    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    asr = Qwen3ASRModel.from_pretrained(
        model_name,
        dtype=torch.float16 if device != "cpu" else torch.float32,
        device_map=device,
        max_new_tokens=256,
    )
    return asr, device


def benchmark_transcribe(asr_model, device: str, iterations: int = 5):
    """전체 transcribe 파이프라인 벤치마크 (5초 오디오)"""
    print(f"\n[벤치마크] 전체 파이프라인 ({iterations}회)")

    # 5초 16kHz 더미 오디오
    audio = np.random.randn(16000 * 5).astype(np.float32) * 0.1

    # 워밍업
    print("  워밍업...")
    for _ in range(2):
        asr_model.transcribe(audio=(audio, 16000), language="Korean")

    # 벤치마크
    times = []
    for i in range(iterations):
        start = time.perf_counter()
        asr_model.transcribe(audio=(audio, 16000), language="Korean")
        elapsed = time.perf_counter() - start
        times.append(elapsed)
        print(f"  [{i+1}/{iterations}] {elapsed*1000:.0f}ms")

    avg = sum(times) / len(times)
    print(f"  평균: {avg*1000:.0f}ms / 추론")
    return avg


def try_torch_compile(asr_model, device: str):
    """torch.compile로 인코더 최적화 시도"""
    print("\n[torch.compile] 인코더 최적화 시도...")

    thinker = asr_model.model.thinker
    original_encoder = thinker.audio_tower

    try:
        compiled = torch.compile(original_encoder, mode="reduce-overhead")
        thinker.audio_tower = compiled
        print("[torch.compile] 컴파일 성공 (첫 추론 시 실제 컴파일)")
        return True
    except Exception as e:
        print(f"[torch.compile] 실패: {e}")
        thinker.audio_tower = original_encoder
        return False


def try_onnx_export(asr_model, device: str):
    """ONNX 변환 시도 (인코더의 동적 연산으로 인해 실패할 수 있음)"""
    print("\n[ONNX] 인코더 변환 시도...")
    print("[ONNX] 주의: Qwen3-ASR 인코더는 동적 청킹/패딩을 사용하여")
    print("[ONNX] ONNX export가 실패할 가능성이 높습니다.")

    output_dir = PROJECT_DIR / "models" / "onnx"
    output_dir.mkdir(parents=True, exist_ok=True)

    thinker = asr_model.model.thinker
    audio_encoder = thinker.audio_tower
    audio_encoder.eval()

    # 인코더는 (input_features, feature_lens) 를 받음
    num_mel_bins = audio_encoder.config.num_mel_bins
    time_steps = 500  # 5초 오디오

    dummy_features = torch.randn(1, num_mel_bins, time_steps).to(device)
    dummy_lens = torch.tensor([time_steps], dtype=torch.long).to(device)
    if device != "cpu":
        dummy_features = dummy_features.half()

    encoder_path = output_dir / "encoder.onnx"

    try:
        with torch.no_grad():
            torch.onnx.export(
                audio_encoder,
                (dummy_features, dummy_lens),
                str(encoder_path),
                input_names=["input_features", "feature_lens"],
                output_names=["audio_features"],
                dynamic_axes={
                    "input_features": {0: "batch", 2: "time"},
                    "feature_lens": {0: "batch"},
                },
                opset_version=17,
                do_constant_folding=True,
            )
        size_mb = encoder_path.stat().st_size / 1024 / 1024
        print(f"[ONNX] 인코더 변환 성공! → {encoder_path} ({size_mb:.1f} MB)")
        return True
    except Exception as e:
        print(f"[ONNX] 인코더 변환 실패: {e}")
        if encoder_path.exists():
            encoder_path.unlink()
        return False


def main():
    parser = argparse.ArgumentParser(description="Qwen3-ASR 추론 최적화")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="모델 이름")
    parser.add_argument("--try-onnx", action="store_true", help="ONNX 변환 시도")
    parser.add_argument("--iterations", type=int, default=5, help="벤치마크 반복 횟수")
    args = parser.parse_args()

    print(f"=== Qwen3-ASR 추론 최적화 ===")
    print(f"모델: {args.model}")
    print(f"CUDA: {'사용 가능' if torch.cuda.is_available() else '미사용 (CPU)'}")
    print(f"PyTorch: {torch.__version__}")

    # 1. 모델 로드
    print("\n[1] 모델 로딩...")
    asr, device = load_model(args.model)

    # 2. 기본 벤치마크 (PyTorch)
    print("\n[2] PyTorch 기본 벤치마크")
    base_time = benchmark_transcribe(asr, device, args.iterations)

    # 3. torch.compile 벤치마크
    print("\n[3] torch.compile 최적화")
    if try_torch_compile(asr, device):
        compile_time = benchmark_transcribe(asr, device, args.iterations)
        speedup = base_time / compile_time if compile_time > 0 else 0
        print(f"\n  속도 향상: {speedup:.2f}x ({base_time*1000:.0f}ms → {compile_time*1000:.0f}ms)")

    # 4. ONNX 시도 (선택)
    if args.try_onnx:
        # torch.compile 해제 후 원본 모델로 ONNX 시도
        asr2, _ = load_model(args.model)
        try_onnx_export(asr2, device)

    print("\n=== 완료 ===")


if __name__ == "__main__":
    main()
