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

class WavFFT(object):
    def __init__(self, filename):
        with wave.open(filename, "r") as wavfile:
            self.sampwidth = wavfile.getsampwidth()
            self.framerate = wavfile.getframerate()
            self.offset = offset = int(max(2**(8*self.sampwidth)/2, 2147483647))  # max 32 bit
            self.size = np.uint32
            self.fft = False
            dither = False
            if self.sampwidth == 1:
                self.size=np.uint8
            elif self.sampwidth == 2:
                self.size=np.uint16
            self.wav = np.zeros(wavfile.getnframes(), dtype=self.size)
            if self.sampwidth > 4:
                for i in range(0,wavfile.getnframes()):
                    self.wav[i] = (int.from_bytes(wavfile.readframes(1)[:self.sampwidth], byteorder="little", signed=True) / 2**32) # 64-bit uint to 32-bit
            else:
                for i in range(0,wavfile.getnframes()):
                    self.wav[i] = int.from_bytes(wavfile.readframes(1)[:self.sampwidth], byteorder="little", signed=True)

    def get_fft(self, pbar=True):
        if not self.fft:
            spacing = float(self.framerate) / CHUNK_SIZE
            avgdata = np.array([0]*((CHUNK_SIZE // 2)), dtype="float64")
            c = None
            offset = None
            bar = progressbar.ProgressBar(widgets=[progressbar.Percentage(), " ", progressbar.Bar()])
            for i in range(0,len(self.wav),CHUNK_SIZE):
                data = np.array([i+self.offset for i in self.wav[i:i+CHUNK_SIZE]], dtype=self.size)
                data += self.offset
                if len(data) != 4096:
                    break
                fft = pyfftw.interfaces.numpy_fft.fft(data)
                fft = np.abs(fft[:CHUNK_SIZE/2])
                avgdata += fft
                del data
                del fft
            self.fft = (avgdata, spacing)
        return self.fft

    def plot_wav(self):
        import matplotlib.pyplot as plt
        plot = plt.figure(1)
        plt.plot(range(len(self.wav)), self.wav, "r")
        plt.xlabel("Amplitude")
        plt.ylabel("Time")
        plt.title("Audio File Waveform")
        plt.show(1)

    def plot_fft(self):
        import matplotlib.pyplot as plt
        plot = plt.figure(1)
        plt.plot([(i*self.fft[1])+self.fft[1] for i in range(len(self.fft[0][1:1000//self.fft[1]]))], list(fft[0][1:1000//self.fft[1]]), "r")
        plt.xlabel("Frequency (Hz)")
        plt.ylabel("Intensity (abs(fft[freq]))")
        plt.title("FFT Analysis")
        plt.show(1)

    def get_max_freq(self):
        fft = self.get_fft()
        return (np.argmax(fft[0][1:]) * fft[1]) + (fft[1] / 2)

class MIDIParser(object):
    def __init__(self, path, orig_freq):
        results = collections.defaultdict(lambda: [])
        notes = collections.defaultdict(lambda: [])
        self.notecount = 0
        with mido.MidiFile(path, "r") as mid:
            time = 0
            for message in mid:
                time += message.time
                if "channel" in message.__dict__ and message.channel == 10: continue  # channel 10 is reserved for percussion
                if message.type == "note_on":
                    notes[message.note].append(time)
                elif message.type == "note_off":
                    results[int(round(notes[message.note][0]*FINAL_SAMPLE_RATE))].append((int(time - notes[message.note][0]) * FINAL_SAMPLE_RATE, orig_freq / self.note_to_freq(message.note)))
                    notes[message.note].pop(0)
                    self.notecount += 1
            for ntime, nlist in notes.items():
                for note in nlist:
                    results[int(round(notes[note][0]*FINAL_SAMPLE_RATE))].append((int(ntime - time) * FINAL_SAMPLE_RATE, orig_freq / self.note_to_freq(note)))
                    self.notecount += 1
            self.notes = sorted(results.items())
            self.length = self.notes[-1][0] + max(self.notes[-1][1])[0]
    
    def note_to_freq(self, notenum):
        # https://en.wikipedia.org/wiki/MIDI_Tuning_Standard
        return (2.0**((notenum-69)/12.0)) * 440.0

notecache = {}
threshold = int(float(FINAL_SAMPLE_RATE) * 0.075)

def render_note(note, orig, threshold):
    scaled = scipy.ndimage.zoom(orig.wav, note[1])
    if len(scaled) < note[0] + threshold:
        return scaled
    else:
        scaled = scaled[:note[0] + threshold]
        cutoff = np.argmin([abs(i)+(d*20) for d, i in enumerate(scaled[note[0]:])])
        return scaled[:note[0]+cutoff]

def hash_array(arr):
    arr.flags.writeable = False
    result = hash(arr.data)
    arr.flags.writeable = True
    return result

ffreq = None

print("Loading sound clip into memory...")
orig = WavFFT(sys.argv[1] if len(sys.argv) > 1 else "doot.wav")
print("Analyzing sound clip...")
ffreq = orig.get_max_freq()
print("Fundamental Frequency: {} Hz".format(ffreq))
if orig.framerate != FINAL_SAMPLE_RATE:
    print("Scaling to the right sample rate.")
    wavfile = scipy.ndimage.zoom(effect, FINAL_SAMPLE_RATE / orig.framerate)
print("Parsing MIDI...")
midi = MIDIParser(sys.argv[2] if len(sys.argv) > 2 else "badtime.MID", ffreq)
print("Rendering audio...")
output = np.empty(midi.length + 1 + threshold, dtype=np.int64)
output.fill(orig.offset)
maxnotes = 0
bar = progressbar.ProgressBar(widgets=[progressbar.Percentage(), " ", progressbar.Bar(), " ", progressbar.ETA()], max_value=midi.notecount)
c = 0
tick = 10
for time, notes in midi.notes:
    for note in notes:
        if note in notecache:
            sbl = len(notecache[note][2])
            output[time:time+sbl] += notecache[note][2]
            notecache[note] = (notecache[note][0] + 1, notecache[note][1], notecache[note][2])
        else:
            rendered = render_note(note, orig, threshold)
            sbl = len(rendered)
            notecache[note] = (1, time, rendered)
            output[time:time+sbl] += rendered
        c += 1
        bar.update(c)
    tick -= 1
    if tick == 0:
        tick = 10
        for k in list(notecache.keys()):
            if (time - notecache[k][1]) > (7.5*FINAL_SAMPLE_RATE) and notecache[k][0] <= 2:
                del notecache[k]
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
