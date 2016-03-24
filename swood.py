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

CHUNK_SIZE = 4096
FINAL_SAMPLE_RATE = 44100

def load_wav(filename, new_sr):
    with wave.open(filename, "r") as wavfile:
        sw = wavfile.getsampwidth()
        dither = False
        offset = 0
        size = None
        if sw == 1:
            dtype=np.uint8
            offset = 127
        elif sw == 2:
            dtype=np.uint16
            offset = 32767
        elif sw == 3 or sw == 4:
            dtype=np.uint32
            offset = 2147483647
        else:
            dtype=np.uint32
            offset = 2147483647
            dither = True
        wav = np.zeros(wavfile.getnframes(), dtype=size)
        if dither:
            for i in range(0,wavfile.getnframes()):
                wav[i] = (int.from_bytes(wavfile.readframes(1)[:sw], byteorder="little", signed=True) / 4294967297) + offset # 64-bit uint to 32-bit
        else:
            for i in range(0,wavfile.getnframes()):
                wav[i] = int.from_bytes(wavfile.readframes(1)[:sw], byteorder="little", signed=True) + offset
        wav -= wav.min()
        return (wav, wavfile.getframerate(), offset, size)

def get_fft(orig, pbar=True):
    spacing = float(orig[1]) / CHUNK_SIZE
    avgdata = np.array([0]*((CHUNK_SIZE // 2)), dtype="float64")
    c = None
    offset = None
    bar = progressbar.ProgressBar(widgets=[progressbar.Percentage(), " ", progressbar.Bar()])
    for i in range(0,len(orig[0]),CHUNK_SIZE):
        data = np.array(orig[0][i:i+CHUNK_SIZE], dtype=orig[3])
        if len(data) != 4096:
            break
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

def plot_wav(wav):
    import matplotlib.pyplot as plt
    plot = plt.figure(1)
    plt.plot(range(len(wav)), wav, "r")
    plt.title = "Audio File Waveform"
    plt.show(1)

def parse_midi(midipath, ffreq):
    results = collections.defaultdict(lambda: [])
    notes = collections.defaultdict(lambda: [])
    with mido.MidiFile(midipath) as mid:
        curtime = 0
        lasttime = 0
        for message in mid: #note_to_freq(message.note) / ffreq
            curtime += message.time
            if "channel" in message.__dict__ and message.channel == 10: continue #channel 10 is reserved for percussion
            if message.type == "note_on":
                notes[message.note].append(curtime)
                lasttime = curtime
            elif message.type == "note_off":
                results[notes[message.note][0]].append((int((curtime - notes[message.note][0])*FINAL_SAMPLE_RATE), ffreq / note_to_freq(message.note)))
                notes[message.note].pop(0)
                lasttime = curtime
        for time, nlist in notes.items():
            for note in nlist:
                results[time].append((int((curtime - time)*FINAL_SAMPLE_RATE), ffreq / note_to_freq(note)))
        return ([(int(round(k*FINAL_SAMPLE_RATE)),results[k]) for k in sorted(results.keys())], lasttime)

ffreq = None

print("Loading sound clip into memory...")
orig = load_wav(sys.argv[1] if len(sys.argv) > 1 else "440.wav", FINAL_SAMPLE_RATE)
print("Analyzing sound clip...")
ffreq = get_max_freq(get_fft(orig))
print("Fundamental Frequency: {} Hz".format(ffreq))
if orig[1] != FINAL_SAMPLE_RATE:
    print("Scaling to the right sample rate.")
    wavfile = scipy.ndimage.zoom(effect, FINAL_SAMPLE_RATE / orig[1])
print("Parsing MIDI...")
notelist, midi_length = parse_midi(sys.argv[2] if len(sys.argv) > 2 else "badtime.mid", ffreq)
output = np.array([0]*(int(FINAL_SAMPLE_RATE*midi_length) + 1), dtype=np.float64)
mask = np.zeros_like(output, dtype=np.uint8) # np.bool_ isn't actually any cheaper
maxnotes = 0
threshold = int(float(FINAL_SAMPLE_RATE) * 0.075)
for time, notes in notelist:
    maxnotes += len(notes)
print("Rendering audio...")
bar = progressbar.ProgressBar(widgets=[progressbar.Percentage(), " ", progressbar.Bar(), " ETA ", progressbar.ETA()], max_value=maxnotes)
c = 0
for time, notes in notelist:
    for note in notes:
        scaled = scipy.ndimage.zoom(orig[0], note[1])[:note[0] + threshold]
        avg = (scaled.max() + scaled.min()) / 2
        cutoff = np.argmin([abs(i-avg)+(d*20) for d, i in enumerate(scaled[note[0]:])])
        output[time:time+note[0]+cutoff] += scaled[:note[0]+cutoff]
        mask[time:time+note[0]] = 1
        c += 1
        bar.update(c)
output[mask == 0] += ((output.max() + output.min()) / 2)
output -= output.min()
output *= (4294967295 / output.max())
output -= ((output.max() + output.min()) / 2)
output = output.astype(np.int32)
with wave.open(sys.argv[3] if len(sys.argv) > 3 else "out.wav", "w") as outwav:
    outwav.setframerate(FINAL_SAMPLE_RATE)
    outwav.setnchannels(1)
    outwav.setsampwidth(4)
    outwav.setnframes(len(output))
    outwav.writeframesraw(output)
