<script setup>
import VueMarkdown from 'vue-markdown-render'

const props = defineProps(['messages', 'isSpeaking', 'parseImageData', 'loading'])
const emit = defineEmits([ 'edit-message', 'speak', 'regenerate', 'copy', 'download'])
</script>

<template>
  <div class="messages-container">
    <div v-if="loading" class="skeleton-chat">
      <div v-for="i in 3" :key="i" class="skeleton-row" :class="i % 2 === 0 ? 'ai' : 'user'">
        <div class="skeleton-avatar"></div>

        <div class="skeleton-bubble">
          <div class="skeleton-line full"></div>
          <div class="skeleton-line medium"></div>
          <div class="skeleton-line short"></div>
        </div>
      </div>
    </div>

    <div v-else-if="messages.length === 0" class="empty-state">
      <div class="welcome-card">
        <div class="welcome-icon">🚀</div>
        <h2>AI Engine 2.0</h2>
        <p>Start a conversation or upload a PDF to begin.</p>
      </div>
    </div>

    <div v-else v-for="(msg, i) in messages" :key="i" :class="['message-row', msg.role]">
      <div class="bubble-wrapper">
        <div class="avatar-container">
          <div class="avatar" :class="msg.role">
            {{ msg.role === 'user' ? 'H' : 'AI' }}
          </div>
        </div>

        <div class="bubble">
          <div v-if="msg.image_data" class="multi-history-images">
            <template v-if="parseImageData(msg.image_data)">
              <img
                v-for="(img, idx) in parseImageData(msg.image_data)"
                :key="idx"
                :src="img.startsWith('http') ? img : `data:image/png;base64,${img}`"
                class="chat-img"
              />
            </template>
          </div>

          <vue-markdown :source="msg.text" class="markdown-content" />

          <div v-if="msg.role === 'user'" class="audio-controls">
            <button @click="emit('edit-message', i)" class="speaker-btn" title="Edit Message">
              <svg viewBox="0 0 24 24" width="14" fill="currentColor">
                <path
                  d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04c.39-.39.39-1.02 0-1.41l-2.34-2.34c-.39-.39-1.02-.39-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"
                />
              </svg>
            </button>
            <button @click="emit('copy', msg.text)" class="speaker-btn" title="Copy Text">
              <svg viewBox="0 0 24 24" width="16" fill="currentColor">
                <path
                  d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z"
                />
              </svg>
            </button>
          </div>

          <div v-if="msg.role === 'ai'" class="audio-controls">
            <button
              @click="emit('regenerate', i)"
              class="speaker-btn"
              title="Regenerate Response"
              :disabled="loading"
            >
              <svg viewBox="0 0 24 24" width="16" fill="currentColor">
                <path
                  d="M17.65 6.35C16.2 4.9 14.21 4 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08c-.82 2.33-3.04 4-5.65 4-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"
                />
              </svg>
            </button>
            <button @click="emit('copy', msg.text)" class="speaker-btn" title="Copy Text">
              <svg viewBox="0 0 24 24" width="16" fill="currentColor">
                <path
                  d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z"
                />
              </svg>
            </button>

            <button
              @click="emit('download', msg.text)"
              class="speaker-btn"
              title="Download as File"
            >
              <svg viewBox="0 0 24 24" width="16" fill="currentColor">
                <path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z" />
              </svg>
            </button>

            <button
              @click="emit('speak', msg.text, i)"
              class="speaker-btn"
              :class="{ 'is-active': isSpeaking === i }"
            >
              <svg v-if="isSpeaking !== i" viewBox="0 0 24 24" width="16" fill="currentColor">
                <path
                  d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02z"
                />
              </svg>
              <svg v-else viewBox="0 0 24 24" width="16" fill="currentColor">
                <path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.messages-container {
  flex: 1;
  overflow-y: auto;
  padding: 30px 20px;
  display: flex;
  flex-direction: column;
  gap: 24px;
  background: #0f172a;
}

/* --- ✨ Pro Message Bubbles --- */
.message-row {
  display: flex;
  width: 100%;
  animation: fadeIn 0.4s ease-out;
}

.message-row.user {
  justify-content: flex-end;
}

.bubble-wrapper {
  display: flex;
  gap: 12px;
  width: 80%;
}

.user .bubble-wrapper {
  flex-direction: row-reverse;
}

.avatar {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: bold;
  font-size: 0.75rem;
  box-shadow: 0 4px 10px rgba(0, 0, 0, 0.2);
}

.avatar.user {
  background: #3b82f6;
  border: 2px solid rgba(255, 255, 255, 0.1);
}
.avatar.ai {
  background: #1e293b;
  border: 2px solid #3b82f6;
  color: #3b82f6;
}

.bubble {
  width: 100%;
  padding: 16px;
  border-radius: 18px;
  font-size: 0.95rem;
  line-height: 1.6;
  position: relative;
  transition: all 0.3s;
}

.user .bubble {
  background: linear-gradient(135deg, #2563eb, #1d4ed8);
  color: white;
  border-bottom-right-radius: 4px;
  box-shadow: 0 8px 20px -8px rgba(37, 99, 235, 0.5);
}

.ai .bubble {
  background: rgba(30, 41, 59, 0.7);
  backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #e2e8f0;
  border-bottom-left-radius: 4px;
}

/* --- 🚀 Empty State Design --- */
.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  text-align: center;
}

.welcome-card {
  padding: 40px;
  border-radius: 24px;
  background: rgba(30, 41, 59, 0.3);
  border: 1px dashed rgba(255, 255, 255, 0.1);
}

.welcome-icon {
  font-size: 3rem;
  margin-bottom: 15px;
}

/* --- 🖼️ Image Styling --- */
.chat-img {
  width: 100%;
  max-width: 250px;
  border-radius: 12px;
  margin-bottom: 12px;
  border: 2px solid rgba(255, 255, 255, 0.05);
}

/* --- 🎭 Animations --- */
@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* ✨ NEW PRO SKELETON STYLES */
.skeleton-chat {
  display: flex;
  flex-direction: column;
  gap: 24px;
  padding: 10px;
}

.skeleton-row {
  display: flex;
  gap: 12px;
  max-width: 80%;
  width: 100%;
}

.skeleton-row.user {
  flex-direction: row-reverse;
  align-self: flex-end;
}

.skeleton-row.ai {
  align-self: flex-start;
}

.skeleton-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  flex-shrink: 0;
  background: #1e293b;
  animation: pulse 1.5s infinite ease-in-out;
}

.skeleton-bubble {
  flex-grow: 1;
  padding: 16px;
  border-radius: 16px;
  background: rgba(30, 41, 59, 0.4);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.skeleton-row.user .skeleton-bubble {
  background: rgba(37, 99, 235, 0.2); /* User jaisa blue tint */
  border-bottom-right-radius: 4px;
}

.skeleton-row.ai .skeleton-bubble {
  border-bottom-left-radius: 4px;
}

.skeleton-line {
  height: 10px;
  margin-bottom: 10px;
  border-radius: 4px;
  background: linear-gradient(90deg, #1e293b 25%, #334155 50%, #1e293b 75%);
  background-size: 200% 100%;
  animation: loading 1.5s infinite linear;
}

.skeleton-line:last-child {
  margin-bottom: 0;
}

.skeleton-line.full {
  width: 100%;
}
.skeleton-line.medium {
  width: 70%;
}
.skeleton-line.short {
  width: 40%;
}

/* Animations */
@keyframes loading {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}

@keyframes pulse {
  0% {
    opacity: 0.5;
  }
  50% {
    opacity: 1;
  }
  100% {
    opacity: 0.5;
  }
}

/* Markdown & Code */
.markdown-content :deep(pre) {
  background: #010409 !important;
  padding: 40px 16px 16px;
  border-radius: 8px;
  margin: 10px 0;
  position: relative;
  overflow-x: auto;
}
.markdown-content :deep(.copy-btn) {
  position: absolute;
  top: 10px;
  right: 10px;
  background: #21262d;
  border: 1px solid #30363d;
  color: #8b949e;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 11px;
  cursor: pointer;
}
.markdown-content :deep(.copy-btn:hover) {
  background: #30363d;
  color: #f0f6fc;
  opacity: 1;
  transform: translateY(-1px);
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2);
}
.markdown-content :deep(.copy-btn.copied) {
  color: #3fb950;
  border-color: #3fb950;
  background: rgba(63, 185, 80, 0.1);
  transform: scale(1.05);
}

.markdown-content :deep(.download-btn) {
  position: absolute;
  top: 10px;
  right: 10px;
  background: #21262d;
  border: 1px solid #30363d;
  color: #8b949e;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 11px;
  cursor: pointer;
}
.markdown-content :deep(.download-btn:hover) {
  background: #30363d;
  color: #f0f6fc;
  opacity: 1;
  transform: translateY(-1px);
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2);
}
.markdown-content :deep(.download-btn.copied) {
  color: #3fb950;
  border-color: #3fb950;
  background: rgba(63, 185, 80, 0.1);
  transform: scale(1.05);
}
.markdown-content :deep(pre)::before {
  content: attr(class);
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 35px;
  background: #161b22;
  color: #8b949e;
  padding: 0 15px;
  display: flex;
  align-items: center;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  border-bottom: 1px solid #30363d;
  border-top-left-radius: 10px;
  border-top-right-radius: 10px;
}
/* Premium Image Loading Skeleton Animation */
.markdown-content :deep(img) {
  max-width: 100%;
  height: auto;
  border-radius: 12px;
  margin-top: 10px;
  border: 2px solid #3b82f6;
  box-shadow: 0 4px 15px rgba(0, 0, 0, 0.3);

  /* Skeleton Background */
  background: linear-gradient(110deg, #1e293b 8%, #334155 18%, #1e293b 33%);
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite linear;
  min-height: 300px; /* Pre-allocate space */
  min-width: 300px;
  display: block;
}

@keyframes shimmer {
  to {
    background-position: -200% 0;
  }
}

/* Buttons */
.speaker-btn {
  background: none;
  border: none;
  color: #94a3b8;
  cursor: pointer;
  padding: 8px;
  border-radius: 50%;
  transition: 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
}

.speaker-btn:hover,
.speaker-btn.is-active {
  background: #334155;
}
.speaker-btn small {
  font-size: 11px;
  font-weight: 500;
}

/* Image Styles */
.multi-history-images {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}
.chat-stored-img-small {
  width: 120px;
  height: 120px;
  object-fit: cover;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.1);
}

/* Audio Controls */
.audio-controls {
  margin-top: 8px;
  display: flex;
  justify-content: flex-start;
  border-top: 1px solid rgba(255, 255, 255, 0.05);
  padding-top: 6px;
}
</style>
