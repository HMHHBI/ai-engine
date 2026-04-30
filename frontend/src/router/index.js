import { createRouter, createWebHistory } from 'vue-router'
import { useUserStore } from '@/stores/userStore'
import Login from '../views/Login.vue'
import Register from '../views/Register.vue'
import ForgotPassword from '../views/ForgotPassword.vue'
import ResetPassword from '../views/ResetPassword.vue'
import PricingModal from '../views/PricingModal.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/login' },
    { path: '/login', component: Login },
    { path: '/register', component: Register },
    {
      path: '/dashboard',
      component: () => import('../views/Dashboard.vue'), // Lazy loading (Professional)
      meta: { requiresAuth: true },
    },
    {
      path: '/settings',
      component: () => import('../views/Settings.vue'),
      meta: { requiresAuth: true },
    },
    { path: '/forgot-password', component: ForgotPassword },
    { path: '/reset-password', component: ResetPassword },
    { path: '/pricing-modal', component: PricingModal },
  ],
})

router.beforeEach((to) => {
  const userStore = useUserStore()
  const token = userStore.token

  // 1. Agar login nahi aur protected page par ja rahe hain
  if (to.meta.requiresAuth && !token) {
    return '/login' // next('/login') ki jagah direct return
  }

  // 2. Agar pehle se login hain aur login/register par ja rahe hain
  if ((to.path === '/login' || to.path === '/register') && token) {
    return '/dashboard' // direct return
  }

  // Baki cases ke liye kuch return karne ki zaroorat nahi (allow default)
})

export default router