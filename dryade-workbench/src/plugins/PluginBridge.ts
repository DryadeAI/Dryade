// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { PluginRegistry } from './PluginRegistry';
import { pluginsApi } from '@/services/api';
import { fetchWithAuth } from '@/services/apiClient';

// Response type for GET /api/plugins/{name} with api_paths
interface PluginDetailWithApiPaths {
  name: string;
  api_paths?: string[] | null;
}

export type MessageType =
  | 'plugin:ready'
  | 'plugin:request_config'
  | 'plugin:update_config'
  | 'plugin:api_request'
  | 'plugin:error'
  | 'host:config_response'
  | 'host:api_response'
  | 'host:theme_changed'
  | 'host:error'
  // Audio message types
  | 'audio:request_start'
  | 'audio:request_stop'
  | 'audio:chunk'
  | 'audio:event'
  | 'audio:status'
  | 'audio:error';

interface PluginMessage {
  source: 'dryade-plugin' | 'dryade-host';
  type: MessageType;
  pluginName: string;
  requestId?: string;
  data?: unknown;
}

interface PendingRequest {
  resolve: (data: unknown) => void;
  reject: (error: Error) => void;
  timeout: ReturnType<typeof setTimeout>;
}

// Audio-specific message interfaces
export interface AudioChunkMessage {
  source: 'dryade-host';
  type: 'audio:chunk';
  pluginName: string;
  data: ArrayBuffer;  // Transferred, not cloned
  sampleRate: number;
  channelCount: number;
}

export interface AudioStatusMessage {
  source: 'dryade-host';
  type: 'audio:status';
  pluginName: string;
  status: 'started' | 'stopped' | 'error';
  error?: string;
}

export interface AudioEventMessage {
  source: 'dryade-host';
  type: 'audio:event';
  pluginName: string;
  data: unknown;
}

// Audio request callback interface
interface AudioStartOptions {
  summarization?: boolean;
  systemAudio?: boolean;
}

interface AudioRequestCallbacks {
  onStart?: (options?: AudioStartOptions) => void;
  onStop?: () => void;
}

class PluginBridgeClass {
  private pendingRequests = new Map<string, PendingRequest>();
  private initialized = false;
  private refCount = 0; // Reference count for multiple consumers
  private audioRequestCallbacks = new Map<string, AudioRequestCallbacks>();
  private apiPathCache = new Map<string, string[]>(); // Cache for plugin API paths

  /**
   * Initialize bridge - supports multiple consumers via ref counting
   */
  initialize(): void {
    this.refCount++;
    if (this.initialized) return;
    window.addEventListener('message', this.handleMessage);
    this.initialized = true;
  }

  /**
   * Cleanup bridge - only destroys when all consumers release
   */
  destroy(): void {
    this.refCount = Math.max(0, this.refCount - 1);
    if (this.refCount > 0) return; // Other consumers still need it

    window.removeEventListener('message', this.handleMessage);
    this.pendingRequests.forEach(req => {
      clearTimeout(req.timeout);
      req.reject(new Error('Bridge destroyed'));
    });
    this.pendingRequests.clear();
    this.initialized = false;
  }

  /**
   * Handle incoming messages from plugins
   */
  private handleMessage = async (event: MessageEvent) => {
    const msg = event.data as PluginMessage;

    // Validate message format
    if (msg.source !== 'dryade-plugin') return;
    if (!msg.type || !msg.pluginName) return;

    // CRITICAL: Verify plugin is registered and verified
    if (!PluginRegistry.isVerified(msg.pluginName)) {
      console.warn(`Rejecting message from unverified plugin: ${msg.pluginName}`);
      return;
    }

    // Route to appropriate handler
    switch (msg.type) {
      case 'plugin:ready':
        console.debug(`Plugin ready: ${msg.pluginName}`);
        break;

      case 'plugin:request_config':
        await this.handleConfigRequest(msg);
        break;

      case 'plugin:update_config':
        await this.handleConfigUpdate(msg);
        break;

      case 'plugin:api_request':
        await this.handleApiRequest(msg);
        break;

      case 'plugin:error':
        console.error(`Plugin error (${msg.pluginName}):`, msg.data);
        PluginRegistry.markError(msg.pluginName, String(msg.data));
        break;

      case 'audio:request_start':
        this.handleAudioRequestStart(msg.pluginName, msg.data as Record<string, unknown> | null);
        break;

      case 'audio:request_stop':
        this.handleAudioRequestStop(msg.pluginName);
        break;
    }
  };

  /**
   * Handle audio start request from plugin
   */
  private handleAudioRequestStart(pluginName: string, data?: Record<string, unknown> | null): void {
    console.log(`[PluginBridge] Audio start request from: ${pluginName}`);
    const callbacks = this.audioRequestCallbacks.get(pluginName);
    if (callbacks?.onStart) {
      console.log(`[PluginBridge] Calling onStart callback for: ${pluginName}`);
      const options: AudioStartOptions | undefined = data
        ? { summarization: data.summarization !== false, systemAudio: data.systemAudio === true }
        : undefined;
      callbacks.onStart(options);
    } else {
      console.warn(`No audio start handler registered for plugin: ${pluginName}`);
    }
  }

  /**
   * Handle audio stop request from plugin
   */
  private handleAudioRequestStop(pluginName: string): void {
    const callbacks = this.audioRequestCallbacks.get(pluginName);
    if (callbacks?.onStop) {
      callbacks.onStop();
    } else {
      console.warn(`No audio stop handler registered for plugin: ${pluginName}`);
    }
  }

  /**
   * Handle config request from plugin
   */
  private async handleConfigRequest(msg: PluginMessage): Promise<void> {
    try {
      const config = await pluginsApi.getPluginConfig(msg.pluginName);
      this.sendToPlugin(msg.pluginName, 'host:config_response', { config });
    } catch (error) {
      this.sendToPlugin(msg.pluginName, 'host:error', {
        type: 'config_fetch_failed',
        message: error instanceof Error ? error.message : 'Unknown error',
      });
    }
  }

  /**
   * Handle config update from plugin
   */
  private async handleConfigUpdate(msg: PluginMessage): Promise<void> {
    // Check permission
    const plugin = PluginRegistry.get(msg.pluginName);
    if (!plugin?.uiManifest?.permissions.includes('write_config')) {
      this.sendToPlugin(msg.pluginName, 'host:error', {
        type: 'permission_denied',
        message: 'Plugin lacks write_config permission',
      });
      return;
    }

    try {
      await pluginsApi.updatePluginConfig(msg.pluginName, msg.data as Record<string, unknown>);
      this.sendToPlugin(msg.pluginName, 'host:config_response', {
        success: true,
        config: msg.data,
      });
    } catch (error) {
      this.sendToPlugin(msg.pluginName, 'host:error', {
        type: 'config_update_failed',
        message: error instanceof Error ? error.message : 'Unknown error',
      });
    }
  }

  /**
   * Fetch plugin API paths from backend, with caching
   */
  private async getPluginApiPaths(pluginName: string): Promise<string[]> {
    // Check cache first
    const cached = this.apiPathCache.get(pluginName);
    if (cached !== undefined) {
      return cached;
    }

    try {
      // Fetch plugin details from backend to get api_paths
      const response = await fetchWithAuth<PluginDetailWithApiPaths>(`/plugins/${pluginName}`);
      const apiPaths = response.api_paths || [];
      this.apiPathCache.set(pluginName, apiPaths);
      return apiPaths;
    } catch (error) {
      console.warn(`Failed to fetch API paths for plugin ${pluginName}:`, error);
      // Cache empty array to avoid repeated failures
      this.apiPathCache.set(pluginName, []);
      return [];
    }
  }

  /**
   * Clear API path cache for a plugin (call on plugin reload)
   */
  clearApiPathCache(pluginName?: string): void {
    if (pluginName) {
      this.apiPathCache.delete(pluginName);
    } else {
      this.apiPathCache.clear();
    }
  }

  /**
   * Handle API proxy request from plugin
   *
   * Allows plugins to make authenticated API calls through the host.
   * Only allows requests to paths declared in the plugin's manifest api_paths,
   * the plugin's own namespace, or common endpoints like /license.
   */
  private async handleApiRequest(msg: PluginMessage): Promise<void> {
    const { requestId, method, path, body } = msg.data as {
      requestId: string;
      method: string;
      path: string;
      body?: unknown;
    };

    // Check api_proxy permission
    const plugin = PluginRegistry.get(msg.pluginName);
    if (!plugin?.uiManifest?.permissions.includes('api_proxy')) {
      this.sendToPlugin(msg.pluginName, 'host:api_response', {
        requestId,
        success: false,
        error: 'Plugin lacks api_proxy permission',
      });
      return;
    }

    // Fetch plugin's declared API paths from manifest (cached)
    const pluginApiPaths = await this.getPluginApiPaths(msg.pluginName);

    // Security: Only allow requests to plugin's own endpoints or declared api_paths
    const allowedPrefixes = [
      `/${msg.pluginName}`,      // Plugin's own endpoints
      '/license',                // License status (common)
      ...pluginApiPaths,         // Plugin-declared API paths from manifest
    ];

    const normalizedPath = path.startsWith('/') ? path : `/${path}`;
    const isAllowed = allowedPrefixes.some(prefix => normalizedPath.startsWith(prefix));

    if (!isAllowed) {
      this.sendToPlugin(msg.pluginName, 'host:api_response', {
        requestId,
        success: false,
        error: `API path not allowed for plugin: ${path}`,
      });
      return;
    }

    try {
      const options: RequestInit = { method };
      if (body && (method === 'POST' || method === 'PUT' || method === 'PATCH')) {
        options.body = JSON.stringify(body);
        options.headers = { 'Content-Type': 'application/json' };
      }

      // Use raw fetch for binary response support (fetchWithAuth only handles JSON/text)
      const url = `/api${normalizedPath}`;
      const headers = new Headers(options.headers);

      // Add auth header
      const tokensStr = localStorage.getItem('auth_tokens');
      if (tokensStr) {
        try {
          const tokens = JSON.parse(tokensStr);
          if (tokens?.access_token) {
            headers.set('Authorization', `Bearer ${tokens.access_token}`);
          }
        } catch { /* ignore parse errors */ }
      }

      const response = await fetch(url, { ...options, headers });

      if (!response.ok) {
        const errBody = await response.json().catch(() => ({ detail: `Request failed: ${response.status}` }));
        throw new Error(typeof errBody.detail === 'string' ? errBody.detail : JSON.stringify(errBody.detail));
      }

      const contentType = response.headers.get('content-type') || '';

      if (contentType.includes('application/json')) {
        const result = await response.json();
        this.sendToPlugin(msg.pluginName, 'host:api_response', {
          requestId,
          success: true,
          result,
        });
      } else {
        // Binary/text response - convert to data URL for cross-iframe transfer
        const blob = await response.blob();
        const reader = new FileReader();
        const dataUrl = await new Promise<string>((resolve, reject) => {
          reader.onload = () => resolve(reader.result as string);
          reader.onerror = () => reject(new Error('Failed to read response'));
          reader.readAsDataURL(blob);
        });
        this.sendToPlugin(msg.pluginName, 'host:api_response', {
          requestId,
          success: true,
          result: { _binary: true, dataUrl, contentType },
        });
      }
    } catch (error) {
      this.sendToPlugin(msg.pluginName, 'host:api_response', {
        requestId,
        success: false,
        error: error instanceof Error ? error.message : 'API request failed',
      });
    }
  }

  /**
   * Send message to specific plugin
   */
  sendToPlugin(pluginName: string, type: MessageType, data?: unknown): void {
    const iframe = PluginRegistry.getIframe(pluginName);
    if (!iframe?.contentWindow) {
      console.warn(`Cannot send message to plugin ${pluginName}: iframe not found`);
      return;
    }

    iframe.contentWindow.postMessage(
      {
        source: 'dryade-host',
        type,
        pluginName,
        data,
      },
      '*' // Must use * for sandboxed iframes
    );
  }

  /**
   * Broadcast message to all loaded plugins
   */
  broadcast(type: MessageType, data?: unknown): void {
    for (const plugin of PluginRegistry.listUIPlugins()) {
      if (plugin.state === 'loaded') {
        this.sendToPlugin(plugin.name, type, data);
      }
    }
  }

  /**
   * Notify plugins of theme change
   */
  notifyThemeChange(theme: 'light' | 'dark'): void {
    this.broadcast('host:theme_changed', { theme });
  }

  /**
   * Send audio chunk to plugin with transferable ArrayBuffer (zero-copy)
   */
  sendAudioChunk(pluginName: string, chunk: ArrayBuffer, sampleRate: number): void {
    const iframe = PluginRegistry.getIframe(pluginName);
    if (!iframe?.contentWindow) {
      console.warn(`Cannot send audio to plugin ${pluginName}: iframe not found`);
      return;
    }

    iframe.contentWindow.postMessage(
      {
        source: 'dryade-host',
        type: 'audio:chunk',
        pluginName,
        data: chunk,
        sampleRate,
        channelCount: 1,
      } as AudioChunkMessage,
      '*',
      [chunk]  // Transferable - zero copy
    );
  }

  /**
   * Send audio status to plugin
   */
  sendAudioStatus(pluginName: string, status: 'started' | 'stopped' | 'error', error?: string): void {
    const iframe = PluginRegistry.getIframe(pluginName);
    if (!iframe?.contentWindow) {
      console.warn(`Cannot send audio status to plugin ${pluginName}: iframe not found`);
      return;
    }

    iframe.contentWindow.postMessage(
      {
        source: 'dryade-host',
        type: 'audio:status',
        pluginName,
        status,
        error,
      } as AudioStatusMessage,
      '*'
    );
  }

  /**
   * Send an audio intelligence event to plugin (transcript/summary/actions/warnings)
   */
  sendAudioEvent(pluginName: string, event: unknown): void {
    const iframe = PluginRegistry.getIframe(pluginName);
    if (!iframe?.contentWindow) {
      console.warn(`Cannot send audio event to plugin ${pluginName}: iframe not found`);
      return;
    }

    iframe.contentWindow.postMessage(
      {
        source: 'dryade-host',
        type: 'audio:event',
        pluginName,
        data: event,
      } as AudioEventMessage,
      '*'
    );
  }

  /**
   * Register callbacks for audio requests from a specific plugin
   * Returns cleanup function to unregister callbacks
   */
  onAudioRequest(pluginName: string, callbacks: AudioRequestCallbacks): () => void {
    this.audioRequestCallbacks.set(pluginName, callbacks);
    return () => {
      this.audioRequestCallbacks.delete(pluginName);
    };
  }
}

// Singleton export
export const PluginBridge = new PluginBridgeClass();
