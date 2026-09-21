/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        navy: {
          900: '#0b1120',
          800: '#0f172a',
          700: '#1e293b',
          600: '#334155',
        },
        police: {
          blue: '#1d4ed8',
          gold: '#f59e0b',
        }
      }
    },
  },
  plugins: [],
}
