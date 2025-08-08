#!/usr/bin/env python3

import time
import json
import binascii
import subprocess
import sys
import textwrap
import shlex
import re

from pubsub import pub
from meshtastic.tcp_interface import TCPInterface
from meshtastic import portnums_pb2

with open('config.json', 'r') as config_file:
    config = json.load(config_file)

MESH_NODE_IP = config["MESH_NODE_IP"]
CHANNEL_SLOT = config["CHANNEL_SLOT"]
KEYWORDS_TO_SCRIPTS = config["KEYWORDS_TO_SCRIPTS"]
MAX_MSG_AGE_SEC = config["MAX_MSG_AGE_SEC"]
STARTUP_GRACE_SEC = config["STARTUP_GRACE_SEC"]
CHUNK_SIZE = config["CHUNK_SIZE"]


VAR_RE = re.compile(r"^var:(.+)$", re.IGNORECASE)   # matches var:anything
TEXT_PORT_VALUES = {portnums_pb2.TEXT_MESSAGE_APP, "TEXT_MESSAGE_APP"}

start_time = time.time()
iface = None   # will hold the TCPInterface object


# ---------- helper: pretty dump that handles bytes ----------------
def debug_dump(pkt):
    def default(o):
        if isinstance(o, bytes):
            return binascii.hexlify(o).decode()
        return str(o)

    print("\n── RAW PACKET ──")
    print(json.dumps(pkt, indent=2, default=default))
    print("── END PACKET ──\n")


# ---------- helper: transmit text back to the mesh ----------------
def send_text(message: str):
    """Split long strings into CHUNK_SIZE pieces and send each one."""
    for chunk in textwrap.wrap(message, CHUNK_SIZE, break_long_words=False):
        try:
            iface.sendText(chunk, channelIndex=CHANNEL_SLOT)
            time.sleep(0.2)      # brief gap so packets queue nicely
        except Exception as exc:
            print(f"[ERROR] failed to send text: {exc}")


# ---------- main callback -----------------------------------------
def on_receive(packet=None, interface=None, **kwargs):
    now = time.time()
    debug_dump(packet)                          # comment out if too noisy

    if now - start_time < STARTUP_GRACE_SEC:
        print("[DEBUG] grace period → skip")
        return

    rx = packet.get("rxTime")
    if rx and now - rx > MAX_MSG_AGE_SEC:
        print(f"[DEBUG] {now - rx:.1f}s-old packet → drop")
        return

    dec  = packet.get("decoded", {})
    slot = dec.get("channelIndex", 0)
    port = dec.get("portnum")
    text = dec.get("text", "").strip()

    print(f"[DEBUG] slot={slot} port={port} text='{text}'")

    if port not in TEXT_PORT_VALUES or slot != CHANNEL_SLOT:
        print("[DEBUG] not text or wrong slot → ignore")
        return

    # ---- keyword match & argument collection ----
    tokens = shlex.split(text)      # respects quotes, e.g. "Alice Smith"
    if not tokens:
        return

    first = tokens[0].lower()
    script = KEYWORDS_TO_SCRIPTS.get(first)
    if script is None:
        print("[DEBUG] no keyword matched")
        return

    args = []
    for tok in tokens[1:]:
        m = VAR_RE.match(tok)
        if m:
            args.append(m.group(1))

    cmd = [script] + args
    print(f"[MATCH] running {cmd!r}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60
        )
        output = (result.stdout + result.stderr).strip()
        send_text(output or f"[{first}] script ran, no output.")
    except subprocess.TimeoutExpired:
        send_text(f"[{first}] script timed out after 60 s.")
    except Exception as exc:
        err = f"[{first}] script failed: {exc}"
        print("[ERROR]", err)
        send_text(err)


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
