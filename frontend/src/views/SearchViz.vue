<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

const query = ref('')
const loading = ref(false)
const details = ref(null)

const STAGES = [
  { key: 'vector_results', title: '① 向量检索', desc: '语义相似（BGE 余弦）', color: '#409eff' },
  { key: 'bm25_results', title: '② BM25 检索', desc: '关键词精确（jieba 分词）', color: '#67c23a' },
  { key: 'fused_results', title: '③ RRF 融合', desc: '排名倒数加权（k=60）', color: '#e6a23c' },
  { key: 'results', title: '④ 重排输出', desc: 'CrossEncoder 精排（最终）', color: '#f56c6c' },
]

async function search() {
  if (!query.value.trim()) return
  loading.value = true
  details.value = null
  try {
    const { data } = await api.post('/search/details', { query: query.value })
    details.value = data
    if (!data.results?.length) ElMessage.info('未检索到相关内容')
  } finally {
    loading.value = false
  }
}

function short(path) {
  return String(path).split(/[\\/]/).pop()
}
</script>

<template>
  <div class="page">
    <el-card shadow="never">
      <template #header><span>混合检索四阶段可视化</span></template>

      <el-input v-model="query" size="large" placeholder="输入查询，观察 向量 → BM25 → RRF → 重排 各阶段结果"
        clearable @keyup.enter="search">
        <template #append>
          <el-button type="primary" :loading="loading" @click="search">检索</el-button>
        </template>
      </el-input>

      <div v-if="details" class="meta">
        总耗时 <b>{{ details.latency_ms }}ms</b>
        <el-divider direction="vertical" />
        <span v-for="(s, i) in STAGES" :key="s.key">
          {{ s.title }}：<b :style="{ color: s.color }">{{ details[s.key]?.length || 0 }}</b>
          <el-divider v-if="i < STAGES.length - 1" direction="vertical" />
        </span>
      </div>
    </el-card>

    <div v-if="details" class="stages">
      <el-card v-for="s in STAGES" :key="s.key" shadow="never" class="stage-card">
        <template #header>
          <div class="stage-header" :style="{ borderLeftColor: s.color }">
            <span class="stage-title" :style="{ color: s.color }">{{ s.title }}</span>
            <span class="stage-desc">{{ s.desc }}</span>
          </div>
        </template>
        <div v-for="(r, i) in details[s.key]" :key="i" class="chunk">
          <div class="chunk-head">
            <el-tag size="small" :color="s.color" effect="dark" style="border: none">
              #{{ i + 1 }}
            </el-tag>
            <span class="chunk-score" v-if="r.score != null">score {{ r.score.toFixed(4) }}</span>
            <span class="chunk-src">{{ short(r.source) }}</span>
          </div>
          <div class="chunk-text">{{ r.content }}</div>
        </div>
        <el-empty v-if="!details[s.key]?.length" description="无结果" :image-size="48" />
      </el-card>
    </div>
  </div>
</template>

<style scoped>
.page { padding: 20px; }

.meta { margin-top: 14px; color: #606266; font-size: 13px; }

.stages {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
  margin-top: 16px;
  align-items: start;
}

.stage-header {
  padding-left: 8px;
  border-left: 3px solid;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.stage-title { font-weight: 600; font-size: 14px; }
.stage-desc { font-size: 12px; color: #909399; }

.chunk { padding: 8px 0; border-bottom: 1px dashed #ebeef5; }
.chunk:last-child { border-bottom: none; }

.chunk-head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  margin-bottom: 4px;
}

.chunk-score { color: #e6a23c; font-family: monospace; }
.chunk-src { color: #909399; }

.chunk-text {
  font-size: 13px;
  color: #303133;
  line-height: 1.6;
  display: -webkit-box;
  -webkit-line-clamp: 4;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

@media (max-width: 1400px) {
  .stages { grid-template-columns: repeat(2, 1fr); }
}
</style>
