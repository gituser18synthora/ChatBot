import typography from "@tailwindcss/typography";

/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#f4f3ff",
          100: "#e8e6ff",
          200: "#d4ceff",
          300: "#b4a8ff",
          400: "#8c77ff",
          500: "#8C52FF",
          600: "#6A5AF9",
          700: "#5547d6",
          800: "#473bb4",
          900: "#3b3195",
        },
        'brand-blue': '#3b82f6',
        'brand-green': '#10b981',
        'brand-red': '#ef4444',
        'brand-gray': '#6b7280',
        'custom-blue': 'rgba(35, 107, 254, 0.2)',
        'custom-purple': 'rgba(140, 82, 255, 0.2)',
        primary: '#6A5AF9',
        'primary-hover': '#7354F0',
        secondary: '#8C52FF',
        'secondary-hover': '#732ED9',
        white: '#FFFFFF',
        'ghost-white': '#F8F9FF',
        'light-gray': '#E6E8F0',
        'jet-black': '#1B1B1B',
        'charcoal-gray': '#1B1B1B',
        danger: '#E51C1C',
        'danger-hover': '#BA2532',
      },
      fontFamily: {
        sans: ["Poppins", "Inter", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
      },
      boxShadow: {
        card: "0 1px 2px rgba(16,24,40,0.06), 0 1px 3px rgba(16,24,40,0.10)",
        pop: "0 12px 32px rgba(16,24,40,0.16)",
      },
    },
  },
  plugins: [typography],
};
