<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { auth_login, auth_google } from '@/api'
import { useUserStore } from '@/stores/userStore'
import { useUIStore } from '@/stores/uiStore'
import { GoogleSignInButton } from 'vue3-google-signin'

const router = useRouter()
const userStore = useUserStore()
const uiStore = useUIStore()

const email = ref('')
const password = ref('')
const error = ref('')

const login = async () => {
  try {
    const data = await auth_login({
      email: email.value,
      password: password.value,
    })

    if (data.detail) {
      uiStore.addToast(typeof data.detail === 'string' ? data.detail : 'Invalid credentials', 'error')
      return
    }

    userStore.setToken(data.access_token)
    userStore.user = data.user
    localStorage.setItem('user', JSON.stringify(data.user))

    uiStore.addToast(`Welcome back, ${data.user.name}!`, 'success')
    router.push('/dashboard')
  } catch (err) {
    uiStore.addToast('Server connection error', 'error')
  }
}

const handleSuccess = async (response) => {
  try {
    alert("SUCCESS TRIGGERED")
    console.log("GOOGLE RESPONSE:", response)
    const { credential } = response
    // Centralized function use karein
    const data = await auth_google(credential)
    
    if (data.access_token) {
      userStore.setToken(data.access_token)
      userStore.user = data.user
      localStorage.setItem('user', JSON.stringify(data.user)) // User info bhi save kar lein sidebar ke liye
      
      uiStore.addToast(`Welcome back, ${data.user.name}!`, 'success')
      router.push('/dashboard')
    } else {
      uiStore.addToast(`Login failed: ${data.detail}!`, 'error')
    }
  } catch (error) {
    uiStore.addToast('Google Auth Error:', 'error')
  }
}
const handleError = () => {
  console.error('Login Failed')
}
</script>

<template>
  <div class="auth-container">
    <div class="auth-card">
      <div class="header">
        <h1>Welcome Back</h1>
        <p>Login to continue your conversations</p>
      </div>

      <GoogleSignInButton
        type="standard"
        shape="rectangular"
        theme="outline"
        size="large"
        @success="handleSuccess"
        @error="handleError"
      ></GoogleSignInButton>

      <div class="form">
        <div class="input-group">
          <label>Email Address</label>
          <input v-model="email" type="email" placeholder="name@company.com" @keyup.enter="login" />
        </div>

        <div class="input-group">
          <label>Password</label>
          <input v-model="password" type="password" placeholder="••••••••" @keyup.enter="login" />
        </div>

        <p class="error-msg" v-if="error">{{ error }}</p>

        <button class="submit-btn" @click="login">Sign In</button>
        <div class="forgot-link">
          <router-link class="link" to="/forgot-password">Forgot Password?</router-link>
        </div>
      </div>

      <div class="footer">
        <p>Don't have an account? <router-link to="/register">Create one</router-link></p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.auth-container {
  min-height: 100vh;
  display: flex;
  justify-content: center;
  align-items: center;
  background: radial-gradient(circle at top right, #1e293b, #0f172a);
  padding: 20px;
}

.auth-card {
  background: rgba(30, 41, 59, 0.7);
  backdrop-filter: blur(10px);
  padding: 40px;
  border-radius: 16px;
  width: 100%;
  max-width: 400px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
}

.header h1 {
  font-size: 24px;
  font-weight: 700;
  margin-bottom: 8px;
  color: #fff;
}
.header p {
  color: #94a3b8;
  font-size: 14px;
  margin-bottom: 30px;
}

.input-group {
  margin-bottom: 20px;
  text-align: left;
}
.input-group label {
  display: block;
  font-size: 13px;
  color: #cbd5e1;
  margin-bottom: 8px;
  font-weight: 500;
}

input {
  width: 100%;
  padding: 12px 16px;
  background: rgba(15, 23, 42, 0.6);
  border: 1px solid #334155;
  border-radius: 8px;
  color: white;
  transition: all 0.2s;
}

input:focus {
  border-color: #3b82f6;
  outline: none;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.2);
}

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
  transition:
    transform 0.1s,
    background 0.2s;
}
.submit-btn:hover {
  background: #1d4ed8;
}
.submit-btn:active {
  transform: scale(0.98);
}

.forgot-link { 
  margin-top: 10px;
  font-size: 13px;
  color: white;
}

.link {
  margin-left: 10px;
  color: #94a3b8;
}
.link:hover { 
  color: white;
}

.error-msg {
  color: #f87171;
  font-size: 13px;
  margin-bottom: 15px;
}

.footer {
  margin-top: 25px;
  font-size: 14px;
  color: #94a3b8;
}
.footer a {
  color: #3b82f6;
  text-decoration: none;
  font-weight: 500;
}
.footer a:hover {
  text-decoration: underline;
}
</style>
