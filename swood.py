from scipy.io import wavfile
import scipy.ndimage
import progressbar
import numpy as np
import collections
import pyfftw
import pprint
import math
import mido
import wave
import sys

pyfftw.interfaces.cache.enable()

CHUNK_SIZE = 8192
FINAL_SAMPLE_RATE = 44100

def get_fft(wav, pbar=True):
    spacing = float(orig.getframerate()) / CHUNK_SIZE
    avgdata = np.array([0]*((CHUNK_SIZE // 2) - 0), dtype="float64")
    c = None
    bar = progressbar.ProgressBar(widgets=[progressbar.Percentage(), " ", progressbar.Bar()])
    for _ in bar(range(math.ceil(wav.getnframes() / CHUNK_SIZE))) if pbar else range(math.ceil(wav.getnframes() / CHUNK_SIZE)):
        frames = orig.readframes(CHUNK_SIZE)
        if not c:
            c = len(frames)
        if len(frames) != c:
            break
        data = np.array([f - 128 for f in frames], dtype=np.int8)
        del frames
        fft = pyfftw.interfaces.numpy_fft.fft(data)
        fft = np.abs(fft[:CHUNK_SIZE/2])
        avgdata += fft
        del data
        del fft
    return (avgdata, spacing)

def get_max_freq(fft):
    return (np.argmax(fft[0][1:]) * fft[1]) + (fft[1] / 2)

def note_to_freq(notenum):
    #https://en.wikipedia.org/wiki/MIDI_Tuning_Standard
    return (2.0**((notenum-69)/12.0)) * 440.0

def plot_fft(fft):
    import matplotlib.pyplot as plt
    plot = plt.figure(1)
    plt.plot([(i*fft[1])+fft[1] for i in range(len(fft[0][1:1000//fft[1]]))], list(fft[0][1:1000//fft[1]]), "r")
    plt.xlabel("Frequency (Hz)")
    plt.ylabel("Intensity (abs(fft[freq]))")
    plt.title("FFT Analysis")
    plt.show(1)

def parse_midi(midipath, ffreq):
    results = collections.defaultdict(lambda: [])
    notes = collections.defaultdict(lambda: [])
    with mido.MidiFile(midipath) as mid:
        curtime = 0
        for message in mid: #note_to_freq(message.note) / ffreq
            curtime += message.time
            if "channel" in message.__dict__ and message.channel != 0: continue
            if message.type == "note_on":
                notes[message.note].append(curtime)
            elif message.type == "note_off":
                results[notes[message.note][0]].append((int((curtime - notes[message.note][0])*FINAL_SAMPLE_RATE), note_to_freq(message.note) / ffreq))
                notes[message.note].pop(0)
        for time, nlist in notes.items():
            for note in nlist:
                results[time].append((int((curtime - time)*FINAL_SAMPLE_RATE), note_to_freq(note) / ffreq))
        for k in results.keys():
            results[k] = results[k]
        return ([(int(round(k*FINAL_SAMPLE_RATE)),results[k]) for k in sorted(results.keys())], curtime)

ffreq = None

with wave.open(sys.argv[1] if len(sys.argv) > 1 else "440.wav") as orig:
    print("Analyzing sound clip...")
    fft = get_fft(orig)
    ffreq = get_max_freq(fft)
    print("Fundamental Frequency: {} Hz".format(ffreq))
    del fft
    print("Loading sound clip into memory...")
    effect = wavfile.read(sys.argv[1] if len(sys.argv) > 1 else "440.wav")[1]
    effect += abs(effect.min())
    if len(effect.shape) > 1:
        print("Muxing stereo audio down to mono.")
        effect = np.average(effect, axis=1)
    effect = np.divide(effect, effect.max() / 255)
    effect = effect.astype(np.uint8)
    print("Parsing MIDI...")
    notelist, midi_length = parse_midi(sys.argv[2] if len(sys.argv) > 2 else "swood.mid", ffreq)
    output = np.array([-1]*(int(FINAL_SAMPLE_RATE*midi_length) + 1), dtype=np.int32)
    maxnotes = 0
    for time, notes in notelist:
        maxnotes += len(notes)
    print("Rendering audio...")
    bar = progressbar.ProgressBar(widgets=[progressbar.Percentage(), " ", progressbar.Bar()], max_value=maxnotes)
    c = 0
    for time, notes in notelist:
        for note in notes:
            output[time:time+note[0]] += effect[:note[0]] #scipy.ndimage.zoom(effect, note[1])
            c += 1
            bar.update(c)
        pass
    #output[output == -1] = max(output) / 2
    output = np.round(output * (255 / max(output))).astype(np.uint8)
    with wave.open(sys.argv[3] if len(sys.argv) > 3 else "out.wav", "w") as outwav:
        outwav.setframerate(FINAL_SAMPLE_RATE)
        outwav.setnchannels(1)
        outwav.setsampwidth(1)
        outwav.setnframes(len(output))
        outwav.writeframesraw(output)
