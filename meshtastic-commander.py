#!/usr/bin/env python3

import time, json, binascii, subprocess, sys, textwrap
from pubsub import pub
from meshtastic.tcp_interface import TCPInterface
from meshtastic import portnums_pb2

# ───────── CONFIG ──────────────────────────────────────────────────
MESH_NODE_IP = "192.168.0.127"
CHANNEL_SLOT = 0
KEYWORDS_TO_SCRIPTS = {
    "keyword1": "/opt/meshtastic-actions/keyword1.sh",
    "test":     "/opt/meshtastic-actions/test.sh",
}
MAX_MSG_AGE_SEC   = 10
STARTUP_GRACE_SEC = 5
# Max payload for one text packet is ~228 bytes; stay conservative:
CHUNK_SIZE = 200
# ───────────────────────────────────────────────────────────────────

start_time = time.time()
iface = None                         # will hold the TCPInterface object

# ---------- helper: pretty dump that handles bytes ----------------
def debug_dump(pkt):
    def default(o):
        if isinstance(o, bytes):
            return binascii.hexlify(o).decode()
        return str(o)
    print("\n── RAW PACKET ──")
    print(json.dumps(pkt, indent=2, default=default))
    print("── END PACKET ──\n")

# Accept both numeric & string enum for TEXT_MESSAGE_APP
TEXT_PORT_VALUES = {
    portnums_pb2.TEXT_MESSAGE_APP,
    "TEXT_MESSAGE_APP"
}

# ---------- helper: transmit text back to the mesh ----------------
def send_text(message: str):
    """Split long strings into CHUNK_SIZE pieces and send each."""
    for chunk in textwrap.wrap(message, CHUNK_SIZE, break_long_words=False):
        try:
            iface.sendText(chunk, channelIndex=CHANNEL_SLOT)
            time.sleep(0.2)          # brief gap so packets queue nicely
        except Exception as exc:
            print(f"[ERROR] failed to send text: {exc}")

# ---------- main callback -----------------------------------------
def on_receive(packet=None, interface=None, **kwargs):
    now = time.time()
    debug_dump(packet)                                   # comment if noisy

    if now - start_time < STARTUP_GRACE_SEC:
        print("[DEBUG] grace period → skip")
        return

    rx = packet.get("rxTime")
    if rx and now - rx > MAX_MSG_AGE_SEC:
        print(f"[DEBUG] {now-rx:.1f}s-old packet → drop")
        return

    dec  = packet.get("decoded", {})
    slot = dec.get("channelIndex", 0)
    port = dec.get("portnum")
    text = dec.get("text", "").strip()

    print(f"[DEBUG] slot={slot} port={port} text='{text}'")

    if port not in TEXT_PORT_VALUES or slot != CHANNEL_SLOT:
        print("[DEBUG] not text or wrong slot → ignore")
        return

    lower = text.lower()
    for kw, script in KEYWORDS_TO_SCRIPTS.items():
        if kw in lower:
            print(f"[MATCH] '{kw}' ⇒ {script}")
            try:
                result = subprocess.run(
                    [script],
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                output = (result.stdout + result.stderr).strip()
                if output:
                    send_text(output)
                else:
                    send_text(f"[{kw}] script ran, no output.")
            except subprocess.TimeoutExpired:
                send_text(f"[{kw}] script timed out.")
            except Exception as exc:
                err = f"[{kw}] script failed: {exc}"
                print("[ERROR]", err)
                send_text(err)
            break
    else:
        print("[DEBUG] no keyword matched")

# ---------- program entry -----------------------------------------
def main():
    global iface
    iface = TCPInterface(hostname=MESH_NODE_IP)
    pub.subscribe(on_receive, "meshtastic.receive")

    print(f"Listening on slot {CHANNEL_SLOT} at {MESH_NODE_IP}")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        iface.close()
        sys.exit()

if __name__ == "__main__":
    main()
