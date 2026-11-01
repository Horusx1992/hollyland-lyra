import json
import subprocess
import time
from unittest.mock import patch

import pytest
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib
from recording import Recorder, microphones


CAPS=Gst.Caps.from_string('video/x-raw,format=RGB,width=160,height=120,framerate=30/1')


def feed(recorder, frames=36):
    for _ in range(frames):
        buffer=Gst.Buffer.new_allocate(None,160*120*3,None)
        buffer.fill(0,bytes((40,100,170))*(160*120))
        recorder.push(Gst.Sample.new(buffer,CAPS,None,None))
        recorder.poll()
        time.sleep(1/30)


def inspect(path):
    result=subprocess.run(['ffprobe','-v','error','-show_streams','-of','json',str(path)],
        capture_output=True,text=True,check=True)
    subprocess.run(['ffmpeg','-v','error','-i',str(path),'-f','null','-'],
        capture_output=True,check=True)
    return json.loads(result.stdout)['streams']


@pytest.mark.parametrize('audio',[False,True])
def test_finalized_mp4_has_playable_processed_video_and_optional_synced_audio(tmp_path,audio):
    recorder=Recorder();path=tmp_path/'clip.mp4'
    recorder.start(path,CAPS,microphone='default' if audio else None,audio_factory='audiotestsrc')
    feed(recorder)
    result=recorder.finish()
    assert result['frames']==36
    assert not recorder.active
    streams=inspect(path)
    video=next(item for item in streams if item['codec_type']=='video')
    assert video['codec_name']=='h264'
    assert (video['width'],video['height'])==(160,120)
    tracks=[item for item in streams if item['codec_type']=='audio']
    assert bool(tracks)==audio
    if audio:
        assert tracks[0]['codec_name']=='aac'
        assert abs(float(video['start_time'])-float(tracks[0]['start_time']))<0.15
        assert abs(float(video['duration'])-float(tracks[0]['duration']))<0.2
    # Starting again uses a fresh timeline, and never reuses a closed descriptor.
    recorder.start(tmp_path/'second.mp4',CAPS,microphone=None)
    feed(recorder,8)
    recorder.finish()
    inspect(tmp_path/'second.mp4')


def test_existing_recording_is_never_overwritten(tmp_path):
    path=tmp_path/'clip.mp4';path.write_bytes(b'keep-me')
    recorder=Recorder()
    with pytest.raises(FileExistsError):recorder.start(path,CAPS,microphone=None)
    assert path.read_bytes()==b'keep-me'
    assert not recorder.active
    assert recorder.fd is None


def test_start_rejects_missing_frame_caps_and_wrong_extension(tmp_path):
    recorder=Recorder()
    with pytest.raises(RuntimeError):recorder.start(tmp_path/'clip.mp4',None)
    with pytest.raises(ValueError):recorder.start(tmp_path/'clip.exe',CAPS)
    assert list(tmp_path.iterdir())==[]


def test_microphone_picker_excludes_speaker_monitors_and_preserves_device_ids():
    sources=[{'name':'mic.name;literal','description':'USB Microphone'},
             {'name':'speaker.monitor','description':'Speakers'}]
    response=subprocess.CompletedProcess([],0,stdout=json.dumps(sources))
    with patch('recording.subprocess.run',return_value=response) as run:
        found=microphones()
    assert [(mic.name,mic.description) for mic in found]==[('mic.name;literal','USB Microphone')]
    assert run.call_args.args[0]==['pactl','-f','json','list','sources']


def test_stream_error_keeps_first_cause_and_still_releases_writer(tmp_path):
    recorder=Recorder();recorder.start(tmp_path/'interrupted.mp4',CAPS,microphone=None)
    feed(recorder,8)
    bus=recorder.pipeline.get_bus()
    for text in ('Microphone disconnected','Internal data stream error'):
        bus.post(Gst.Message.new_error(recorder.pipeline,GLib.Error(text),''))
    with pytest.raises(RuntimeError,match='Microphone disconnected'):recorder.poll()
    recorder.finish()
    assert not recorder.active and recorder.fd is None
    inspect(tmp_path/'interrupted.mp4')


def test_first_frames_have_explicit_monotonic_timestamps_before_audio_startup(tmp_path):
    recorder=Recorder();recorder.start(tmp_path/'startup.mp4',CAPS,audio_factory='audiotestsrc')
    source=recorder.source
    stamps=[]
    def emit(signal,*args):
        if signal=='push-buffer':stamps.append((args[0].pts,args[0].dts))
        return source.emit(signal,*args)
    with patch.object(recorder,'source') as wrapped:
        wrapped.emit.side_effect=emit
        feed(recorder,8)
        recorder.finish()
    assert all(pts!=Gst.CLOCK_TIME_NONE and dts==pts for pts,dts in stamps)
    assert all(a[0]<b[0] for a,b in zip(stamps,stamps[1:]))
    inspect(tmp_path/'startup.mp4')
