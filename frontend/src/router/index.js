import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const routes = [
  {
    path: '/login',
    name: 'login',
    component: () => import('../views/Login.vue'),
    meta: { public: true },
  },
  {
    path: '/',
    component: () => import('../layouts/MainLayout.vue'),
    children: [
      { path: '', redirect: '/chat' },
      { path: 'chat', name: 'chat', component: () => import('../views/Chat.vue'), meta: { title: '知识库对话' } },
      { path: 'search', name: 'search', component: () => import('../views/SearchViz.vue'), meta: { title: '检索可视化' } },
      { path: 'documents', name: 'documents', component: () => import('../views/Documents.vue'), meta: { title: '文档管理' } },
      { path: 'api-keys', name: 'api-keys', component: () => import('../views/ApiKeys.vue'), meta: { title: 'API Key 管理' } },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/chat' },
]

const router = createRouter({ history: createWebHistory(), routes })

// 全局守卫：未登录跳转登录页
router.beforeEach((to) => {
  const auth = useAuthStore()
  if (!to.meta.public && !auth.token) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
})

export default router
