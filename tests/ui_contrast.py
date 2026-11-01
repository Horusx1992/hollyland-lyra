"""Opt-in style checks against actual GTK popup states; no camera video."""
import json
from pathlib import Path
import sys
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from ui_theme import COLORS
from gi.repository import Gdk,GLib,Gtk

snapshot=app.camera.snapshot()
with patch.object(app.Window,'refresh'):
    w=app.Window()
w.auto_preview_started=True
w.loaded(snapshot)
settings=Gtk.Settings.get_default()
original=(settings.props.gtk_theme_name,settings.props.gtk_application_prefer_dark_theme)
choices=[('capture',w.mode_choice,1),('orientation',w.rotation_choice,1),('shape',w.shape_choice,1),
         ('effect',w.effect_choice,1),('quality',w.record_quality,2),('microphone',w.mic_choice,2),
         ('anti-flicker',w.rows['anti-flicker'].editor,0)]
queue=[(theme,name,combo,page) for theme in (original,('Adwaita',False),('Adwaita',True))
       for name,combo,page in choices]
results=[];errors=[];current=None


def lum(c):
    vals=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in (c.red,c.green,c.blue)]
    return sum(v*k for v,k in zip(vals,(.2126,.7152,.0722)))


def contrast(a,b):
    lo,hi=sorted((lum(a),lum(b)));return (hi+.05)/(lo+.05)


def finish():
    settings.props.gtk_theme_name,settings.props.gtk_application_prefer_dark_theme=original
    w.destroy();return False


def begin():
    global current
    if not queue:
        (app.ROOT/'artifacts/studio-popup-contrast.json').write_text(json.dumps(results,indent=2)+'\n')
        print('PASS:',len(results),'popup/theme combinations; min contrast',min(x['contrast'] for x in results))
        return finish()
    current=queue.pop(0);theme,name,combo,page=current
    settings.props.gtk_theme_name,settings.props.gtk_application_prefer_dark_theme=theme
    w.sidebar.set_current_page(page)
    combo.popup()
    GLib.timeout_add(100,check);return False


def check():
    theme,name,combo,page=current
    try:
        menu=combo.get_popup_accessible().get_widget()
        background=menu.get_style_context().get_background_color(Gtk.StateFlags.NORMAL)
        ratios=[]
        for item in menu.get_children():
            ctx=item.get_style_context()
            for state in (Gtk.StateFlags.NORMAL,Gtk.StateFlags.PRELIGHT,Gtk.StateFlags.INSENSITIVE):
                fg=ctx.get_color(state);bg=ctx.get_background_color(state)
                ratios.append(contrast(fg,bg if bg.alpha else background))
        assert min(ratios)>=4.5,(name,theme,min(ratios))
        results.append({'dropdown':name,'theme':theme[0],'dark':theme[1],'contrast':round(min(ratios),2)})
    except Exception as e:
        errors.append(repr(e));combo.popdown();return finish()
    combo.popdown();GLib.timeout_add(60,begin);return False


GLib.timeout_add(200,begin)
Gtk.main()
if errors:raise RuntimeError(errors)

pairs=[('text','bg'),('text','panel'),('text','surface'),('muted','panel'),('muted','bg'),
       ('disabled','input'),('on_accent','accent'),('on_accent','accent_hover'),
       ('text','danger'),('text','danger_hover'),('danger_text','bg'),('success','surface')]
colors={k:Gdk.RGBA() for k in COLORS}
for k,v in COLORS.items():colors[k].parse(v)
text_results=[{'text':a,'background':b,'contrast':round(contrast(colors[a],colors[b]),2)} for a,b in pairs]
assert min(x['contrast'] for x in text_results)>=4.5
(app.ROOT/'artifacts/studio-contrast.json').write_text(json.dumps(text_results,indent=2)+'\n')
print('PASS: text and button contrast',min(x['contrast'] for x in text_results))
