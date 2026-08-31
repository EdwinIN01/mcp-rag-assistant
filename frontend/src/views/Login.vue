<script setup>
import { reactive, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '../api'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const mode = ref('login') // login / register
const loading = ref(false)
const formRef = ref()

const form = reactive({ username: '', password: '' })

const rules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { pattern: /^[a-zA-Z0-9_-]{3,32}$/, message: '3-32 位字母数字下划线连字符', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 8, max: 64, message: '密码至少 8 位', trigger: 'blur' },
  ],
}

async function submit() {
  await formRef.value.validate()
  loading.value = true
  try {
    if (mode.value === 'register') {
      await api.post('/auth/register', form)
      ElMessage.success('注册成功，请登录')
      mode.value = 'login'
      return
    }
    const { data } = await api.post('/auth/token', form)
    auth.setSession(data.access_token, form.username, '')
    // 拉取真实身份（角色）
    try {
      const me = await api.get('/auth/me')
      auth.setSession(data.access_token, me.data.username, me.data.role)
    } catch { /* 身份查询失败不阻断登录 */ }
    ElMessage.success('登录成功')
    router.push(route.query.redirect || '/chat')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <el-card class="login-card">
      <div class="login-title">
        <el-icon :size="36" color="#409eff"><Reading /></el-icon>
        <h2>MCP-RAG 知识库助手</h2>
        <p class="sub">检索增强问答 · 混合检索 · 全链路可观测</p>
      </div>

      <el-segmented v-model="mode" :options="[
        { label: '登录', value: 'login' },
        { label: '注册', value: 'register' },
      ]" block style="margin-bottom: 24px" />

      <el-form ref="formRef" :model="form" :rules="rules" @keyup.enter="submit">
        <el-form-item prop="username">
          <el-input v-model="form.username" placeholder="用户名" size="large" :prefix-icon="'User'" />
        </el-form-item>
        <el-form-item prop="password">
          <el-input v-model="form.password" type="password" placeholder="密码（至少 8 位）" size="large"
            :prefix-icon="'Lock'" show-password />
        </el-form-item>
        <el-button type="primary" size="large" style="width: 100%" :loading="loading" @click="submit">
          {{ mode === 'login' ? '登 录' : '注 册' }}
        </el-button>
      </el-form>

      <p class="tip">首个注册用户自动成为管理员</p>
    </el-card>
  </div>
</template>

<style scoped>
.login-page {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.login-card {
  width: 400px;
  padding: 12px 8px;
  border-radius: 16px;
}

.login-title {
  text-align: center;
  margin-bottom: 24px;
}

.login-title h2 {
  margin: 8px 0 4px;
  color: #303133;
}

.login-title .sub {
  color: #909399;
  font-size: 13px;
}

.tip {
  text-align: center;
  color: #c0c4cc;
  font-size: 12px;
  margin-top: 16px;
}
</style>
