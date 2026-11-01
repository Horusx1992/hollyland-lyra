#!/usr/bin/env python3
"""Narrow, read-only Lyra HID queries reconstructed from HollyStudio MLSDK.

No setting, upgrade, arbitrary-command or arbitrary-device operation is exposed.
Protocol reconstruction is static evidence until confirmed by a live response.
"""
from pathlib import Path
import argparse
import json
import os
import secrets
import select
import stat
import struct
import sys
import time

REPORT_ID = 5
REPORT_SIZE = 1024
HEADER = struct.Struct('<BIBI')
LYRA_ID = '00003547:00000500'
COMMANDS = {'info': (17, '设备信息'), 'capabilities': (16, 'CMD_SYSTEM_DEVICE_CAPACITY'),
            'zoom': (566, '焦距'), 'zoom-mode': (569, '数字变焦'),
            'focus-mode': (562, '对焦模式'), 'anti-flicker': (564, '抗闪烁'),
            'shutter': (565, '快门'), 'iso': (567, 'ISO'),
            'white-balance': (570, '白平衡'), 'brightness': (571, '亮度'),
            'contrast': (572, '对比度'), 'saturation': (573, '饱和度'),
            'sharpness': (574, '清晰度'), 'auto-exposure': (578, '自动曝光'),
            'auto-framing': (586, '智能构图')}
EXPECTED_DESCRIPTOR = bytes.fromhex(
    '06 02 ff 09 01 a1 01 85 05 09 01 15 00 26 ff 00 75 08 '
    '96 ff 03 81 02 09 01 75 08 96 ff 03 91 02 c0')


def find_device(sysfs=Path('/sys/class/hidraw'), dev=Path('/dev')):
    candidates = []
    for entry in sorted(sysfs.glob('hidraw*')):
        device = entry / 'device'
        try:
            fields = dict(line.split('=', 1) for line in (device/'uevent').read_text().splitlines() if '=' in line)
            hid_id = fields.get('HID_ID', '').upper()
            if ':'.join(hid_id.split(':')[1:]) != LYRA_ID:
                continue
            if (device/'report_descriptor').read_bytes() != EXPECTED_DESCRIPTOR:
                raise RuntimeError('Lyra HID descriptor changed; inspect it before probing.')
            candidates.append(dev/entry.name)
        except FileNotFoundError:
            continue
    if len(candidates) != 1:
        raise RuntimeError(f'Expected one matching Lyra HID interface, found {len(candidates)}.')
    return candidates[0]


def request_for(name, request_id):
    command, description = COMMANDS[name]
    return {'id': request_id, 'type': 1,
            'data': [{'cmd': command, 'cmdDes': description}]}


def encode_request(request, message_id):
    if request.get('type') != 1 or set(request) != {'id', 'type', 'data'}:
        raise ValueError('Only the recovered GET envelope is accepted.')
    expected = {value[0] for value in COMMANDS.values()}
    if not isinstance(request['data'], list) or len(request['data']) != 1:
        raise ValueError('Exactly one read-only command is required.')
    item = request['data'][0]
    if set(item) != {'cmd', 'cmdDes'} or item['cmd'] not in expected:
        raise ValueError('Command is outside the read-only allowlist.')
    if not isinstance(item['cmdDes'], str):
        raise ValueError('Command description must be text.')
    if not 0 <= message_id < 2**32 or not 0 <= request['id'] <= 10000:
        raise ValueError('Invalid request/message ID.')
    payload = json.dumps(request, ensure_ascii=False, separators=(',', ':')).encode('utf8')
    if len(payload) > REPORT_SIZE-HEADER.size:
        raise ValueError('Read request does not fit a single HID report.')
    return (HEADER.pack(REPORT_ID, message_id, 1, 0) + payload).ljust(REPORT_SIZE, b'\0')


class Decoder:
    def __init__(self):
        self.pending = {}

    def feed(self, report):
        if len(report) != REPORT_SIZE:
            raise ValueError(f'Unexpected report length {len(report)}; expected {REPORT_SIZE}.')
        report_id, message_id, complete, sequence = HEADER.unpack_from(report)
        if report_id != REPORT_ID or complete not in (0, 1) or sequence > 100:
            raise ValueError('Unexpected HID framing.')
        if sequence == 0:
            self.pending[message_id] = (0, bytearray())
        if message_id not in self.pending:
            raise ValueError('Continuation without initial frame.')
        expected, payload = self.pending[message_id]
        if sequence != expected:
            del self.pending[message_id]
            raise ValueError('Out-of-order HID report.')
        chunk = report[HEADER.size:]
        payload.extend(chunk.rstrip(b'\0') if complete else chunk)
        if len(payload) > 128*1024 or len(self.pending) > 16:
            self.pending.clear()
            raise ValueError('Response assembly exceeded limits.')
        if not complete:
            self.pending[message_id] = (sequence+1, payload)
            return None
        del self.pending[message_id]
        value = json.loads(payload.decode('utf8'))
        if not isinstance(value, dict):
            raise ValueError('Expected a JSON response object.')
        return value


def probe(device, request, report, timeout):
    fd = os.open(device, os.O_RDWR | os.O_NONBLOCK | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        if not stat.S_ISCHR(os.fstat(fd).st_mode):
            raise RuntimeError('Expected a hidraw character device.')
        written = os.write(fd, report)
        if written != len(report):
            raise RuntimeError(f'Short HID write: {written}/{len(report)}.')
        result = {'device': str(device), 'request': request, 'bytes_sent': written,
                  'matched_response': None, 'unmatched_responses': [], 'decode_errors': []}
        decoder = Decoder()
        deadline = time.monotonic()+timeout
        while time.monotonic() < deadline:
            remaining = deadline-time.monotonic()
            ready, _, _ = select.select([fd], [], [], max(0, remaining))
            if not ready:
                break
            try:
                raw = os.read(fd, REPORT_SIZE)
            except BlockingIOError:
                continue
            if not raw:
                raise RuntimeError('Camera disconnected while reading.')
            try:
                response = decoder.feed(raw)
            except (ValueError, UnicodeError, struct.error) as error:
                result['decode_errors'].append({'error':str(error), 'head_hex':raw[:40].hex(), 'bytes':len(raw)})
                if len(result['decode_errors']) >= 16:
                    break
                continue
            if response is None:
                continue
            if response.get('id') == request['id'] and response.get('type') == 2:
                result['matched_response'] = response
                break
            result['unmatched_responses'].append(response)
            if len(result['unmatched_responses']) >= 16:
                break
        return result
    finally:
        os.close(fd)


def write_result(path, result):
    data = json.dumps(result, ensure_ascii=False, indent=2)+'\n'
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(data)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('query', choices=COMMANDS, nargs='?', default='info')
    parser.add_argument('--dry-run', action='store_true', help='Display packet only; do not open the camera.')
    parser.add_argument('--timeout', type=float, default=3)
    parser.add_argument('--output', type=Path, help='Save private JSON results to a new file.')
    args = parser.parse_args(argv)
    if not 0.1 <= args.timeout <= 15:
        parser.error('timeout must be between 0.1 and 15 seconds')
    request_id = secrets.randbelow(10001)
    message_id = secrets.randbelow(10001)
    request = request_for(args.query, request_id)
    report = encode_request(request, message_id)
    if args.dry_run:
        print(json.dumps({'request':request, 'report_bytes':len(report),
                          'header_hex':report[:HEADER.size].hex(),
                          'live_validation':'not performed'},ensure_ascii=False,indent=2))
        return 0
    device = find_device()
    try:
        result = probe(device, request, report, args.timeout)
    except PermissionError:
        print(f'Access denied to {device}; no request was sent.\n'
              f'Temporary access for your user: sudo setfacl -m u:{os.getuid()}:rw {device}',file=sys.stderr)
        return 2
    if args.output:
        write_result(args.output, result)
    if result['matched_response'] is None:
        print(json.dumps({'status':'no matching response','device':str(device),
                          'decode_errors':result['decode_errors'],
                          'unmatched_responses':len(result['unmatched_responses'])},indent=2))
        return 3
    print(json.dumps({'status':'matched response','query':args.query,
                      'response':result['matched_response']},ensure_ascii=False,indent=2))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as error:
        print(f'lyra_probe: {error}', file=sys.stderr)
        raise SystemExit(1)
