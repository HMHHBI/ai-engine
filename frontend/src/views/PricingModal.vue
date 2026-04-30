<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { useUserStore } from '@/stores/userStore'
import { useUIStore } from '@/stores/uiStore'
import { upgradeRequestApi } from '@/api'

const userStore = useUserStore()
const uiStore = useUIStore()
const showPricing = ref(false);

const handleUpgrade = async () => {
  try {
    // Fake Upgrade Request
    const res = await upgradeRequestApi(userStore.token); 
    
    if (res.success) {
      // Profile dobara fetch karein taake userStore update ho jaye
      await userStore.fetchProfile(); 
      uiStore.addToast("Subscription active! Enjoy PRO features.", "success");
      showPricing.value = false;
    } else {
      uiStore.addToast(res.detail || "Upgrade failed", "error");
    }
  } catch (err) {
    uiStore.addToast("Payment failed", "error");
  }
};
</script>
<template>
  <div class="pricing-overlay" @click.self="$emit('close')">
    <div class="pricing-card shadow-2xl">
      <h2 class="title">Upgrade to Pro</h2>
      <p class="subtitle">Experience the full power of AI Engine</p>

      <div class="plans-grid">
        <div class="plan-box">
          <span class="plan-name">Free</span>
          <div class="price">$0<span>/mo</span></div>
          <ul class="features">
            <li>✅ Basic AI access</li>
            <li>✅ 50 messages per day</li>
            <li>❌ No Image Analysis</li>
          </ul>
          <button disabled class="current-btn">Current Plan</button>
        </div>

        <div class="plan-box pro highlight">
          <div class="badge">Recommended</div>
          <span class="plan-name">Pro</span>
          <div class="price">$20<span>/mo</span></div>
          <ul class="features">
            <li>✅ Gemini 1.5 Pro (Fastest)</li>
            <li>✅ 5000 Messages</li>
            <li>✅ 1000 Image & PDF Analysis</li>
          </ul>
          <button @click="handleUpgrade" class="upgrade-btn">Upgrade Now</button>
        </div>

        <div class="plan-box">
          <span class="plan-name">Pro</span>
          <div class="price">$50<span>/mo</span></div>
          <ul class="features">
            <li>✅ Gemini 1.5 Pro (Fastest)</li>
            <li>✅ Unlimited Messages</li>
            <li>✅ Image & PDF Analysis + High priority</li>
          </ul>
          <button disabled class="current-btn">Current Plan</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.pricing-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.8);
  backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.pricing-card {
  background: #1e293b;
  border: 1px solid #334155;
  padding: 40px;
  border-radius: 24px;
  max-width: 700px;
  width: 90%;
  text-align: center;
}
.plans-grid {
  display: flex;
  gap: 20px;
  margin-top: 30px;
}
.plan-box {
  flex: 1;
  padding: 24px;
  background: #0f172a;
  border-radius: 16px;
  border: 1px solid #334155;
  display: flex;
  flex-direction: column;
}
.plan-box.highlight {
  border-color: #3b82f6;
  position: relative;
  transform: scale(1.05);
}
.badge {
  position: absolute;
  top: -12px;
  left: 50%;
  transform: translateX(-50%);
  background: #3b82f6;
  color: white;
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 12px;
}
.price { font-size: 32px; font-weight: bold; margin: 15px 0; }
.price span { font-size: 16px; color: #64748b; }
.features { text-align: left; list-style: none; margin: 20px 0; flex: 1; }
.features li { margin-bottom: 10px; font-size: 14px; }

.upgrade-btn {
  background: #3b82f6;
  color: white;
  border: none;
  padding: 12px;
  border-radius: 10px;
  cursor: pointer;
  font-weight: bold;
}
.current-btn { background: #334155; color: #94a3b8; border: none; padding: 12px; border-radius: 10px; }
</style>