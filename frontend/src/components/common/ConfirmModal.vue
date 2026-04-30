<script setup>
import { useUIStore } from '@/stores/uiStore'
const uiStore = useUIStore()

const handleConfirm = () => {
  if (uiStore.confirmModal.onConfirm) {
    uiStore.confirmModal.onConfirm() // Function chalao
  }
  uiStore.closeConfirm() // Modal band karo
}
</script>

<template>
  <Transition name="fade">
    <div v-if="uiStore.confirmModal.show" class="modal-overlay" @click.self="uiStore.closeConfirm">
      <div class="modal-card">
        <div class="modal-header">
          <h3>{{ uiStore.confirmModal.title }}</h3>
        </div>
        <div class="modal-body">
          <p>{{ uiStore.confirmModal.message }}</p>
        </div>
        <div class="modal-footer">
          <button class="cancel-btn" @click="uiStore.closeConfirm">Cancel</button>
          <button class="confirm-btn" @click="handleConfirm">Confirm Delete</button>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.7);
  backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10000;
}

.modal-card {
  background: #1e293b;
  border: 1px solid rgba(255, 255, 255, 0.1);
  padding: 30px;
  border-radius: 20px;
  max-width: 400px;
  width: 90%;
  box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
  text-align: center;
}

h3 { color: white; margin-bottom: 10px; font-size: 1.25rem; }
p { color: #94a3b8; margin-bottom: 25px; line-height: 1.5; }

.modal-footer {
  display: flex;
  gap: 12px;
}

.modal-footer button {
  flex: 1;
  padding: 12px;
  border-radius: 10px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  border: none;
}

.cancel-btn { background: #334155; color: white; }
.cancel-btn:hover { background: #475569; }

.confirm-btn { background: #ef4444; color: white; }
.confirm-btn:hover { background: #dc2626; transform: translateY(-2px); }

/* Animation */
.fade-enter-active, .fade-leave-active { transition: opacity 0.3s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>