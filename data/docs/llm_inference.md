# 大模型推理优化

## 为什么需要推理优化

大模型参数量大，推理（inference）时计算密集、显存占用高。优化推理可以降低延迟、提升吞吐、节省成本。

## 核心优化技术

### 1. KV Cache
Transformer 自回归生成时，缓存已计算的 Key/Value 矩阵，避免重复计算。是所有推理加速的基础。

### 2. PagedAttention
vLLM 提出的分页注意力机制，借鉴操作系统虚拟内存思想，将 KV Cache 分块管理，减少显存碎片，提升吞吐量。

### 3. 连续批处理（Continuous Batching）
动态拼合不同请求的 batch，避免等待慢请求，显著提升 GPU 利用率。

### 4. 量化（Quantization）
将模型权重从 FP16 降到 INT8 或 INT4，减少显存和计算量。常见方法：
- GPTQ：训练后量化
- AWQ：激活感知量化
- GGUF：llama.cpp 使用的格式

### 5. 投机解码（Speculative Decoding）
用小模型快速生成草稿，大模型验证，减少大模型的前向次数。

## 主流推理框架

| 框架 | 特点 |
|------|------|
| vLLM | 高吞吐，PagedAttention，生产首选 |
| TensorRT-LLM | NVIDIA 官方，极致性能 |
| llama.cpp | CPU/GPU 通用，轻量 |
| Ollama | 本地一键部署，易用 |

## 部署建议

- 高并发生产：vLLM / TensorRT-LLM
- 本地开发：Ollama / llama.cpp
- 资源受限：量化模型 + llama.cpp
