# Baseline Environment

## 推荐环境

优先直接使用已有 conda 环境：

```powershell
conda activate ai4s
```

当前 baseline 骨架依赖很轻：

- Python 3.10+
- `torch`
- `pandas`
- `pyyaml`
- `scikit-learn`
- `numpy`

## 快速自检

```powershell
conda run -n ai4s python -c "import torch, pandas, yaml, sklearn, numpy; print(torch.__version__)"
```

## 如果需要重建最小环境

```powershell
conda create -n ai4s-baseline python=3.11 -y
conda activate ai4s-baseline
pip install torch pandas pyyaml scikit-learn numpy
```

如果后续加入 GPU、结构模态或更复杂评估，再在这个基础上增补依赖。

