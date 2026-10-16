// SenseHive uses EdgeShell's palette (one look across the fleet tools): its
// primary blue, its success, warning and danger colours, and the same grays.
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./frontend/**/*.jsx', './version-1.0/templates/**/*.html'],
  theme: {
    extend: {
      colors: {
        blue: { 50: '#e8effc', 100: '#d4e2fa', 400: '#5b8def', 500: '#2f6ae3', 600: '#1a56db', 700: '#1044b0', 800: '#0d3a96' },
        green: { 100: '#d1fae5', 400: '#34d399', 500: '#059669', 600: '#047857', 700: '#065f46' },
        red: { 100: '#fee2e2', 400: '#f87171', 500: '#dc2626', 600: '#c81e1e', 700: '#9b1c1c' },
        yellow: { 100: '#fef3c7', 400: '#fbbf24', 500: '#d97706', 600: '#b45309' },
        purple: { 400: '#38bdf8', 500: '#0ea5e9', 600: '#0284c7', 700: '#0369a1' },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'Arial', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'Consolas', 'monospace'],
      },
      borderRadius: { lg: '8px', xl: '12px' },
    },
  },
  plugins: [],
};
