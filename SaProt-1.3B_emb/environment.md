# SaProt-1.3B Environment

## 优先策略

优先复用 `ai4s`，前提是：

- `torch.cuda.is_available() == True`
- `transformers`、`huggingface_hub`、`safetensors`、`pandas`、`pyarrow` 已安装
- `AutoModel.from_pretrained(...)` 能完成预检

## 当前已确认的 ai4s 状态

- Python `3.12.12`
- torch `2.10.0+cu128`
- CUDA 可用
- `transformers`、`safetensors`、`pandas`、`pyarrow`、`sentencepiece` 已安装

## 何时新建环境

只有在以下情况才新建 `saprot13b`：

- 模型加载时出现原生崩溃
- 依赖冲突无法通过小改动解决
- CUDA 推理不稳定

## 独立环境最小依赖

- Python `3.10` 或 `3.11`
- GPU 版 PyTorch
- `transformers`
- `huggingface_hub`
- `safetensors`
- `pandas`
- `pyarrow`
- `tqdm`
