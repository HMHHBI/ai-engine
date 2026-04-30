import { nextTick } from 'vue'
import { useUIStore } from '@/stores/uiStore'

import Prism from 'prismjs'
import 'prismjs/themes/prism-tomorrow.css'
import 'prismjs/components/prism-javascript'
import 'prismjs/components/prism-python'
import 'prismjs/components/prism-css'
import 'prismjs/components/prism-jsx'

export function useChatUI() {
  const uiStore = useUIStore()

  const highlightCode = () => {
    nextTick(() => {
      Prism.highlightAll()
      document.querySelectorAll('.markdown-content pre').forEach((block) => {
        if (block.querySelector('.actions-wrapper')) return

        const wrapper = document.createElement('div')
        wrapper.className = 'actions-wrapper'

        // Copy Button
        const copyBtn = document.createElement('button')
        copyBtn.innerText = 'Copy'
        copyBtn.className = 'copy-btn'
        copyBtn.onclick = () => {
          const code = block.querySelector('code').innerText
          copyToClipboard(code)
          copyBtn.innerText = 'Copied!'
          setTimeout(() => (copyBtn.innerText = 'Copy'), 2000)
        }

        // Download Button (Specific for this code block)
        const downBtn = document.createElement('button')
        downBtn.innerText = 'Download'
        downBtn.className = 'download-btn'
        downBtn.style.marginRight = '60px'
        downBtn.onclick = () => {
          const code = block.querySelector('code').innerText
          const langClass = block.querySelector('code').className // e.g. language-python
          downloadCodeBlock(code, langClass)
        }

        wrapper.appendChild(downBtn)
        wrapper.appendChild(copyBtn)
        block.appendChild(wrapper)
      })
    })
  }

  const parseImageData = (data) => {
    try {
      if (!data) return null
      const parsed = typeof data === 'string' ? JSON.parse(data) : data
      return Array.isArray(parsed) ? parsed : [parsed]
    } catch (e) {
      return [data]
    }
  }

  const saveFile = (content, fileName, type) => {
    const blob = new Blob([content], { type })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = fileName
    a.click()
    URL.revokeObjectURL(url)
  }

  const getExtension = (lang) => {
    const map = {
      python: 'py',
      javascript: 'js',
      typescript: 'ts',
      html: 'html',
      css: 'css',
      cpp: 'cpp',
      java: 'java',
      markdown: 'md',
      json: 'json',
      jsx: 'jsx',
    }
    return map[lang.toLowerCase()] || 'txt'
  }

  const downloadCodeBlock = (code, langClass) => {
    try {
      const lang = langClass.split('-')[1] || 'txt'
      const ext = getExtension(lang)
      saveFile(code, `code_snippet_${Math.floor(Date.now() / 1000)}.${ext}`, 'text/plain')

      uiStore.addToast('Download Successfully!', 'success')
    } catch {
      uiStore.addToast('Failed to download', 'error')
    }
  }

  const downloadChat = (text) => {
    const fileName = `chat_msg_${Math.floor(Date.now() / 1000)}.md`

    saveFile(text, fileName, 'text/markdown')
    uiStore.addToast('Message downloaded as Markdown', 'success')
  }

  const copyToClipboard = async (text) => {
    try {
      await navigator.clipboard.writeText(text)
      uiStore.addToast('Message copied to clipboard!', 'success')
    } catch (err) {
      uiStore.addToast('Failed to copy', 'error')
    }
  }

  return {
    highlightCode,
    parseImageData,
    downloadChat,
    copyToClipboard,
  }
}
