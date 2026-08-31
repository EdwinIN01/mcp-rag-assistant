<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'

const keys = ref([])
const loading = ref(false)
const createVisible = ref(false)
const createForm = reactive({ name: '' })
const creating = ref(false)
const newKey = ref('') // 创建成功后一次性展示

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/auth/api-keys')
    keys.value = data.keys || []
  } finally {
    loading.value = false
  }
}

async function create() {
  if (!createForm.name.trim()) return
  creating.value = true
  try {
    const { data } = await api.post('/auth/api-keys', { name: createForm.name })
    newKey.value = data.key
    keys.value.unshift({
      id: data.key_id, name: data.name, key_prefix: data.key.slice(0, 16),
      revoked: false, created_at: new Date().toISOString().slice(0, 19), last_used_at: null,
    })
  } finally {
    creating.value = false
  }
}

function closeCreate() {
  createVisible.value = false
  createForm.name = ''
  newKey.value = ''
}

async function copyKey() {
  await navigator.clipboard.writeText(newKey.value)
  ElMessage.success('已复制到剪贴板')
}

async function revoke(row) {
  await ElMessageBox.confirm(
    `吊销后使用该 Key 的所有调用将立即失效，确定吊销「${row.name}」？`, '吊销确认', { type: 'warning' }
  )
  await api.delete(`/auth/api-keys/${row.id}`)
  ElMessage.success('已吊销')
  load()
}

onMounted(load)
</script>

<template>
  <div class="page">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>我的 API Key（供脚本 / MCP 客户端调用，请求头 X-API-Key）</span>
          <el-button type="primary" @click="createVisible = true">
            <el-icon><Plus /></el-icon>&nbsp;新建 Key
          </el-button>
        </div>
      </template>

      <el-alert type="info" :closable="false" style="margin-bottom: 14px"
        title="安全提示：完整 Key 仅在创建时展示一次，服务端只存哈希；请像密码一样保管。" />

      <el-table :data="keys" v-loading="loading" stripe>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="name" label="用途" min-width="140" />
        <el-table-column label="Key 前缀" min-width="180">
          <template #default="{ row }">
            <code>{{ row.key_prefix }}...</code>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.revoked ? 'danger' : 'success'" size="small">
              {{ row.revoked ? '已吊销' : '有效' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="170" />
        <el-table-column prop="last_used_at" label="最后使用" width="170">
          <template #default="{ row }">{{ row.last_used_at || '从未使用' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="90" fixed="right">
          <template #default="{ row }">
            <el-button v-if="!row.revoked" type="danger" link size="small" @click="revoke(row)">
              吊销
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 新建对话框 -->
    <el-dialog v-model="createVisible" title="新建 API Key" width="480px" @close="closeCreate">
      <template v-if="!newKey">
        <el-form @submit.prevent>
          <el-form-item label="用途备注">
            <el-input v-model="createForm.name" placeholder="如 mcp-client / 数据导入脚本"
              @keyup.enter="create" />
          </el-form-item>
        </el-form>
        <div style="text-align: right">
          <el-button type="primary" :loading="creating" @click="create">生成</el-button>
        </div>
      </template>

      <template v-else>
        <el-alert type="warning" :closable="false" style="margin-bottom: 12px"
          title="请立即复制保存，关闭后将无法再次查看完整 Key" />
        <el-input :model-value="newKey" readonly>
          <template #append>
            <el-button @click="copyKey">复制</el-button>
          </template>
        </el-input>
        <div style="text-align: right; margin-top: 16px">
          <el-button type="primary" @click="closeCreate">我已保存</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.page { padding: 20px; max-width: 1000px; margin: 0 auto; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
code { color: #e6a23c; font-size: 13px; }
</style>
