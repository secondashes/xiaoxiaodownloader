<!-- ASMR 后台迷你播放器：切站/离开详情后悬浮右下角，续播可控（暂停/切轨/拖进度/音量/字幕/停止）。
     挂载在 App.vue，可见性由父级控制（有播放任务且全量播放器不可见时显示）。
     状态全部来自通用播放器样板 audioPlayer.js；其他音声站可直接复制本组件。 -->
<template>
  <div class="asmr-mini">
    <div class="asmr-mini-head">
      <span class="asmr-mini-icon">🎵</span>
      <span class="asmr-mini-title" :title="`${st.work?.album_name || ''} · ${st.track?.title || ''}`" @click="$emit('jump-back')">
        {{ st.track?.title || '音声播放中' }}
      </span>
      <n-button size="tiny" quaternary type="primary" title="回到作品详情" @click="$emit('jump-back')">⤢</n-button>
      <n-button size="tiny" quaternary type="error" title="停止播放" @click="stopPlayer">✕</n-button>
    </div>
    <div class="asmr-mini-ctrl">
      <n-button size="tiny" quaternary :disabled="st.index <= 0" title="上一个音轨" @click="playOffset(-1)">⏮</n-button>
      <n-button size="tiny" quaternary :type="st.paused ? 'primary' : 'default'" :title="st.paused ? '播放' : '暂停'" @click="togglePlay">{{ st.paused ? '▶' : '⏸' }}</n-button>
      <n-button size="tiny" quaternary :disabled="st.index >= st.queue.length - 1" title="下一个音轨" @click="playOffset(1)">⏭</n-button>
      <n-button size="tiny" quaternary :title="st.muted ? '取消静音' : '静音'" @click="toggleMute">{{ st.muted ? '🔇' : '🔊' }}</n-button>
      <input class="asmr-mini-vol" type="range" min="0" max="100" :value="Math.round(st.volume * 100)"
        title="音量（拖动后自动记住）" @input="e => setVolume(Number(e.target.value) / 100)" />
      <span v-if="st.subStatus === 'ready'" class="asmr-mini-subtoggle" :class="{ off: !st.subOn }"
        title="显示 / 隐藏字幕" @click="setSubOn(!st.subOn)">字</span>
      <span class="asmr-mini-time">{{ st.error || st.timeText }}</span>
    </div>
    <!-- 字幕/歌词：贴进度条上方，双行（当前行 + 下一行预览），字号随迷你条宽度自适应 -->
    <div v-if="st.subOn && st.subStatus && st.subStatus !== 'loading'" class="asmr-mini-sub"
      :class="{ err: st.subStatus === 'error' }" :title="st.subText">
      <div v-if="st.subStatus === 'error'" class="sub-cur">（字幕加载失败）</div>
      <div v-else-if="st.subStatus === 'none'" class="sub-none">（本音轨无字幕）</div>
      <template v-else>
        <div class="sub-cur" :class="{ dim: !st.subText }">{{ st.subText || '···' }}</div>
        <div v-if="st.subNext" class="sub-nxt">{{ st.subNext }}</div>
      </template>
    </div>
    <input class="asmr-mini-seek" type="range" min="0" max="1000" :value="progressVal"
      title="播放进度（可拖动）" @input="onSeekInput" />
  </div>
</template>

<script setup>
// 播放状态与控制全部来自全局单例 store（audioPlayer.js），本组件自身无音频逻辑
import { computed } from 'vue'
import { NButton } from 'naive-ui'
import { playerState as st, togglePlay, playOffset, seekTo, setVolume, toggleMute, setSubOn, stopPlayer, fmtTime } from '../audioPlayer.js'

defineEmits(['jump-back'])

const progressVal = computed(() =>
  st.duration ? Math.round((st.currentTime / st.duration) * 1000) : 0)

function onSeekInput(e) {
  seekTo((Number(e.target.value) / 1000) * (st.duration || 0))
}
</script>

<style scoped>
/* 迷你条容器供字幕 cqw 自适应（宽度 360px 固定，但窗口缩放/未来尺寸变化都跟随） */
.asmr-mini {
  position: fixed;
  right: 16px;
  bottom: 16px;
  z-index: 2000;
  width: 360px;
  max-width: calc(100vw - 32px);
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 8px 10px;
  border-radius: 10px;
  background: rgba(24, 24, 28, 0.96);
  border: 1px solid rgba(99, 226, 183, 0.35);
  box-shadow: 0 8px 28px rgba(0, 0, 0, 0.55);
  backdrop-filter: blur(8px);
  container-type: inline-size;
}
.asmr-mini-head {
  display: flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
}
.asmr-mini-icon {
  flex-shrink: 0;
  font-size: 14px;
}
.asmr-mini-title {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  color: #e0e0e6;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: pointer;
}
.asmr-mini-title:hover {
  color: #63e2b7;
}
.asmr-mini-ctrl {
  display: flex;
  align-items: center;
  gap: 4px;
}
/* 字幕区：当前行（高亮，可换行）+ 下一行（预览，单行截断），cqw 自适应 */
.asmr-mini-sub {
  display: flex;
  flex-direction: column;
  gap: 1px;
  text-align: center;
  overflow: hidden;
}
.asmr-mini-sub .sub-cur {
  font-size: clamp(13px, 4.8cqw, 17px);
  line-height: 1.4;
  color: #63e2b7;
  white-space: pre-line;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
.asmr-mini-sub .sub-cur.dim {
  color: rgba(99, 226, 183, 0.35);
}
.asmr-mini-sub .sub-nxt {
  font-size: clamp(11px, 3.6cqw, 14px);
  line-height: 1.4;
  color: rgba(99, 226, 183, 0.5);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.asmr-mini-sub .sub-none {
  font-size: 11px;
  color: #7a7a85;
}
.asmr-mini-sub.err .sub-cur {
  color: #e88080;
}
.asmr-mini-vol {
  flex-shrink: 0;
  width: 64px;
  height: 4px;
  accent-color: #63e2b7;
  cursor: pointer;
}
.asmr-mini-subtoggle {
  flex-shrink: 0;
  font-size: 11px;
  color: #63e2b7;
  cursor: pointer;
  padding: 0 2px;
  user-select: none;
}
.asmr-mini-subtoggle.off {
  color: #7a7a85;
  text-decoration: line-through;
}
.asmr-mini-time {
  margin-left: auto;
  flex-shrink: 0;
  font-size: 11px;
  color: #9a9aa5;
  font-variant-numeric: tabular-nums;
  max-width: 110px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.asmr-mini-seek {
  width: 100%;
  height: 4px;
  accent-color: #63e2b7;
  cursor: pointer;
}
/* 日间模式 */
html.light-mode .asmr-mini {
  background: rgba(255, 255, 255, 0.97);
  border-color: rgba(24, 160, 88, 0.4);
  box-shadow: 0 8px 28px rgba(0, 0, 0, 0.18);
}
html.light-mode .asmr-mini-title {
  color: #333;
}
html.light-mode .asmr-mini-title:hover {
  color: #18a058;
}
html.light-mode .asmr-mini-sub .sub-cur {
  color: #18a058;
}
html.light-mode .asmr-mini-sub .sub-cur.dim {
  color: rgba(24, 160, 88, 0.4);
}
html.light-mode .asmr-mini-sub .sub-nxt {
  color: rgba(24, 160, 88, 0.55);
}
html.light-mode .asmr-mini-sub .sub-none {
  color: #8a8a95;
}
html.light-mode .asmr-mini-sub.err .sub-cur {
  color: #d03050;
}
html.light-mode .asmr-mini-subtoggle {
  color: #18a058;
}
html.light-mode .asmr-mini-subtoggle.off {
  color: #b0b0b8;
}
html.light-mode .asmr-mini-time {
  color: #666;
}
</style>
