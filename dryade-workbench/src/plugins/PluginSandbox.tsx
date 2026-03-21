// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useEffect, useRef, useCallback } from 'react';
import { PluginRegistry } from './PluginRegistry';
import type { PluginUIPermission } from './types/pluginManifest';

// SDK CSS files loaded as raw strings at build time (Vite ?raw imports)
// These replace the former 1030-line PLUGIN_SHARED_CSS string literal.
import layersCss from '../../../packages/plugin-sdk/src/styles/layers.css?raw';
import baseCss from '../../../packages/plugin-sdk/src/styles/base.css?raw';
import tokensCss from '../../../packages/plugin-sdk/src/styles/tokens.css?raw';
import componentsCss from '../../../packages/plugin-sdk/src/styles/components.css?raw';
import utilitiesCss from '../../../packages/plugin-sdk/src/styles/utilities.css?raw';
import animationsCss from '../../../packages/plugin-sdk/src/styles/animations.css?raw';

/**
 * Compiled SDK CSS bundle — concatenated from individual @layer files.
 * Layer cascade order: base < tokens < components < utilities < plugin
 * Plugin-custom styles go into @layer plugin (highest priority).
 */
const SDK_CSS = [layersCss, baseCss, tokensCss, componentsCss, utilitiesCss, animationsCss].join('\n');

interface PluginSandboxProps {
  pluginName: string;
  bundleCode: string;
  styles?: string;
  permissions: PluginUIPermission[];
  theme?: 'light' | 'dark';
  locale?: string;
  className?: string;
  onReady?: () => void;
  onError?: (error: string) => void;
}

/**
 * CSS Custom Properties to extract from host document
 * These are the essential design tokens that plugins need for theming
 */
const CSS_PROPERTIES_TO_EXTRACT = [
  // Core colors
  '--background', '--foreground', '--card', '--card-foreground',
  '--popover', '--popover-foreground', '--primary', '--primary-foreground',
  '--secondary', '--secondary-foreground', '--muted', '--muted-foreground',
  '--accent', '--accent-foreground', '--destructive', '--destructive-foreground',
  '--success', '--success-foreground', '--warning', '--warning-foreground',
  '--info', '--info-foreground',
  '--border', '--input', '--ring', '--radius',
  // Extended accents (from 54-01)
  '--accent-secondary', '--accent-secondary-foreground',
  '--accent-tertiary', '--accent-tertiary-foreground',
  // Glass/shadows
  '--glass-bg', '--glass-border', '--glass-glow',
  '--shadow-glow', '--shadow-glow-sm', '--shadow-card', '--shadow-elevated',
  '--shadow-glow-secondary', '--shadow-glow-tertiary',
  // Animation
  '--duration-fast', '--duration-normal', '--duration-slow',
  // Node colors
  '--node-input', '--node-process', '--node-output', '--node-decision', '--node-default',
];

/**
 * Extracts all CSS custom properties from the host document's :root
 * Returns a CSS string that plugins can use for theming
 *
 * @param theme - Current theme ('light' or 'dark') to determine which values to extract
 */
function extractCSSCustomProperties(theme: 'light' | 'dark' = 'dark'): string {
  // In SSR or test environments, return static fallback values
  if (typeof document === 'undefined') {
    return getStaticCSSVariables(theme);
  }

  const rootStyles = getComputedStyle(document.documentElement);
  const cssVars: string[] = [];

  for (const prop of CSS_PROPERTIES_TO_EXTRACT) {
    const value = rootStyles.getPropertyValue(prop).trim();
    if (value) {
      cssVars.push(`  ${prop}: ${value};`);
    }
  }

  return `:root {\n${cssVars.join('\n')}\n}`;
}

/**
 * Static CSS variables fallback for SSR/test environments
 */
function getStaticCSSVariables(theme: 'light' | 'dark'): string {
  if (theme === 'light') {
    return `:root {
  --background: 107 4% 96%;
  --foreground: 108 19% 13%;
  --card: 0 0% 100%;
  --card-foreground: 108 19% 13%;
  --popover: 0 0% 100%;
  --popover-foreground: 108 19% 13%;
  --primary: 116 66% 83%;
  --primary-foreground: 96 26% 4%;
  --secondary: 105 8% 92%;
  --secondary-foreground: 108 19% 13%;
  --muted: 105 6% 90%;
  --muted-foreground: 100 8% 45%;
  --accent: 127 55% 43%;
  --accent-foreground: 0 0% 100%;
  --destructive: 0 72% 56%;
  --destructive-foreground: 0 0% 100%;
  --success: 127 55% 32%;
  --success-foreground: 0 0% 100%;
  --warning: 38 92% 50%;
  --warning-foreground: 108 19% 13%;
  --info: 199 89% 48%;
  --info-foreground: 0 0% 100%;
  --border: 105 12% 78%;
  --input: 105 8% 90%;
  --ring: 116 66% 83%;
  --radius: 0.5rem;
  --glass-bg: 107 4% 90% / 0.9;
  --glass-border: 101 8% 27% / 0.25;
  --glass-glow: 127 55% 32% / 0.06;
  --shadow-glow: 0 0 30px -5px hsl(127 55% 32% / 0.15);
  --shadow-glow-sm: 0 0 15px -3px hsl(127 55% 32% / 0.1);
  --shadow-card: 0 4px 24px -4px hsl(105 12% 50% / 0.1);
}`;
  }

  return `:root {
  --background: 96 26% 4%;
  --foreground: 110 6% 80%;
  --card: 108 19% 5%;
  --card-foreground: 110 6% 80%;
  --popover: 102 10% 20%;
  --popover-foreground: 110 6% 80%;
  --primary: 116 66% 83%;
  --primary-foreground: 96 26% 4%;
  --secondary: 102 10% 20%;
  --secondary-foreground: 110 6% 80%;
  --muted: 105 18% 10%;
  --muted-foreground: 95 6% 45%;
  --accent: 117 60% 75%;
  --accent-foreground: 96 26% 4%;
  --destructive: 0 72% 56%;
  --destructive-foreground: 0 85% 97%;
  --success: 127 55% 32%;
  --success-foreground: 107 4% 90%;
  --warning: 38 92% 50%;
  --warning-foreground: 96 26% 4%;
  --info: 199 89% 48%;
  --info-foreground: 0 0% 100%;
  --border: 102 10% 20%;
  --input: 105 18% 10%;
  --ring: 100 7% 32%;
  --radius: 0.5rem;
  --glass-bg: 96 26% 4% / 0.55;
  --glass-border: 127 55% 32% / 0.2;
  --glass-glow: 118 55% 65% / 0.1;
  --shadow-glow: 0 0 30px -5px hsl(118 55% 65% / 0.25);
  --shadow-glow-sm: 0 0 15px -3px hsl(118 55% 65% / 0.2);
  --shadow-card: 0 4px 24px -4px hsl(96 26% 1% / 0.6);
}`;
}

/**
 * Combines CSS custom properties and base styles for efficient theme updates.
 * Sent via postMessage when theme changes (much smaller than full SDK_CSS).
 */
function getPluginThemeCSS(theme: 'light' | 'dark' = 'dark'): string {
  return extractCSSCustomProperties(theme);
}

/**
 * Build sandboxed HTML content for plugin iframe
 *
 * Security:
 * - CSP restricts script sources to inline only
 * - connect-src limited to Dryade API
 * - No external font CDN (system fonts via SDK base.css)
 * - Plugin bridge provides controlled API surface
 *
 * CSS Architecture:
 * - SDK styles loaded via @layer cascade (layers -> base -> tokens -> components -> utilities -> animations)
 * - Theme vars override SDK token defaults with live host values
 * - Plugin-custom styles go into separate <style> tag (highest @layer priority)
 */
function buildSandboxHtml(
  pluginName: string,
  bundleCode: string,
  styles?: string,
  permissions: PluginUIPermission[] = [],
  theme: 'light' | 'dark' = 'dark',
  locale: string = 'en'
): string {
  // Extract live theme variables from host document
  const themeVarsCSS = extractCSSCustomProperties(theme);

  // Build CSP - restrictive, no external font/style sources needed
  const csp = [
    "default-src 'none'",
    "script-src 'unsafe-inline'",
    "style-src 'unsafe-inline'",
    `connect-src ${window.location.origin}`,
  ].join('; ');

  return `
<!DOCTYPE html>
<html class="${theme}" dir="${locale === 'ar' ? 'rtl' : 'ltr'}">
<head>
  <meta charset="UTF-8">
  <meta http-equiv="Content-Security-Policy" content="${csp}">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="color-scheme" content="light dark">
  <style id="sdk-layers">${SDK_CSS}</style>
  <style id="theme-vars">${themeVarsCSS}</style>
  ${styles ? `<style id="plugin-styles">${styles}</style>` : ''}
</head>
<body>
  <div id="plugin-root"></div>
  <script>
    // Plugin bridge - provides controlled API to plugin code
    window.DryadeBridge = {
      pluginName: '${pluginName}',
      permissions: ${JSON.stringify(permissions)},
      currentTheme: '${theme}',
      currentLocale: '${locale}',

      // Send message to host
      postMessage: function(type, data) {
        window.parent.postMessage({
          source: 'dryade-plugin',
          pluginName: '${pluginName}',
          type: type,
          data: data
        }, '*');
      },

      // Request config from host
      requestConfig: function() {
        this.postMessage('plugin:request_config', null);
      },

      // Update config (requires write_config permission)
      updateConfig: function(config) {
        if (!this.permissions.includes('write_config')) {
          console.warn('Plugin lacks write_config permission');
          return;
        }
        this.postMessage('plugin:update_config', config);
      },

      // API request (requires api_proxy permission)
      apiRequest: function(requestId, method, path, body) {
        if (!this.permissions.includes('api_proxy')) {
          console.warn('Plugin lacks api_proxy permission');
          return;
        }
        this.postMessage('plugin:api_request', {
          requestId: requestId,
          method: method,
          path: path,
          body: body
        });
      },

      // Signal plugin is ready
      ready: function() {
        this.postMessage('plugin:ready', null);
      },

      // Audio API - request host to start audio capture
      requestAudioStart: function(options) {
        if (!this.permissions.includes('audio_capture')) {
          console.warn('Plugin lacks audio_capture permission');
          return;
        }
        this.postMessage('audio:request_start', options || null);
      },

      // Audio API - request host to stop audio capture
      requestAudioStop: function() {
        if (!this.permissions.includes('audio_capture')) {
          console.warn('Plugin lacks audio_capture permission');
          return;
        }
        this.postMessage('audio:request_stop', null);
      },

      // Callback for receiving audio chunks
      // Set by plugin: function(data, sampleRate) { }
      onAudioChunk: null,

      // Callback for receiving audio events (transcript/summary/actions/warnings)
      // Set by plugin: function(event) { }
      onAudioEvent: null,

      // Callback for audio status changes
      // Set by plugin: function(status, error) { }
      onAudioStatus: null,

      // Callback for theme changes
      // Set by plugin: function(theme) { }
      onThemeChange: null,

      // Callback for language/locale changes
      // Set by plugin: function(locale) { }
      onLanguageChange: null,

      // Internal: apply theme to document and optionally update CSS variables
      _applyTheme: function(theme, cssVars) {
        this.currentTheme = theme;
        document.documentElement.classList.remove('light', 'dark');
        document.documentElement.classList.add(theme);

        // Update CSS variables if provided (optimized theme update)
        if (cssVars) {
          var styleEl = document.getElementById('theme-vars');
          if (styleEl) {
            styleEl.textContent = cssVars;
          }
        }

        if (this.onThemeChange) {
          this.onThemeChange(theme);
        }
      }
    };

    // Listen for host messages
    window.addEventListener('message', function(event) {
      if (event.data && event.data.source === 'dryade-host') {
        var msg = event.data;

        // Handle theme changes with optional CSS variable updates
        if (msg.type === 'theme:change') {
          window.DryadeBridge._applyTheme(msg.theme, msg.cssVars);
          return;
        }

        // Handle language/locale changes
        if (msg.type === 'language:change') {
          window.DryadeBridge.currentLocale = msg.locale;
          // Set RTL direction for Arabic
          document.documentElement.dir = msg.locale === 'ar' ? 'rtl' : 'ltr';
          if (window.DryadeBridge.onLanguageChange) {
            window.DryadeBridge.onLanguageChange(msg.locale);
          }
          return;
        }

        // Route audio messages to specific handlers
        if (msg.type === 'audio:chunk' && window.DryadeBridge.onAudioChunk) {
          window.DryadeBridge.onAudioChunk(msg.data, msg.sampleRate);
          return;
        }

        if (msg.type === 'audio:event' && window.DryadeBridge.onAudioEvent) {
          window.DryadeBridge.onAudioEvent(msg.data);
          return;
        }

        if (msg.type === 'audio:status' && window.DryadeBridge.onAudioStatus) {
          window.DryadeBridge.onAudioStatus(msg.status, msg.error);
          return;
        }

        // Route other messages to general handler
        if (window.onDryadeBridgeMessage) {
          window.onDryadeBridgeMessage(msg.type, msg.data);
        }
      }
    });
  </script>
  <script>
    try {
      ${bundleCode}
    } catch (e) {
      window.DryadeBridge.postMessage('plugin:error', { message: e.message });
    }
  </script>
</body>
</html>
`;
}

export function PluginSandbox({
  pluginName,
  bundleCode,
  styles,
  permissions,
  theme = 'dark',
  locale = 'en',
  className = '',
  onReady,
  onError,
}: PluginSandboxProps) {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const initialThemeRef = useRef<'light' | 'dark' | null>(theme);
  const initialLocaleRef = useRef<string | null>(locale);

  // Handle messages from plugin iframe
  const handleMessage = useCallback((event: MessageEvent) => {
    const msg = event.data;
    if (msg?.source !== 'dryade-plugin' || msg?.pluginName !== pluginName) {
      return;
    }

    // Verify this plugin is registered
    if (!PluginRegistry.isVerified(pluginName)) {
      console.warn(`Message from unverified plugin: ${pluginName}`);
      return;
    }

    switch (msg.type) {
      case 'plugin:ready':
        onReady?.();
        break;
      case 'plugin:error':
        onError?.(msg.data?.message || 'Unknown plugin error');
        break;
      // Other message types handled by PluginBridge
    }
  }, [pluginName, onReady, onError]);

  useEffect(() => {
    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, [handleMessage]);

  // Register iframe ref when component mounts
  useEffect(() => {
    if (iframeRef.current) {
      PluginRegistry.markLoaded(pluginName, iframeRef.current);
    }
  }, [pluginName]);

  // Send theme updates to iframe when theme changes (after initial render)
  // Sends only CSS variables for efficient theme updates (not the full SDK_CSS)
  useEffect(() => {
    // Skip initial theme since it's already set in the HTML
    if (theme === initialThemeRef.current) {
      initialThemeRef.current = null; // Clear so future changes are sent
      return;
    }

    const iframe = iframeRef.current;
    if (iframe?.contentWindow) {
      // Extract fresh CSS variables for the new theme
      const cssVars = getPluginThemeCSS(theme);

      iframe.contentWindow.postMessage({
        source: 'dryade-host',
        type: 'theme:change',
        theme,
        cssVars,
      }, '*');
    }
  }, [theme]);

  // Send locale updates to iframe when locale changes (after initial render)
  useEffect(() => {
    // Skip initial locale since it's already set in the HTML
    if (locale === initialLocaleRef.current) {
      initialLocaleRef.current = null; // Clear so future changes are sent
      return;
    }

    const iframe = iframeRef.current;
    if (iframe?.contentWindow) {
      iframe.contentWindow.postMessage({
        source: 'dryade-host',
        type: 'language:change',
        locale,
      }, '*');
    }
  }, [locale]);

  // Build sandbox content (use initial theme to avoid unnecessary reloads)
  const sandboxHtml = buildSandboxHtml(pluginName, bundleCode, styles, permissions, theme, locale);

  return (
    <div className={`relative w-full h-full ${className}`}>
      <iframe
        ref={iframeRef}
        srcDoc={sandboxHtml}
        sandbox="allow-scripts"  // CRITICAL: NO allow-same-origin
        title={`Plugin: ${pluginName}`}
        className="w-full h-full border-0"
      />
      <div
        aria-hidden="true"
        className="absolute inset-0 pointer-events-none"
        style={{
          backgroundImage: "url('/dryade-bg.svg')",
          backgroundRepeat: 'no-repeat',
          backgroundPosition: 'center',
          backgroundSize: '42%',
          opacity: 0.04,
          filter: 'blur(3px)',
        }}
      />
    </div>
  );
}
