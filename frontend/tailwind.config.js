import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

/** @type {import('tailwindcss').Config} */
export default {
  content: [
    path.join(__dirname, "index.html"),
    path.join(__dirname, "src/**/*.{js,ts,jsx,tsx}"),
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
    "./frontend/index.html",
    "./frontend/src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        dark: {
          950: "#070B14",
          900: "#0A0F1D",
          850: "#0F172A",
          800: "#1E293B",
          700: "#334155",
        },
        confidence: {
          high: "#10B981",    // Emerald
          medium: "#F59E0B",  // Amber
          low: "#F43F5E",     // Rose Ruby
        },
      },
    },
  },
  plugins: [],
};
