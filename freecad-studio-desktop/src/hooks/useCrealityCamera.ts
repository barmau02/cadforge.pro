import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import { connectCrealityCamera } from "../lib/crealityWebRtc";

export type CameraViewState = "off" | "connecting" | "live" | "snapshot";

const CONNECT_TIMEOUT_MS = 20000;
const SNAPSHOT_INTERVAL_MS = 2500;

export function useCrealityCamera(printerIp: string | null | undefined, online: boolean | undefined) {
  const [viewState, setViewState] = useState<CameraViewState>("off");
  const [statusText, setStatusText] = useState("Offline");
  const [snapshotTs, setSnapshotTs] = useState(0);
  const [reloadKey, setReloadKey] = useState(0);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const connectionRef = useRef<{ stop: () => void } | null>(null);

  const reconnect = useCallback(() => setReloadKey((k) => k + 1), []);

  useEffect(() => {
    if (!online || !printerIp) {
      connectionRef.current?.stop();
      connectionRef.current = null;
      setViewState("off");
      setStatusText("Offline");
      return;
    }

    let cancelled = false;
    let failTimer: number | undefined;
    let snapshotTimer: number | undefined;

    const startSnapshot = (reason?: string) => {
      if (cancelled) return;
      setViewState("snapshot");
      setStatusText(reason ? `Snapshot — ${reason}` : "Snapshot");
      setSnapshotTs(Date.now());
      if (snapshotTimer) window.clearInterval(snapshotTimer);
      snapshotTimer = window.setInterval(() => setSnapshotTs(Date.now()), SNAPSHOT_INTERVAL_MS);
    };

    const markLive = () => {
      if (cancelled) return;
      if (failTimer) window.clearTimeout(failTimer);
      if (snapshotTimer) {
        window.clearInterval(snapshotTimer);
        snapshotTimer = undefined;
      }
      setViewState("live");
      setStatusText("Live");
    };

    const connect = async () => {
      setViewState("connecting");
      setStatusText("Connecting…");
      connectionRef.current?.stop();
      connectionRef.current = null;

      const video = videoRef.current;
      if (video) video.srcObject = null;

      failTimer = window.setTimeout(() => {
        if (!cancelled) startSnapshot("live stream timed out");
      }, CONNECT_TIMEOUT_MS);

      try {
        const conn = await connectCrealityCamera(
          printerIp,
          async (offerSdp) => {
            const payload = btoa(JSON.stringify({ type: "offer", sdp: offerSdp }));
            const res = await api.exchangeCameraWebRtc(payload);
            return res.answer;
          },
          (status) => {
            if (!cancelled) setStatusText(status);
          },
        );

        if (cancelled) {
          conn.stop();
          return;
        }

        connectionRef.current = conn;

        if (video) {
          video.srcObject = conn.stream;
          void video.play().catch(() => undefined);
        }

        conn.stream.onaddtrack = () => markLive();
        if (conn.stream.getVideoTracks().length > 0) markLive();

        const priorIceHandler = conn.pc.oniceconnectionstatechange;
        conn.pc.oniceconnectionstatechange = (ev) => {
          priorIceHandler?.call(conn.pc, ev);
          const state = conn.pc.iceConnectionState;
          if (state === "connected" || state === "completed") markLive();
          if (state === "failed" && !cancelled) startSnapshot("ICE failed");
        };
      } catch (err) {
        if (!cancelled) {
          startSnapshot((err as Error).message || "camera failed");
        }
      }
    };

    void connect();

    return () => {
      cancelled = true;
      if (failTimer) window.clearTimeout(failTimer);
      if (snapshotTimer) window.clearInterval(snapshotTimer);
      connectionRef.current?.stop();
      connectionRef.current = null;
      const video = videoRef.current;
      if (video) video.srcObject = null;
    };
  }, [online, printerIp, reloadKey]);

  return {
    videoRef,
    viewState,
    statusText,
    snapshotTs,
    reconnect,
  };
}
