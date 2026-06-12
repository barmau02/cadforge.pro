import asyncio
import json
from pathlib import Path

import websockets

from creality_preflight import preflight_send

IP = "192.168.1.134"
GCODE = Path(r"c:\Users\mauri\boat_print\eb1d6899188f\plate_1.gcode")
STL = Path(r"c:\Users\mauri\boat_print\eb1d6899188f\PrintableCube.stl")


async def live_snapshot() -> dict:
    async with websockets.connect(f"ws://{IP}:9999/", subprotocols=["wsslicer"], open_timeout=8) as ws:
        return json.loads(await asyncio.wait_for(ws.recv(), timeout=8))


def main() -> None:
    snap = asyncio.run(live_snapshot())
    print("=== Live printer ===")
    for key in (
        "materialStatus",
        "materialDetect",
        "materialDetector1",
        "feedState",
        "cfsConnect",
        "state",
        "printFileName",
        "TotalLayer",
        "printProgress",
        "targetNozzleTemp",
        "nozzleTemp",
        "bedTemp0",
    ):
        print(f"  {key}: {snap.get(key)}")

    pre = preflight_send(str(IP), GCODE, [STL])
    print("\n=== Preflight ===")
    print(f"  ready_to_send: {pre['ok']}")
    pf = pre["printer_file"]
    print(f"  model size on printer: X={pf.get('modelX')} Y={pf.get('modelY')} Z={pf.get('modelZ')}")
    print(f"  slice time (local): {pre['local_gcode'].get('print_time')}")
    if pre["blockers"]:
        print("  still blocking:")
        for item in pre["blockers"]:
            print(f"   - {item}")
    else:
        print("  all checks passed")


if __name__ == "__main__":
    main()
