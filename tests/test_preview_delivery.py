"""Exercise burst delivery and bounded GUI buffering without a physical camera."""
from types import SimpleNamespace
import time

import pytest
from video_preview import Preview, Gst, Gtk, GLib


@pytest.fixture
def preview():
    if not Gtk.init_check()[0]:
        pytest.skip('GTK display required')
    instance = Preview(lambda *_: None)
    instance.pipeline = Gst.Pipeline.new(None)
    yield instance
    instance.destroy()


def deliver(preview, value):
    caps = Gst.Caps.from_string('video/x-raw,format=RGB,width=4,height=2,framerate=60/1')
    buffer = Gst.Buffer.new_wrapped(bytes([value]) * 24)
    sample = Gst.Sample.new(buffer, caps, None, None)
    assert preview.new_sample(SimpleNamespace(emit=lambda _: sample)) == Gst.FlowReturn.OK


def test_usb_burst_does_not_discard_the_next_display_frame(preview):
    deliver(preview, 10)
    preview.pull_frame()
    assert preview.frame is None  # One frame of initial jitter tolerance.
    deliver(preview, 20)
    preview.pull_frame()
    assert preview.frame.get_pixels()[0] == 10
    deliver(preview, 30)
    deliver(preview, 40)
    preview.pull_frame()
    assert preview.frame.get_pixels()[0] == 20
    preview.pull_frame()
    assert preview.frame.get_pixels()[0] == 30
    preview.pull_frame()
    assert preview.frame.get_pixels()[0] == 40


def test_hidden_preview_drops_old_frames_and_stop_releases_them(preview):
    for value in range(10):
        deliver(preview, value)
    assert len(preview.display_samples) == 3
    preview.pull_frame()
    assert preview.frame.get_pixels()[0] == 7
    preview.stop()
    assert not preview.display_samples
    assert preview.frame is None
    assert not preview.frame_tick
    assert not preview.timer


def test_stream_watch_stops_a_hidden_preview_without_frame_clock_ticks(preview):
    pipeline = preview.pipeline
    deliver(preview, 10)
    assert not preview.get_mapped()
    preview.frame_tick = preview.add_tick_callback(preview.present_frame)
    preview.timer = GLib.timeout_add(1, preview.check_stream)
    pipeline.get_bus().post(Gst.Message.new_eos(pipeline))
    deadline = time.monotonic() + 1
    while preview.running and time.monotonic() < deadline:
        GLib.MainContext.default().iteration(False)
        time.sleep(.001)
    assert not preview.running
    assert not preview.timer
    assert not preview.frame_tick
    assert not preview.display_samples
