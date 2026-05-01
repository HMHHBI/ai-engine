import apiClient from './apiClient'

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
  const res = await apiClient.get(`/chat/${chatId}`)
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

// 8. AI Streaming (Note: Streaming ke liye axios ke bajaye fetch use karna behtar hai)
export const streamAI = async (payload, signal) => {
  const token = localStorage.getItem('token')
  const res = await fetch(`${import.meta.env.VITE_API_BASE_URL}/chat/stream`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
    signal: signal,
  })

  if (res.status === 429) throw new Error('RATE_LIMIT_EXCEEDED')
  if (res.status === 401) throw new Error('UNAUTHORIZED')

  return res
}
