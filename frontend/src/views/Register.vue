<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/userStore'
import { useUIStore } from '@/stores/uiStore'
import { auth_register } from '@/api'

const router = useRouter()
const userStore = useUserStore()
const uiStore = useUIStore()
const name = ref('')
const email = ref('')
const password = ref('')
const error = ref('')

const register = async () => {
  error.value = ''
  try {
    const data = await auth_register(name.value, email.value, password.value)
    
    if (data.detail) {
      uiStore.addToast(typeof data.detail === 'string' ? data.detail : 'Registration failed', 'error')
      return
    }

    userStore.setToken(data.token)
    userStore.user = data.user
    uiStore.addToast("Account created successfully! 🚀", "success")
    router.push('/dashboard')
  } catch (err) {
    uiStore.addToast('Failed to connect to server', 'error')
  }
}
</script>

<template>
  <div class="auth-container">
    <div class="auth-card">
      <div class="header">
        <h1>Create Account</h1>
        <p>Join us to start building with AI</p>
      </div>

      <div class="form">
        <div class="input-group">
          <label>Full Name</label>
          <input v-model="name" placeholder="John Doe" />
        </div>

        <div class="input-group">
          <label>Email Address</label>
          <input v-model="email" type="email" placeholder="name@company.com" />
        </div>

        <div class="input-group">
          <label>Password</label>
          <input v-model="password" type="password" placeholder="••••••••" />
        </div>

        <p class="error-msg" v-if="error">{{ error }}</p>

        <button class="submit-btn" @click="register">Get Started</button>
      </div>

      <div class="footer">
        <p>Already have an account? <router-link to="/login">Sign In</router-link></p>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Styles same as login page for consistency */
.auth-container {
  min-height: 100vh;
  display: flex;
  justify-content: center;
  align-items: center;
  background: radial-gradient(circle at bottom left, #1e293b, #0f172a);
  padding: 20px;
}

.auth-card {
  background: rgba(30, 41, 59, 0.7);
  backdrop-filter: blur(10px);
  padding: 40px;
  border-radius: 16px;
  width: 100%;
  max-width: 420px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
}

.header h1 { font-size: 24px; font-weight: 700; margin-bottom: 8px; color: #fff; }
.header p { color: #94a3b8; font-size: 14px; margin-bottom: 30px; }

.input-group { margin-bottom: 20px; text-align: left; }
.input-group label { display: block; font-size: 13px; color: #cbd5e1; margin-bottom: 8px; font-weight: 500; }

input {
  width: 100%;
  padding: 12px 16px;
  background: rgba(15, 23, 42, 0.6);
  border: 1px solid #334155;
  border-radius: 8px;
  color: white;
}

input:focus { border-color: #3b82f6; outline: none; box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.2); }

.submit-btn {
  width: 100%;
  padding: 12px;
  background: #2563eb;
  color: white;
  border: none;
  border-radius: 8px;
  font-weight: 600;
  cursor: pointer;
  margin-top: 10px;
}

.submit-btn:hover { background: #1d4ed8; }

.error-msg { color: #f87171; font-size: 13px; margin-bottom: 15px; }

.footer { margin-top: 25px; font-size: 14px; color: #94a3b8; }
.footer a { color: #3b82f6; text-decoration: none; font-weight: 500; }
</style>