"""Drive the config menu with a real gamepad and capture what happens at each press.

    python tools/controller_check.py                 open the menu and walk it with the D-pad
    python tools/controller_check.py --keep-pad      leave the virtual controller connected afterwards

The menu is built out of button lists rather than dropdowns so that a controller can drive it, and this is
what checks that claim instead of asserting it. A virtual Xbox pad is connected through ViGEmBus, the menu
is opened, and the D-pad and A button are used to move the highlight and press a button; a screenshot is
taken after each press into captures/.

The controller lives in a `client_drive.py padhost` process started in the background, because a pad that
disconnects makes the game stop on "Controller lost connection" and close whatever form is open.

Needs the server up, the MCP bridge with it, and the client joined to the server.
"""
import argparse
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import client_drive
from bridge import Bridge, PLAYER

# What to press, and what the screenshot after it is called. The menu opens on the first button, so a
# couple of downs and an A should land on the second setting's own screen.
WALK = [("down", "01_down"), ("down", "02_down_again"), ("a", "03_pressed"),
        ("down", "04_inside_down"), ("a", "05_chose"), ("b", "06_back")]


def padhost(lifetime=600):
    """Start the process that holds the virtual controller open, and wait for it to come up."""
    out = os.path.join(os.path.dirname(HERE), "captures")
    os.makedirs(out, exist_ok=True)
    marker = os.path.join(out, "pad.cmd")
    if os.path.exists(marker):
        os.remove(marker)
    process = subprocess.Popen([sys.executable, os.path.join(HERE, "client_drive.py"), "padhost", str(lifetime)],
                               cwd=os.path.dirname(HERE))
    time.sleep(4)       # the pad has to enumerate before the game will see it
    return process


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep-pad", action="store_true")
    args = parser.parse_args()

    bridge = Bridge()
    players = bridge.tool("mc_player_list")
    if PLAYER not in players:
        sys.exit(f"{PLAYER} is not on the server; join first")
    # mc_entity_run_command_as wants the entity's id, which the player list carries next to the name
    entity_id = None
    for line in players.splitlines():
        if "id:" in line and entity_id is None and PLAYER in players.split("id:")[0]:
            entity_id = line.split("id:")[1].strip().strip('"')
            break
    if not entity_id:
        sys.exit(f"could not find {PLAYER}'s entity id in the player list")
    client_drive.focus()

    print("connecting a virtual controller through ViGEmBus")
    host = padhost()
    try:
        client_drive.focus()
        client_drive.shot("controller_00_before")
        # open the menu as the player, so the form has somebody to show itself to
        print("opening the menu")
        bridge.tool("mc_entity_run_command_as", entity_id=entity_id, command="scriptevent sbi:menu")
        time.sleep(3)
        client_drive.shot("controller_00_menu")
        for press, name in WALK:
            print(f"  pad: {press}")
            client_drive.pad([press])
            time.sleep(1.2)
            client_drive.shot(f"controller_{name}")
    finally:
        if not args.keep_pad:
            host.terminate()
    print("\nshots are in captures/controller_*.png; look at them to see the highlight move")
    return 0


if __name__ == "__main__":
    sys.exit(main())
