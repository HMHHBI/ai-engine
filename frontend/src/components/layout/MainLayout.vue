<script setup>
import Sidebar from '../components/layout/Sidebar.vue'
</script>

<template>
  <div class="app">
    <Sidebar />

    <div class="main">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.app {
  display: flex;
  height: 100vh;
}

.main {
  flex: 1;
  background: #f7f7f8;
}
</style>
