<script setup>
import { onUpdated, watch } from 'vue'
import { getChatDetailApi } from '@/api'
import { useChatUI } from '@/composables/useChatUI'
import { useChatActions } from '@/composables/useChatActions'
import { useSpeech } from '@/composables/useSpeech'

import TaskBar from '@/components/chat/TaskBar.vue'
import MessageContainer from '@/components/chat/MessageContainer.vue'
import InputArea from '@/components/chat/InputArea.vue'

const props = defineProps(['messages', 'chatId', 'isMessagesLoading'])
const emit = defineEmits(['refresh', 'scrollToBottom'])

const { highlightCode, parseImageData, copyToClipboard, downloadChat } = useChatUI()
const { userStore, currentTask, tasks, loading, prompt, selectedImages, showAttachmentMenu, pdfContext, handleImageUpload, handleFileUpload, handleEditMessage, send, handleRegenerate, stopGeneration } = useChatActions(props, emit)
const { isSpeaking, isListening, toggleListen, speak } = useSpeech(prompt)

onUpdated(() => {
  highlightCode()
  // emit('scrollToBottom')
})

watch(
  () => props.chatId,
  async (newId) => {
    if (!newId) return
    try {
      const data = await getChatDetailApi(userStore.token, newId)
      pdfContext.value = data.pdf_context || ''
    } catch (err) {
      console.error(err)
    }
  },
  { immediate: true },
)
</script>

<template>
  <div class="chat-container">
    <TaskBar v-model="currentTask" :tasks="tasks" :pdf-context="pdfContext" :loading="loading" />

    <MessageContainer
      :messages="messages"
      :is-speaking="isSpeaking"
      :loading="isMessagesLoading"
      @edit-message="handleEditMessage"
      @speak="speak"
      @regenerate="handleRegenerate"
      @copy="copyToClipboard"
      @download="downloadChat"
      @stop="stopGeneration"
      :parseImageData="parseImageData"
    />

    <InputArea
      v-model="prompt"
      :loading="loading"
      :selected-images="selectedImages"
      :is-listening="isListening"
      :show-attachment-menu="showAttachmentMenu"
      @send="send"
      @image-upload="handleImageUpload"
      @file-upload="handleFileUpload"
      @toggle-listen="toggleListen"
      @remove-image="(idx) => selectedImages.splice(idx, 1)"
      @toggle-attachment="showAttachmentMenu = !showAttachmentMenu"
    />
  </div>
</template>

<style scoped>
.chat-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #0f172a;
  color: #f8fafc;
}
</style>
