# TODO

## Performance
- [x] ASR 추론 벤치마크 — PyTorch 기본 201ms/5초 (25x 실시간)
- [x] torch.compile 시도 — PyTorch 2.5.1 + triton-windows 3.6.0 버전 불일치로 미작동
- [ ] PyTorch + triton 호환 조합 찾기 (Windows에서 torch.compile 활성화)
- [ ] TensorRT — Qwen3-ASR 인코더가 동적 연산(pad_sequence, split, cumsum) 사용하여 ONNX 비호환

## AI Quality
- [ ] LoRA 파인튜닝 - 스트리머/채널별 채팅 스타일 학습 (현재 프롬프트 메모리 → 모델 레벨)
