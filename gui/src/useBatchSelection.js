// 通用批量勾选模块（模块化架构 m7）：勾选模式的完整交互状态机，供 GenericSiteView
// 与任何站点组件复用（RightPanel 内 ha/or/asmr 的既有批量逻辑后续迁移到此处）。
//
// 交互规范（全站统一，源自 准则与调研/站点接入调研清单.md 批量交互规范）：
//   独立开关按钮（默认关）→ 点卡片切换勾选 → 「开始下载(n)」→ 进行中可取消
//   → 完成后「查看收集的文件」。视图切换/退出勾选自动清空。
//
// 用法：
//   const batch = useBatchSelection()
//   batch.mode.value / batch.checked.value / batch.toggle() / batch.toggleItem(id)
//   batch.start(() => {...收集 ids 并发命令...})  // 空选不发；发出后自动退出勾选并清空

import { ref, computed } from 'vue'

export function useBatchSelection() {
  const mode = ref(false)              // 勾选模式开关
  const checked = ref(new Set())       // 已勾选 id
  const running = ref(false)           // 后端批量进行中（由 gs_state/站点事件驱动置位）

  const count = computed(() => checked.value.size)

  function toggle() {
    mode.value = !mode.value
    if (!mode.value) checked.value = new Set()
  }

  function toggleItem(id) {
    if (id == null || id === '') return
    const next = new Set(checked.value)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    checked.value = next
  }

  function reset() {
    mode.value = false
    checked.value = new Set()
  }

  /** 开始下载：idsOf() 返回勾选条目 id 数组；空选不发。发出后自动退出勾选。 */
  function start(idsOf) {
    const ids = (idsOf || (() => []))()
    if (!ids.length) return
    reset()
    return ids
  }

  /** 全选（ids=当前列表全部可勾选 id）。 */
  function selectAll(ids) {
    checked.value = new Set(ids || [])
  }

  /** 反选（ids=当前列表全部可勾选 id；取未勾选部分）。 */
  function invert(ids) {
    checked.value = new Set((ids || []).filter(id => !checked.value.has(id)))
  }

  /** 清空勾选（保留勾选模式）。 */
  function clearChecked() {
    checked.value = new Set()
  }

  return { mode, checked, running, count, toggle, toggleItem, reset, start,
           selectAll, invert, clearChecked }
}
