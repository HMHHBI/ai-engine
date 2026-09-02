import apiClient from './apiClient'
import { useUserStore } from '@/stores/userStore'

// 1. Saari Chats ki list (Dashboard ke liye)
export const getChats = async () => {
  const res = await apiClient.get('/chat/all')
  return res.data
}

// 2. Naya Chat create karna
export const createChat = async () => {
  const res = await apiClient.post('/chat/new')
  return res.data
}

// 3. Specific chat history load karna
export const getChat = async (id) => {
  const res = await apiClient.get(`/chat/${id}`)
  return res.data
}

// 4. Chat delete karna
export const deleteChatApi = async (id) => {
  return apiClient.delete(`/chat/${id}`)
}

// 5. Title update karna (Manual ya AI generated)
export const editTitleApi = async (id, newTitle) => {
  return apiClient.put(`/chat/${id}/title?new_title=${encodeURIComponent(newTitle)}`)
}

export const getChatDetailApi = async (chatId) => {
  const res = await apiClient.get(`/chat/details/${chatId}`)
  return res.data
}

// 6. PDF upload karna
export const uploadPDFApi = async (chatId, formData) => {
  const res = await apiClient.post(`/chat/upload-pdf/${chatId}`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return res.data
}

// 7. Message cleanup (Editing ke liye)
export const cleanupChatApi = async (chatId, index) => {
  return apiClient.delete(`/chat/${chatId}/cleanup/${index}`)
}

// 8. AI Streaming (Dynamic Payload Builder)
export const streamAI = async (payload, signal) => {
  const token = localStorage.getItem('token')

  // 1. Basic required fields (Inko convert karna zaroori hai)
  const cleanPayload = {
    chat_id: Number(payload.chat_id),
    prompt: String(payload.prompt),
    task: payload.task || 'general',
    model: payload.model || 'ollama-llama3.2',
  }

  // 2. File Context handle karein
  if (payload.file_context && payload.file_context.trim() !== '') {
    cleanPayload.file_context = payload.file_context
  }

  // 3. Image Base64 handle karein - sirf valid array allow karein
  if (Array.isArray(payload.image_base64) && payload.image_base64.length > 0) {
    cleanPayload.image_base64 = payload.image_base64
  }

  // 4. Image Mime handle karein - STRICT Check
  // Agar payload.image_mime empty string "" hui to yeh block skip ho jayega!
  if (Array.isArray(payload.image_mime) && payload.image_mime.length > 0) {
    cleanPayload.image_mime = payload.image_mime
  } else if (typeof payload.image_mime === 'string' && payload.image_mime.trim() !== '') {
    cleanPayload.image_mime = [payload.image_mime]
  }

  // Ab cleanPayload mein image_mime aur image_base64 ki key HOGI HI NAHI agar data nahi hai.
  // Pydantic isko default None assign kar dega.

  const res = await fetch(`${import.meta.env.VITE_API_BASE_URL}/chat/stream`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(cleanPayload),
    signal: signal,
  })

  if (res.status === 429) throw new Error('RATE_LIMIT_EXCEEDED')
  if (res.status === 401) throw new Error('UNAUTHORIZED')

  return res
}
