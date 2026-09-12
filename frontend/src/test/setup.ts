import { vi } from 'vitest';
import '@testing-library/jest-dom';

vi.mock('vue-router', () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
  }),
  useRoute: () => ({
    params: {},
    query: {},
  }),
}));

vi.mock('element-plus', () => ({
  ElMessage: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
  },
  ElMessageBox: {
    confirm: vi.fn(),
    prompt: vi.fn(),
  },
  ElNotification: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

vi.mock('@/api', () => ({
  api: {
    listSessions: vi.fn(),
    getSession: vi.fn(),
    chatStream: vi.fn(),
    resumeSession: vi.fn(),
    listSkills: vi.fn(),
    installSkill: vi.fn(),
    uninstallSkill: vi.fn(),
    submitFeedback: vi.fn(),
    clearShortMemory: vi.fn(),
  },
}));

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation(query => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

Object.defineProperty(window, 'scrollTo', {
  writable: true,
  value: vi.fn(),
});
