import { createApp } from 'vue'

import App from './App.vue'
import { restoreAuthentication } from './auth'
import { router } from './router'

void restoreAuthentication().finally(() => {
  createApp(App).use(router).mount('#app')
})
