<script setup>
import { ref } from 'vue'
import { resetPasswordApi } from '@/api'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()
const newPassword = ref('')
const message = ref('')
const token = route.query.token // 👈 URL se token utha raha hai

const handleReset = async () => {
  try {
    const res = await resetPasswordApi(token, newPassword.value)
    const data = await res.json()
    
    message.value = data.message || data.detail
    
    if (res.ok) {
      // Success styling ya toast dikhayein
      setTimeout(() => router.push('/login'), 2000)
    }
  } catch (error) {
    message.value = "Connection error. Please try again."
  }
}
</script>

<template>
  <div class="auth-container">
    <div class="auth-card">
      <h1>New Password</h1>
      <p>Enter your new secure password.</p>
      <input v-model="newPassword" type="password" placeholder="••••••••" />
      <button @click="handleReset" class="submit-btn">Update Password</button>
      <p v-if="message">{{ message }}</p>
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
</style>