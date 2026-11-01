"""Opt-in Auto/Reset HID regression; restores the prior image profile."""
from pathlib import Path
import json,sys,time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from gi.repository import Gtk,GLib
before={name:app.camera.read(name) for name in app.camera.IMAGE_SETTINGS}
w=app.Window();stage=0;idx=0;started=time.monotonic();names=['white-balance','shutter','iso'];records=[];failures=[]
def tick():
 global stage,idx
 try:
  assert time.monotonic()-started<25,w.status.get_text()
  if w.busy:return True
  if stage==0:
   if len(w.rows)!=10:return True
   assert all(w.rows[n].setting['isAuto']==0 for n in names)
   w.rows[names[idx]].auto.set_active(False);stage=1
  elif stage==1:
   setting=app.camera.read(names[idx]);assert setting['isAuto']==1,(names[idx],setting)
   assert w.rows[names[idx]].editor.get_sensitive()
   w.rows[names[idx]].auto.set_active(True);stage=2
  elif stage==2:
   setting=app.camera.read(names[idx]);assert setting['isAuto']==0,(names[idx],setting)
   assert not w.rows[names[idx]].editor.get_sensitive()
   records.append({'setting':names[idx],'manual_and_auto_confirmed':True})
   idx+=1
   if idx<len(names):stage=0
   else:
    def dirty():
     app.camera.apply('white-balance',6000,False)
     app.camera.apply('iso',12,False)
     app.camera.apply('anti-flicker',2)
     return app.camera.snapshot()
    w.submit(dirty,w.loaded,'Testing original-default recovery…');stage=3
  elif stage==3:
   assert not w.rows['shutter'].auto.get_sensitive()
   w.reset_button.emit('clicked');stage=4
  elif stage==4:
   assert all(w.rows[n].setting['isAuto']==0 for n in names),w.status.get_text()
   assert w.rows['brightness'].editor.get_sensitive()
   assert w.rows['anti-flicker'].setting['cur']==0
   assert w.rows['white-balance'].setting['cur']==5100
   iso=w.rows['iso'].setting;assert iso['list'][int(iso['cur'])]=='250'
   records.append({'reset_restored_first_profile':True,'all_auto_modes_restored':True,'brightness_enabled':True})
   (app.ROOT/'artifacts/auto-reset-repair.json').write_text(json.dumps(records,indent=2)+'\n')
   w.destroy();return False
  return True
 except Exception as e:failures.append(repr(e));w.destroy();return False
GLib.timeout_add(100,tick)
try:Gtk.main()
finally:app.camera.restore_image_state(before)
if failures:raise RuntimeError(failures)
print('PASS:',records)
