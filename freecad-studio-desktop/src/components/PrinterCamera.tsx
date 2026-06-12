import { cameraSnapshotUrl } from "../api";
import { useCrealityCamera } from "../hooks/useCrealityCamera";

export function PrinterCamera({
  printerIp,
  online,
}: {
  printerIp: string | null | undefined;
  online: boolean | undefined;
}) {
  const { videoRef, viewState, statusText, snapshotTs, reconnect } = useCrealityCamera(
    printerIp,
    online,
  );

  if (!online || !printerIp) {
    return (
      <div className="printer-camera-box">
        <p className="printer-camera-placeholder">Connect printer on WiFi to view live feed</p>
      </div>
    );
  }

  const showSnapshot = viewState === "snapshot";
  const pillClass =
    viewState === "live" ? "live" : viewState === "connecting" ? "busy" : viewState === "snapshot" ? "warn" : "off";

  return (
    <div className="printer-camera-wrap">
      <div className="printer-camera-toolbar">
        <span className={`camera-pill camera-pill--${pillClass}`}>{statusText}</span>
        <button type="button" className="btn btn-ghost btn-compact" onClick={reconnect}>
          Reconnect
        </button>
        <button
          type="button"
          className="btn btn-ghost btn-compact"
          onClick={() => window.open(`http://${printerIp}:8000/?action=stream`, "_blank", "noopener")}
        >
          Open on printer
        </button>
      </div>
      <div className="printer-camera-box">
        {showSnapshot ? (
          <img
            className="printer-camera-snapshot"
            src={cameraSnapshotUrl(snapshotTs)}
            alt="Printer camera snapshot"
          />
        ) : (
          <>
            <video
              ref={videoRef}
              className="printer-camera-video"
              autoPlay
              playsInline
              muted
            />
            {viewState === "connecting" && (
              <p className="printer-camera-overlay-msg">{statusText}</p>
            )}
          </>
        )}
      </div>
    </div>
  );
}
