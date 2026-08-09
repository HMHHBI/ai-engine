<script setup>
const props = defineProps({
  tasks: { type: Array, default: () => [] },
  models: { type: Array, default: () => [] },
  taskValue: { type: String, default: 'general' },
  modelValue: { type: String, default: 'gemini-2.0-flash' },
  pdfContext: { type: String, default: '' },
  loading: { type: Boolean, default: false }
})

const emit = defineEmits(['update:taskValue', 'update:modelValue'])
</script>

<template>
  <div class="task-bar">
    <div class="task-info">
      <!-- 1. Task / Agent Selector -->
      <select
        :value="taskValue"
        @change="e => emit('update:taskValue', e.target.value)"
        class="professional-select"
      >
        <option v-for="t in tasks" :key="t.id" :value="t.id">
          {{ t.icon }} {{ t.name }}
        </option>
      </select>

      <!-- 2. AI Model Selector -->
      <select
        :value="modelValue"
        @change="e => emit('update:modelValue', e.target.value)"
        class="professional-select model-select"
      >
        <option v-for="m in models" :key="m.id" :value="m.id">
          🤖 {{ m.name }}
        </option>
      </select>
    </div>

    <div class="status-group">
      <div v-if="pdfContext" class="pdf-badge">📄 PDF Active</div>

      <div class="status">
        <span class="status-dot" :class="{ 'is-loading': loading }"></span>
        <small>{{ loading ? 'Thinking...' : 'Ready' }}</small>
      </div>
    </div>
  </div>
</template>

<style scoped>
.task-bar {
  padding: 12px 24px;
  background: #1e293b;
  border-bottom: 1px solid #334155;
  display: flex;
  justify-content: space-between;
  align-items: center;
  z-index: 10;
}

.task-info {
  display: flex;
  gap: 12px;
  align-items: center;
}

.professional-select {
  background: #0f172a;
  color: #f8fafc;
  border: 1px solid #334155;
  padding: 6px 12px;
  border-radius: 8px;
  font-size: 13px;
  outline: none;
  cursor: pointer;
  transition: border-color 0.2s;
}

.professional-select:hover {
  border-color: #475569;
}

.model-select {
  border-color: #3b82f6;
  background: #1e1b4b;
}

.status-group {
  display: flex;
  align-items: center;
  gap: 16px;
}

.status {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #94a3b8;
}

.pdf-badge {
  background: #064e3b;
  color: #34d399;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 600;
}

.status-dot {
  width: 8px;
  height: 8px;
  background: #22c55e;
  border-radius: 50%;
}

.status-dot.is-loading {
  background: #eab308;
  animation: blink 1s infinite;
}

@keyframes blink {
  50% {
    opacity: 0.5;
  }
}
</style>