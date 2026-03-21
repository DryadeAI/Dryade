import type { Config } from "tailwindcss";
import tailwindcssAnimate from "tailwindcss-animate";
import tailwindcssTypography from "@tailwindcss/typography";

export default {
  darkMode: ["class"],
  content: ["./pages/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./app/**/*.{ts,tsx}", "./src/**/*.{ts,tsx}"],
  prefix: "",
  theme: {
  	container: {
  		center: true,
  		padding: '2rem',
  		screens: {
  			'2xl': '1400px'
  		}
  	},
  	extend: {
		fontFamily: {
			sans: [
				'Inter',
				'ui-sans-serif',
				'system-ui',
				'sans-serif'
			],
			mono: [
				'JetBrains Mono',
				'ui-monospace',
				'SFMono-Regular',
				'Menlo',
				'Monaco',
				'Consolas',
				'Liberation Mono',
				'Courier New',
				'monospace'
			],
			display: [
				'Inter',
				'system-ui',
				'sans-serif'
			],
		},
		colors: {
			border: 'hsl(var(--border))',
			input: 'hsl(var(--input))',
			ring: 'hsl(var(--ring))',
			background: 'hsl(var(--background))',
			foreground: 'hsl(var(--foreground))',
			primary: {
				DEFAULT: 'hsl(var(--primary))',
				foreground: 'hsl(var(--primary-foreground))'
			},
			secondary: {
				DEFAULT: 'hsl(var(--secondary))',
				foreground: 'hsl(var(--secondary-foreground))'
			},
			destructive: {
				DEFAULT: 'hsl(var(--destructive))',
				foreground: 'hsl(var(--destructive-foreground))'
			},
			success: {
				DEFAULT: 'hsl(var(--success))',
				foreground: 'hsl(var(--success-foreground))'
			},
			warning: {
				DEFAULT: 'hsl(var(--warning))',
				foreground: 'hsl(var(--warning-foreground))'
			},
			info: {
				DEFAULT: 'hsl(var(--info))',
				foreground: 'hsl(var(--info-foreground))'
			},
			muted: {
				DEFAULT: 'hsl(var(--muted))',
				foreground: 'hsl(var(--muted-foreground))'
			},
			accent: {
				DEFAULT: 'hsl(var(--accent))',
				foreground: 'hsl(var(--accent-foreground))',
				secondary: 'hsl(var(--accent-secondary))',
				'secondary-foreground': 'hsl(var(--accent-secondary-foreground))',
				tertiary: 'hsl(var(--accent-tertiary))',
				'tertiary-foreground': 'hsl(var(--accent-tertiary-foreground))'
			},
			popover: {
				DEFAULT: 'hsl(var(--popover))',
				foreground: 'hsl(var(--popover-foreground))'
			},
			card: {
				DEFAULT: 'hsl(var(--card))',
				foreground: 'hsl(var(--card-foreground))'
			},
			sidebar: {
				DEFAULT: 'hsl(var(--sidebar-background))',
				foreground: 'hsl(var(--sidebar-foreground))',
				primary: 'hsl(var(--sidebar-primary))',
				'primary-foreground': 'hsl(var(--sidebar-primary-foreground))',
				accent: 'hsl(var(--sidebar-accent))',
				'accent-foreground': 'hsl(var(--sidebar-accent-foreground))',
				border: 'hsl(var(--sidebar-border))',
				ring: 'hsl(var(--sidebar-ring))'
			},
			node: {
				input: 'hsl(var(--node-input))',
				process: 'hsl(var(--node-process))',
				output: 'hsl(var(--node-output))',
				decision: 'hsl(var(--node-decision))',
				default: 'hsl(var(--node-default))'
			},
			/* Dryade forest scale — available as Tailwind classes */
			forest: {
				950: 'hsl(var(--forest-950))',
				900: 'hsl(var(--forest-900))',
				850: 'hsl(var(--forest-850))',
				800: 'hsl(var(--forest-800))',
				750: 'hsl(var(--forest-750))',
				700: 'hsl(var(--forest-700))',
				600: 'hsl(var(--forest-600))',
				500: 'hsl(var(--forest-500))',
				400: 'hsl(var(--forest-400))',
				300: 'hsl(var(--forest-300))',
				200: 'hsl(var(--forest-200))',
				100: 'hsl(var(--forest-100))',
				50:  'hsl(var(--forest-50))',
			},
			emerald: {
				900: 'hsl(var(--emerald-900))',
				800: 'hsl(var(--emerald-800))',
				700: 'hsl(var(--emerald-700))',
				600: 'hsl(var(--emerald-600))',
				500: 'hsl(var(--emerald-500))',
				400: 'hsl(var(--emerald-400))',
				300: 'hsl(var(--emerald-300))',
				200: 'hsl(var(--emerald-200))',
			},
		},
		borderRadius: {
			lg: 'var(--radius)',
			md: 'calc(var(--radius) - 2px)',
			sm: 'calc(var(--radius) - 4px)'
		},
		transitionDuration: {
			fast: 'var(--duration-fast)',
			normal: 'var(--duration-normal)',
			slow: 'var(--duration-slow)'
		},
		boxShadow: {
			glow: 'var(--shadow-glow)',
			'glow-sm': 'var(--shadow-glow-sm)',
			'glow-lg': '0 0 40px -5px hsl(var(--emerald-400) / 0.35)',
			'glow-secondary': 'var(--shadow-glow-secondary)',
			'glow-tertiary': 'var(--shadow-glow-tertiary)',
			'2xs': 'var(--shadow-2xs)',
			xs: 'var(--shadow-xs)',
			sm: 'var(--shadow-sm)',
			md: 'var(--shadow-md)',
			lg: 'var(--shadow-lg)',
			xl: 'var(--shadow-xl)',
			'2xl': 'var(--shadow-2xl)'
		},
		keyframes: {
			'accordion-down': {
				from: { height: '0' },
				to: { height: 'var(--radix-accordion-content-height)' }
			},
			'accordion-up': {
				from: { height: 'var(--radix-accordion-content-height)' },
				to: { height: '0' }
			},
			'flow-pulse': {
				'0%, 100%': { opacity: '0.4' },
				'50%': { opacity: '1' }
			},
			'node-appear': {
				from: { opacity: '0', transform: 'scale(0.9)' },
				to: { opacity: '1', transform: 'scale(1)' }
			},
			shimmer: {
				'0%': { transform: 'translateX(-100%)' },
				'100%': { transform: 'translateX(100%)' }
			},
			'ring-rotate': {
				'0%': { transform: 'rotate(0deg)' },
				'100%': { transform: 'rotate(360deg)' }
			},
			'glow-pulse': {
				'0%, 100%': { opacity: '0.4', transform: 'scale(1)' },
				'50%': { opacity: '1', transform: 'scale(1.05)' }
			}
		},
		animation: {
			'accordion-down': 'accordion-down 0.2s ease-out',
			'accordion-up': 'accordion-up 0.2s ease-out',
			'flow-pulse': 'flow-pulse 2s ease-in-out infinite',
			'node-appear': 'node-appear 0.2s ease-out',
			shimmer: 'shimmer 2s ease-in-out infinite',
			'ring-rotate': 'ring-rotate 4s linear infinite',
			'glow-pulse': 'glow-pulse 2s ease-in-out infinite'
		},
		backgroundImage: {
			'gradient-radial': 'radial-gradient(var(--tw-gradient-stops))',
			'gradient-conic': 'conic-gradient(from 180deg at 50% 50%, var(--tw-gradient-stops))'
		}
	}
  },
  plugins: [tailwindcssAnimate, tailwindcssTypography],
} satisfies Config;
