<script setup>
import { nextTick, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { streamChat } from '../api/sse'

const messages = ref([]) // { role: 'user'|'assistant', content, sources?, streaming? }
const input = ref('')
const sending = ref(false)
const listRef = ref()

const SUGGESTIONS = ['什么是 RAG？', '混合检索的原理是什么？', '如何评估 RAG 系统的效果？']

function scrollBottom() {
  nextTick(() => {
    const el = listRef.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

function shortSource(path) {
  // 引用来源取文件名，避免整路径过长
  return String(path).split(/[\\/]/).pop()
}

async function send(text) {
  const message = (text || input.value).trim()
  if (!message || sending.value) return

  input.value = ''
  messages.value.push({ role: 'user', content: message })
  const reply = { role: 'assistant', content: '', sources: [], latency_ms: null, streaming: true }
  messages.value.push(reply)
  scrollBottom()

  // 组装多轮历史（最近 6 轮，与后端记忆压缩配合）
  const history = messages.value
    .slice(0, -2)
    .filter((m) => !m.streaming && m.content)
    .slice(-6)
    .map((m) => ({ role: m.role, content: m.content }))

  sending.value = true
  try {
    await streamChat(message, history, {
      onSources(payload) {
        reply.sources = payload.sources || []
        reply.latency_ms = payload.latency_ms
        scrollBottom()
      },
      onDelta(content) {
        reply.content += content
        scrollBottom()
      },
      onDone() {
        reply.streaming = false
      },
    })
  } catch (e) {
    reply.content += `\n\n（连接中断：${e.message}）`
    ElMessage.error(e.message)
  } finally {
    reply.streaming = false
    sending.value = false
    scrollBottom()
  }
}

function clearChat() {
  messages.value = []
}
</script>

<template>
  <div class="chat-page">
    <div class="chat-header">
      <span>知识库对话（流式输出 · 引用溯源）</span>
      <el-button size="small" @click="clearChat" :disabled="sending || !messages.length">
        <el-icon><Delete /></el-icon>&nbsp;清空对话
      </el-button>
    </div>

    <div ref="listRef" class="chat-list">
      <div v-if="!messages.length" class="empty">
        <el-empty description="向知识库提问，试试：">
          <div class="suggestions">
            <el-button v-for="s in SUGGESTIONS" :key="s" round @click="send(s)">{{ s }}</el-button>
          </div>
        </el-empty>
      </div>

      <div v-for="(m, i) in messages" :key="i" class="chat-row" :class="`chat-${m.role}`">
        <div class="avatar">
          <el-icon v-if="m.role === 'user'" :size="20" color="#fff"><User /></el-icon>
          <el-icon v-else :size="20" color="#fff"><ChatDotRound /></el-icon>
        </div>
        <div class="chat-body">
          <div class="chat-bubble" :class="{ 'streaming-cursor': m.streaming }">{{ m.content }}</div>

          <!-- 引用来源（检索完成后展示） -->
          <div v-if="m.role === 'assistant' && !m.streaming && m.sources?.length" class="sources">
            <el-divider style="margin: 8px 0" />
            <div class="sources-line">
              <el-icon><Collection /></el-icon>
              <span>引用来源 · 检索耗时 {{ m.latency_ms }}ms</span>
            </div>
            <el-tag v-for="(s, j) in m.sources" :key="j" size="small" type="info" class="src-tag">
              <el-icon style="vertical-align: -2px"><Document /></el-icon>
              {{ shortSource(s) }}
            </el-tag>
          </div>
        </div>
      </div>
    </div>

    <div class="chat-input">
      <el-input v-model="input" placeholder="输入问题，Enter 发送（Shift+Enter 换行）" size="large"
        :disabled="sending" @keydown.enter.exact.prevent="send()">
        <template #append>
          <el-button type="primary" :loading="sending" @click="send()">
            {{ sending ? '生成中' : '发送' }}
          </el-button>
        </template>
      </el-input>
    </div>
  </div>
</template>

<style scoped>
.chat-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  max-width: 900px;
  margin: 0 auto;
  background: #fff;
}

.chat-header {
  height: 52px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  border-bottom: 1px solid #e4e7ed;
  font-weight: 600;
  color: #303133;
}

.chat-list {
  flex: 1;
  overflow-y: auto;
  padding: 24px 20px;
  background: #f5f7fa;
}

.chat-row {
  display: flex;
  gap: 10px;
  margin-bottom: 20px;
}

.chat-user {
  flex-direction: row-reverse;
}

.chat-user .chat-body {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

.avatar {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.chat-user .avatar { background: #409eff; }
.chat-assistant .avatar { background: #67c23a; }

.chat-body { max-width: 100%; }

.sources { padding: 4px 2px 0; }

.sources-line {
  color: #909399;
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 6px;
}

.src-tag { margin: 0 6px 6px 0; }

.chat-input {
  padding: 16px 20px;
  border-top: 1px solid #e4e7ed;
  background: #fff;
}

.empty { padding-top: 80px; }

.suggestions {
  display: flex;
  flex-direction: column;
  gap: 10px;
  align-items: center;
}
</style>
