"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import Hls from "hls.js";

interface HlsPlayerState {
  isPlaying: boolean;
  isBuffering: boolean;
  currentLevel: number;
  levels: Array<{ height: number; bitrate: number }>;
  bandwidth: number;
  error: string | null;
}

interface UseHlsPlayerOptions {
  streamUrl: string;
  autoplay?: boolean;
  muted?: boolean;
}

export function useHlsPlayer(
  videoRef: React.RefObject<HTMLVideoElement | null>,
  options: UseHlsPlayerOptions
) {
  const hlsRef = useRef<Hls | null>(null);
  const [state, setState] = useState<HlsPlayerState>({
    isPlaying: false,
    isBuffering: false,
    currentLevel: -1,
    levels: [],
    bandwidth: 0,
    error: null,
  });

  const destroy = useCallback(() => {
    if (hlsRef.current) {
      hlsRef.current.destroy();
      hlsRef.current = null;
    }
  }, []);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !options.streamUrl) return;

    // Reset error state
    setState((prev) => ({ ...prev, error: null }));

    const isHls = options.streamUrl.endsWith(".m3u8") || options.streamUrl.includes(".m3u8") || options.streamUrl.includes("manifest");
    if (!isHls) {
      video.src = options.streamUrl;
      if (options.autoplay !== false) {
        video.play().catch(() => {});
      }
      return () => {
        video.src = "";
      };
    }

    if (Hls.isSupported()) {
      const hls = new Hls({
        enableWorker: true,
        lowLatencyMode: true,
        backBufferLength: 30,
        maxBufferLength: 15,
        maxMaxBufferLength: 30,
        startLevel: -1, // Auto ABR
      });

      hlsRef.current = hls;
      hls.loadSource(options.streamUrl);
      hls.attachMedia(video);

      hls.on(Hls.Events.MANIFEST_PARSED, (_event, data) => {
        setState((prev) => ({
          ...prev,
          levels: data.levels.map((l) => ({ height: l.height, bitrate: l.bitrate })),
        }));
        if (options.autoplay !== false) {
          video.play().catch(() => {
            // Autoplay blocked — user needs to interact
          });
        }
      });

      hls.on(Hls.Events.LEVEL_SWITCHED, (_event, data) => {
        setState((prev) => ({ ...prev, currentLevel: data.level }));
      });

      hls.on(Hls.Events.FRAG_BUFFERED, (_event, data) => {
        const stats = data.frag.stats;
        if (stats.loaded && stats.loading.end && stats.loading.start) {
          const durationMs = stats.loading.end - stats.loading.start;
          const bw = durationMs > 0 ? Math.round((stats.loaded * 8) / durationMs) : 0;
          setState((prev) => ({ ...prev, bandwidth: bw }));
        }
      });

      hls.on(Hls.Events.ERROR, (_event, data) => {
        if (data.fatal) {
          switch (data.type) {
            case Hls.ErrorTypes.NETWORK_ERROR:
              setState((prev) => ({ ...prev, error: "Network error — retrying..." }));
              hls.startLoad();
              break;
            case Hls.ErrorTypes.MEDIA_ERROR:
              setState((prev) => ({ ...prev, error: "Media error — recovering..." }));
              hls.recoverMediaError();
              break;
            default:
              setState((prev) => ({ ...prev, error: "Fatal playback error" }));
              destroy();
              break;
          }
        }
      });

      return () => {
        destroy();
      };
    } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
      // Native HLS support (Safari)
      video.src = options.streamUrl;
      if (options.autoplay !== false) {
        video.play().catch(() => {});
      }
    } else {
      setState((prev) => ({ ...prev, error: "HLS not supported in this browser" }));
    }
  }, [options.streamUrl, options.autoplay, videoRef, destroy]);

  // Track play/pause and buffering
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    const onPlay = () => setState((p) => ({ ...p, isPlaying: true }));
    const onPause = () => setState((p) => ({ ...p, isPlaying: false }));
    const onWaiting = () => setState((p) => ({ ...p, isBuffering: true }));
    const onPlaying = () => setState((p) => ({ ...p, isBuffering: false }));

    video.addEventListener("play", onPlay);
    video.addEventListener("pause", onPause);
    video.addEventListener("waiting", onWaiting);
    video.addEventListener("playing", onPlaying);

    return () => {
      video.removeEventListener("play", onPlay);
      video.removeEventListener("pause", onPause);
      video.removeEventListener("waiting", onWaiting);
      video.removeEventListener("playing", onPlaying);
    };
  }, [videoRef]);

  const togglePlay = useCallback(() => {
    const video = videoRef.current;
    if (!video) return;
    if (video.paused) {
      video.play().catch(() => {});
    } else {
      video.pause();
    }
  }, [videoRef]);

  const togglePiP = useCallback(async () => {
    const video = videoRef.current;
    if (!video) return;
    try {
      if (document.pictureInPictureElement) {
        await document.exitPictureInPicture();
      } else {
        await video.requestPictureInPicture();
      }
    } catch {
      // PiP not supported or blocked
    }
  }, [videoRef]);

  const setQuality = useCallback((levelIndex: number) => {
    if (hlsRef.current) {
      hlsRef.current.currentLevel = levelIndex;
    }
  }, []);

  return {
    ...state,
    togglePlay,
    togglePiP,
    setQuality,
  };
}
