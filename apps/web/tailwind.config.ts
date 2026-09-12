import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        severity: {
          red: "#dc2626",
          "red-bg": "#fee2e2",
          yellow: "#ca8a04",
          "yellow-bg": "#fef9c3",
          green: "#16a34a",
          "green-bg": "#dcfce7",
        },
      },
    },
  },
  plugins: [],
};

export default config;
