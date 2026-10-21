"""
probe_timings.py — Utilitário de precisão para medição de áudio com FFprobe.
Extrai a duração exata em segundos/milissegundos, sample rate e canais
para sincronização cirúrgica na timeline GSAP do Hyperframes.
"""

import json
import os
import subprocess
from pathlib import Path
from typing import Dict, Any


def measure_audio_duration(file_path: str) -> Dict[str, Any]:
    """
    Executa o ffprobe em um arquivo de áudio (.wav/.mp3) e retorna metadados
    de duração com precisão de milissegundos.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Arquivo de áudio não encontrado: {file_path}")

    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    probe_data = json.loads(result.stdout)

    fmt = probe_data.get("format", {})
    streams = probe_data.get("streams", [{}])
    stream0 = streams[0] if streams else {}

    duration_sec = float(fmt.get("duration", stream0.get("duration", 0.0)))
    sample_rate = int(stream0.get("sample_rate", 24000))
    channels = int(stream0.get("channels", 1))

    return {
        "file": str(path).replace("\\", "/"),
        "duration_s": round(duration_sec, 3),
        "duration_ms": int(round(duration_sec * 1000)),
        "sample_rate": sample_rate,
        "channels": channels,
    }


def probe_directory(audio_dir: str = "brag-output/audio", output_json: str = "brag-output/audio/timings.json") -> Dict[str, Any]:
    """
    Inspeciona todos os arquivos .wav de um diretório, calcula o tempo acumulado
    e salva o mapa de tempos em JSON.
    """
    audio_path = Path(audio_dir)
    if not audio_path.exists():
        raise FileNotFoundError(f"Diretório não encontrado: {audio_dir}")

    timings: Dict[str, Any] = {}
    wav_files = sorted(audio_path.glob("*.wav"))

    current_offset = 0.5  # Margem inicial padrão de 500ms na timeline
    scene_gap = 1.0       # Transição padrão entre cenas (1.0s)

    for wav in wav_files:
        scene_id = wav.stem
        info = measure_audio_duration(str(wav))
        info["recommended_start_s"] = round(current_offset, 2)
        info["recommended_end_s"] = round(current_offset + info["duration_s"], 2)
        timings[scene_id] = info
        current_offset = round(info["recommended_end_s"] + scene_gap, 2)

    os.makedirs(Path(output_json).parent, exist_ok=True)
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(timings, f, indent=2, ensure_ascii=False)

    return timings


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Mede a duração exata de áudios com FFprobe para o Hyperframes.")
    parser.add_argument("--dir", default="brag-output/audio", help="Diretório contendo os arquivos .wav")
    parser.add_argument("--out", default="brag-output/audio/timings.json", help="Arquivo JSON de saída")
    args = parser.parse_args()

    results = probe_directory(args.dir, args.out)
    total_s = sum(item["duration_s"] for item in results.values())
    print(f"=== FFprobe Audio Sync Report ({len(results)} cenas | {total_s:.2f}s de locução) ===")
    for k, v in results.items():
        print(f" - {k}: {v['duration_s']:.3f}s ({v['duration_ms']}ms) | janela sugerida: {v['recommended_start_s']}s -> {v['recommended_end_s']}s")
