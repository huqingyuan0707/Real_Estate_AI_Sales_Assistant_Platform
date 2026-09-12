import { defineStore } from 'pinia';
import { ref } from 'vue';
import type { AgentPhase, AgentStatus } from '../types/agent';

export const useAgentStateStore = defineStore('agentState', () => {
  const status = ref<AgentStatus>({
    phase: 'done',
    phaseText: '',
    isStreaming: false,
  });

  const PHASES: Record<AgentPhase, string> = {
    planning: '🧠 规划中...',
    executing: '⚙️ 执行中...',
    validating: '✅ 校验中...',
    summarizing: '✍️ 生成回答...',
    done: '完成',
    error: '错误',
  };

  function startStreaming() {
    status.value = {
      phase: 'planning',
      phaseText: PHASES.planning,
      isStreaming: true,
    };
  }

  function setPhase(phase: AgentPhase) {
    status.value.phase = phase;
    status.value.phaseText = PHASES[phase];
  }

  function setPhaseText(text: string) {
    status.value.phaseText = text;
  }

  function finishStreaming() {
    status.value = {
      phase: 'done',
      phaseText: PHASES.done,
      isStreaming: false,
    };
  }

  function setError() {
    status.value = {
      phase: 'error',
      phaseText: '❌ 出错了',
      isStreaming: false,
    };
  }

  return {
    status,
    startStreaming,
    setPhase,
    setPhaseText,
    finishStreaming,
    setError,
  };
});
