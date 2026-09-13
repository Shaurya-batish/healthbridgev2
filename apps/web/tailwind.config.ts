import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        severity: {
          // Darkened from the Tailwind 600-level shade so text/icons on the
          // matching tinted "-bg" pass WCAG AA (4.5:1) for body text --
          // critical here since the triage result screen (RED/YELLOW/GREEN)
          // is meant to be read outdoors in sunlight.
          red: "#991b1b",
          "red-bg": "#fee2e2",
          yellow: "#854d0e",
          "yellow-bg": "#fef9c3",
          green: "#166534",
          "green-bg": "#dcfce7",
        },
      },
    },
  },
  plugins: [],
};

export default config;
