"""Decode actual files to verify detail preservation, not encoder property names."""
import math
import subprocess
import time
import gi
gi.require_version('Gst','1.0')
from gi.repository import Gst
from recording import Recorder


def encode(tmp_path,quality):
    width,height=160,120
    y=bytes(16+((x*17+y*23) % 220) for y in range(height) for x in range(width))
    image=y+bytes([100])*(width*height//4)+bytes([150])*(width*height//4)
    caps=Gst.Caps.from_string(f'video/x-raw,format=I420,width={width},height={height},framerate=30/1')
    path=tmp_path/f'{quality}.mp4';r=Recorder();r.start(path,caps,microphone=None,quality=quality)
    try:
        for _ in range(8):
            buffer=Gst.Buffer.new_allocate(None,len(image),None);buffer.fill(0,image)
            r.push(Gst.Sample.new(buffer,caps,None,None));time.sleep(1/30)
        r.finish()
    finally:
        if r.active:r.finish()
    decoded=subprocess.run(['ffmpeg','-v','error','-i',str(path),'-frames:v','1',
        '-f','rawvideo','-pix_fmt','yuv420p','-'],capture_output=True,check=True).stdout
    return image,decoded,path.stat().st_size


def test_lossless_preserves_every_processed_pixel_and_best_retains_more_detail(tmp_path):
    original,lossless,lossless_size=encode(tmp_path,'lossless')
    assert lossless==original
    original,best,best_size=encode(tmp_path,'best')
    original,balanced,balanced_size=encode(tmp_path,'balanced')
    def psnr(data):
        mse=sum((a-b)**2 for a,b in zip(original[:160*120],data[:160*120]))/(160*120)
        return 10*math.log10(255**2/mse)
    best_score,balanced_score=psnr(best),psnr(balanced)
    assert best_score>balanced_score+2,(best_score,balanced_score)
    assert lossless_size>best_size>balanced_size
    print('PSNR',{'best':best_score,'balanced':balanced_score,'lossless':'exact pixels'})
