<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { useUserStore } from '@/stores/userStore'
import { useUIStore } from '@/stores/uiStore'
import { getChats, createChat, getChat, deleteChatApi, editTitleApi } from '@/api'

import Sidebar from '@/components/layout/Sidebar.vue'
import Chat from '@/components/chat/Chat.vue'

const userStore = useUserStore()
const uiStore = useUIStore()
const chats = ref([])
const chatsLoading = ref(true)
const messagesLoading = ref(false)
const chatId = ref(null)
const messages = ref([])
const isSidebarOpen = ref(false)

const scrollToBottom = async () => {
  await nextTick()
  const el = document.querySelector('.messages-container')
  el?.scrollTo({
    top: el.scrollHeight,
    behavior: 'smooth',
  })
}

// LOAD CHATS
const loadChats = async () => {
  chatsLoading.value = true;
  try {
    const data = await getChats(userStore.token)
    if (data && !data.detail) {
      chats.value = data
      scrollToBottom()
    } else {
      console.error('Route error:', data?.detail)
      chats.value = []
    }
  } finally {
    chatsLoading.value = false
  }
}

// OPEN CHAT
const openChat = async (id) => {
  messagesLoading.value = true

  await new Promise(r => setTimeout(r, 2000))

  chatId.value = id
  localStorage.setItem('active_chat', id)

  try {
    const data = await getChat(userStore.token, id)
    messages.value = Array.isArray(data) ? data : []
    scrollToBottom()
  } finally {
    messagesLoading.value = false // ✅ Loading khatam
  }
}

// NEW CHAT
const newChat = async () => {
  const data = await createChat(userStore.token)
  await loadChats()
  await openChat(data.chat_id)
}

// DELETE CHAT
const deleteChat = async (id) => {
  try {
    await deleteChatApi(userStore.token, id)
    await loadChats()
    uiStore.addToast('Chat deleted successfully', 'success')

    if (chatId.value === id) {
      chats.value.length > 0 ? await openChat(chats.value[0].id) : await newChat()
    }
  } catch (err) {
    uiStore.addToast('Failed to delete chat', 'error') // ✅ Add this
  }
}

// EDIT TITLE
const handleUpdateTitle = async ({ id, title }) => {
  try {
    await editTitleApi(userStore.token, id, title)
    // Local state update karein taake foran nazar aaye
    const chat = chats.value.find((c) => c.id === id)
    if (chat) chat.title = title
    uiStore.addToast('Title updated', 'success')
  } catch (err) {
    console.error('Title update failed', err)
    uiStore.addToast('Error updating title', 'error')
  }
}

const toggleSidebar = () => {
  isSidebarOpen.value = !isSidebarOpen.value
}

// Jab chat open ho toh mobile par sidebar khud band ho jaye
const handleOpenChat = (id) => {
  isSidebarOpen.value = false
  openChat(id)
}

// INIT
onMounted(async () => {
  // 1. Pehle profile fetch karein taake sidebar bhar jaye
  if (userStore.token) {
    await userStore.fetchProfile()
  }
  await loadChats()

  // Pehle check karein ke kya koi chat mojud hai
  if (chats.value.length > 0) {
    const savedId = localStorage.getItem('active_chat')
    const exists = chats.value.find((c) => c.id == savedId)
    
    messagesLoading.value = true
    await openChat(exists ? savedId : chats.value[0].id)
  } else {
    await newChat()
  }
})
</script>

<template>
  <div class="dashboard-layout">
    <header class="mobile-header">
      <button @click="toggleSidebar" class="menu-btn">☰</button>
      <span class="mobile-logo">AI Assistant</span>
    </header>

    <Sidebar
      :chats="chats"
      :activeChat="chatId"
      :isOpen="isSidebarOpen"
      :chatsLoading="chatsLoading"
      @openChat="handleOpenChat"
      @newChat="newChat"
      @deleteChat="deleteChat"
      @toggleSidebar="toggleSidebar"
      @updateTitle="handleUpdateTitle"
    />
    <main class="main-content">
      <Chat
        :messages="messages"
        :chatId="chatId"
        :isMessagesLoading="messagesLoading"
        @scrollToBottom="scrollToBottom"
        @refresh="openChat"
      />
    </main>
  </div>
</template>

<style scoped>
.dashboard-layout {
  display: flex;
  height: 100vh;
  width: 100vw;
  background: #0f172a;
}
.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.mobile-header {
  display: none;
  background: #1e293b;
  padding: 10px 15px;
  align-items: center;
  gap: 15px;
  border-bottom: 1px solid #334155;
}

@media (max-width: 768px) {
  .dashboard-layout {
    flex-direction: column;
  }
  .mobile-header {
    display: flex;
  }
  .main-content {
    height: calc(100vh - 50px);
  }
}

.menu-btn {
  background: none;
  border: none;
  color: white;
  font-size: 1.5rem;
  cursor: pointer;
}
.mobile-logo {
  color: white;
  font-weight: bold;
}
</style>
