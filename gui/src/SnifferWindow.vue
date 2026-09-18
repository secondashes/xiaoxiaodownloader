<template>
  <!-- 壳：仅提供 naive-ui 主题与消息上下文（useMessage 必须在 Provider 子组件内使用） -->
  <n-config-provider :theme="darkTheme" :locale="zhCN" :date-locale="dateZhCN" style="height: 100%">
    <n-message-provider>
      <SnifferInner />
    </n-message-provider>
  </n-config-provider>
</template>

<script setup>
import { NConfigProvider, NMessageProvider, darkTheme, zhCN, dateZhCN } from 'naive-ui'
import SnifferInner from './SnifferInner.vue'
</script>

<style>
html, body, #app { height: 100%; margin: 0; background: #16161a; }
</style>
