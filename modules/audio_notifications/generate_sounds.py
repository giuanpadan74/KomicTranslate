#!/usr/bin/env python3
"""
Script per generare i file audio WAV per le notifiche di KomicTranslate
"""

import os
import numpy as np
import wave
import struct
from typing import Tuple

def generate_tone(frequency: float, duration: float, sample_rate: int = 44100, amplitude: float = 0.3) -> np.ndarray:
    """Genera un tono sinusoidale"""
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    # Applica un envelope per evitare click
    envelope = np.exp(-t * 3)  # Decay esponenziale
    wave_data = amplitude * np.sin(2 * np.pi * frequency * t) * envelope
    return wave_data

def generate_chord(frequencies: list, duration: float, sample_rate: int = 44100, amplitude: float = 0.2) -> np.ndarray:
    """Genera un accordo combinando più frequenze"""
    wave_data = np.zeros(int(sample_rate * duration))
    for freq in frequencies:
        wave_data += generate_tone(freq, duration, sample_rate, amplitude / len(frequencies))
    return wave_data

def generate_beep_sequence(frequencies: list, durations: list, gaps: list, sample_rate: int = 44100) -> np.ndarray:
    """Genera una sequenza di beep"""
    wave_data = np.array([])
    
    for i, (freq, dur) in enumerate(zip(frequencies, durations)):
        # Aggiungi il tono
        tone = generate_tone(freq, dur, sample_rate)
        wave_data = np.concatenate([wave_data, tone])
        
        # Aggiungi pausa se non è l'ultimo elemento
        if i < len(frequencies) - 1 and i < len(gaps):
            silence = np.zeros(int(sample_rate * gaps[i]))
            wave_data = np.concatenate([wave_data, silence])
    
    return wave_data

def save_wav(filename: str, wave_data: np.ndarray, sample_rate: int = 44100):
    """Salva i dati audio come file WAV"""
    # Normalizza e converti in 16-bit
    wave_data = np.clip(wave_data, -1.0, 1.0)
    wave_data_int = (wave_data * 32767).astype(np.int16)
    
    with wave.open(filename, 'w') as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(wave_data_int.tobytes())

def generate_all_sounds():
    """Genera tutti i suoni necessari per KomicTranslate"""
    sounds_dir = os.path.join(os.path.dirname(__file__), 'sounds')
    os.makedirs(sounds_dir, exist_ok=True)
    
    print("Generazione suoni per KomicTranslate...")
    
    # 1. Detect - Beep semplice (rilevazione testo)
    print("- detect.wav")
    detect_sound = generate_tone(800, 0.2)
    save_wav(os.path.join(sounds_dir, 'detect.wav'), detect_sound)
    
    # 2. OCR - Due beep rapidi
    print("- ocr.wav")
    ocr_sound = generate_beep_sequence([600, 800], [0.1, 0.1], [0.05])
    save_wav(os.path.join(sounds_dir, 'ocr.wav'), ocr_sound)
    
    # 3. OCR Color - Tre beep ascendenti
    print("- ocr_color.wav")
    ocr_color_sound = generate_beep_sequence([500, 650, 800], [0.08, 0.08, 0.12], [0.04, 0.04])
    save_wav(os.path.join(sounds_dir, 'ocr_color.wav'), ocr_color_sound)
    
    # 4. Translate - Accordo maggiore (suono di successo)
    print("- translate.wav")
    translate_sound = generate_chord([523, 659, 784], 0.4)  # Do-Mi-Sol
    save_wav(os.path.join(sounds_dir, 'translate.wav'), translate_sound)
    
    # 5. Segment - Sequenza ritmica
    print("- segment.wav")
    segment_sound = generate_beep_sequence([700, 700, 900], [0.06, 0.06, 0.15], [0.03, 0.03])
    save_wav(os.path.join(sounds_dir, 'segment.wav'), segment_sound)
    
    # 6. Inpaint - Suono "whoosh" simulato
    print("- inpaint.wav")
    # Sweep di frequenza per simulare un whoosh
    duration = 0.3
    sample_rate = 44100
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    freq_sweep = 400 + 600 * (1 - t / duration)  # Da 1000Hz a 400Hz
    inpaint_sound = 0.2 * np.sin(2 * np.pi * freq_sweep * t) * np.exp(-t * 4)
    save_wav(os.path.join(sounds_dir, 'inpaint.wav'), inpaint_sound)
    
    # 7. Render - Campanello finale
    print("- render.wav")
    render_sound = generate_chord([880, 1108, 1319], 0.5)  # La-Do#-Mi (accordo di La maggiore)
    save_wav(os.path.join(sounds_dir, 'render.wav'), render_sound)
    
    print(f"\nTutti i suoni generati in: {sounds_dir}")
    print("File creati:")
    for filename in os.listdir(sounds_dir):
        if filename.endswith('.wav'):
            filepath = os.path.join(sounds_dir, filename)
            size = os.path.getsize(filepath)
            print(f"  - {filename} ({size} bytes)")

if __name__ == "__main__":
    generate_all_sounds()