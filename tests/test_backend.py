import json
import unittest
from unittest.mock import patch

import lyra_backend as camera


class BackendTests(unittest.TestCase):
    range = {'cmd':566,'cur':1,'min':1,'max':4,'step':0.10000000149,'enable':1,'isAuto':2}

    def test_validate_capabilities_before_writing(self):
        for value in (1,1.1,2,4):
            camera.validate('zoom',value,self.range,False)
        for value in (0.9,4.1,1.15,float('nan')):
            with self.assertRaises(ValueError):camera.validate('zoom',value,self.range,False)
        with self.assertRaises(camera.CameraError):
            camera.validate('zoom',2,dict(self.range,enable=0),False)
        with self.assertRaises(ValueError):camera.validate('zoom',2,self.range,True)

    def test_enum_index_must_exist_and_be_integral(self):
        setting={'list':['OFF','50Hz','60Hz'],'cur':0,'enable':1,'isAuto':2}
        self.assertEqual(camera.validate('anti-flicker',2,setting,False),2)
        for value in (-1,3,1.5):
            with self.assertRaises(ValueError):camera.validate('anti-flicker',value,setting,False)

    def test_setting_packet_is_narrow_and_contains_native_fields(self):
        frame=camera.encode_set('contrast',1,2,42,7)
        self.assertEqual(frame[:10],bytes.fromhex('05 07 00 00 00 01 00 00 00 00'))
        self.assertEqual(json.loads(frame[10:].rstrip(b'\0')),
            {'id':42,'type':0,'data':[{'cmd':572,'cmdDes':'对比度','cur':1,'isAuto':2}]})
        for name in ('info','capabilities','focus-mode','upgrade'):
            with self.assertRaises(ValueError):camera.encode_set(name,1,2,42,7)

    def test_no_write_for_invalid_value(self):
        with patch.object(camera,'read',return_value=self.range),patch.object(camera.os,'open') as opened:
            with self.assertRaises(ValueError):camera.apply('zoom',9)
            opened.assert_not_called()

    def test_mismatched_readback_is_failure_and_does_not_resend(self):
        with patch.object(camera,'read',side_effect=[self.range,self.range]),\
             patch.object(camera.wire,'find_device',return_value='/dev/hidraw-test'),\
             patch.object(camera.os,'open',return_value=10),\
             patch.object(camera.os,'write',return_value=1024) as write,\
             patch.object(camera.os,'close') as close:
            with self.assertRaises(camera.CameraError):camera.apply('zoom',2)
            self.assertEqual(write.call_count,1)
            close.assert_called_once_with(10)

    def test_auto_accepts_changed_current_only_when_mode_is_confirmed(self):
        before={'min':2800,'max':7000,'step':1,'cur':5100,'isAuto':1,'enable':1}
        after=dict(before,cur=5200,isAuto=0)
        with patch.object(camera,'read',side_effect=[before,after]),\
             patch.object(camera.wire,'find_device',return_value='/dev/hidraw-test'),\
             patch.object(camera.os,'open',return_value=10),\
             patch.object(camera.os,'write',return_value=1024),patch.object(camera.os,'close'):
            self.assertEqual(camera.apply('white-balance',5100,True),after)


if __name__=='__main__':unittest.main()
