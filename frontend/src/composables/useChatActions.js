import { ref } from 'vue'
import { useUserStore } from '@/stores/userStore'
import { useUIStore } from '@/stores/uiStore'
import { streamAI, uploadPDFApi, cleanupChatApi } from '@/api'

export function useChatActions(props, emit) {
  const userStore = useUserStore()
  const uiStore = useUIStore()

  const currentTask = ref('general')
  const selectedModel = ref('gemini-2.5-flash')

  const tasks = [
    { id: 'general', name: 'General Assistant', icon: '✨' },
    { id: 'research', name: 'Research Mode (Web)', icon: '🔍' },
    { id: 'code', name: 'Code Assistant', icon: '💻' },
    { id: 'blog', name: 'Creative Writer', icon: '📝' },
    { id: 'email', name: 'Email Writer', icon: '✉️' },
  ]

  const models = [
    { id: 'gemini-2.5-flash', name: 'Gemini 2.5 Flash' },
    { id: 'ollama-llama3.2', name: 'Ollama Llama 3.2 (Local)' },
    { id: 'openai-gpt-4o-mini', name: 'OpenAI GPT-4o Mini' },
  ]

  const loading = ref(false)
  const prompt = ref('')
  const selectedImages = ref([])
  const showAttachmentMenu = ref(false)
  const imageMime = ref('')
  const pdfContext = ref('')
  const abortController = ref(null)
  const editingMessageIndex = ref(null)

  const handleImageUpload = (event) => {
    const files = Array.from(event.target.files)
    if (files.length === 0) return
    showAttachmentMenu.value = false

    files.forEach((file) => {
      const reader = new FileReader()
      reader.onload = (e) => {
        selectedImages.value.push(e.target.result.split(',')[1])
      }
      reader.readAsDataURL(file)
    })
  }

  const handleFileUpload = async (event) => {
    const file = event.target.files[0]
    if (!file || !props.chatId) return

    showAttachmentMenu.value = false
    loading.value = true

    const formData = new FormData()
    formData.append('file', file)

    try {
      const data = await uploadPDFApi(props.chatId, formData)
      pdfContext.value = data.pdf_context
      uiStore.addToast('PDF processed and added to context!', 'success')
    } catch (err) {
      uiStore.addToast('Error reading PDF', 'error')
    } finally {
      loading.value = false
    }
  }

  const handleEditMessage = async (index) => {
    if (loading.value) return

    const msgToEdit = props.messages[index]
    if (msgToEdit.role !== 'user') return

    prompt.value = msgToEdit.text
    editingMessageIndex.value = index

    if (msgToEdit.image_data) {
      try {
        const images =
          typeof msgToEdit.image_data === 'string'
            ? JSON.parse(msgToEdit.image_data)
            : msgToEdit.image_data

        selectedImages.value = Array.isArray(images) ? [...images] : [images]
      } catch (e) {
        console.error('Image parsing failed during edit:', e)
        selectedImages.value = []
      }
    } else {
      selectedImages.value = []
    }

    uiStore.addToast('Edit mode active. Update your message.', 'success')
  }

  const send = async () => {
    if (
      (!prompt.value.trim() && selectedImages.value.length === 0) ||
      !props.chatId ||
      loading.value
    )
      return

    if (editingMessageIndex.value !== null) {
      try {
        await cleanupChatApi(props.chatId, parseInt(editingMessageIndex.value))
        props.messages.splice(
          editingMessageIndex.value,
          props.messages.length - editingMessageIndex.value,
        )
        editingMessageIndex.value = null
      } catch (err) {
        uiStore.addToast('Sync failed with server', 'error')
        return
      }
    }

    const userMsg = prompt.value
    const currentImages = [...selectedImages.value]
    const currentMime = imageMime.value

    prompt.value = ''
    selectedImages.value = []
    loading.value = true

    props.messages.push({
      role: 'user',
      text: userMsg || 'Uploaded images',
      image_data: JSON.stringify(currentImages),
    })

    abortController.value = new AbortController()
    const signal = abortController.value.signal

    try {
      const res = await streamAI(
        {
          task: currentTask.value || 'general',
          model: selectedModel.value || 'gemini-2.5-flash',
          prompt: userMsg || 'Explain these images',
          chat_id: props.chatId,
          signal: signal,
          file_context: pdfContext.value,
          image_base64: currentImages,
          image_mime: currentMime,
        },
        signal,
      )

      if (!res.ok) throw new Error('Unauthorized or Server Error')

      const reader = res.body.getReader()
      const decoder = new TextDecoder()

      let aiMsg = { role: 'ai', text: '' }
      props.messages.push(aiMsg)

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        aiMsg.text += decoder.decode(value)
      }
    } catch (err) {
      if (err.name === 'AbortError') {
        console.log('User stopped the request')
      } else {
        props.messages.push({ role: 'ai', text: 'Error occurred.' })
      }
    } finally {
      loading.value = false
      abortController.value = null
      emit('refresh', props.chatId)
    }
  }

  const handleRegenerate = async (index) => {
    if (loading.value) return

    const msgToRegenerate = props.messages[index]
    if (msgToRegenerate.role !== 'ai') return

    const userMessage = props.messages[index - 1]
    if (!userMessage || userMessage.role !== 'user') {
      uiStore.addToast('Cannot find the original prompt', 'error')
      return
    }

    let originalImages = []
    try {
      if (userMessage.image_data) {
        if (Array.isArray(userMessage.image_data)) {
          originalImages = userMessage.image_data
        } else if (typeof userMessage.image_data === 'string') {
          if (userMessage.image_data.startsWith('[') || userMessage.image_data.startsWith('{')) {
            originalImages = JSON.parse(userMessage.image_data)
          } else {
            originalImages = [userMessage.image_data]
          }
        }
      }
    } catch (e) {
      console.error('Image parsing failed, using empty array', e)
      originalImages = []
    }

    const originalText = userMessage.text

    props.messages.splice(index - 1, 2)
    prompt.value = originalText
    selectedImages.value = originalImages

    await send()
  }

  const stopGeneration = () => {
    if (abortController.value) {
      abortController.value.abort()
      abortController.value = null
      loading.value = false
      uiStore.addToast('Generation stopped', 'info')
    }
  }

  return {
    userStore,
    currentTask,
    selectedModel,
    tasks,
    models,
    loading,
    prompt,
    selectedImages,
    showAttachmentMenu,
    pdfContext,
    handleImageUpload,
    handleFileUpload,
    handleEditMessage,
    send,
    handleRegenerate,
    stopGeneration,
  }
}
