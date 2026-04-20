/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'bg-deep': '#050608',
        'bg-panel': '#0c0e14',
        'bg-card': '#12151c',
        'bg-hover': '#1a1e28',
        'border-subtle': '#1e2430',
        'border-active': '#2a3142',
        'accent-wine': '#722f37',
        'accent-wine-dim': '#5a252c',
        'accent-violet': '#8b5cf6',
        'accent-amber': '#f59e0b',
        'accent-rose': '#f43f5e',
        'accent-cyan': '#06b6d4',
        'text-primary': '#e8eaed',
        'text-secondary': '#9ca3af',
        'text-muted': '#6b7280',
        'text-code': '#c58fa3',
      },
      fontFamily: {
        'mono': ['JetBrains Mono', 'monospace'],
        'body': ['IBM Plex Sans', 'sans-serif'],
      },
    },
  },
  plugins: [],
}