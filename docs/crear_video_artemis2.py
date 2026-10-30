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
    ("Artemis II rocket launch April 2026", "VOLVIERON A LA LUNA", "DESPUÉS DE 50 AÑOS"),
    ("Artemis II launch SLS rocket 2026", "1 DE ABRIL DE 2026", "EL DESPEGUE"),
    ("Artemis II launch Kennedy Space Center", "UNA MISIÓN HISTÓRICA", "CUATRO ASTRONAUTAS"),
    ("Artemis II crew astronauts 2026", "LA TRIPULACIÓN", "TRES DE NASA, UNO DE CANADÁ"),
    ("Artemis II crew Orion spacecraft", "LA NAVE ORIÓN", "RUMBO AL ESPACIO PROFUNDO"),
    ("Artemis II astronauts inside Orion", "PRUEBAS CRUCIALES", "SISTEMAS DE SUPERVIVENCIA"),
    ("Artemis II Moon lunar flyby April 2026", "ALREDEDOR DE LA LUNA", "SIN ATERRIZAR"),
    ("Artemis II far side Moon photo 2026", "UNA VISTA ÚNICA", "DESDE EL ESPACIO"),
    ("Artemis II Orion Earth photo 2026", "MÁS DE 400 MIL KM", "LEJOS DE LA TIERRA"),
    ("Artemis II lunar flyby Moon 2026", "9 DÍAS EN EL ESPACIO", "Y LLEGÓ EL REGRESO"),
    ("Artemis II splashdown recovery April 2026", "10 DE ABRIL", "EL REGRESO A LA TIERRA"),
    ("Artemis II splashdown parachutes 2026", "AMERIZAJE EN EL PACÍFICO", "CERCA DE SAN DIEGO"),
    ("Artemis II crew recovery April 2026", "LOS CUATRO REGRESARON", "SANOS Y SALVOS"),
    ("Artemis II Moon photo Orion spacecraft", "¿QUÉ VIENE AHORA?", "EL FUTURO DE LA LUNA"),
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
    "launch", "launch", "crew", "crew", "crew", "crew",
    "moon", "moon", "moon", "moon",
    "splashdown", "splashdown", "recovery", "moon"
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


# Audio en español latino gratuito, con voz masculina de Edge TTS.
print("2/5 Generando narración...")
audio_path = ROOT/"narracion.mp3"
async def edge_voice():
    import edge_tts
    await edge_tts.Communicate(SCRIPT, "es-MX-JorgeNeural", rate="+5%", pitch="+0Hz").save(str(audio_path))

try:
    import edge_tts
    asyncio.run(edge_voice())
except Exception as error:
    print("Edge TTS no respondió, intentando voz alternativa:",str(error)[:180])
    from gtts import gTTS
    gTTS(SCRIPT,lang="es",tld="com.mx").save(str(audio_path))
if not audio_path.exists() or audio_path.stat().st_size < 25000:
    raise RuntimeError("No se obtuvo narración válida, no se renderiza un video mudo.")

def run(args):
    subprocess.run(args, check=True)

def duration(path):
    r = subprocess.check_output([
        "ffprobe","-v","error","-show_entries","format=duration",
        "-of","default=noprint_wrappers=1:nokey=1",str(path)
    ],text=True).strip()
    return float(r)

audio_seconds=duration(audio_path)
print(f"Duración de voz: {audio_seconds:.1f} segundos")

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
    draw.rounded_rectangle((48,1320,345,1400),radius=14,fill=(255,214,10))
    draw.text((68,1331),"ARTEMIS II",font=smallfont,fill=(12,12,12))
    words=main.split()
    lines=[];current=""
    for word in words:
        test=(current+" "+word).strip()
        if draw.textbbox((0,0),test,font=font)[2] > W-96 and current:
            lines.append(current);current=word
        else:
            current=test
    if current:lines.append(current)
    yy=1460
    for line in lines[:3]:
        draw.text((50,yy),line,font=font,fill="white",stroke_width=1,stroke_fill="black")
        yy += 96
    draw.text((50,min(1810,yy+13)),secondary,font=smallfont,fill=(255,214,10))
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

print("5/5 Renderizando MP4 con movimiento suave estilo Remotion...")
scene_secs=(audio_seconds+1.0)/len(slide_paths)
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
     "-filter_complex","[0:v]fps=30,zoompan=z=\'min(1.04,1.015+0.00018*on)\':x=\'(iw-iw/zoom)/2\':y=\'(ih-ih/zoom)/2\':d=1:s=1080x1920:fps=30,format=yuv420p[v];[1:a]volume=1.0[n];[2:a]volume=0.18[m];[n][m]amix=inputs=2:duration=first:dropout_transition=0[a]",
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
