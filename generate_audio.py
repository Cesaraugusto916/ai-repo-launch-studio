"""
generate_audio.py — Motor de Síntese de Voz Neural (Google GenAI TTS)
======================================================================
Gera arquivos de locução modulares (.wav) utilizando a voz "Aoede" via
Google Gemini API, converte fluxos PCM L16 automaticamente para cabeçalho
WAV compatível e calcula a duração exata em milissegundos via FFprobe
para sincronização com o Hyperframes/GSAP.

REGRA FUNDAMENTAL (GEMINI.md):
Nos modelos TTS do Google Gemini, o campo `contents` é vocalizado literalmente
na íntegra. NUNCA inclua diretrizes de atuação ("Fale com clareza...",
"Tom persuasivo:") dentro de `contents`. Passe exclusivamente o texto puro
do roteiro a ser falado, modulando ritmo e pausas através da pontuação.
"""

import json
import os
import shutil
import sys
import time
import wave
from pathlib import Path
from typing import List, Dict, Any

from dotenv import load_dotenv
from google import genai
from google.genai import types

# Adiciona a pasta raiz ao sys.path para permitir importação limpa de scripts.probe_timings
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.probe_timings import measure_audio_duration

# Carrega variáveis de ambiente (.env)
load_dotenv()

DEFAULT_VOICE = "Aoede"
DEFAULT_MODELS = [
    "gemini-2.5-flash-preview-tts",
    "gemini-3.1-flash-tts-preview",
    "gemini-2.5-pro-preview-tts",
]


# =============================================================================
# ROTEIRO OFICIAL (DOGFOODING — AI REPO LAUNCH STUDIO)
# =============================================================================
DEFAULT_SCENES: List[Dict[str, str]] = [
    {
        "id": "cena_01_problema",
        "file": "brag-output/audio/cena_01_problema.wav",
        "text": (
            "Entender o que um repositório faz apenas lendo blocos de texto e pastas de código nem "
            "sempre é simples. Muitas vezes, projetos incríveis de estudo, portfólio ou código aberto "
            "deixam de ser compreendidos porque falta uma explicação visual, rápida e acessível logo "
            "no primeiro contato."
        ),
    },
    {
        "id": "cena_02_arquitetura",
        "file": "brag-output/audio/cena_02_arquitetura.wav",
        "text": (
            "O AI Repo Launch Studio nasceu para tornar qualquer repositório mais humano e prático "
            "de entender. Basta informar o link do GitHub ou o caminho de uma pasta local: a "
            "inteligência artificial explora os arquivos, compreende o propósito do projeto e cria "
            "uma apresentação completa — sem precisar gravar telas manualmente."
        ),
    },
    {
        "id": "cena_03_motor_tecnico",
        "file": "brag-output/audio/cena_03_motor_tecnico.wav",
        "text": (
            "O pipeline transforma código em história de forma totalmente sincronizada. Primeiro, "
            "estrutura um roteiro didático explicando o problema e a solução. Depois, gera uma "
            "narração fluida com a voz neural do Google Gemini. Um script em Python mede a duração "
            "exata de cada fala em milissegundos, alinhando as animações na tela exatamente com o "
            "que está sendo explicado."
        ),
    },
    {
        "id": "cena_04_resultado",
        "file": "brag-output/audio/cena_04_resultado.wav",
        "text": (
            "Ao final do processo, a ferramenta entrega o vídeo em alta definição, estrutura um "
            "README claro com o player no topo da página e deixa tudo pronto para publicação. "
            "AI Repo Launch Studio: tecnologia e inteligência artificial para tornar seus "
            "repositórios mais acessíveis, visuais e fáceis de entender."
        ),
    },
]


def save_audio_payload(raw_bytes: bytes, mime_type: str, output_path: str) -> None:
    """
    Salva o payload binário retornado pela API do Gemini como um arquivo .wav válido.
    Trata automaticamente fluxos PCM L16 brutos adicionando cabeçalho RIFF/WAV.
    """
    os.makedirs(Path(output_path).parent, exist_ok=True)

    if mime_type and "audio/l16" in mime_type.lower():
        sample_rate = 24000
        if "rate=" in mime_type:
            try:
                sample_rate = int(mime_type.split("rate=")[1].split(";")[0].strip())
            except Exception:
                sample_rate = 24000
        with wave.open(output_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(raw_bytes)
    else:
        with open(output_path, "wb") as f:
            f.write(raw_bytes)


def synthesize_scenes(
    scenes: List[Dict[str, str]] = DEFAULT_SCENES,
    voice_name: str = DEFAULT_VOICE,
    models_fallback: List[str] = DEFAULT_MODELS,
    composition_audio_dir: str = "brag-composition/assets/audio",
    timings_output_path: str = "brag-output/audio/timings.json",
) -> Dict[str, Any]:
    """
    Sintetiza todas as cenas do roteiro com fallback automático de modelos TTS,
    copia os arquivos .wav para a pasta de assets do Hyperframes e retorna o
    mapa de duração medido via FFprobe.
    """
    raw_keys = os.getenv("GEMINI_API_KEYS") or os.getenv("GEMINI_API_KEY", "")
    keys_pool = [k.strip() for k in raw_keys.split(",") if k.strip() and k.strip() != "cole_sua_chave_do_google_ai_studio_aqui"]
    if not keys_pool:
        raise ValueError(
            "GEMINI_API_KEY ausente ou não configurada no arquivo .env. "
            "Copie .env.example para .env e insira sua chave do Google AI Studio."
        )

    os.makedirs(composition_audio_dir, exist_ok=True)
    os.makedirs(Path(timings_output_path).parent, exist_ok=True)

    audio_timings: Dict[str, Any] = {}
    current_offset = 0.5  # Início da primeira locução em 0.50s
    scene_transition_gap = 1.1  # Pausa de respiração/transição entre cenas

    for idx, scene in enumerate(scenes):
        scene_id = scene["id"]
        out_file = scene["file"]
        pure_text = scene["text"].strip()

        if os.path.exists(out_file) and os.path.getsize(out_file) > 10000:
            print(f"[TTS] Reutilizando audio ja sintetizado para '{scene_id}' ({out_file})...")
            used_model = "gemini-2.5-flash-preview-tts"
        else:
            response = None
            used_model = None
            last_err = None

            for model_candidate in models_fallback:
                for key_idx in range(len(keys_pool)):
                    api_key = keys_pool[(idx + key_idx) % len(keys_pool)]
                    client = genai.Client(api_key=api_key)
                    try:
                        print(f"[TTS] Sintetizando '{scene_id}' | Modelo: {model_candidate} | Key #{(idx + key_idx) % len(keys_pool) + 1} | Voz: {voice_name}...")
                        response = client.models.generate_content(
                            model=model_candidate,
                            contents=pure_text,
                            config=types.GenerateContentConfig(
                                response_modalities=["AUDIO"],
                                speech_config=types.SpeechConfig(
                                    voice_config=types.VoiceConfig(
                                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                            voice_name=voice_name
                                        )
                                    )
                                ),
                            ),
                        )
                        used_model = model_candidate
                        break
                    except Exception as exc:
                        last_err = exc
                        print(f"  [!] Aviso ({model_candidate}, Key #{(idx + key_idx) % len(keys_pool) + 1}): {exc.__class__.__name__} - tentando proxima...")
                if response is not None:
                    break

            if response is None:
                raise RuntimeError(f"Falha ao sintetizar '{scene_id}' em todos os modelos TTS: {last_err}")

            part = response.candidates[0].content.parts[0]
            raw_audio = part.inline_data.data
            mime_type = part.inline_data.mime_type or "audio/wav"

            save_audio_payload(raw_audio, mime_type, out_file)
            time.sleep(1.0)

        # Copia para o diretório de composição do Hyperframes
        comp_target = os.path.join(composition_audio_dir, os.path.basename(out_file))
        shutil.copy2(out_file, comp_target)

        # Mede a duração exata com FFprobe
        probe_info = measure_audio_duration(out_file)
        duration_s = probe_info["duration_s"]

        start_s = round(current_offset, 2)
        end_s = round(start_s + duration_s, 2)
        scene_end_s = round(end_s + 0.6, 2)

        audio_timings[scene_id] = {
            "file": out_file,
            "composition_asset": f"assets/audio/{os.path.basename(out_file)}",
            "duration_s": duration_s,
            "duration_ms": probe_info["duration_ms"],
            "vo_start_s": start_s,
            "vo_end_s": end_s,
            "scene_end_s": scene_end_s,
            "voice": voice_name,
            "model": used_model,
            "text": pure_text,
        }

        print(
            f"  [OK] Salvo: {out_file} ({duration_s:.3f}s / {probe_info['duration_ms']}ms) "
            f"| Janela VO: {start_s:.2f}s -> {end_s:.2f}s"
        )
        current_offset = round(end_s + scene_transition_gap, 2)
        time.sleep(1.0)

    with open(timings_output_path, "w", encoding="utf-8") as f:
        json.dump(audio_timings, f, indent=2, ensure_ascii=False)

    total_vo = sum(item["duration_s"] for item in audio_timings.values())
    print(f"\n[OK] Síntese concluída! Locução total: {total_vo:.3f}s | Mapa salvo em: {timings_output_path}")
    return audio_timings


if __name__ == "__main__":
    synthesize_scenes()
