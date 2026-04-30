import { ref } from 'vue'

export function useSpeech(prompt) {
  const isSpeaking = ref(null)
  const isListening = ref(false)
  const synth = window.speechSynthesis

  // --- Speech to Text (Mic) ---
  const recognition =
    window.SpeechRecognition || window.webkitSpeechRecognition
      ? new (window.SpeechRecognition || window.webkitSpeechRecognition)()
      : null

  if (recognition) {
    recognition.continuous = false
    recognition.onstart = () => {
      isListening.value = true
    }
    recognition.onend = () => {
      isListening.value = false
    }
    recognition.onresult = (event) => {
      prompt.value += event.results[0][0].transcript
    }
  }

  const toggleListen = () => {
    if (isListening.value) recognition.stop()
    else recognition.start()
  }

  // --- Text to Speech (Speaker) ---
  const speak = (text, index) => {
    if (synth.speaking) {
      synth.cancel()
      if (isSpeaking.value === index) {
        isSpeaking.value = null
        return
      }
    }

    const cleanText = text
      .replace(/```[\s\S]*?```/g, ' [Code block skipped] ')
      .replace(/[*#_~`>]/g, '')
      .trim()

    const utterance = new SpeechSynthesisUtterance(cleanText)
    const voices = synth.getVoices()
    utterance.voice = voices.find((v) => v.lang.includes('en-US')) || voices[0]
    utterance.pitch = 1.1
    utterance.rate = 0.95

    utterance.onstart = () => {
      isSpeaking.value = index
    }
    utterance.onend = () => {
      isSpeaking.value = null
    }
    synth.speak(utterance)
  }

  return { isSpeaking, isListening, toggleListen, speak }
}
