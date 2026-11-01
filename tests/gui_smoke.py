"""Opt-in GTK/live-camera integration check; restores original zoom."""
from pathlib import Path
import json
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from gi.repository import Gdk, GLib, Gtk

root=Path(__file__).resolve().parents[1]
(root/'artifacts').mkdir(exist_ok=True)
window=app.Window()
original=app.camera.read('zoom')
started=time.monotonic()
stage=0
preview_started=0
failure=[]


def tick():
    global stage,preview_started
    try:
        if time.monotonic()-started>25:
            raise RuntimeError('GUI integration timeout: '+window.status.get_text())
        if window.busy:
            return True
        if stage==0:
            assert len(window.rows)==10,window.status.get_text()
            assert not window.rows['focus-mode'].apply_button.get_sensitive()
            if window.video.frames_received < 5:return True
            window.rows['zoom'].editor.set_value(1.1)
            window.rows['zoom'].apply_button.emit('clicked')
            stage=1
        elif stage==1:
            assert abs(window.rows['zoom'].setting['cur']-1.1)<1e-5,window.status.get_text()
            window.rows['zoom'].editor.set_value(original['cur'])
            window.rows['zoom'].apply_button.emit('clicked')
            stage=2
        elif stage==2:
            assert abs(app.camera.read('zoom')['cur']-original['cur'])<1e-5
            assert window.video.frames_received >= 5
            window.shape_choice.set_active_id('phone')
            window.effect_choice.set_active_id('inkwell')
            window.mirror_check.set_active(True)
            preview_started=time.monotonic()
            stage=3
        elif stage==3:
            if time.monotonic()-preview_started<1:
                return True
            frame=window.video.frame
            assert frame and abs(frame.get_width()/frame.get_height()-9/16)<0.01
            assert window.video.pipeline.get_by_name('balance').get_property('saturation')==0
            assert window.video.pipeline.get_by_name('flip').get_property('method').value_nick=='horizontal-flip'
            window.shape_choice.set_active_id('rectangle')
            window.effect_choice.set_active_id('normal')
            window.mirror_check.set_active(False)
            def denied():raise PermissionError('simulated')
            window.submit(denied,lambda _:None,'Permission test')
            stage=4
        elif stage==4:
            assert window.access_button.get_visible()
            assert not window.controls.get_sensitive()
            window.refresh()
            stage=5
        elif stage==5:
            assert not window.access_button.get_visible()
            assert window.controls.get_sensitive()
            assert len(window.rows)==10
            window.set_preview_only(True)
            stage=6
        elif stage==6:
            assert not window.sidebar.get_visible()
            assert window.restore_button.get_visible()
            window.toggle_fullscreen()
            preview_started=time.monotonic()
            stage=7
        elif stage==7:
            if time.monotonic()-preview_started<1:return True
            assert window.is_fullscreen
            window.toggle_fullscreen()
            window.set_preview_only(False)
            window.video.set_software_zoom(0.5)
            preview_started=time.monotonic()
            stage=8
        elif stage==8:
            if time.monotonic()-preview_started<1:return True
            assert bytes(window.video.frame.get_pixels()[:3])==b'\0\0\0'
            (root/'artifacts/gui-validation.json').write_text(json.dumps({
                'native_rows':10,'zoom_apply_and_restore':True,'embedded_frames_received':window.video.frames_received,'shapes_filters_mirror':True,
                'permission_recovery':True,'preview_only_fullscreen':True,
                'software_zoom':True,'original_zoom':original['cur']},indent=2)+'\n')
            window.preview()
            preview_started=time.monotonic()
            stage=9
        elif stage==9:
            if time.monotonic()-preview_started<0.3:return True
            width,height=window.get_size()
            picture=Gdk.pixbuf_get_from_window(window.get_window(),0,0,width,height)
            assert picture
            picture.savev(str(root/'artifacts/interface.png'),'png',[],[])
            window.destroy()
            return False
        return True
    except Exception as error:
        failure.append(repr(error))
        window.destroy()
        return False


GLib.timeout_add(120,tick)
try:
    Gtk.main()
finally:
    app.camera.apply('zoom',original['cur'],original['isAuto']==0)
if failure:
    raise SystemExit('; '.join(failure))
print('PASS: one-process embedded camera, native zoom apply/restore, shapes/filter/mirror, permission recovery.')
