/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        page: '#F7F8FA',
        card: '#FFFFFF',
        borderSubtle: '#E5E7EB',
        charcoal: '#111827',
        secondary: '#6B7280',
        brandBlue: '#2563EB',
        psifRed: '#B91C1C',
        brandAmber: '#D97706',
      },
      fontFamily: {
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'Roboto', 'sans-serif'],
      },
      borderRadius: {
        card: '8px',
      },
      boxShadow: {
        card: '0 1px 3px rgba(0, 0, 0, 0.06)',
      }
    },
  },
  plugins: [],
}
