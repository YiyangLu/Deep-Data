/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Modern light theme colors
        'light-bg': '#ffffff',
        'light-secondary': '#f7f7f8',
        'light-input': '#ffffff',
        'light-border': '#e5e5e5',
        'light-text': '#1a1a1a',
        'light-text-secondary': '#6e6e80',
        'light-hover': '#f0f0f1',
      },
    },
  },
  plugins: [],
}
