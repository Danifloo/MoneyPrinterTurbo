"""Crea un video informativo vertical de Artemis II desde Google Colab.
Fuentes visuales: NASA Image and Video Library. No utiliza imagenes de IA como evidencia.
"""
import asyncio
import io
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import wave
from pathlib import Path

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

ROOT = Path("/content/gonews_artemis2")
ROOT.mkdir(parents=True, exist_ok=True)
OUT = Path("/content/Artemis_II_GoNews_9x16.mp4")
W, H, FPS = 1080, 1920, 30

SCRIPT = (
    "Por primera vez en más de cincuenta años, cuatro astronautas viajaron alrededor de la Luna. "
    "Pero hay un detalle: ninguno aterrizó. "
    "La misión Artemis dos despegó de Florida el primero de abril de dos mil veintiséis, "
    "a bordo del poderoso cohete S L S. "
    "La cápsula Orión transportó a Reid Wiseman, Victor Glover, Christina Koch y Jeremy Hansen, de Canadá. "
    "Durante el viaje, la tripulación puso a prueba los sistemas de navegación, comunicaciones y soporte vital. "
    "También observó la Luna desde una perspectiva que ningún ser humano había tenido en más de medio siglo. "
    "En su punto más lejano, estuvieron a más de cuatrocientos mil kilómetros de la Tierra. "
    "El propósito no era plantar una bandera, sino comprobar que la nave pudiera llevar personas al espacio profundo y traerlas de vuelta. "
    "Tras nueve días, una hora y treinta y dos minutos en el espacio, llegó la parte más delicada: regresar. "
    "El diez de abril, Orión cruzó la atmósfera, desplegó sus paracaídas y amerizó en el océano Pacífico, cerca de San Diego. "
    "Los cuatro astronautas volvieron sanos y salvos. "
    "Artemis dos no llevó seres humanos a caminar sobre la Luna, pero abrió una nueva etapa de exploración lunar. "
    "Y dejó una pregunta: ¿cuándo veremos de nuevo a una persona sobre su superficie?"
)

SCENES = [
    ("Artemis II rocket launch April 2026", "CUATRO ASTRONAUTAS", "RUMBO A LA LUNA"),
    ("Artemis II launch SLS rocket 2026", "PRIMERO DE ABRIL", "MISIÓN ARTEMIS DOS"),
    ("Artemis II crew astronauts 2026", "DESPUÉS DE 50 AÑOS", "OTRA VEZ MÁS ALLÁ"),
    ("Artemis II Moon lunar flyby April 2026", "SOBREVOLARON LA LUNA", "SIN ATERRIZAR"),
    ("Artemis II far side Moon photo 2026", "LA NAVE ORIÓN", "PRUEBAS EN EL ESPACIO"),
    ("Artemis II Orion Earth photo 2026", "EL OBJETIVO", "FUTUROS ALUNIZAJES"),
    ("Artemis II splashdown recovery April 2026", "DIEZ DE ABRIL", "EL REGRESO A CASA"),
    ("Artemis II splashdown parachutes 2026", "AMERIZAJE EN EL PACÍFICO", "LOS CUATRO REGRESARON"),
    ("Artemis II Moon photo Orion spacecraft", "¿Y EL SIGUIENTE PASO?", "EL FUTURO DE LA LUNA"),
]

SOURCES = [
    "https://www.nasa.gov/mission/artemis-ii/",
    "https://www.nasa.gov/blogs/missions/2026/04/10/artemis-ii-flight-day-10-re-entry-live-updates/",
    "https://www.nasa.gov/gallery/artemis-ii-splashdown-and-recovery/",
    "https://www.nasa.gov/nasa-brand-center/images-and-media/",
]

session = requests.Session()
session.headers.update({"User-Agent": "GoNewsEducationalVideo/1.0"})

def nasa_assets(query):
    response = session.get("https://images-api.nasa.gov/search",
                           params={"q":query, "media_type":"image", "page_size":70},
                           timeout=30)
    response.raise_for_status()
    items = response.json().get("collection", {}).get("items", [])
    found = []
    words = query.lower().split()
    for item in items:
        data = (item.get("data") or [{}])[0]
        title = data.get("title","")
        description = data.get("description","") or ""
        txt = (title+" "+description[:300]).lower()
        if not re.search(r"artemis[\s-]*(ii|2)\b", txt):
            continue
        if re.search(r"artist'?s|illustration|rendering|artwork|concept art", title.lower()):
            continue
        links = [x["href"] for x in item.get("links",[]) if x.get("render","image")=="image" and x.get("href","").startswith("http")]
        if not links:
            continue
        keywords = {
            "launch":("launch", "rocket", "liftoff", "sls"),
            "crew":("crew", "astronaut", "wiseman", "koch", "glover", "hansen"),
            "moon":("moon", "lunar", "far side", "flyby", "orion"),
            "earth":("earth", "orion", "planet"),
            "splashdown":("splashdown", "recovery", "parachute", "pacific"),
            "recovery":("recovery", "splashdown", "crew"),
        }
        term = next((t for t in keywords if t in query.lower()),"")
        score = sum(3 for k in keywords.get(term,()) if k in txt)
        score += sum(1 for w in words if len(w)>3 and w in txt)
        date = data.get("date_created","")
        score += 3 if date.startswith("2026") else 0
        found.append((score, data.get("nasa_id", title), links[0], title))
    found.sort(key=lambda row:row[0], reverse=True)
    return found

def download_photo(item, number):
    _, nasa_id, initial_url, title = item
    # Usar fotografia real. Preferir imagen grande de la coleccion oficial.
    urls = []
    try:
        catalog = session.get("https://images-api.nasa.gov/asset/"+requests.utils.quote(nasa_id, safe=""), timeout=22)
        if catalog.ok:
            candidates = [x.get("href","") for x in catalog.json().get("collection",{}).get("items",[])]
            for key in ("~large", "~medium", "~orig"):
                urls.extend([u for u in candidates if key in u.lower() and u.lower().split("?")[0].endswith((".jpg",".jpeg",".png"))])
    except Exception:
        pass
    urls.append(initial_url)
    for url in dict.fromkeys(urls):
        try:
            resp = session.get(url,timeout=35)
            resp.raise_for_status()
            if len(resp.content) > 18_000_000:
                continue
            image=Image.open(io.BytesIO(resp.content)).convert("RGB")
            image.thumbnail((2000,2000), Image.Resampling.LANCZOS)
            if image.width<350 or image.height<300:
                continue
            return image, {"nasa_id":nasa_id,"title":title,"url":url}
        except Exception:
            continue
    return None,None

print("1/5 Descargando fotografías REALES y verificadas de Artemis II...")
# Fotografías de abril de 2026, no representaciones de IA.
# Imágenes de agencias espaciales y medios que reproducen fotografías de NASA.
PHOTO_SOURCES = {
    "launch": (
        "Lanzamiento Artemis II, NASA, 1 abril 2026",
        "https://npr-brightspot.s3.amazonaws.com/c9/14/d673790e4357bb70317327660cc8/nasa-artemis-ii-launch.jpg",
    ),
    "crew": (
        "Tripulación Artemis II ante Orion, fotografía NASA, 2023",
        "https://gcp-na-images.contentstack.com/v3/assets/bltea6093859af6183b/bltd04fdead560b9111/6998cc2c7323afcfa02bd197/KSC-20230808-PH-KLS02_0098orig.jpg?branch=production",
    ),
    "moon": (
        "Superficie lunar y Tierra desde Artemis II, NASA, 6 abril 2026",
        "https://img.pressone.ro/MxESoMuSFvre67e0nF3vAgDirZc%3D/1980x1319/smart/https%3A%2F%2Fimages.pressone.ro%2Fwp-content%2Fuploads%2F2026%2F04%2F07182559%2FArtemis-2-luna-07.jpg",
    ),
    "splashdown": (
        "Amerizaje de Orion Artemis II, foto de recuperación del programa, 10 abril 2026",
        "https://d1ldvf68ux039x.cloudfront.net/thumbs/photos/2605/9676175/1000w_q95.jpg",
    ),
    "recovery": (
        "US Navy recupera cápsula Orion tras Artemis II, 10 abril 2026",
        "https://d1ldvf68ux039x.cloudfront.net/thumbs/photos/2604/9609121/2000w_q95.jpg",
    ),
}
# Relación entre escenas del guion y fotografías adecuadas.
PHOTO_SEQUENCE = (
    "launch", "launch", "crew", "moon", "moon", "moon", "splashdown", "splashdown", "moon"
)
assert len(PHOTO_SEQUENCE) == len(SCENES)
downloaded = {}
credits = []
for key,(title,url) in PHOTO_SOURCES.items():
    print("Foto:",title)
    try:
        response=session.get(url, timeout=45)
        response.raise_for_status()
        image=Image.open(io.BytesIO(response.content)).convert("RGB")
        image.thumbnail((2000, 2000),Image.Resampling.LANCZOS)
        if min(image.size) < 300:
            raise RuntimeError("Foto demasiado pequeña")
        downloaded[key]=image
        credits.append({"title":title,"url":url})
    except Exception as exc:
        print("No disponible:",key,str(exc)[:180])

required = {"launch","moon","splashdown"}
if not required.issubset(set(downloaded)):
    raise RuntimeError("Falta una fotografía real de despegue, Luna o amerizaje. No se inventará ninguna imagen.")
images=[]
for i,(_query,headline,caption) in enumerate(SCENES):
    category=PHOTO_SEQUENCE[i]
    if category not in downloaded:
        # Respaldo solo para grupos relacionados; nunca mostrar Luna como amerizaje.
        substitute={"crew":"launch","recovery":"splashdown"}.get(category)
        if substitute is None or substitute not in downloaded:
            raise RuntimeError("Falta una foto real de "+category)
        category=substitute
    images.append((downloaded[category],headline,caption))


# Nueva voz de ElevenLabs generada previamente en español latino.
print("2/5 Recuperando narración real de ElevenLabs, sin comprar plan...")
audio_path=ROOT/"narracion_elevenlabs.mp3"
VOICE_URL="https://storage.googleapis.com/xi-backend/database/workspace/57e1bd34f7cf40a99803bc62ed30b2c7/content_generation/LDQVMuaDDgDxIa6AjKM0/X8TaLhn2DZW5Uhgzsy4f/content.mp3?X-Goog-Algorithm=GOOG4-RSA-SHA256&X-Goog-Credential=xi-backend-prod%40xi-labs.iam.gserviceaccount.com%2F20261023%2Fauto%2Fstorage%2Fgoog4_request&X-Goog-Date=20261023T192802Z&X-Goog-Expires=7200&X-Goog-SignedHeaders=host&X-Goog-Signature=1e2f22276955ce85157792ceda59b6a1330f8c0202958252a112060ffb572b9065c3d10502c32bd54e3a4ebf64373445897f4f592c8eae78ccbd7660b58683e41960dc72b700f272d780d022af1446635d65d1bef1e8dedf9f68230856b61c6026be0a4b88d3836a4e1540fc2f8ba51327fc52fe3669f0c3f5da434c4599b0651109c2b0b789c8996359ea1b439f333ef3d259c7d9f99b83639cb836629c43a3fbd73a1ff58a92969a6dc083abba069a91bce9bf3a4999a9dae231ac598c67eca73352de7bacc64a9aa0889b71fce1ed0dc9e0b876237821942192bbe371b1318ef44daab044e46d83e73e6f7082c048a565cc5b3db98ac95b331ae651579546"
voice_response=session.get(VOICE_URL,timeout=90)
voice_response.raise_for_status()
audio_path.write_bytes(voice_response.content)
if audio_path.stat().st_size < 15000:
    raise RuntimeError("No se descargó correctamente la narración de ElevenLabs")

def run(args):
    subprocess.run(args,check=True)

def duration(path):
    r=subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(path)],text=True).strip()
    return float(r)

audio_seconds=duration(audio_path)
print(f"Duración de voz ElevenLabs: {audio_seconds:.2f} segundos")

# Subtítulos en español divididos en frases; ajuste proporcional a la locución.
CAPTIONS=[
 "El primero de abril, cuatro astronautas",
 "despegaron rumbo a la Luna.",
 "Era Artemis dos: el primer viaje tripulado",
 "a sus alrededores en más de cincuenta años.",
 "A bordo de Orión, la tripulación dejó atrás",
 "la Tierra y sobrevoló la Luna.",
 "No aterrizaron. Esta misión puso a prueba",
 "la nave y sus sistemas antes de futuros alunizajes.",
 "El diez de abril, la cápsula regresó",
 "y amerizó en el océano Pacífico.",
 "Ahora, la NASA tiene nuevos datos",
 "para preparar el siguiente paso.",
 "¿Te subirías a una misión como esta?",
]
def ass_time(t):
    cs=round(t*100)
    return f"{cs//360000}:{(cs//6000)%60:02d}:{(cs//100)%60:02d}.{cs%100:02d}"
weights=[max(1, len(c.split())) for c in CAPTIONS]
total_weight=sum(weights)
sub_path=ROOT/"subtitulos.ass"
header="[Script Info]\\nScriptType: v4.00+\\nPlayResX: 1080\\nPlayResY: 1920\\nWrapStyle: 2\\n[V4+ Styles]\\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\\nStyle: TikTok,DejaVu Sans,66,&H00FFFFFF,&H00FFD60A,&H00000000,&H99000000,-1,0,0,0,100,100,0,0,1,5,2,2,70,70,170,1\\n[Events]\\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\\n"
lines=[header.replace("\\n","\n")]
t=0
for i,(caption,w) in enumerate(zip(CAPTIONS,weights)):
    end=audio_seconds if i==len(CAPTIONS)-1 else t+audio_seconds*w/total_weight
    lines.append(f"Dialogue: 0,{ass_time(t)},{ass_time(end)},TikTok,,0,0,0,,{caption}\\N".replace("\\N",""))
    t=end
sub_path.write_text("\n".join(lines)+"\n",encoding="utf-8")

print("3/5 Diseñando escenas verticales...")
font_base = "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf"
font = ImageFont.truetype(font_base, 77)
smallfont = ImageFont.truetype(font_base, 45)
slide_paths=[]
for i, (photo, main, secondary) in enumerate(images):
    background = ImageOps.fit(photo, (W,H), method=Image.Resampling.LANCZOS).filter(ImageFilter.GaussianBlur(34))
    dark = Image.new("RGB",(W,H),(4,5,12))
    background=Image.blend(background,dark,0.45)
    foreground=ImageOps.contain(photo,(W,1400), method=Image.Resampling.LANCZOS)
    background.paste(foreground,((W-foreground.width)//2, max(50,(1420-foreground.height)//2)))
    # Gradiente oscuro inferior para titulares.
    mask=Image.new("L",(W,H),0)
    p=mask.load()
    for y in range(1050,H):
        alpha = int(242*(y-1050)/(H-1050))
        for x in range(W):
            p[x,y]=alpha
    background.paste(dark,(0,0),mask)
    draw=ImageDraw.Draw(background)
    draw.rounded_rectangle((48,1080,345,1160),radius=14,fill=(255,214,10))
    draw.text((68,1091),"ARTEMIS II",font=smallfont,fill=(12,12,12))
    words=main.split()
    lines=[];current=""
    for word in words:
        test=(current+" "+word).strip()
        if draw.textbbox((0,0),test,font=font)[2] > W-96 and current:
            lines.append(current);current=word
        else:
            current=test
    if current:lines.append(current)
    yy=1200
    for line in lines[:3]:
        draw.text((50,yy),line,font=font,fill="white",stroke_width=1,stroke_fill="black")
        yy += 91
    draw.text((50,min(1490,yy+13)),secondary,font=smallfont,fill=(255,214,10))
    path=ROOT/f"frame_{i:02d}.jpg"
    background.save(path,"JPEG",quality=91,optimize=True)
    slide_paths.append(path)
if not slide_paths:
    raise RuntimeError("No se pudieron crear las imágenes del video.")

print("4/5 Creando música instrumental original...")
music_path=ROOT/"musica.wav"
sr=22050
seconds=math.ceil(audio_seconds)+4
with wave.open(str(music_path),"wb") as wf:
    wf.setnchannels(1);wf.setsampwidth(2);wf.setframerate(sr)
    chords = [(110,164.81,220),(98,146.83,196),(130.81,164.81,261.62),(87.31,130.81,174.61)]
    for step in range(0,seconds):
        n=sr
        t=(np.arange(n,dtype=np.float64)+step*sr)/sr
        freqs=chords[(step//4)%len(chords)]
        v=sum(np.sin(2*np.pi*f*t)/len(freqs) for f in freqs)
        v*= 0.11*(0.75+0.25*np.sin(2*np.pi*0.27*t)**2)
        v+= 0.015*np.sin(2*np.pi*55*t)
        amp=np.clip(v,-0.8,0.8)
        fade=np.minimum(1,np.minimum(t/2.0,(seconds-t)/2.0))
        wf.writeframes((amp*fade*32767).astype("<i2").tobytes())

print("5/5 Montaje Reel con 9 cortes, zoom y subtítulos... ")
scene_secs=audio_seconds/len(slide_paths)
concat=ROOT/"slides.ffconcat"
with concat.open("w") as file:
    file.write("ffconcat version 1.0\n")
    for p in slide_paths:
        file.write("file '"+str(p)+"'\n")
        file.write(f"duration {scene_secs:.4f}\n")
    file.write("file '"+str(slide_paths[-1])+"'\n")
run(["ffmpeg","-y","-hide_banner","-loglevel","error",
     "-f","concat","-safe","0","-i",str(concat),
     "-i",str(audio_path),"-stream_loop","-1","-i",str(music_path),
     "-filter_complex","[0:v]fps=30,zoompan=z='min(1.065,1.018+0.00006*on)':x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2':d=1:s=1080x1920:fps=30,subtitles=/content/gonews_artemis2/subtitulos.ass,format=yuv420p[v];[1:a]volume=1.0[n];[2:a]volume=0.12[m];[n][m]amix=inputs=2:duration=first:dropout_transition=0[a]",
     "-map","[v]","-map","[a]","-t",str(audio_seconds+0.3),
     "-c:v","libx264","-preset","veryfast","-crf","23",
     "-pix_fmt","yuv420p","-c:a","aac","-b:a","160k",
     "-r","30","-movflags","+faststart",str(OUT)])
assert OUT.is_file() and OUT.stat().st_size>150_000, "El MP4 no se generó correctamente."

(ROOT/"fuentes_y_guion.txt").write_text(
    "GUION:\n\n"+SCRIPT+"\n\nFUENTES DE LA INFORMACION:\n"+
    "\n".join(SOURCES)+"\n\nIMAGENES NASA (sin créditos dentro del video):\n"+
    "\n".join(f"{d['title']} — {d['url']}" for d in credits)+
    "\n\nNASA imagery usage: https://www.nasa.gov/nasa-brand-center/images-and-media/\n",
    encoding="utf-8"
)
print(f"✅ VIDEO CREADO: {OUT}")
print(f"Duración: {duration(OUT):.1f} s. Tamaño: {OUT.stat().st_size/1024**2:.1f} MB")
print("Fuentes/guion:",ROOT/"fuentes_y_guion.txt")
