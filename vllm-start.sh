
# For Qwen models, reffer to official docs
# https://qwen.readthedocs.io/en/latest/framework/function_call.html#vllm
CUDA_VISIBLE_DEVICES=1 vllm serve "Qwen/Qwen3.5-9B" \
  --enable-auto-tool-choice \
  --tool-call-parser hermes \
  --reasoning-parser deepseek_r1 \
  --port 9000
