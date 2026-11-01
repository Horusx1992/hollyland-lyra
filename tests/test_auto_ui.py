"""GTK regression for the actual checkbox call path; no camera hardware needed."""
from types import SimpleNamespace
from unittest.mock import Mock,patch
import gi
import pytest
gi.require_version('Gtk','3.0')
from gi.repository import Gtk
import app


def test_toggling_auto_applies_and_reads_back_without_an_extra_apply_click():
    if not Gtk.init_check()[0]:pytest.skip('GTK display required')
    setting={'cur':5100,'def':5100,'min':2800,'max':7000,'step':1,'isAuto':1,'enable':1}
    host=SimpleNamespace(status=Gtk.Label(),refresh=Mock())
    def submit(task,done,message,failed=None):
        done(task());return True
    host.submit=submit
    with patch.object(app.camera,'read',return_value=setting),\
         patch.object(app.camera,'apply',side_effect=lambda name,value,automatic:dict(setting,isAuto=0 if automatic else 1)) as writer:
        row=app.SettingRow(host,'white-balance',setting)
        row.auto.set_active(True)
        assert writer.call_count==1,'Auto checkbox changed only its appearance; nothing was sent to the camera'
        assert row.setting['isAuto']==0
        assert not row.editor.get_sensitive()


def test_busy_window_does_not_leave_an_unsent_auto_selection_checked():
    if not Gtk.init_check()[0]:pytest.skip('GTK display required')
    setting={'cur':5100,'min':2800,'max':7000,'step':1,'isAuto':1,'enable':1}
    host=SimpleNamespace(status=Gtk.Label(),refresh=Mock(),submit=lambda *args,**kwargs:False)
    with patch.object(app.camera,'apply') as writer:
        row=app.SettingRow(host,'white-balance',setting)
        row.auto.set_active(True)
        assert not row.auto.get_active()
        assert row.editor.get_sensitive()
        writer.assert_not_called()
