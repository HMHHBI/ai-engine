const BASE_URL = import.meta.env.VITE_API_BASE_URL

const getHeaders = (token) => ({
  Authorization: `Bearer ${token}`,
  'Content-Type': 'application/json',
})

export const createChat = async (token) => {
  const res = await fetch(`${BASE_URL}/chat/new`, {
    method: 'POST',
    headers: getHeaders(token),
  })
  return res.json()
}

export const getChats = async (token) => {
  const res = await fetch(`${BASE_URL}/chat/all`, {
    headers: getHeaders(token),
  })
  return res.json()
}

export const getChat = async (token, id) => {
  const res = await fetch(`${BASE_URL}/chat/${id}`, {
    headers: getHeaders(token),
  })
  return res.json()
}

export const deleteChatApi = async (token, id) => {
  return fetch(`${BASE_URL}/chat/${id}`, {
    method: 'DELETE',
    headers: getHeaders(token),
  })
}

export const editTitleApi = async (token, id, newTitle) => {
  return fetch(`${BASE_URL}/chat/${id}/title?new_title=${encodeURIComponent(newTitle)}`, {
    method: 'PUT', // Backend par PUT endpoint hai
    headers: getHeaders(token),
  })
}

export const getChatDetailApi = async (token, chatId) => {
  const res = await fetch(`${BASE_URL}/chat/details/${chatId}`, {
    headers: getHeaders(token),
  })
  return res.json()
}

export const streamAI = async (token, payload, signal) => {
  return fetch(`${BASE_URL}/chat/stream`, {
    method: 'POST',
    headers: getHeaders(token),
    body: JSON.stringify(payload),
    signal: signal,
  })
}

export const uploadPDFApi = async (token, chatId, formData) => {
  const res = await fetch(`${BASE_URL}/chat/upload-pdf/${chatId}`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  })
  return res.json()
}

// src/api/chat.js

export const cleanupChatApi = async (token, chatId, index) => {
  return fetch(`${BASE_URL}/chat/${chatId}/cleanup/${index}`, {
    method: 'DELETE',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    }
  })
}