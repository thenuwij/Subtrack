import type { MetadataRoute } from 'next'

// Lets people add Pocketday to their home screen, with a long-press shortcut
// straight to "Can I afford it?".
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: 'Pocketday',
    short_name: 'Pocketday',
    description: 'What’s free to spend until payday.',
    start_url: '/dashboard',
    display: 'standalone',
    background_color: '#ffffff',
    theme_color: '#0a84ff',
    icons: [
      { src: '/icon.svg', sizes: 'any', type: 'image/svg+xml' },
      { src: '/apple-icon', sizes: '180x180', type: 'image/png' },
    ],
    shortcuts: [
      { name: 'Can I afford it?', short_name: 'Afford it?', url: '/afford' },
      { name: 'Update today’s balance', short_name: 'Balance', url: '/balance' },
    ],
  }
}
