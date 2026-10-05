// Static JSON produced by `python -m congress.site_data`. Each file is fetched
// once per page load and shared between pages.
const cache = new Map()

function load(path) {
  if (!cache.has(path)) {
    cache.set(path, fetch(`/data/${path}`).then((r) => {
      if (!r.ok) throw new Error(`Could not load ${path} (${r.status})`)
      return r.json()
    }).catch((e) => { cache.delete(path); throw e }))
  }
  return cache.get(path)
}

export const getSummary = () => load('summary.json')
export const getMembers = () => load('members.json')
export const getOther = () => load('other.json')
export const getMember = (id) => load(`members/${encodeURIComponent(id)}.json`)
