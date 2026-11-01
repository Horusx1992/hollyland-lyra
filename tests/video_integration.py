"""Opt-in live video mode and lifecycle checks; no image files are saved."""
from pathlib import Path
import json
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import video_device
from video_preview import Preview, MODES, Gst, Gtk, GLib, Gdk, GstVideo
import virtual_camera

node = video_device()
window = Gtk.Window()
preview = Preview(lambda text, playing: print(text, flush=True))
if '--portrait-output' in sys.argv:
    preview.rotation = 90
    preview.output_device = virtual_camera.find_device()
    assert preview.output_device, 'Set up the named virtual camera first'
window.add(preview)
window.show_all()
stages = list(MODES)
if '--quick' in sys.argv:
    stages = stages[:1]
records = []
error = []
started = time.monotonic()
preview.start(node, stages[0])


def tick():
    try:
        assert time.monotonic()-started < 35, 'Video mode timeout'
        assert preview.running, preview.message
        if preview.frames_received < 4 or preview.frames_drawn < 1:
            return True
        capture = preview.capture
        native = GstVideo.VideoInfo.new_from_caps(preview.last_caps)
        records.append({'mode':stages[0], 'frames':preview.frames_received,
                        'draws':preview.frames_drawn,
                        'size':[native.width,native.height],
                        'display_size':[preview.frame.get_width(),preview.frame.get_height()],
                        'requested_fps':capture.fps})
        previous = preview.pipeline
        preview.stop()
        assert previous.get_state(0).state == Gst.State.NULL
        stages.pop(0)
        if stages:
            preview.start(node, stages[0])
            return True
        window.destroy()
        Gtk.main_quit()
        return False
    except Exception as failure:
        error.append(repr(failure))
        preview.stop()
        window.destroy()
        Gtk.main_quit()
        return False


GLib.timeout_add(150, tick)
Gtk.main()
if error:
    raise SystemExit('; '.join(error))
root = Path(__file__).resolve().parents[1]
name = 'video-wayland.json' if '--quick' in sys.argv else 'video-integration.json'
if '--portrait-output' in sys.argv:
    name = 'portrait-modes.json'
(root/'artifacts'/name).write_text(json.dumps({'backend':Gdk.Display.get_default().__gtype__.name,
    'modes':records},indent=2)+'\n')
print('PASS:', records)
