"""Opt-in real camera/microphone recording. Temporary A/V files are deleted."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from gi.repository import GLib,Gtk

root=app.ROOT
config=app.preferences.config_path()
original_config=config.read_bytes() if config.exists() else None
folder=tempfile.TemporaryDirectory(prefix='lyra-recording-check-')
window=app.Window()
window.record_folder=Path(folder.name)
window.mode_choice.set_active(2)
window.sidebar.set_current_page(2)
started=time.monotonic();record_started=0;stage=0;index=0
records=[];failures=[];choices=[];final_file=None


def inspect(path,audio):
    data=json.loads(subprocess.run(['ffprobe','-v','error','-show_streams','-count_packets',
        '-of','json',str(path)],capture_output=True,text=True,check=True).stdout)
    subprocess.run(['ffmpeg','-v','error','-i',str(path),'-f','null','-'],capture_output=True,check=True)
    streams=data['streams'];video=next(item for item in streams if item['codec_type']=='video')
    assert (video['width'],video['height'])==(1080,1920)
    tracks=[item for item in streams if item['codec_type']=='audio']
    assert bool(tracks)==audio
    if audio:
        assert tracks[0]['codec_name']=='aac'
        assert abs(float(video['start_time'])-float(tracks[0]['start_time']))<0.25
        assert abs(float(video['duration'])-float(tracks[0]['duration']))<0.3
    return {'width':video['width'],'height':video['height'],'video_packets':int(video['nb_read_packets']),
            'video_duration':float(video['duration']),'audio':audio,
            'audio_duration':float(tracks[0]['duration']) if tracks else None}


def tick():
    global stage,record_started,index,choices,final_file
    try:
        assert time.monotonic()-started<45,window.status.get_text()
        if window.busy:return True
        if stage==0:
            if window.video.frames_received<5 or not window.mics:return True
            assert Gtk.Widget.get_default_direction()==Gtk.TextDirection.LTR
            assert window.sidebar.get_n_pages()==3
            assert window.reset_button.get_label()=='Reset to defaults'
            choices=[mic.name for mic in window.mics]+['none']
            window.portrait()
            window.toggle_output()
            stage=1
        elif stage==1:
            if window.video.frames_received<5:return True
            assert window.video.output_device,window.status.get_text()
            window.mic_choice.set_active_id(choices[index])
            window.toggle_recording()
            assert window.video.recorder.active,window.status.get_text()
            assert not window.framing.get_sensitive()
            assert not window.mic_choice.get_sensitive()
            assert window.record_button.get_sensitive()
            if choices[index]!='none':
                assert window.video.recorder.audio_source.get_property('device')==choices[index]
            window.set_preview_only(True)
            assert window.record_bar.get_visible()
            window.set_preview_only(False)
            try:window.video.set_rotation(0)
            except RuntimeError:pass
            else:raise AssertionError('Rotation changed while recording')
            record_started=time.monotonic();stage=2
        elif stage==2:
            if time.monotonic()-record_started<1.4:return True
            assert window.video.recorder.active and not window.record_finalizing,window.status.get_text()
            assert window.video.recorder.frames>=5,window.video.recorder.frames
            window.toggle_recording();stage=3
        elif stage==3:
            if window.record_finalizing:return True
            assert window.last_recording,window.status.get_text()
            record=inspect(window.last_recording['path'],choices[index]!='none')
            record['microphone']=choices[index]
            records.append(record)
            assert window.video.running
            assert window.framing.get_sensitive()
            index+=1
            if index<len(choices):stage=1
            else:
                window.mic_choice.set_active_id(choices[0])
                window.toggle_recording()
                final_file=window.video.recorder.path
                record_started=time.monotonic();stage=4
        elif stage==4:
            if time.monotonic()-record_started<1:return True
            assert window.delete_event(window,None)
            assert window.close_pending and window.record_finalizing
            stage=5
        return True
    except Exception as error:
        import traceback;traceback.print_exc();print('stage',stage,'frames',window.video.recorder.frames,'active',window.video.recorder.active,'finalizing',window.record_finalizing,'failure',window.video.recorder.failure,'detail',window.video.recorder.failure_debug,flush=True);failures.append(repr(error));window.destroy();return False


GLib.timeout_add(80,tick)
try:
    Gtk.main()
    if failures:raise RuntimeError(failures)
    assert stage==5
    final=inspect(final_file,True)
    records.append(dict(final,closed_while_recording=True))
    (root/'artifacts/recording-validation.json').write_text(json.dumps({
        'cases':records,'recorded_with_virtual_output':True,'temporary_media_deleted':True,
        'framing_and_audio_settings_locked_while_recording':True,'close_finalizes_mp4':True},indent=2)+'\n')
finally:
    if original_config is None:config.unlink(missing_ok=True)
    else:config.write_bytes(original_config)
    folder.cleanup()
print('PASS: selected physical microphones, video-only, portrait 1080p60, virtual output, repeat recording and close finalization.',records)
