<script setup>
import { RouterView } from 'vue-router'
import ToastProvider from '@/components/common/ToastProvider.vue'
import ConfirmModal from '@/components/common/ConfirmModal.vue'
</script>

<template>
  <div class="app-layout">
    <ConfirmModal />
    <ToastProvider />
    <RouterView />
  </div>
</template>

<style>
body {
  margin: 0;
  font-family: system-ui, Arial;
  background: #0f172a;
  color: white;
}

.app-layout {
  height: 100vh;
}
</style>