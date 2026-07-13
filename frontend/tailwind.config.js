import typography from "@tailwindcss/typography";

/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#eef4ff",
          100: "#dbe6ff",
          200: "#bcd0ff",
          300: "#8eb0ff",
          400: "#5985ff",
          500: "#335dff",
          600: "#1d3ff5",
          700: "#172ee1",
          800: "#1928b6",
          900: "#1b298f",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
      },
      boxShadow: {
        card: "0 1px 2px rgba(16,24,40,0.06), 0 1px 3px rgba(16,24,40,0.10)",
        pop: "0 12px 32px rgba(16,24,40,0.16)",
      },
    },
  },
  plugins: [typography],
};
