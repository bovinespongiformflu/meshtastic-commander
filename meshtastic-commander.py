#!/usr/bin/env python3

import time, json, binascii, subprocess, sys
from pubsub import pub
from meshtastic.tcp_interface import TCPInterface
from meshtastic import portnums_pb2

# ────────── CONFIG ─────────────────────────────────────────────────
MESH_NODE_IP = "10.0.0.1"
CHANNEL_SLOT = 0                          # primary slot
KEYWORDS_TO_SCRIPTS = {
    "keyword1": "/opt/meshtastic-actions/keyword1.sh",
    "test":     "/opt/meshtastic-actions/test.sh",
}
MAX_MSG_AGE_SEC   = 10
STARTUP_GRACE_SEC = 5
# ───────────────────────────────────────────────────────────────────

start_time = time.time()

# ---------- pretty-print helper (bytes → hex) ----------------------
def debug_dump(pkt):
    def default(o):
        if isinstance(o, bytes):
            return binascii.hexlify(o).decode()
        return str(o)
    print("\n── RAW PACKET ──")
    print(json.dumps(pkt, indent=2, default=default))
    print("── END PACKET ──\n")

# Accept both the string and numeric representation of TEXT_MESSAGE_APP
TEXT_PORT_VALUES = {
    portnums_pb2.TEXT_MESSAGE_APP,        # numeric (256)
    "TEXT_MESSAGE_APP"                    # string
}

# ---------- callback ------------------------------------------------
def on_receive(packet=None, interface=None, **kwargs):
    now = time.time()
    debug_dump(packet)                                   # comment if noisy

    # Grace-period skip
    if now - start_time < STARTUP_GRACE_SEC:
        print("[DEBUG] grace period → skip")
        return

    # Age filter
    rx = packet.get("rxTime")
    if rx and now - rx > MAX_MSG_AGE_SEC:
        print(f"[DEBUG] {now-rx:.1f}s-old packet → drop")
        return

    dec  = packet.get("decoded", {})
    slot = dec.get("channelIndex", 0)                    # default slot 0
    port = dec.get("portnum")
    text = dec.get("text", "").strip()

    print(f"[DEBUG] slot={slot} port={port} text='{text}'")

    # Only react to text packets on the chosen slot
    if port not in TEXT_PORT_VALUES or slot != CHANNEL_SLOT:
        print("[DEBUG] not text or wrong slot → ignore")
        return

    lower = text.lower()
    for kw, script in KEYWORDS_TO_SCRIPTS.items():
        if kw in lower:
            print(f"[MATCH] '{kw}' ⇒ {script}")
            try:
                subprocess.run([script], check=True)
            except Exception as exc:
                print(f"[ERROR] script failed: {exc}")
            break
    else:
        print("[DEBUG] no keyword matched")

# ---------- main ----------------------------------------------------
def main():
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
