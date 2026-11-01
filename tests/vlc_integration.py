"""Opt-in GUI/VLC portrait check. No camera frames are saved."""
import sys,time,subprocess,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from video_preview import GstVideo
from gi.repository import Gtk,GLib,Gdk
original_rotation=app.preferences.load_rotation()
config=app.preferences.config_path()
original_config=config.read_bytes() if config.exists() else None
w=app.Window();started=time.monotonic();stage=0;process=None;log=None;errors=[];vlc_started=0;quit_sent=False
def tick():
    global stage,process,log,vlc_started,quit_sent
    try:
        assert time.monotonic()-started<30,w.status.get_text()
        if w.busy:return True
        if stage==0:
            assert len(w.rows)==10,w.status.get_text()
            if w.video.frames_received<5:return True
            w.mode_choice.set_active(1)
            w.portrait()
            assert w.video.rotation==90
            assert w.video.shape=='rectangle'
            w.toggle_output()
            stage=1
        elif stage==1:
            assert w.video.output_device,w.status.get_text()
            if w.video.frames_received<5:return True
            assert w.vlc_button.get_sensitive()
            native=GstVideo.VideoInfo.new_from_caps(w.video.last_caps)
            assert (native.width,native.height)==(1080,1920)
            log=open('/tmp/lyra-vlc-check.log','w')
            process=subprocess.Popen(['vlc','-I','rc','--rc-fake-tty','-vv','--no-one-instance','--vout=dummy','--no-audio','--run-time=2','--play-and-exit',f'v4l2://{w.video.output_device}',':v4l2-chroma=YUYV',':live-caching=80','vlc://quit'],stdout=log,stderr=log,stdin=subprocess.PIPE,text=True)
            vlc_started=time.monotonic()
            stage=2
        elif stage==2:
            if process.poll() is None:
                if time.monotonic()-vlc_started>3 and not quit_sent:
                    process.stdin.write('stats\nquit\n');process.stdin.flush();quit_sent=True
                return True
            log.close();log=None
            assert process.returncode==0,process.returncode
            data=Path('/tmp/lyra-vlc-check.log').read_text()
            assert '1080x1920' in data,'VLC did not negotiate portrait video'
            assert 'Received first picture' in data,'VLC did not decode a frame'
            app.preferences.save_rotation(90)
            w.toggle_output()
            w.preview()
            for child in w.preview_options.get_children():
                if isinstance(child,Gtk.Expander):child.set_expanded(True)
            stage=3
        elif stage==3:
            width,height=w.get_size()
            picture=Gdk.pixbuf_get_from_window(w.get_window(),0,0,width,height)
            assert picture
            picture.savev(str(app.ROOT/'artifacts/portrait-interface.png'),'png',[],[])
            (app.ROOT/'artifacts/vlc-validation.json').write_text(json.dumps({'VLC_exit_code':0,'portrait_size':[1080,1920],'UI_output_toggle':True,'saved_rotation':app.preferences.load_rotation(),'screenshot_size':[width,height]},indent=2)+'\n')
            w.destroy();return False
        return True
    except Exception as e:
        errors.append(repr(e));w.destroy();return False
GLib.timeout_add(120,tick)
try:Gtk.main()
finally:
    if process and process.poll() is None:process.terminate();process.wait(timeout=5)
    if log:log.close()
    if original_config is None:config.unlink(missing_ok=True)
    else:config.write_bytes(original_config)
if errors:raise RuntimeError(errors)
print('PASS: GTK portrait/output controls and VLC decoded 1080x1920; no camera frames saved.')
