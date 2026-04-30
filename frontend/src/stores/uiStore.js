import { defineStore } from 'pinia'

export const useUIStore = defineStore('ui', {
  state: () => ({
    toasts: [], // [ {id, message, type} ]
    confirmModal: {
      show: false,
      title: '',
      message: '',
      onConfirm: null, // Yahan hum function save karenge
    },
  }),
  actions: {
    addToast(message, type = 'success') {
      const id = Date.now()
      this.toasts.push({ id, message, type })

      // 3 second baad khud hi nikal do
      setTimeout(() => {
        this.removeToast(id)
      }, 3000)
    },
    removeToast(id) {
      this.toasts = this.toasts.filter((t) => t.id !== id)
    },
    
    openConfirm(title, message, callback) {
      this.confirmModal = {
        show: true,
        title,
        message,
        onConfirm: callback,
      }
    },

    // Modal band karo
    closeConfirm() {
      this.confirmModal.show = false
    },
  },
})
