<script setup>
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/userStore'
import { useUIStore } from '@/stores/uiStore'
import { ref, onMounted, onUnmounted } from 'vue'
import { getProfileApi, updateProfileApi } from '@/api'

const userStore = useUserStore()
const uiStore = useUIStore()
const loading = ref(false)
const form = ref({ name: '' })
const selectedFile = ref(null)
const previewUrl = ref(null)
const router = useRouter()

const goBack = () => {
  router.push('/dashboard')
}

const upgrade = () => {
  router.push('/pricing-modal')
}

const onFileChange = (e) => {
  const file = e.target.files[0]
  if (!file) return
  selectedFile.value = file

  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = URL.createObjectURL(file)
}

onMounted(async () => {
  try {
    const data = await getProfileApi(userStore.token)
    // Direct store update karein
    userStore.user = data
    form.value.name = data.full_name
  } catch (err) {
    console.error('Failed to load profile', err)
  }
})

const updateProfile = async () => {
  loading.value = true
  try {
    const formData = new FormData()
    if (form.value.name) formData.append('name', form.value.name)
    if (selectedFile.value) formData.append('profile_img', selectedFile.value)

    const res = await updateProfileApi(userStore.token, formData)

    // Sync store
    userStore.user = { ...userStore.user, ...res }
    localStorage.setItem('user', JSON.stringify(userStore.user))

    uiStore.addToast('Profile updated successfully!', 'success')
  } catch (error) {
    uiStore.addToast('Failed to update profile', 'error')
  } finally {
    loading.value = false
  }
}

onUnmounted(() => {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
})
</script>

<template>
  <div class="settings-container">
    <div class="settings-card">
      <h1 class="title">Account Settings</h1>

      <div class="profile-section">
        <div class="avatar-wrapper">
          <img
            :src="previewUrl || userStore.user?.profile_image || '/default-avatar.png'"
            class="preview-img"
          />
          <label for="file-upload" class="upload-btn">
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <path
                d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"
              />
              <circle cx="12" cy="13" r="4" />
            </svg>
          </label>
          <input id="file-upload" type="file" @change="onFileChange" hidden />
        </div>
        <div class="user-info">
          <h3>{{ userStore.user?.full_name || 'Loading...' }}</h3>
          <p>{{ userStore.user?.email || '' }}</p>
          <span class="plan-badge" :class="userStore.user?.plan">
            {{ userStore.user?.plan || 'Free' }} Plan
          </span>
        </div>
      </div>

      <hr class="divider" />

      <form @submit.prevent="updateProfile" class="settings-form">
        <div class="input-group">
          <label>Full Name</label>
          <input v-model="form.name" type="text" placeholder="Hassan..." />
        </div>

        <div class="pricing-overview">
          <h4>Your Usage</h4>
          <div class="usage-stats">
            <div class="stat">
              <span>📷 Images Remaining</span>
              <strong>{{ userStore.user?.limits.image ?? 0 }}</strong>
            </div>
            <div class="stat">
              <span>🔍 Searches Remaining</span>
              <strong>{{ userStore.user?.limits.search ?? 0 }}</strong>
            </div>
          </div>
          <button type="button" class="upgrade-link save-btn back-btn" @click="upgrade">
            Upgrade to Pro 🚀
          </button>
        </div>

        <div class="form-actions">
          <button type="submit" class="save-btn" :disabled="loading">
            {{ loading ? 'Saving...' : 'Save Changes' }}
          </button>
          <button type="button" class="save-btn back-btn" @click="goBack">Back</button>
        </div>
      </form>
    </div>
  </div>
</template>

<style scoped>
.settings-container {
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 40px;
  background: #0f172a;
  min-height: 100vh;
}
.settings-card {
  background: rgba(30, 41, 59, 0.7);
  backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 20px;
  padding: 30px;
  width: 100%;
  max-width: 500px;
  color: white;
}
.profile-section {
  display: flex;
  align-items: center;
  gap: 20px;
  margin-bottom: 30px;
}
.avatar-wrapper {
  position: relative;
  width: 80px;
  height: 80px;
}
.preview-img {
  width: 100%;
  height: 100%;
  border-radius: 50%;
  object-fit: cover;
  border: 2px solid #3b82f6;
}
.upload-btn {
  position: absolute;
  bottom: 0;
  right: 0;
  background: #3b82f6;
  padding: 5px;
  border-radius: 50%;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}
.plan-badge {
  font-size: 10px;
  text-transform: uppercase;
  padding: 2px 8px;
  border-radius: 20px;
  background: #1e293b;
  color: #94a3b8;
}
.plan-badge.pro {
  background: gold;
  color: black;
}

.settings-form {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.form-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.divider {
  border: 0;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
  margin: 20px 0;
}
.input-group label {
  display: block;
  font-size: 13px;
  color: #94a3b8;
  margin-bottom: 5px;
}
.input-group input {
  width: 100%;
  background: #1e293b;
  border: 1px solid #334155;
  padding: 12px;
  border-radius: 8px;
  color: white;
}

.pricing-overview {
  background: rgba(59, 130, 246, 0.1);
  padding: 15px;
  border-radius: 12px;
}
.usage-stats {
  display: flex;
  justify-content: space-between;
  margin-top: 10px;
  font-size: 12px;
}
.stat {
  display: flex;
  justify-content: space-between;
  margin: 10px;
  font-size: 12px;
  background: #0f172a;
  color: #f8fafc;
  border: 1px solid #334155;
  padding: 6px 12px;
  border-radius: 8px;
  font-size: 13px;
  outline: none;
}
.save-btn {
  background: #2563eb;
  color: white;
  border: none;
  padding: 12px 24px;
  border-radius: 8px;
  cursor: pointer;
  font-weight: bold;
}
.back-btn {
  background: #475569;
  margin-left: 10px;
}
</style>
