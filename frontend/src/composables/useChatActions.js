import { ref } from 'vue'
import { useUserStore } from '@/stores/userStore'
import { useUIStore } from '@/stores/uiStore'
import { streamAI, uploadPDFApi, cleanupChatApi } from '@/api'

export function useChatActions(props, emit) {
  const userStore = useUserStore()
  const uiStore = useUIStore()

  const currentTask = ref('general')
  const tasks = [
    { id: 'general', name: 'Gemini 2.0 Flash', icon: '✨' },
    { id: 'research', name: 'Research Mode (Web)', icon: '🔍' },
    { id: 'code', name: 'Code Assistant', icon: '💻' },
    { id: 'blog', name: 'Creative Writer', icon: '📝' },
    { id: 'email', name: 'Email Writer', icon: '✉️' },
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
      pdfContext.value = data.text
      uiStore.addToast('PDF processed and added to context!', 'success')
    } catch (err) {
      uiStore.addToast('Error reading PDF', 'error')
    } finally {
      loading.value = false
    }
  }

  // useChatActions.js mein ye naya function add karein:

  const handleEditMessage = async (index) => {
    if (loading.value) return

    const msgToEdit = props.messages[index]
    if (msgToEdit.role !== 'user') return

    // 1. Purana text input area mein wapis le ayein
    prompt.value = msgToEdit.text

    // Database ID save karein taake backend ko pata ho kahan se agay delete karna hai
    editingMessageIndex.value = index

    // 2. Images handle karein (agar user ne images bheji thin)
    if (msgToEdit.image_data) {
      try {
        // Agar JSON string hai toh parse karein, warna as-is array use karein
        const images =
          typeof msgToEdit.image_data === 'string'
            ? JSON.parse(msgToEdit.image_data)
            : msgToEdit.image_data

        // Ensure karein ke selectedImages mein array hi jaye[cite: 2]
        selectedImages.value = Array.isArray(images) ? [...images] : [images]
      } catch (e) {
        console.error('Image parsing failed during edit:', e)
        selectedImages.value = []
      }
    } else {
      selectedImages.value = []
    }

    // 4. Focus wapis input bar par le ayein (optional UI touch)
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
          // API call jo humne pehle discuss ki thi (cleanup endpoint)
          await cleanupChatApi(props.chatId, parseInt(editingMessageIndex.value))

          // UI se purane messages hatayein
          props.messages.splice(
            editingMessageIndex.value,
            props.messages.length - editingMessageIndex.value,
          )
          editingMessageIndex.value = null // Reset edit mode
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
        scrollToBottom()
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

    // 1. SAFE IMAGE PARSING
    let originalImages = []
    try {
      if (userMessage.image_data) {
        // Agar pehle se hi Array hai toh direct use karein
        if (Array.isArray(userMessage.image_data)) {
          originalImages = userMessage.image_data
        }
        // Agar String hai toh check karein ke JSON hai ya direct Base64
        else if (typeof userMessage.image_data === 'string') {
          if (userMessage.image_data.startsWith('[') || userMessage.image_data.startsWith('{')) {
            originalImages = JSON.parse(userMessage.image_data)
          } else {
            // Agar sirf ek Base64 string hai toh array mein daal dein
            originalImages = [userMessage.image_data]
          }
        }
      }
    } catch (e) {
      console.error('Image parsing failed, using empty array', e)
      originalImages = []
    }

    const originalText = userMessage.text

    // 2. UI Cleanup
    props.messages.splice(index - 1, 2)

    // 3. Reset Inputs & Resend
    prompt.value = originalText
    selectedImages.value = originalImages // Ab ye error nahi dega

    await send()
  }

  const stopGeneration = () => {
    if (abortController.value) {
      abortController.value.abort() // Connection kaat do
      abortController.value = null
      loading.value = false
      uiStore.addToast('Generation stopped', 'info')
    }
  }

  return {
    userStore,
    currentTask,
    tasks,
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
