<script setup>
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/userStore'
import { useUIStore } from '@/stores/uiStore'
import { ref, nextTick } from 'vue'

const router = useRouter()
const userStore = useUserStore()
const uiStore = useUIStore()

const logout = () => {
  uiStore.addToast("Logged out successfully. See you soon!", "success")
  // Delay logout taake toast nazar aa jaye (optional)
  setTimeout(() => {
    userStore.logout()
  }, 1000)
}

const goToSettings = () => {
  router.push('/settings')
}

const editingId = ref(null)
const editValue = ref('')
const editInput = ref(null)

const startEdit = (chat) => {
  editingId.value = chat.id
  editValue.value = chat.title || 'New Chat'

  nextTick(() => {
    // Vue 3 mein v-for ke andar ref array hoti hai
    const el = editInput.value
    if (el) {
      if (Array.isArray(el) && el[0]) {
        el[0].focus()
      } else if (el.focus) {
        el.focus()
      }
    }
  })
}

const saveEdit = (id) => {
  if (editingId.value === id) {
    emit('updateTitle', { id, title: editValue.value })
    editingId.value = null
  }
}

const confirmDelete = (id) => {
  // Browser confirm() ki jagah hamara Custom Modal call karein
  uiStore.openConfirm(
    "Delete Conversation?", 
    "Kiya aap waqai is chat ko hamesha ke liye delete karna chahte hain? Isay wapas nahi laya ja sakay ga.",
    () => {
      // Yeh callback function tabhi chalega jab user "Confirm" dabaye ga
      emit('deleteChat', id)
    }
  )
}

defineProps(['chats', 'activeChat', 'isOpen', 'chatsLoading'])
const emit = defineEmits(['openChat', 'newChat', 'deleteChat', 'toggleSidebar', 'updateTitle'])
</script>

<template>
  <div v-if="isOpen" class="mobile-overlay" @click="emit('toggleSidebar')"></div>

  <aside class="sidebar" :class="{ 'is-open': isOpen }">
    <div class="sidebar-header">
      <div class="header-top">
        <h2 class="logo">AI Engine</h2>
        <button class="close-mobile-btn" @click="emit('toggleSidebar')">
          <svg
            width="24"
            height="24"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <path d="M18 6L6 18M6 6l12 12" />
          </svg>
        </button>
      </div>

      <button class="new-chat-btn" @click="emit('newChat')">
        <span class="plus-icon">+</span>
        <span class="btn-text">New Chat</span>
      </button>
    </div>

    <div class="chat-history">
      <p class="section-label">Recent Conversations</p>

      <div v-if="chatsLoading" class="skeleton-list">
        <div v-for="i in 5" :key="i" class="skeleton-item">
          <div class="skeleton-circle"></div>
          <div class="skeleton-line"></div>
        </div>
      </div>

      <div v-else-if="chats.length === 0" class="no-chats">
        <p>No history yet</p>
      </div>

      <div
        v-else
        v-for="chat in chats"
        :key="chat.id"
        class="chat-record"
        :class="{ active: chat.id === activeChat }"
        @click="emit('openChat', chat.id)"
      >
        <div class="chat-info" @dblclick="startEdit(chat)">
          <svg
            class="chat-icon"
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
          </svg>

          <input
            v-if="editingId === chat.id"
            v-model="editValue"
            class="edit-input"
            ref="editInput"
            @blur="saveEdit(chat.id)"
            @keyup.enter="saveEdit(chat.id)"
          />
          <span v-else class="chat-title">{{ chat.title || 'New Chat' }}</span>
        </div>

        <div class="actions">
          <button class="edit-btn" @click.stop="startEdit(chat)">
            <svg
              width="12"
              height="12"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <path
                d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"
              />
            </svg>
          </button>
          <button class="del-btn" @click.stop="confirmDelete(chat.id)">
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <path
                d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"
              />
            </svg>
          </button>
        </div>
      </div>
    </div>

    <div class="sidebar-footer">
      <div class="user-pill" @click="goToSettings">
        <img
          v-if="userStore.user?.profile_image"
          :src="userStore.user?.profile_image"
          class="avatar-img"
          :key="userStore.user.profile_image"
        />
        <div v-else class="avatar">
          {{ userStore.user?.full_name?.charAt(0).toUpperCase() || 'H' }}
        </div>

        <div class="user-meta">
          <span class="user-name">{{ userStore.user?.full_name || 'User' }}</span>
          <span class="user-plan">{{ userStore.user?.plan || 'Free' }} Plan</span>
        </div>
      </div>
      <button class="logout-btn" @click="logout">
        <span>Logout</span>
      </button>
    </div>
  </aside>
</template>

<style scoped>
.sidebar {
  width: 280px;
  background: #0f172a;
  border-right: 1px solid #1e293b;
  display: flex;
  flex-direction: column;
  padding: 1.25rem;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  z-index: 100;
  height: 100vh;
}

/* Sidebar Skeleton */
.skeleton-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  margin-bottom: 4px;
}

.skeleton-circle {
  width: 16px;
  height: 16px;
  border-radius: 4px;
  background: #1e293b;
}

.skeleton-line {
  height: 12px;
  background: #1e293b;
  border-radius: 4px;
  flex: 1;
  position: relative;
  overflow: hidden;
}

/* Pulsing Animation */
.skeleton-circle, .skeleton-line {
  background: linear-gradient(90deg, #1e293b 25%, #334155 50%, #1e293b 75%);
  background-size: 200% 100%;
  animation: loading 1.5s infinite;
}

@keyframes loading {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

.logo {
  color: #f8fafc;
  font-size: 1.25rem;
  font-weight: 700;
  letter-spacing: -0.025em;
}
.header-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

/* Buttons */
.close-mobile-btn {
  display: none;
  background: none;
  border: none;
  color: #94a3b8;
  cursor: pointer;
}

.new-chat-btn {
  width: 100%;
  margin-top: 1.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  background: #2563eb;
  color: white;
  border: none;
  border-radius: 12px;
  padding: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  box-shadow: 0 4px 6px -1px rgba(37, 99, 235, 0.2);
}
.new-chat-btn:hover {
  background: #1d4ed8;
  transform: translateY(-1px);
}

/* History List */
.chat-history {
  flex: 1;
  margin-top: 2rem;
  overflow-y: auto;
  scrollbar-width: none;
}
.chat-history::-webkit-scrollbar {
  display: none;
}
.section-label {
  font-size: 0.7rem;
  color: #64748b;
  text-transform: uppercase;
  margin-bottom: 1rem;
  font-weight: 600;
}

.chat-record {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-radius: 10px;
  margin-bottom: 4px;
  color: #94a3b8;
  cursor: pointer;
  transition: all 0.2s;
}

.chat-info {
  display: flex;
  align-items: center;
  gap: 12px;
  overflow: hidden;
  flex: 1;
}
.chat-title {
  font-size: 0.9rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.chat-record:hover {
  background: #1e293b;
  color: #f8fafc;
}
.chat-record.active {
  background: #1e293b;
  color: #3b82f6;
  font-weight: 500;
}

.del-btn {
  opacity: 0;
  padding: 5px;
  background: none;
  border: none;
  color: #64748b;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
}
.chat-record:hover .del-btn {
  opacity: 1;
}
.del-btn:hover {
  color: #f87171;
}

.no-chats {
  text-align: center;
  color: #475569;
  font-size: 0.85rem;
  margin-top: 2rem;
}

/* Footer Section */
.sidebar-footer {
  border-top: 1px solid #1e293b;
  padding-top: 1.5rem;
  margin-top: 1rem;
}
.user-pill {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px;
  margin-bottom: 0.5rem;
  cursor: pointer;
  transition: background 0.2s;
  border-radius: 8px;
}
.user-pill:hover {
  background: #1e293b;
}
.avatar {
  width: 32px;
  height: 32px;
  background: #3b82f6;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-weight: bold;
  font-size: 0.8rem;
}
.avatar-img {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  object-fit: cover;
}
.user-meta {
  display: flex;
  flex-direction: column;
}
.user-name {
  font-size: 0.85rem;
  color: #f8fafc;
  font-weight: 500;
}
.user-plan {
  font-size: 0.7rem;
  color: #64748b;
}

.logout-btn {
  background: transparent;
  border: 1px solid #334155;
  color: #94a3b8;
  padding: 10px;
  width: 100%;
  border-radius: 8px;
  font-size: 0.85rem;
  cursor: pointer;
  transition: all 0.2s;
}
.logout-btn:hover {
  background: #7f1d1d22;
  color: #f87171;
  border-color: #7f1d1d;
}

/* Mobile Logic */
@media (max-width: 768px) {
  .sidebar {
    position: fixed;
    height: 100vh;
    left: -280px;
  }
  .sidebar.is-open {
    left: 0;
  }
  .close-mobile-btn {
    display: block;
  }
  .mobile-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.7);
    backdrop-filter: blur(2px);
    z-index: 90;
  }
}

.edit-input {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid #3b82f6;
  color: #f8fafc;
  border-radius: 4px;
  padding: 2px 6px;
  font-size: 0.9rem;
  width: 100%;
  outline: none;
}

.actions {
  display: flex;
  gap: 4px;
  opacity: 0;
  transition: opacity 0.2s;
}

.chat-record:hover .actions {
  opacity: 1;
}

.edit-btn {
  background: none;
  border: none;
  color: #64748b;
  cursor: pointer;
  padding: 4px;
}

.edit-btn:hover {
  color: #3b82f6;
}
</style>
