import type { Config } from "tailwindcss";

const config: Config = {
	darkMode: ["class"],
	content: [
		"./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
		"./src/components/**/*.{js,ts,jsx,tsx,mdx}",
		"./src/app/**/*.{js,ts,jsx,tsx,mdx}",
	],
	theme: {
		extend: {
			fontFamily: {
				sans: ['var(--font-lexend)', 'Lexend', 'system-ui', 'sans-serif'],
			},
			colors: {
				// JobClaw dark palette
				surface: {
					DEFAULT: '#161B22',
					2: '#21262D',
					3: '#282E36',
				},
				border: '#30363D',
				'text-primary': '#E6EDF3',
				'text-secondary': '#8B949E',
				accent: {
					DEFAULT: '#F0883E',
					hover: '#E07020',
				},
				success: '#3FB950',
				info: '#58A6FF',
				warning: '#D29922',
				// Semantic tokens
				background: '#0D1117',
				foreground: '#E6EDF3',
				card: {
					DEFAULT: '#161B22',
					foreground: '#E6EDF3',
				},
				muted: {
					DEFAULT: '#21262D',
					foreground: '#8B949E',
				},
				// Chart colors
				chart: {
					'1': '#F0883E',
					'2': '#58A6FF',
					'3': '#3FB950',
					'4': '#D29922',
					'5': '#BC8CFF',
					'6': '#FF7B72',
				},
			},
			borderRadius: {
				'xl': '16px',
				'lg': '12px',
				'md': '8px',
				'sm': '6px',
			},
			animation: {
				'fade-in': 'fadeIn 0.3s ease-out',
				'slide-up': 'slideUp 0.4s ease-out',
				'slide-in': 'slideIn 0.3s ease-out',
			},
			keyframes: {
				fadeIn: {
					'0%': { opacity: '0' },
					'100%': { opacity: '1' },
				},
				slideUp: {
					'0%': { opacity: '0', transform: 'translateY(12px)' },
					'100%': { opacity: '1', transform: 'translateY(0)' },
				},
				slideIn: {
					'0%': { opacity: '0', transform: 'translateX(-12px)' },
					'100%': { opacity: '1', transform: 'translateX(0)' },
				},
			},
		},
	},
	plugins: [require("tailwindcss-animate")],
};
export default config;
