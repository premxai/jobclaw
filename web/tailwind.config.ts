import type { Config } from "tailwindcss";

const config: Config = {
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
				// Warm palette
				background: '#FAF7F2',
				foreground: '#1A1A1A',
				surface: {
					DEFAULT: '#FFFFFF',
					2: '#F5F0E8',
					3: '#EDE6D8',
				},
				border: '#E5DDD0',
				'text-primary': '#1A1A1A',
				'text-secondary': '#7A7062',
				accent: {
					DEFAULT: '#E8713A',
					hover: '#D4612E',
					light: '#FFF0E6',
				},
				success: '#2D8A4E',
				info: '#3574D4',
				warning: '#C98A1A',
				card: {
					DEFAULT: '#FFFFFF',
					foreground: '#1A1A1A',
				},
				muted: {
					DEFAULT: '#F5F0E8',
					foreground: '#7A7062',
				},
				// Chart colors — warm palette
				chart: {
					'1': '#E8713A',
					'2': '#3574D4',
					'3': '#2D8A4E',
					'4': '#C98A1A',
					'5': '#9B6FD4',
					'6': '#D44B4B',
				},
			},
			borderRadius: {
				'xl': '16px',
				'lg': '12px',
				'md': '8px',
				'sm': '6px',
			},
			boxShadow: {
				// Consolidates the hover-shadow already used ad hoc in .job-card:hover
				// (globals.css) so components can share one elevation language instead
				// of re-declaring the same rgba() by hand.
				'card': '0 1px 2px rgba(26, 26, 26, 0.04)',
				'card-hover': '0 4px 20px rgba(232, 113, 58, 0.08)',
				// Matches the room-scene panel shadow in JobBoard.tsx so new surfaces
				// (filter panel, company cards) share its elevation.
				'popover': '0 20px 60px rgba(120, 80, 40, 0.12)',
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
