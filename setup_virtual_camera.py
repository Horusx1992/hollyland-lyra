#!/usr/bin/env python3
"""Create a temporary, uniquely named virtual camera without unloading modules."""
import os
from pathlib import Path
import pwd
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from virtual_camera import LABEL, find_device


def main():
    if os.geteuid() != 0:
        raise RuntimeError('Run this helper through pkexec or sudo.')
    uid = int(os.environ.get('PKEXEC_UID') or os.environ.get('SUDO_UID') or 0)
    if uid <= 0:
        raise RuntimeError('A non-root invoking user is required.')
    pwd.getpwuid(uid)
    node = find_device()
    if not node:
        if Path('/sys/module/v4l2loopback').exists():
            raise RuntimeError('v4l2loopback is already loaded without a Lyra Control output. Existing outputs will not be removed.')
        number = next((n for n in range(42, 64) if not Path(f'/dev/video{n}').exists()), None)
        if number is None:
            raise RuntimeError('No free virtual video node in the reserved range.')
        subprocess.run(['/usr/sbin/modprobe', 'v4l2loopback', 'devices=1',
                        f'video_nr={number}', f'card_label={LABEL}', 'exclusive_caps=1'],
                       check=True, timeout=15)
        for _ in range(30):
            node = find_device()
            if node and Path(node).exists():
                break
            time.sleep(0.1)
    if not node or node != find_device():
        raise RuntimeError('Could not identify the virtual camera after setup.')
    subprocess.run(['/usr/bin/setfacl', '-m', f'u:{uid}:rw', node], check=True, timeout=5)
    print(node)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
