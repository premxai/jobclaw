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
				sans: ["var(--font-inter)", "var(--font-geist-sans)", "system-ui", "sans-serif"],
				serif: ["var(--font-fraunces)", "Georgia", "serif"],
			},
			colors: {
				background: "#FFF3D6",
				foreground: "#2A1606",
				surface: {
					DEFAULT: "#FFFFFF",
					2: "#FFE8B8",
					3: "#FFD48A",
				},
				border: "#F0C979",
				ink: "#2A1606",
				"muted-ink": "#9B6B22",
				"text-primary": "#2A1606",
				"text-secondary": "#9B6B22",
				accent: {
					DEFAULT: "#F59E0B",
					hover: "#EA7A10",
					light: "#FFE2A3",
				},
				success: "#247A4D",
				info: "#3C6FD7",
				warning: "#B67A20",
				card: {
					DEFAULT: "#FFFFFF",
					foreground: "#080808",
				},
				muted: {
					DEFAULT: "#FFF3D6",
					foreground: "#9B6B22",
				},
				chart: {
					"1": "#F59E0B",
					"2": "#3C6FD7",
					"3": "#247A4D",
					"4": "#B67A20",
					"5": "#B4578F",
					"6": "#C44E4E",
				},
			},
			borderRadius: {
				xl: "16px",
				lg: "12px",
				md: "8px",
				sm: "6px",
			},
			boxShadow: {
				card: "0 1px 0 rgba(90, 48, 7, 0.06)",
				"card-hover": "0 14px 32px rgba(173, 98, 6, 0.14)",
				popover: "0 24px 70px rgba(90, 48, 7, 0.16)",
				soft: "0 10px 30px rgba(90, 48, 7, 0.12)",
			},
			animation: {
				"fade-in": "fadeIn 0.3s ease-out",
				"slide-up": "slideUp 0.4s ease-out",
				"slide-in": "slideIn 0.3s ease-out",
			},
			keyframes: {
				fadeIn: {
					"0%": { opacity: "0" },
					"100%": { opacity: "1" },
				},
				slideUp: {
					"0%": { opacity: "0", transform: "translateY(12px)" },
					"100%": { opacity: "1", transform: "translateY(0)" },
				},
				slideIn: {
					"0%": { opacity: "0", transform: "translateX(-12px)" },
					"100%": { opacity: "1", transform: "translateX(0)" },
				},
			},
		},
	},
	plugins: [require("tailwindcss-animate")],
};

export default config;
