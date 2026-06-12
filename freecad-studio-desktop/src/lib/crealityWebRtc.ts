/** Repair malformed duplicate-codec SDP from Creality K-series cameras. */
export function fixCrealitySdp(sdp: string, printerIp: string): string {
  const lines = sdp.replace(/\r\n/g, "\n").split("\n").filter(Boolean);
  const out: string[] = [];
  let inVideo = false;
  let videoPt: string | null = null;
  let seenRtpmap = false;
  let fmtpLines: string[] = [];
  let fmtpInsertAt = 0;

  const flushFmtp = () => {
    if (!fmtpLines.length) return;
    const preferred =
      fmtpLines.find((line) => line.includes("packetization-mode")) || fmtpLines[0];
    out.splice(fmtpInsertAt, 0, preferred);
    fmtpLines = [];
  };

  for (const line of lines) {
    if (line.startsWith("m=video")) {
      flushFmtp();
      inVideo = true;
      seenRtpmap = false;
      fmtpLines = [];
      const parts = line.split(" ");
      const payloadTypes = parts.length > 3 ? parts.slice(3) : [];
      if (payloadTypes.length >= 2 && payloadTypes[0] !== payloadTypes[1]) {
        videoPt = payloadTypes[1];
      } else if (payloadTypes.length) {
        videoPt = payloadTypes[0];
      } else {
        videoPt = null;
      }
      const next = videoPt ? parts.slice(0, 3).concat([videoPt]) : parts;
      out.push(next.join(" "));
      fmtpInsertAt = out.length;
      continue;
    }

    if (line.startsWith("m=")) {
      flushFmtp();
      inVideo = false;
      videoPt = null;
    }

    if (inVideo && videoPt) {
      if (line.startsWith("a=rtpmap:")) {
        const pt = line.split(":", 2)[1].split(" ")[0];
        if (pt !== videoPt || seenRtpmap) continue;
        seenRtpmap = true;
      } else if (line.startsWith("a=fmtp:")) {
        if (line.includes("x-google")) continue;
        const pt = line.split(":", 2)[1].split(" ")[0];
        if (pt !== videoPt) continue;
        fmtpLines.push(line);
        continue;
      }
    }

    if (line === "c=IN IP4 0.0.0.0") {
      out.push(`c=IN IP4 ${printerIp}`);
      continue;
    }

    out.push(line);
  }

  flushFmtp();
  let text = out.join("\r\n");
  if (!text.endsWith("\r\n")) text += "\r\n";
  return text;
}

export function parseCrealityAnswer(raw: string, printerIp: string): RTCSessionDescriptionInit {
  const text = (raw || "").trim();
  if (!text) throw new Error("Empty answer from printer");
  let answer: { type?: string; sdp?: string };
  try {
    answer = JSON.parse(atob(text));
  } catch {
    answer = JSON.parse(text);
  }
  if (answer.type !== "answer" || !answer.sdp) {
    throw new Error("Printer returned invalid WebRTC answer");
  }
  return {
    type: "answer",
    sdp: fixCrealitySdp(answer.sdp, printerIp),
  };
}

export type CrealityCameraConnection = {
  pc: RTCPeerConnection;
  stream: MediaStream;
  stop: () => void;
};

export async function connectCrealityCamera(
  printerIp: string,
  exchangeOffer: (offerSdp: string) => Promise<string>,
  onStatus?: (status: string) => void,
): Promise<CrealityCameraConnection> {
  const pc = new RTCPeerConnection({
    iceServers: [{ urls: "stun:stun.l.google.com:19302" }],
    bundlePolicy: "max-bundle",
  });

  const stream = new MediaStream();
  let offerSent = false;
  let stopped = false;

  const sendOffer = async () => {
    if (offerSent || stopped || !pc.localDescription?.sdp) return;
    offerSent = true;
    onStatus?.("Negotiating stream…");
    const answerRaw = await exchangeOffer(pc.localDescription.sdp);
    const answer = parseCrealityAnswer(answerRaw, printerIp);
    await pc.setRemoteDescription(answer);
  };

  pc.ontrack = (event) => {
    const track = event.track;
    if (!stream.getTracks().includes(track)) {
      stream.addTrack(track);
    }
    onStatus?.("Live");
  };

  pc.oniceconnectionstatechange = () => {
    const state = pc.iceConnectionState;
    if (state === "checking") onStatus?.("Connecting…");
    if (state === "connected" || state === "completed") onStatus?.("Live");
    if (state === "failed") onStatus?.("ICE failed");
  };

  pc.onicecandidate = (event) => {
    if (event.candidate !== null) return;
    void sendOffer().catch((err) => {
      if (!stopped) throw err;
    });
  };

  // Creality stock page uses sendrecv (same as Creality Print on phone).
  pc.addTransceiver("video", { direction: "sendrecv" });
  const offer = await pc.createOffer({ offerToReceiveVideo: true });
  await pc.setLocalDescription(offer);

  // Some Chromium builds never emit the null candidate; force offer after a short wait.
  window.setTimeout(() => {
    void sendOffer().catch(() => {
      /* handled by caller timeout */
    });
  }, 2500);

  return {
    pc,
    stream,
    stop: () => {
      stopped = true;
      stream.getTracks().forEach((track) => track.stop());
      pc.close();
    },
  };
}
