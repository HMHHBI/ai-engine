<script setup>
import { useUIStore } from '@/stores/uiStore'
const uiStore = useUIStore()
</script>

<template>
  <div class="toast-container">
    <TransitionGroup name="list">
      <div 
        v-for="toast in uiStore.toasts" 
        :key="toast.id" 
        class="toast-item" 
        :class="toast.type"
      >
        <span class="icon">
          {{ toast.type === 'success' ? '✅' : '❌' }}
        </span>
        {{ toast.message }}
      </div>
    </TransitionGroup>
  </div>
</template>

<style scoped>
.toast-container {
  position: fixed;
  top: 20px;
  right: 20px;
  z-index: 9999;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.toast-item {
  padding: 12px 20px;
  border-radius: 12px;
  background: rgba(30, 41, 59, 0.9);
  backdrop-filter: blur(10px);
  color: white;
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.3);
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 200px;
}

.toast-item.success { border-left: 4px solid #10b981; }
.toast-item.error { border-left: 4px solid #ef4444; }

/* Transitions */
.list-enter-active, .list-leave-active { transition: all 0.4s ease; }
.list-enter-from { opacity: 0; transform: translateX(30px); }
.list-leave-to { opacity: 0; transform: scale(0.9); }
</style>