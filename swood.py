from PIL import Image
import progressbar
import numpy as np
import collections
import warnings
import pyfftw
import pprint
import math
import mido
import wave
import sys

pyfftw.interfaces.cache.enable()
warnings.filterwarnings("ignore")

class WavFFT(object):
    def __init__(self, filename, chunksize):
        with wave.open(filename, "r") as wavfile:
            self.sampwidth = wavfile.getsampwidth()
            self.framerate = wavfile.getframerate()
            self.chunksize = chunksize
            self.offset = int(2**(8*max(self.sampwidth, 4))/2) #max 32-bit
            self.size = np.int32
            self.fft = None
            self.maxfreq = None
            dither = False
            if self.sampwidth == 1:
                self.size=np.int8
            elif self.sampwidth == 2:
                self.size=np.int16
            self.wav = np.zeros(wavfile.getnframes(), dtype=self.size)
            if self.sampwidth > 4:
                for i in range(0,wavfile.getnframes()):
                    self.wav[i] = int.from_bytes(wavfile.readframes(1)[:self.sampwidth], byteorder="little", signed=True) / 2**32 # 64-bit int to 32-bit
            else:
                for i in range(0,wavfile.getnframes()):
                    self.wav[i] = int.from_bytes(wavfile.readframes(1)[:self.sampwidth], byteorder="little", signed=True)
            self.wav -= int(np.average(self.wav))

    def get_fft(self):
        if not self.fft:
            spacing = float(self.framerate) / self.chunksize
            avgdata = np.zeros(self.chunksize // 2, dtype=np.float64)
            c = None
            offset = None
            for i in range(0,len(self.wav),self.chunksize):
                data = np.array(self.wav[i:i+self.chunksize], dtype=self.size)
                if len(data) != self.chunksize:
                    continue
                fft = pyfftw.interfaces.numpy_fft.fft(data)
                fft = np.abs(fft[:self.chunksize/2])
                avgdata += fft
                del data
                del fft
            if max(avgdata) == 0:
                self.chunksize = self.chunksize // 2
                self.fft = self.get_fft()
            else:
                self.fft = (avgdata, spacing)
        return self.fft
        
    def get_max_freq(self):
        if not self.maxfreq:
            fft = self.get_fft()
            self.maxfreq = (np.argmax(fft[0][1:]) * fft[1]) + (fft[1] / 2)
        return self.maxfreq

class MIDIParser(object):
    def __init__(self, path, wav, transpose=0, speed=1):
        results = collections.defaultdict(lambda: [])
        notes = collections.defaultdict(lambda: [])
        self.notecount = 0
        self.maxnotes = 0
        with mido.MidiFile(path, "r") as mid:
            time = 0
            for message in mid:
                time += message.time
                if "channel" in message.__dict__ and message.channel == 10: continue  # channel 10 is reserved for percussion
                if message.type == "note_on":
                    notes[message.note].append(time)
                    self.maxnotes = max(sum(len(i) for i in notes.values()), self.maxnotes)
                elif message.type == "note_off":
                    results[int(round(notes[message.note][0]*sample.framerate/speed))].append((int((time - notes[message.note][0]) * wav.framerate), wav.get_max_freq() / self.note_to_freq(message.note+transpose), 1 if message.velocity / 127 == 0 else message.velocity / 127))
                    notes[message.note].pop(0)
                    self.notecount += 1
            for ntime, nlist in notes.items():
                for note in nlist:
                    results[int(round(notes[note][0]*sample.framerate/speed))].append((int((ntime - time) * wav.framerate), wav.get_max_freq() / self.note_to_freq(note+transpose), 1))
                    self.notecount += 1
            self.notes = sorted(results.items())
            self.length = self.notes[-1][0] + max(self.notes[-1][1])[0]
    
    def note_to_freq(self, notenum):
        # https://en.wikipedia.org/wiki/MIDI_Tuning_Standard
        return (2.0**((notenum-69)/12.0)) * 440.0


def zoom(array, multiplier):
    array.flags.writeable = False
    im = PIL.Image.frombuffer("L", (1, len(array.data)), array.data)
    im = im.resize((1, int(round(len(array.data)*multiplier))), resample=Image.BICUBIC)
    return np.asarray(im, type=np.float64)

def render_note(note, sample, threshold):
    scaled = zoom(sample.wav[:max(int((note[0] + threshold)*note[1]),len(sample.wav))], note[1]) * note[2]
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

def run(inwav, inmid, outpath, transpose=0, speed=1, binsize=8192, threshold_mult=0.075):
    print("Loading sample into memory")
    sample = WavFFT(inwav, binsize)
    print("Analyzing sample")
    ffreq = sample.get_max_freq()
    threshold = int(float(sample.framerate) * threshold_mult)
    print("Fundamental Frequency: {} Hz".format(ffreq)) 
    print("Parsing MIDI")
    midi = MIDIParser(inmid, sample)
    print("Creating output buffer")
    output = np.zeros(midi.length + 1 + threshold, dtype=np.float64)
    print("Rendering audio")
    c = 0
    tick = 10
    notecache = {}
    bar = progressbar.ProgressBar(widgets=[progressbar.Percentage(), " ", progressbar.Bar(), " ", progressbar.ETA()], max_value=midi.notecount)
    for time, notes in midi.notes:
        for note in notes:
            if note[:2] in notecache:
                sbl = len(notecache[note[:2]][2])
                output[time:time+sbl] += notecache[note[:2]][2]
                notecache[note[:2]] = (notecache[note[:2]][0] + 1, notecache[note[:2]][1], notecache[note[:2]][2])
            else:
                rendered = render_note(note, sample, threshold)
                sbl = len(rendered)
                output[time:min(time+sbl, len(output))] += rendered[:min(time+sbl, len(output))-time]
                notecache[note[:2]] = (1, time, rendered)
            c += 1
            bar.update(c)
        # cache "garbage collection"
        tick -= 1
        if tick == 0:
            tick = 10
            for k in list(notecache.keys()):
                if (time - notecache[k][1]) > (7.5*sample.framerate) and notecache[k][0] <= 2:
                    del notecache[k]
                    
    print("Normalizing audio")

    # normalize and convert float64s into PCM int32s
    output *= ((2**32) / (abs(output.max()) + (abs(output.min()))))
    output -= output.min() + (2**32/2)
    
    print("Saving audio")
    
    with wave.open(outpath, "w") as outwav:
        outwav.setframerate(sample.framerate)
        outwav.setnchannels(1)
        outwav.setsampwidth(4)
        outwav.setnframes(len(output))
        outwav.writeframesraw(output.astype(np.int32))
        
    print("Saved to {}".format(outpath))
    
def run_cmd():
    if len(sys.argv) == 1:
        print("""swood.exe - the automatic ytpmv generator

usage: swood in_wav in_midi out_wav
  in_wav: a wav file to use as the instrument for the midi
  in_midi: a midi to output with the wav sample as the instrument
  out_wav: location for the finished song as a wav

options:
  --transpose=0      transpose the midi by n semitones
  --speed=1.0        speed up the midi by this multiplier
  --threshold=0.075  maximum amount of time after a note ends that it can go on for a smoother ending
  --binsize=8192     FFT bin size for the sample analysis; the lower this number, the more off-pitch the result could be""")
  
if __name__ == "__main__":
    run_cmd()
