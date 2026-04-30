<script setup>
import { ref, nextTick, watch } from 'vue'
const props = defineProps([
  'modelValue',
  'loading',
  'selectedImages',
  'isListening',
  'showAttachmentMenu',
])

const emit = defineEmits([
  'update:modelValue',
  'send',
  'image-upload',
  'file-upload',
  'toggle-listen',
  'remove-image',
  'toggle-attachment',
  'stop'
])

const handleKeydown = (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    emit('send')
  }
}

const textareaRef = ref(null)

const autoResize = () => {
  const el = textareaRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = el.scrollHeight + 'px'
}

watch(
  () => props.modelValue,
  () => {
    nextTick(autoResize)
  },
)
</script>

<template>
  <div class="input-area">
    <transition name="fade">
      <div v-if="selectedImages?.length > 0" class="multi-preview-container shadow-2xl">
        <div v-for="(img, idx) in selectedImages" :key="idx" class="preview-item">
          <img :src="`data:image/png;base64,${img}`" class="mini-img-grid" />
          <button @click="emit('remove-image', idx)" class="mini-close-btn">✕</button>
        </div>
      </div>
    </transition>

    <div class="input-wrapper">
      <div class="text-section">
        <textarea
          ref="textareaRef"
          :value="modelValue"
          @input="
            (e) => {
              emit('update:modelValue', e.target.value)
              autoResize()
            }
          "
          @keydown="handleKeydown"
          placeholder="Ask AI Engine anything..."
          rows="1"
          :disabled="loading"
        ></textarea>
      </div>

      <div class="utility-bar">
        <div class="left-tools">
          <div class="attachment-container">
            <button
              class="tool-btn"
              @click.stop="emit('toggle-attachment')"
              :class="{ active: showAttachmentMenu }"
            >
              <svg
                viewBox="0 0 24 24"
                width="20"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              >
                <path
                  d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48"
                />
              </svg>
            </button>

            <transition name="pop">
              <div v-if="showAttachmentMenu" class="attachment-menu shadow-xl">
                <label class="menu-item">
                  <span class="menu-icon">📷</span>
                  <div class="menu-text">
                    <span>Images<small>Multiple selection</small></span>
                  </div>
                  <input
                    type="file"
                    @change="(e) => emit('image-upload', e)"
                    multiple
                    accept="image/*"
                    hidden
                  />
                </label>
                <label class="menu-item">
                  <span class="menu-icon">📄</span>
                  <div class="menu-text">
                    <span>PDF<small>Analyze PDF</small></span>
                  </div>
                  <input
                    type="file"
                    @change="(e) => emit('file-upload', e)"
                    accept="application/pdf"
                    hidden
                  />
                </label>
              </div>
            </transition>
          </div>
        </div>

        <div class="right-tools">
          <button
            @click="emit('toggle-listen')"
            class="tool-btn mic-btn"
            :class="{ 'is-recording': isListening }"
          >
            <svg viewBox="0 0 24 24" width="20" fill="currentColor">
              <path
                d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z"
              />
              <path
                d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z"
              />
            </svg>
          </button>

          <button
            v-if="loading"
            @click="emit('stop')"
            class="stop-btn shadow-lg"
            title="Stop Generation"
          >
            <svg viewBox="0 0 24 24" width="20" fill="currentColor">
              <path d="M6 6h12v12H6z" />
            </svg>
          </button>

          <button
            v-else
            @click="emit('send')"
            :disabled="(!modelValue?.trim() && !selectedImages?.length)"
            class="send-btn-gemini"
            :class="{ 'has-content': modelValue?.trim() || selectedImages?.length }"
          >
            <svg viewBox="0 0 24 24" width="18" fill="currentColor">
              <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.input-area {
  padding: 10px 20px 30px;
}

.input-wrapper {
  max-width: 800px;
  margin: 0 auto;
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 20px;
  display: flex;
  flex-direction: column; /* Upar text, niche buttons */
  box-shadow: 0 10px 25px rgba(0, 0, 0, 0.3);
  overflow: visible; /* Dropdown menu bahar dikhane ke liye zaroori hai */
}

/* 1. Text Section */
.text-section {
  padding: 12px 16px 4px;
}

textarea {
  width: 100%;
  background: transparent;
  border: none;
  color: white;
  padding: 8px 0;
  resize: none;
  outline: none;
  font-size: 16px;
  line-height: 1.5;
  max-height: 100px;
  min-height: 44px;
  font-family: inherit;
}

/* 2. Utility Bar (Fixed Overlap) */
.utility-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  border-top: 1px solid rgba(255, 255, 255, 0.05);
}

.left-tools,
.right-tools {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* Buttons */
.tool-btn {
  background: none;
  border: none;
  color: #94a3b8;
  padding: 8px;
  border-radius: 50%;
  cursor: pointer;
  transition: 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
}

.tool-btn:hover,
.tool-btn.active {
  background: #334155;
  color: white;
}

.send-btn-gemini {
  background: #334155;
  border: none;
  color: #64748b;
  width: 36px;
  height: 36px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s;
}

.send-btn-gemini.has-content {
  background: #2563eb;
  color: white;
}

/* InputArea.vue CSS mein */
.stop-btn {
  background: #ef4444; /* Bright Red */
  color: white;
  border: none;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.stop-btn:hover {
  background: #dc2626;
  transform: scale(1.05);
}

/* Dropdown Menu Fix */
.attachment-container {
  position: relative;
}

.attachment-menu {
  position: absolute;
  bottom: 100%; /* Button ke upar khulay ga */
  left: 0;
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 12px;
  width: 160px;
  margin-bottom: 12px;
  padding: 6px;
  z-index: 100;
}

.menu-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px;
  cursor: pointer;
  border-radius: 8px;
  transition: background 0.2s;
  color: #cbd5e1;
  font-size: 14px;
}

.menu-item:hover {
  background: #334155;
  color: white;
}
.menu-icon {
  font-size: 18px;
  margin-right: 12px;
}
.menu-text span {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: #f8fafc;
}
.menu-text small {
  display: block;
  font-size: 11px;
  color: #64748b;
}

/* Previews */
.multi-preview-container {
  display: flex;
  gap: 10px;
  padding: 12px;
  background: rgba(30, 41, 59, 0.8);
  border-radius: 12px;
  margin: 0 auto 10px;
  max-width: 800px;
  border: 1px solid #3b82f6;
  overflow-x: auto;
}

.mini-img-grid {
  width: 50px;
  height: 50px;
  object-fit: cover;
  border-radius: 6px;
}
.mini-close-btn {
  position: absolute;
  top: -10px;
  right: -10px;
  background: #ef4444;
  border-radius: 50%;
  width: 20px;
  height: 20px;
  color: white;
  border: none;
  font-size: 10px;
  cursor: pointer;
}

/* Transitions */
.pop-enter-active,
.pop-leave-active {
  transition: all 0.2s ease;
}
.pop-enter-from,
.pop-leave-to {
  opacity: 0;
  transform: translateY(10px) scale(0.95);
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.mic-btn.is-recording {
  color: #ef4444;
  background: rgba(239, 68, 68, 0.1);
  animation: pulse 1.5s infinite;
}

@keyframes pulse {
  0% {
    box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.4);
  }
  70% {
    box-shadow: 0 0 0 10px rgba(239, 68, 68, 0);
  }
  100% {
    box-shadow: 0 0 0 0 rgba(239, 68, 68, 0);
  }
}
</style>
