/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: '#010828',
        cream: '#EFF4FF',
        neon: '#6FFF00'
      },
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
        grotesk: ['Anton', 'sans-serif'],
        condiment: ['Condiment', 'cursive'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Monaco', 'Consolas', 'Liberation Mono', 'Courier New', 'monospace'],
      },
    },
  },
  plugins: [],
}
