"""Preset no destructivo para MoneyPrinterTurbo en Google Colab.

Ejecutar: python docs/preset_es_mobile.py /content/MoneyPrinterTurbo

No imprime ni modifica claves de acceso. No hace llamadas a proveedores de IA.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
import tomllib
from pathlib import Path


def set_values(document: str, section: str, values: dict[str, object]) -> str:
    # Edita solamente claves concretas dentro de una tabla TOML; las otras se conservan.
    section_pattern = re.compile(r"(?m)^\[" + re.escape(section) + r"\][ \t]*$")
    match = section_pattern.search(document)
    if not match:
        document = document.rstrip() + "\n\n[" + section + "]\n"
        match = section_pattern.search(document)
    boundary = re.search(r"(?m)^\[[^\r\n]+\][ \t]*$", document[match.end():])
    end = match.end() + boundary.start() if boundary else len(document)
    body = document[match.end():end]
    for key, value in values.items():
        if isinstance(value, bool):
            literal = "true" if value else "false"
        elif isinstance(value, (int, float)):
            literal = str(value)
        else:
            literal = json.dumps(value, ensure_ascii=False)
        declaration = re.compile(r"(?m)^[ \t]*" + re.escape(key) + r"[ \t]*=[^\r\n]*$")
        line = key + " = " + literal
        if declaration.search(body):
            body = declaration.sub(lambda _m, value=line: value, body, count=1)
        else:
            body = body.rstrip("\r\n") + "\n" + line + "\n"
    return document[:match.end()] + body + document[end:]


def configure(repository: Path) -> None:
    example = repository / "config.example.toml"
    destination = repository / "config.toml"
    if not example.is_file():
        raise FileNotFoundError(f"No existe {example}")
    if not destination.is_file():
        shutil.copy2(example, destination)
    content = destination.read_text(encoding="utf-8")
    cfg = tomllib.loads(content)
    app = cfg.get("app", {})
    ui = cfg.get("ui", {})
    provider = str(app.get("llm_provider", "moonshot"))
    provider_key = str(app.get(f"{provider}_api_key", "") or "")
    # Si ya hay un proveedor configurado, no se sustituyen sus credenciales.
    # Cuando solo existe el valor de ejemplo sin clave, se elige OpenRouter.
    use_openrouter = provider == "moonshot" and not provider_key
    app_updates: dict[str, object] = {
        "video_source": "pexels",
        "match_materials_to_script": True,
    }
    if use_openrouter:
        app_updates.update({
            "llm_provider": "openrouter",
            "openrouter_model_name": "minimax/minimax-m3:free",
        })

    ui_updates: dict[str, object] = {
        "language": "es",
        "video_language": "es",
        "video_script_prompt": (
            "Escribe en español latinoamericano un guion de entre 165 y 195 palabras "
            "para un video vertical de noticias de aproximadamente 80 segundos. "
            "Empieza con un hecho interesante y verificable, sin introducciones ni logos. "
            "Usa frases cortas y naturales, sin exageraciones ni datos inventados. "
            "No incluyas instrucciones de cámara ni etiquetas dentro de la narración."
        ),
        "video_aspect_pexels": "9:16",
        "video_fit_mode": "cover",
        "video_concat_mode": "sequential",
        "video_transition_mode": "None",
        "video_clip_duration": 3,
        "video_count": 1,
        "tts_server": "azure-tts-v1",
        "voice_mode": "tts",
        "voice_name": "es-MX-JorgeNeural",
        "voice_rate": 1.05,
        "voice_volume": 1.0,
        "bgm_type": "random",
        "bgm_volume": 0.18,
        "subtitle_enabled": False,
        "open_task_folder_on_completion": False,
    }
    # Conserva cualquier clave y parametro no incluido en las preferencias.
    revised = set_values(content, "app", app_updates)
    revised = set_values(revised, "ui", ui_updates)
    tomllib.loads(revised)  # Validar antes de escribir.
    if revised != content:
        destination.write_text(revised, encoding="utf-8")
    provider_after = "openrouter" if use_openrouter else provider
    print("✅ Preferencias de video preparadas: español latino, 9:16, voz masculina, música, sin subtítulos.")
    print("Modelo de IA configurado:", provider_after)
    updated = tomllib.loads(revised)["app"]
    if provider_after == "openrouter" and not updated.get("openrouter_api_key"):
        print("⚠️ Falta la API Key personal de OpenRouter; no puede generarse un guion automáticamente todavía.")
    if not updated.get("pexels_api_keys"):
        print("⚠️ Falta la API Key personal de Pexels; no podrá descargar videos desde Pexels todavía.")
    print("Las credenciales existentes permanecieron intactas. Ningún servicio de pago fue invocado.")
    if ui.get("language") != "es":
        print("Si había una ventana abierta, vuelve a abrir el generador para cargar estas preferencias.")


if __name__ == "__main__":
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    configure(root)
