import asyncio, json, os, math, subprocess, urllib.request, re
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import edge_tts
import numpy as np
from scipy.io import wavfile

ROOT=Path("gonews/dragonfly_20261024")
ROOT.mkdir(parents=True,exist_ok=True)
VIDEO=ROOT/"nasa_dragonfly_source.mp4"
OUTPUT=ROOT/"output"
OUTPUT.mkdir(exist_ok=True)
URL="https://science.nasa.gov/wp-content/uploads/2026/01/dragonflyattitan2025.mp4"
if not VIDEO.exists():
    subprocess.run(["curl","-fL","--retry","3","--connect-timeout","30","--max-time","480","-A","Mozilla/5.0","-o",str(VIDEO),URL],check=True)
size=VIDEO.stat().st_size
if size<1000000: raise RuntimeError(f"NASA file too small: {size}")

narration=(
 "La NASA acaba de probar el primer vuelo de un dron que viajará a una luna de Saturno. "
 "Pero hay un detalle: todavía no ha volado allí. "
 "Lo que ocurrió fue una simulación en el laboratorio Johns Hopkins de Maryland. "
 "La computadora hizo que Dragonfly recorriera dunas virtuales, buscara un lugar seguro, "
 "girara y descendiera sin ayuda de un piloto. "
 "Allá en Titán, el dron tendrá que tomar decisiones por sí mismo. "
 "La NASA planea lanzarlo no antes de dos mil veintiocho, y que llegue en dos mil treinta y cuatro. "
 "Estudiará la atmósfera y las moléculas de Titán para investigar pistas sobre los orígenes de la vida. "
 "¿Tú te montarías en una nave para verlo de cerca?"
)

async def voice():
    chunks=[]
    events=[]
    comm=edge_tts.Communicate(narration,voice="es-MX-JorgeNeural",rate="+7%")
    async for m in comm.stream():
        if m["type"]=="audio":chunks.append(m["data"])
        elif m["type"]=="WordBoundary":events.append(m)
    (OUTPUT/"voz.mp3").write_bytes(b"".join(chunks))
    return events

try:
    ev=asyncio.run(voice())
    if (OUTPUT/"voz.mp3").stat().st_size<100000:
        raise ValueError("Edge voice too small")
    print("Natural speech OK",len(ev))
except Exception as e:
    print("Edge unavailable, stop rather than produce robot voice",str(e),flush=True)
    raise

def probe(path):
    return float(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(path)],text=True).strip())
dur=probe(OUTPUT/"voz.mp3")
print("Voice duration",dur,flush=True)
starts=[2,12,21,31,42,51,60,72,80,89,99,109,120,126,15,55]
headlines=[
 "EL DRON QUE VOLARÁ EN TITÁN",
 "LA NASA ACABA DE PROBARLO",
 "PERO NO FUE EN SATURNO",
 "FUE UNA SIMULACIÓN",
 "MARYLAND, ESTADOS UNIDOS",
 "DUNAS COMPLETAMENTE VIRTUALES",
 "BUSCÓ UN LUGAR SEGURO",
 "Y DESCENDIÓ POR SÍ MISMO",
 "NO NECESITÓ PILOTO",
 "EN TITÁN DEBERÁ DECIDIR SOLO",
 "DESPEGUE: DESDE 2028",
 "LLEGADA PREVISTA: 2034",
 "¿QUÉ VA A BUSCAR?",
 "PISTAS DEL ORIGEN DE LA VIDA",
 "TODAVÍA FALTAN PRUEBAS",
 "¿TE GUSTARÍA VERLO VOLAR?"
]
N=len(starts)
parts=[]
for i,st in enumerate(starts):
    segdur=dur/N+0.07
    path=OUTPUT/f"shot_{i:02}.mp4"
    # Actual motion footage: credited official NASA conceptual animation, never presented as live 2026 footage.
    # Crop vertical from UHD with varied virtual camera focus and tiny push-in.
    x=[450,620,770,680,560,700,810,640,760,525,790,720,610,835,705,650][i]
    vf=f"fps=30,scale=2276:1280:flags=bicubic,crop=720:1280:{x}:0,eq=contrast=1.07:saturation=1.04,format=yuv420p"
    subprocess.run(["ffmpeg","-y","-hide_banner","-loglevel","error","-ss",str(st),"-i",str(VIDEO),"-t",str(segdur),"-vf",vf,"-an","-c:v","libx264","-preset","ultrafast","-crf","23",str(path)],check=True)
    parts.append(path)
    print("SHOT",i,flush=True)
(OUTPUT/"input.txt").write_text("".join("file '"+str(x.absolute())+"'\n" for x in parts))
subprocess.run(["ffmpeg","-y","-hide_banner","-loglevel","error","-f","concat","-safe","0","-i",str(OUTPUT/"input.txt"),"-t",str(dur),"-an","-c:v","libx264","-preset","veryfast","-crf","21",str(OUTPUT/"picture.mp4")],check=True)
def ts(sec):
    cs=int(round(max(0,sec)*100));h=cs//360000;mm=cs//6000%60;s=cs//100%60;cc=cs%100
    return f"{h}:{mm:02}:{s:02}.{cc:02}"
safe=lambda s:s.replace("\\","\\\\").replace("{","\\{").replace("}","\\}")
# Burned readable subtitles and editorial headlines, keep action visible.
ass="""[Script Info]
ScriptType: v4.00+
PlayResX: 720
PlayResY: 1280
WrapStyle: 2
ScaledBorderAndShadow: yes
[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Eyebrow,Roboto Condensed,21,&H000AD6FF,&H000AD6FF,&H00000000,&H00000000,-1,0,0,0,100,100,1,0,1,2,1,8,45,45,75,1
Style: Title,Roboto Condensed,52,&H000AD6FF,&H000AD6FF,&H00000000,&H00000000,-1,0,0,0,93,100,0,0,1,3,1,2,42,42,370,1
Style: Caption,Roboto Condensed,39,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,3,1,2,45,45,177,1
[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
for i,title in enumerate(headlines):
    a=i*dur/N;b=(i+1)*dur/N
    ass+=f"Dialogue: 0,{ts(a)},{ts(b)},Title,,0,0,0,,{safe(title)}\n"
ass+=f"Dialogue: 0,{ts(0)},{ts(dur)},Eyebrow,,0,0,0,,GoNews    /    NASA DRAGONFLY   •   ANIMACIÓN OFICIAL, NO VUELO REAL\n"
if ev:
    words=[]
    for v in ev:
        text=v.get("text","").strip()
        if text:words.append((v["offset"]/10000000, (v["offset"]+v.get("duration",0))/10000000,text))
    for j in range(0,len(words),5):
        group=words[j:j+5]
        a=group[0][0];b=min(dur,words[j+5][0] if j+5<len(words) else dur)
        txt=" ".join(w[2] for w in group).replace("\n"," ")
        ass+=f"Dialogue: 0,{ts(a)},{ts(b)},Caption,,0,0,0,,{safe(txt)}\n"
else:
    for i,title in enumerate(headlines):
        ass+=f"Dialogue: 0,{ts(i*dur/N)},{ts((i+1)*dur/N)},Caption,,0,0,0,,{safe(title)}\n"
(OUTPUT/"subtitulos.ass").write_text(ass,encoding="utf-8")
# Original subtle documentary underscore, no stock or copyrighted music.
sr=44100
t=np.arange(math.ceil(dur*sr),dtype=np.float32)/sr
music=(np.sin(2*np.pi*55*t)*0.022+np.sin(2*np.pi*82.4*t)*0.010+np.sin(2*np.pi*110*t)*0.008).astype(np.float32)
music*=np.minimum(1,np.minimum(t,.99*np.maximum(.01,dur-t))).clip(0,1)
wavfile.write(str(OUTPUT/"music.wav"),sr,np.int16(music*32767))
subprocess.run(["ffmpeg","-y","-hide_banner","-loglevel","error","-i",str(OUTPUT/"picture.mp4"),"-i",str(OUTPUT/"voz.mp3"),"-i",str(OUTPUT/"music.wav"),
 "-filter_complex",f"[0:v]subtitles={OUTPUT/'subtitulos.ass'}:force_style='Fontname=Roboto Condensed'[v];[1:a]loudnorm=I=-17:TP=-2:LRA=8[voice];[2:a]volume=0.65[mu];[voice][mu]amix=inputs=2:duration=first:normalize=0[a]",
 "-map","[v]","-map","[a]","-c:v","libx264","-preset","veryfast","-crf","20","-pix_fmt","yuv420p","-c:a","aac","-b:a","160k","-t",str(dur),"-movflags","+faststart",str(OUTPUT/"GoNews_Dragonfly_2026_REEL_PRO_REAL_MOTION.mp4")],check=True)
print("READY",str(OUTPUT/"GoNews_Dragonfly_2026_REEL_PRO_REAL_MOTION.mp4"), flush=True)
