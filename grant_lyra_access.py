#!/usr/bin/env python3
"""Grant temporary access to the uniquely identified Lyra HID interface."""
from pathlib import Path
import argparse
import os
import pwd
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lyra_probe import find_device


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    uid = 1000
    user = pwd.getpwuid(uid).pw_name
    device = find_device()
    commands = []
    commands.append(['/usr/bin/setfacl', '-m', f'u:{uid}:rw', str(device)])
    print(f'Identified Hollyland Lyra: {device}; user {user} ({uid})', flush=True)
    for command in commands:
        print(' '.join(command), flush=True)
    if args.dry_run:
        return 0
    if os.geteuid() != 0:
        parser.error('Run through sudo to change the device ACL.')
    # Revalidate identity immediately before granting access.
    if find_device() != device:
        raise RuntimeError('Device changed; retry discovery.')
    for command in commands:
        subprocess.run(command, check=True)
    print('Temporary Lyra access granted. No camera command was sent.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
