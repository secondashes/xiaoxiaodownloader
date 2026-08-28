<template>
  <div class="pg-bar">
    <!-- 页码：上一页 / 数字窗口 / 下一页（仿 EX 顶底分页） -->
    <div class="pg-pages">
      <button
        class="pg-btn pg-nav"
        :disabled="page <= 1 || searching"
        title="上一页"
        @click="go(page - 1)"
      >‹ 上一页</button>
      <template v-for="(p, i) in pageList" :key="i">
        <span v-if="p === 0" class="pg-ellipsis">…</span>
        <button
          v-else
          class="pg-btn pg-num"
          :class="{ active: p === page }"
          :disabled="searching"
          @click="go(p)"
        >{{ p }}</button>
      </template>
      <button
        class="pg-btn pg-nav"
        :disabled="!canNext || searching"
        title="下一页"
        @click="go(page + 1)"
      >下一页 ›</button>
    </div>
    <!-- 跳页框（仿 EX "Jump to page"） -->
    <div class="pg-jump" v-if="totalPages > 1 || hasMore">
      <span>跳到第</span>
      <input
        class="pg-input"
        type="number"
        min="1"
        v-model.number="jumpTo"
        @keyup.enter="doJump"
      />
      <span>页</span>
      <button class="pg-btn pg-jump-btn" :disabled="searching" @click="doJump">跳转</button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  page: { type: Number, default: 1 },
  totalPages: { type: Number, default: 0 },
  hasMore: { type: Boolean, default: false },
  searching: { type: Boolean, default: false },
})

const emit = defineEmits(['go-page'])

const jumpTo = ref(null)

// 页码窗口：首页 + 当前页 ±2 + 末页（已知时），间隔过大用省略号
const pageList = computed(() => {
  const cur = props.page
  const known = props.totalPages > 0
  const set = new Set([1, cur - 2, cur - 1, cur, cur + 1, cur + 2])
  if (known) set.add(props.totalPages)
  const pages = [...set]
    .filter(p => p >= 1 && (!known || p <= props.totalPages))
    .sort((a, b) => a - b)
  const out = []
  let prev = 0
  for (const p of pages) {
    if (prev && p - prev > 1) out.push(0) // 0 = 省略号占位
    out.push(p)
    prev = p
  }
  // 未知总页数但还有下一页：尾部补省略号表示可继续
  if (!known && props.hasMore && out[out.length - 1] !== 0) out.push(0)
  return out
})

const canNext = computed(() => {
  if (props.hasMore) return true
  return props.totalPages > 0 && props.page < props.totalPages
})

function go(p) {
  if (p === props.page || p < 1) return
  emit('go-page', p)
}

function doJump() {
  const p = Math.floor(Number(jumpTo.value))
  if (!p || p < 1) return
  go(p)
  jumpTo.value = null
}
</script>

<style scoped>
.pg-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
  padding: 6px 0;
}

.pg-pages {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
}

.pg-btn {
  background: #2d2d33;
  color: #c8c8d0;
  border: 1px solid #3d3d45;
  border-radius: 4px;
  font-size: 12px;
  padding: 3px 10px;
  cursor: pointer;
  line-height: 1.5;
  transition: background 0.12s ease, color 0.12s ease, border-color 0.12s ease;
}

.pg-btn:hover:not(:disabled) {
  background: #3d3d45;
  color: #fff;
}

.pg-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.pg-num.active {
  background: #4a7c3a;
  border-color: #5a9c46;
  color: #dff5cf;
  font-weight: bold;
}

.pg-ellipsis {
  color: #7f7f88;
  padding: 0 2px;
  font-size: 12px;
}

.pg-jump {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #8f8f98;
}

.pg-input {
  width: 58px;
  background: #1e1e22;
  border: 1px solid #3d3d45;
  border-radius: 4px;
  color: #e6e6ec;
  font-size: 12px;
  padding: 3px 6px;
  text-align: center;
  outline: none;
}

.pg-input:focus {
  border-color: #63e2b7;
}

.pg-jump-btn {
  padding: 3px 12px;
}
</style>
