import { createRouter, createWebHistory } from 'vue-router'

const SITE = 'Congress Trades Tracker'

const router = createRouter({
  history: createWebHistory(),
  scrollBehavior: (to, from, saved) => saved || (to.hash ? { el: to.hash, top: 72 } : { top: 0 }),
  routes: [
    { path: '/', name: 'overview', component: () => import('./pages/Overview.vue'), meta: { title: 'Do members of Congress beat the market?' } },
    { path: '/members', name: 'members', component: () => import('./pages/Members.vue'), meta: { title: 'Members' } },
    { path: '/members/:id', name: 'member', component: () => import('./pages/Member.vue'), props: true },
    { path: '/trades', name: 'trades', component: () => import('./pages/Trades.vue'), meta: { title: 'Latest trades' } },
    { path: '/other', name: 'other', component: () => import('./pages/Other.vue'), meta: { title: 'Options, bonds & funds' } },
    { path: '/picks', name: 'picks', component: () => import('./pages/Picks.vue'), meta: { title: 'Your picks' } },
    { path: '/methodology', redirect: '/' },
    { path: '/:pathMatch(.*)*', name: 'not-found', component: () => import('./pages/NotFound.vue'), meta: { title: 'Page not found' } },
  ],
})

// Member pages set their own title once the member loads.
router.afterEach((to) => {
  if (to.meta.title) document.title = to.name === 'overview' ? `${SITE} · ${to.meta.title}` : `${to.meta.title} · ${SITE}`
})

export default router
