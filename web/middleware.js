// Vercel Routing Middleware: HTTP Basic Auth in front of the private picks page
// and its data. The password lives in the PICKS_PASSWORD environment variable
// on Vercel, never in this repo. Any username is accepted.
import { next } from '@vercel/functions'

export const config = { matcher: ['/picks', '/picks/:path*'] }

const unauthorized = () =>
  new Response('Password required.', {
    status: 401,
    headers: { 'WWW-Authenticate': 'Basic realm="Congress picks", charset="UTF-8"', 'Cache-Control': 'no-store' },
  })

// Constant-time comparison so response timing doesn't leak the password.
function safeEqual(a, b) {
  if (a.length !== b.length) return false
  let diff = 0
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i)
  return diff === 0
}

export default function middleware(request) {
  const expected = process.env.PICKS_PASSWORD
  if (!expected) return unauthorized() // fail closed if the variable is missing
  const header = request.headers.get('authorization') || ''
  const [scheme, encoded] = header.split(' ')
  if (scheme === 'Basic' && encoded) {
    let decoded = ''
    try { decoded = atob(encoded) } catch { return unauthorized() }
    const password = decoded.slice(decoded.indexOf(':') + 1)
    if (safeEqual(password, expected)) {
      return next({ headers: { 'Cache-Control': 'private, no-store', 'X-Robots-Tag': 'noindex' } })
    }
  }
  return unauthorized()
}
