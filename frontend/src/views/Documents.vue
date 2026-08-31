<script setup>
import { onMounted, onUnmounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'

const loading = ref(false)
const documents = ref([])
const totalChunks = ref(0)

const statusMap = {
  pending: { label: '排队中', type: 'warning' },
  parsing: { label: '解析中', type: 'primary' },
  available: { label: '可用', type: 'success' },
  duplicate: { label: '重复跳过', type: 'info' },
  failed: { label: '失败', type: 'danger' },
}

const textForm = reactive({ source: '', text: '' })
const textSubmitting = ref(false)

// 上传任务轮询表：task_id → setInterval
const pollers = {}
let listTimer = null

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/documents')
    documents.value = data.documents || []
    totalChunks.value = data.total_chunks
  } finally {
    loading.value = false
  }
}

function pollTask(taskId) {
  pollers[taskId] = setInterval(async () => {
    try {
      const { data } = await api.get(`/documents/tasks/${taskId}`)
      if (['available', 'duplicate', 'failed'].includes(data.status)) {
        clearInterval(pollers[taskId])
        delete pollers[taskId]
        if (data.status === 'available') ElMessage.success(`入库完成：${data.detail}`)
        else if (data.status === 'failed') ElMessage.error(`入库失败：${data.detail}`)
        else ElMessage.info(data.detail)
        load()
      }
    } catch {
      clearInterval(pollers[taskId])
      delete pollers[taskId]
    }
  }, 1500)
}

async function onUpload({ file }) {
  const fd = new FormData()
  fd.append('file', file)
  try {
    const { data } = await api.post('/documents', fd)
    ElMessage.success('已接收，后台解析中…')
    pollTask(data.task_id)
    load()
  } catch { /* 拦截器已提示 */ }
  return false
}

async function submitText() {
  if (!textForm.source || !textForm.text) {
    ElMessage.warning('请填写来源名与文本内容')
    return
  }
  textSubmitting.value = true
  try {
    const { data } = await api.post('/documents/text', textForm)
    if (data.status === 'available') ElMessage.success(`入库成功：${data.detail}`)
    else ElMessage.info(data.detail)
    textForm.source = ''
    textForm.text = ''
    load()
  } finally {
    textSubmitting.value = false
  }
}

async function remove(doc) {
  await ElMessageBox.confirm(
    `确定删除文档「${doc.source}」（${doc.chunks || 0} 个片段）？`, '删除确认', { type: 'warning' }
  )
  await api.delete(`/documents/${encodeURIComponent(doc.source)}`)
  ElMessage.success('已删除')
  load()
}

onMounted(() => {
  load()
  // 兜底轮询：后台任务可能被其他会话触发
  listTimer = setInterval(load, 10000)
})
onUnmounted(() => {
  clearInterval(listTimer)
  Object.values(pollers).forEach(clearInterval)
})
</script>

<template>
  <div class="page">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>知识库文档（共 {{ documents.length }} 个文档 / {{ totalChunks }} 个片段）</span>
          <el-upload :show-file-list="false" :http-request="onUpload"
            accept=".pdf,.md,.docx,.txt" :disabled="loading">
            <el-button type="primary"><el-icon><Upload /></el-icon>&nbsp;上传文档</el-button>
          </el-upload>
        </div>
      </template>

      <el-table :data="documents" v-loading="loading" stripe>
        <el-table-column prop="source" label="来源" min-width="220" show-overflow-tooltip />
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="statusMap[row.status]?.type || 'info'" size="small">
              {{ statusMap[row.status]?.label || row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="chunks" label="片段数" width="90" align="center" />
        <el-table-column prop="detail" label="说明" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ row.error || row.detail || '-' }}</template>
        </el-table-column>
        <el-table-column prop="created_at" label="入库时间" width="170" />
        <el-table-column label="操作" width="90" fixed="right">
          <template #default="{ row }">
            <el-popconfirm title="确认删除该文档？" @confirm="remove(row)">
              <template #reference>
                <el-button type="danger" link size="small">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" style="margin-top: 16px">
      <template #header><span>快速文本入库</span></template>
      <el-form inline>
        <el-form-item label="来源名">
          <el-input v-model="textForm.source" placeholder="如 notes.txt" style="width: 220px" />
        </el-form-item>
      </el-form>
      <el-input v-model="textForm.text" type="textarea" :rows="5"
        placeholder="粘贴文本内容，将切分入库（自动去重）" />
      <div style="margin-top: 12px; text-align: right">
        <el-button type="primary" :loading="textSubmitting" @click="submitText">入库</el-button>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.page { padding: 20px; max-width: 1100px; margin: 0 auto; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
</style>
