import { createRouter, createWebHistory } from 'vue-router'

export default createRouter({
  history: createWebHistory(),
  scrollBehavior: (to, from, saved) => saved || { top: 0 },
  routes: [
    { path: '/', name: 'overview', component: () => import('./pages/Overview.vue') },
    { path: '/members', name: 'members', component: () => import('./pages/Members.vue') },
    { path: '/members/:id', name: 'member', component: () => import('./pages/Member.vue'), props: true },
    { path: '/trades', name: 'trades', component: () => import('./pages/Trades.vue') },
    { path: '/methodology', name: 'methodology', component: () => import('./pages/Methodology.vue') },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})
