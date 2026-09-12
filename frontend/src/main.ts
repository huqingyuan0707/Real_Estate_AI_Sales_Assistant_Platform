import { createApp } from 'vue';
import 'element-plus/theme-chalk/index.css';
import App from './App.vue';
import router from './router';
import { createPinia } from 'pinia';

// 样式引入顺序：EP 原始样式 → 设计令牌 → 组件覆盖 → 全局基础
import './styles/design-tokens.css';
import './styles/element-override.css';
import './styles/global.css';

const app = createApp(App);
const pinia = createPinia();

app.use(pinia);
app.use(router);
app.mount('#app');
