<script setup>
import { computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const menus = [
  { path: '/chat', icon: 'ChatDotRound', title: '知识库对话' },
  { path: '/search', icon: 'Search', title: '检索可视化' },
  { path: '/documents', icon: 'FolderOpened', title: '文档管理' },
  { path: '/api-keys', icon: 'Key', title: 'API Key 管理' },
]

const activeMenu = computed(() => '/' + (route.path.split('/')[1] || 'chat'))

async function logout() {
  await ElMessageBox.confirm('确定退出登录？', '提示', { type: 'warning' })
  auth.logout()
  router.push({ name: 'login' })
}
</script>

<template>
  <el-container class="layout">
    <el-aside width="220px" class="aside">
      <div class="logo">
        <el-icon :size="26" color="#409eff"><Reading /></el-icon>
        <span>MCP-RAG</span>
      </div>
      <el-menu :default-active="activeMenu" router background-color="#001529"
        text-color="#a6adb4" active-text-color="#fff">
        <el-menu-item v-for="m in menus" :key="m.path" :index="m.path">
          <el-icon><component :is="m.icon" /></el-icon>
          <span>{{ m.title }}</span>
        </el-menu-item>
      </el-menu>
      <div class="user-box">
        <el-icon><UserFilled /></el-icon>
        <span class="name">{{ auth.username }}</span>
        <el-tag v-if="auth.role" size="small" :type="auth.role === 'admin' ? 'danger' : 'info'">
          {{ auth.role }}
        </el-tag>
        <el-button link type="danger" size="small" @click="logout">退出</el-button>
      </div>
    </el-aside>

    <el-main class="main">
      <router-view />
    </el-main>
  </el-container>
</template>

<style scoped>
.layout { height: 100%; }

.aside {
  background: #001529;
  display: flex;
  flex-direction: column;
}

.logo {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: #fff;
  font-size: 18px;
  font-weight: 600;
}

.aside .el-menu {
  border-right: none;
  flex: 1;
}

.user-box {
  padding: 14px 16px;
  color: #a6adb4;
  display: flex;
  align-items: center;
  gap: 6px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
}

.user-box .name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.main {
  padding: 0;
  height: 100%;
  overflow: hidden;
}
</style>
