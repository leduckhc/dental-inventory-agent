# Start vLLM with Qwen3.5-9B.
# Ref: https://qwen.readthedocs.io/en/latest/framework/function_call.html#vllm
CUDA_VISIBLE_DEVICES=1 vllm serve "Qwen/Qwen3.5-9B" \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3_coder \
  --reasoning-parser qwen3 \
  --port 9000
