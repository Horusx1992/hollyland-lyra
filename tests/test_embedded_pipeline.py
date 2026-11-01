import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst

from camview.config import CaptureConfig, PixelFormat
from camview.pipeline import PipelineBuilder

Gst.init(None)


def test_appsink_description_does_not_include_overlay_properties():
    description = PipelineBuilder().with_capture(CaptureConfig()).with_sink('appsink').build_description()
    assert description.endswith('appsink name=sink')


def test_embedded_sink_decodes_rgb_without_display_or_camera():
    pipeline = (PipelineBuilder().with_capture(CaptureConfig(width=320, height=240,
        pixel_format=PixelFormat.NV12)).with_sink('appsink').build())
    source = pipeline.get_by_name('source')
    source.unlink(pipeline.get_by_name('capsfilter'))
    pipeline.remove(source)
    synthetic = Gst.ElementFactory.make('videotestsrc')
    synthetic.set_property('num-buffers', 1)
    pipeline.add(synthetic)
    assert synthetic.link(pipeline.get_by_name('capsfilter'))
    sink = pipeline.get_by_name('sink')
    sink.set_property('caps', Gst.Caps.from_string('video/x-raw,format=RGB'))
    sink.set_property('sync', False)
    try:
        assert pipeline.set_state(Gst.State.PLAYING) != Gst.StateChangeReturn.FAILURE
        sample = sink.emit('try-pull-sample', Gst.SECOND*3)
        assert sample is not None
        caps = sample.get_caps().get_structure(0)
        assert caps.get_value('format') == 'RGB'
        assert (caps.get_value('width'), caps.get_value('height')) == (320, 240)
    finally:
        pipeline.set_state(Gst.State.NULL)
