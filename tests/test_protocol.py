import tempfile
import unittest
from pathlib import Path
import lyra_probe as p


class ProtocolTests(unittest.TestCase):
    def test_known_get_frame_layout_and_padding(self):
        request = {'id':42,'type':1,'data':[{'cmd':17,'cmdDes':'设备信息'}]}
        report = p.encode_request(request, 0x01020304)
        expected = (bytes.fromhex('05 04 03 02 01 01 00 00 00 00')+
                    '{"id":42,"type":1,"data":[{"cmd":17,"cmdDes":"设备信息"}]}'.encode())
        self.assertEqual(report, expected+b'\0'*(1024-len(expected)))

    def test_forbids_setting_and_firmware_commands(self):
        for request in [
            {'id':1,'type':0,'data':[{'cmd':566,'cmdDes':''}]},
            {'id':1,'type':1,'data':[{'cmd':18,'cmdDes':''}]},
            {'id':1,'type':1,'data':[{'cmd':566,'cmdDes':'','value':2}]},
        ]:
            with self.assertRaises(ValueError):p.encode_request(request, 1)

    def test_reassembles_split_utf8_json(self):
        # Split a multi-byte character across full 1014-byte payload boundaries.
        payload = ('{"id":42,"type":2,"text":"'+'x'*988+'设备"}').encode()
        first = p.HEADER.pack(5,7,0,0)+payload[:1014]
        second = (p.HEADER.pack(5,7,1,1)+payload[1014:]).ljust(1024,b'\0')
        decoder = p.Decoder()
        self.assertIsNone(decoder.feed(first))
        self.assertEqual(decoder.feed(second)['text'], 'x'*988+'设备')

    def test_rejects_incomplete_or_unordered_frames(self):
        decoder = p.Decoder()
        with self.assertRaises(ValueError):decoder.feed(b'\x05')
        with self.assertRaises(ValueError):decoder.feed(p.HEADER.pack(5,3,1,1).ljust(1024,b'\0'))
        decoder.feed(p.HEADER.pack(5,3,0,0).ljust(1024,b'x'))
        with self.assertRaises(ValueError):decoder.feed(p.HEADER.pack(5,3,1,2).ljust(1024,b'\0'))

    def test_selects_only_exact_lyra_and_descriptor(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name,product in [('hidraw0','00000501'),('hidraw7','00000500')]:
                device=root/name/'device';device.mkdir(parents=True)
                (device/'uevent').write_text(f'HID_ID=0003:00003547:{product}\n')
                (device/'report_descriptor').write_bytes(p.EXPECTED_DESCRIPTOR)
            self.assertEqual(p.find_device(root,Path('/dev')),Path('/dev/hidraw7'))
            (root/'hidraw7/device/report_descriptor').write_bytes(b'changed')
            with self.assertRaises(RuntimeError):p.find_device(root,Path('/dev'))


if __name__ == '__main__':unittest.main()
