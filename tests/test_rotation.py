"""Check actual asymmetric RGB pixels, not just pipeline description strings."""
import gi
import pytest

gi.require_version('Gst', '1.0')
gi.require_version('GstVideo', '1.0')
from gi.repository import Gst, GstVideo
from camview.config import CaptureConfig, PixelFormat
from camview.pipeline import PipelineBuilder

Gst.init(None)


def frame(rotation=0, mirror=False, crop=(0, 0, 0, 0), viewport=None):
    builder = (PipelineBuilder().with_capture(CaptureConfig(width=320, height=180,
        pixel_format=PixelFormat.NV12)).with_sink('appsink')
        .with_rotation(rotation).with_mirror(mirror).with_crop(crop))
    if viewport:
        builder.with_viewport(*viewport)
    pipeline = builder.build()
    source = pipeline.get_by_name('source')
    caps = pipeline.get_by_name('capsfilter')
    source.unlink(caps)
    pipeline.remove(source)
    pattern = Gst.ElementFactory.make('videotestsrc')
    pattern.set_property('num-buffers', 1)
    pipeline.add(pattern)
    assert pattern.link(caps)
    sink = pipeline.get_by_name('sink')
    sink.set_property('caps', Gst.Caps.from_string('video/x-raw,format=RGB'))
    sink.set_property('sync', False)
    try:
        pipeline.set_state(Gst.State.PLAYING)
        sample = sink.emit('try-pull-sample', 3*Gst.SECOND)
        assert sample is not None
        info = GstVideo.VideoInfo.new_from_caps(sample.get_caps())
        buffer = sample.get_buffer()
        return info.width, info.height, info.stride[0], buffer.extract_dup(0, buffer.get_size())
    finally:
        pipeline.set_state(Gst.State.NULL)


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
@pytest.mark.parametrize('mirror', [False, True])
def test_rotation_preserves_full_frame_and_mirrors_after_rotation(rotation, mirror):
    width, height, stride, original = frame()
    out_w, out_h, out_stride, actual = frame(rotation, mirror)
    assert (out_w, out_h) == ((height, width) if rotation in (90, 270) else (width, height))
    for x, y in [(20, 20), (70, 20), (120, 20), (220, 20), (290, 20), (20, 130), (270, 130)]:
        ox, oy = {0: (x, y), 90: (height-1-y, x),
                  180: (width-1-x, height-1-y), 270: (y, width-1-x)}[rotation]
        if mirror:
            ox = out_w-1-ox
        expected = original[y*stride+x*3:y*stride+x*3+3]
        observed = actual[oy*out_stride+ox*3:oy*out_stride+ox*3+3]
        assert all(abs(a-b) <= 3 for a, b in zip(expected, observed)), (rotation, mirror, x, y, expected, observed)


def test_full_portrait_viewport_does_not_crop_to_narrow_strip():
    assert frame(90, viewport=(180, 320, 1))[:2] == (180, 320)


def test_circle_crop_uses_rotated_coordinates():
    assert frame(90, crop=(0, 0, 70, 70), viewport=(180, 180, 1))[:2] == (180, 180)


@pytest.mark.parametrize('rotation', [-90, 45, 360, '90'])
def test_invalid_rotation_rejected(rotation):
    with pytest.raises(ValueError):
        PipelineBuilder().with_rotation(rotation)
