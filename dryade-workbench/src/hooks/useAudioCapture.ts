// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState, useCallback, useRef, useEffect } from 'react';
import { PluginBridge } from '@/plugins/PluginBridge';
import { audioMeetingsApi } from '@/services/api';

interface UseAudioCaptureOptions {
  pluginName: string;
  sampleRate?: number;  // Default 16000 for backend compatibility
  onError?: (error: string) => void;
}

interface UseAudioCaptureResult {
  isCapturing: boolean;
  systemAudioActive: boolean;
  startCapture: () => Promise<void>;
  stopCapture: () => void;
  error: string | null;
}

/**
 * Hook for host-side audio capture to transfer to plugin iframes.
 *
 * Browser sandboxed iframes cannot use getUserMedia without allow-same-origin,
 * which would break the security model. Instead, the host application captures
 * audio and transfers data to plugins via postMessage with transferable ArrayBuffers.
 *
 * Key features:
 * - 16kHz mono sample rate (matches backend expectation)
 * - Float32 to Int16 PCM conversion
 * - Transferable ArrayBuffer for zero-copy postMessage
 * - Automatic cleanup on unmount
 * - Listens for plugin requests via PluginBridge singleton
 */
export function useAudioCapture({
  pluginName,
  sampleRate = 16000,
  onError,
}: UseAudioCaptureOptions): UseAudioCaptureResult {
  const [isCapturing, setIsCapturing] = useState(false);
  const [systemAudioActive, setSystemAudioActive] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const systemStreamRef = useRef<MediaStream | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const meetingIdRef = useRef<number | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const getAccessToken = () => {
    try {
      const raw = localStorage.getItem('auth_tokens');
      if (!raw) return null;
      const parsed = JSON.parse(raw) as { access_token?: string };
      return parsed.access_token || null;
    } catch {
      return null;
    }
  };

  const openBackendStream = useCallback(async (summarization = true) => {
    // Create a meeting (server-first, per-user)
    const meeting = await audioMeetingsApi.createMeeting();
    meetingIdRef.current = meeting.id;
    PluginBridge.sendAudioEvent(pluginName, { type: 'meeting_started', meeting_id: meeting.id });

    const token = getAccessToken();
    if (!token) {
      throw new Error('Missing auth token');
    }

    const wsProto = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const wsUrl = `${wsProto}://${window.location.host}/api/audio/ws/${meeting.id}?token=${encodeURIComponent(token)}&sample_rate=${sampleRate}&summarization=${summarization ? 'true' : 'false'}`;

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    // Wait for WebSocket to actually open before resolving
    await new Promise<void>((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error('Backend WS open timeout')), 15000);

      ws.onopen = () => {
        clearTimeout(timeout);
        console.log(`[AudioCapture] Backend WS connected (meeting ${meeting.id})`);
        resolve();
      };

      ws.onerror = () => {
        clearTimeout(timeout);
        reject(new Error('Backend WS connection error'));
      };
    });

    ws.onmessage = (evt) => {
      try {
        const parsed = JSON.parse(String(evt.data));
        PluginBridge.sendAudioEvent(pluginName, parsed);
      } catch {
        // Ignore non-JSON frames
      }
    };

    ws.onerror = () => {
      PluginBridge.sendAudioEvent(pluginName, {
        type: 'warning',
        code: 'backend_ws_error',
        message: 'Backend audio stream encountered an error.',
      });
    };

    ws.onclose = () => {
      console.log(`[AudioCapture] Backend WS closed (meeting ${meeting.id})`);
    };
  }, [pluginName, sampleRate]);

  const startingRef = useRef(false);

  const startCapture = useCallback(async (options?: { summarization?: boolean; systemAudio?: boolean }) => {
    // Prevent double-start (e.g., rapid listener re-registration or multiple clicks)
    if (startingRef.current || wsRef.current) return;
    startingRef.current = true;

    const summarization = options?.summarization !== false;

    try {
      // Run mic permission + backend stream setup in parallel (they're independent)
      const [stream] = await Promise.all([
        navigator.mediaDevices.getUserMedia({
          audio: {
            channelCount: 1,
            echoCancellation: true,
            noiseSuppression: true,
          },
        }),
        openBackendStream(summarization),
      ]);
      streamRef.current = stream;

      // Attempt system audio capture via getDisplayMedia if requested
      let systemStream: MediaStream | null = null;
      const wantSystemAudio = options?.systemAudio === true;

      if (wantSystemAudio) {
        try {
          systemStream = await navigator.mediaDevices.getDisplayMedia({
            video: true,  // MANDATORY -- getDisplayMedia throws TypeError with video:false
            audio: {
              // @ts-expect-error -- systemAudio is Chrome 119+ only, not in TS stdlib yet
              systemAudio: 'include',
              suppressLocalAudioPlayback: false,
              echoCancellation: true,
              noiseSuppression: true,
            },
            // @ts-expect-error -- selfBrowserSurface is Chrome 107+, not in TS stdlib yet
            selfBrowserSurface: 'exclude',
          });

          // Immediately discard the unwanted video track
          systemStream.getVideoTracks().forEach(t => t.stop());

          // Validate that user actually shared audio
          if (systemStream.getAudioTracks().length === 0) {
            console.warn('[AudioCapture] User did not share audio. Falling back to mic-only.');
            PluginBridge.sendAudioEvent(pluginName, {
              type: 'system_audio_no_audio',
              message: 'No audio was detected. Try sharing again and check "Share tab audio" in the dialog.',
            });
            systemStream = null;
          }
        } catch (displayErr) {
          // User cancelled picker or browser doesn't support it -- graceful fallback
          console.warn('[AudioCapture] System audio unavailable:', displayErr);
          if (displayErr instanceof DOMException && displayErr.name === 'NotAllowedError') {
            PluginBridge.sendAudioEvent(pluginName, {
              type: 'system_audio_denied',
              message: 'System audio sharing was cancelled. Recording with microphone only.',
            });
          } else {
            PluginBridge.sendAudioEvent(pluginName, {
              type: 'system_audio_unavailable',
              message: 'System audio capture is not available on this browser.',
            });
          }
          systemStream = null;
        }
      }

      // Create audio context at hardware's native sample rate (required for MediaStreamSource)
      const audioContext = new AudioContext();
      audioContextRef.current = audioContext;
      const nativeSampleRate = audioContext.sampleRate;

      // Build source node: mix mic + system audio when available, otherwise mic-only
      let sourceNode: AudioNode;

      if (systemStream && systemStream.getAudioTracks().length > 0) {
        // Mix mic + system audio via AudioContext destination node
        const dest = audioContext.createMediaStreamDestination();
        audioContext.createMediaStreamSource(stream).connect(dest);
        audioContext.createMediaStreamSource(systemStream).connect(dest);
        sourceNode = audioContext.createMediaStreamSource(dest.stream);

        // Listen for system track ending (user clicks "Stop sharing" in browser bar)
        const systemTrack = systemStream.getAudioTracks()[0];
        systemTrack.addEventListener('ended', () => {
          console.log('[AudioCapture] System audio track ended (user stopped sharing)');
          PluginBridge.sendAudioEvent(pluginName, {
            type: 'system_audio_stopped',
          });
          systemStreamRef.current = null;
          setSystemAudioActive(false);
        });
        systemStreamRef.current = systemStream;
        setSystemAudioActive(true);
      } else {
        // Mic only (existing behavior, unchanged)
        sourceNode = audioContext.createMediaStreamSource(stream);
      }

      // Use ScriptProcessorNode for PCM access
      // Note: Deprecated but AudioWorklet requires more setup and CORS considerations
      const processor = audioContext.createScriptProcessor(4096, 1, 1);
      processorRef.current = processor;

      // Calculate resampling ratio (e.g., 48000 -> 16000 = 3:1)
      const resampleRatio = nativeSampleRate / sampleRate;

      processor.onaudioprocess = (e) => {
        const inputData = e.inputBuffer.getChannelData(0);

        // Downsample if needed (simple linear interpolation)
        let outputData: Float32Array;
        if (resampleRatio > 1) {
          const outputLength = Math.floor(inputData.length / resampleRatio);
          outputData = new Float32Array(outputLength);
          for (let i = 0; i < outputLength; i++) {
            const srcIndex = i * resampleRatio;
            const srcIndexFloor = Math.floor(srcIndex);
            const srcIndexCeil = Math.min(srcIndexFloor + 1, inputData.length - 1);
            const t = srcIndex - srcIndexFloor;
            // Linear interpolation between samples
            outputData[i] = inputData[srcIndexFloor] * (1 - t) + inputData[srcIndexCeil] * t;
          }
        } else {
          outputData = inputData;
        }

        // Convert Float32 (-1 to 1) to Int16 for backend
        const int16Data = new Int16Array(outputData.length);
        for (let i = 0; i < outputData.length; i++) {
          const s = Math.max(-1, Math.min(1, outputData[i]));
          int16Data[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
        }

        // Stream to backend WS (guaranteed open at this point)
        const ws = wsRef.current;
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(int16Data.buffer);
        }

        // Transfer to plugin iframe (keep backward compatibility)
        // Note: postMessage transfers the buffer; send a copy.
        PluginBridge.sendAudioChunk(pluginName, int16Data.buffer.slice(0), sampleRate);
      };

      sourceNode.connect(processor);
      processor.connect(audioContext.destination);

      setIsCapturing(true);
      setError(null);
      console.log(`[AudioCapture] Started for ${pluginName}, native rate: ${nativeSampleRate}, target: ${sampleRate}`);
      PluginBridge.sendAudioStatus(pluginName, 'started');

      // Notify plugin of active audio sources
      PluginBridge.sendAudioEvent(pluginName, {
        type: 'audio_sources',
        sources: systemStream ? ['mic', 'system'] : ['mic'],
      });

    } catch (err) {
      // Clean up any partial state from the failed attempt
      startingRef.current = false;
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(track => track.stop());
        streamRef.current = null;
      }
      if (systemStreamRef.current) {
        systemStreamRef.current.getTracks().forEach(track => track.stop());
        systemStreamRef.current = null;
      }
      meetingIdRef.current = null;

      const errorMsg = err instanceof Error ? err.message : 'Failed to start audio capture';
      setError(errorMsg);
      onError?.(errorMsg);
      PluginBridge.sendAudioStatus(pluginName, 'error', errorMsg);
    }
  }, [pluginName, sampleRate, onError, openBackendStream]);

  const stopCapture = useCallback(() => {
    startingRef.current = false;

    // Stop processor
    if (processorRef.current) {
      processorRef.current.disconnect();
      processorRef.current = null;
    }

    // Close audio context
    if (audioContextRef.current) {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }

    // Stop media stream
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop());
      streamRef.current = null;
    }

    // Stop system audio stream
    if (systemStreamRef.current) {
      systemStreamRef.current.getTracks().forEach(track => track.stop());
      systemStreamRef.current = null;
    }

    // Close backend WS
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    if (meetingIdRef.current != null) {
      PluginBridge.sendAudioEvent(pluginName, { type: 'meeting_stopped', meeting_id: meetingIdRef.current });
      meetingIdRef.current = null;
    }

    setIsCapturing(false);
    setSystemAudioActive(false);
    PluginBridge.sendAudioStatus(pluginName, 'stopped');
  }, [pluginName]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (isCapturing) {
        stopCapture();
      }
    };
  }, [isCapturing, stopCapture]);

  // Listen for plugin audio requests
  useEffect(() => {
    return PluginBridge.onAudioRequest(pluginName, {
      onStart: (opts) => startCapture(opts),
      onStop: stopCapture,
    });
  }, [pluginName, startCapture, stopCapture]);

  return { isCapturing, systemAudioActive, startCapture, stopCapture, error };
}
