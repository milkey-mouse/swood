import matplotlib.pyplot as plt
import progressbar
import numpy as np
import pyfftw
import math
import wave

pyfftw.interfaces.cache.enable()

CHUNK_SIZE = 2048

class FakeSin(object):
    def __init__(self, freq, framerate=41000, amplitude=0.8, length=10.0):
        self.framerate = framerate
        self.freq = freq
        self.amplitude = amplitude
        self.pi2 = math.pi * 2
        self.step = (self.pi2 * self.freq) / framerate
        self.length = length
        self.ls = length * framerate
        self.nframes = self.length * self.framerate
        self.pos = 0
        self.pi2 = math.pi * 2

    def getnframes(self):
        return self.nframes

    def getframerate(self):
        return self.framerate

    def readframes(self, n):
        a = []
        for i in range(n):
            if self.ls == 0:
                continue
            self.pos += self.step
            self.pos %= self.pi2
            a.append(int(round( ((math.sin(self.pos) / 2) + 0.5) * 255 )))
            self.ls -= 1
        return a

    def __exit__(self, a, b, c):
        pass

    def __enter__(self):
        return self

def get_top_freq(wav, pbar=True):
    spacing = float(orig.getframerate()) / CHUNK_SIZE
    avgdata = np.array([0]*((CHUNK_SIZE // 2) - 0), dtype="float64")
    bar = progressbar.ProgressBar()
    for _ in bar(range(math.ceil(wav.getnframes() / CHUNK_SIZE))) if pbar else range(math.ceil(wav.getnframes() / CHUNK_SIZE)):
        frames = orig.readframes(CHUNK_SIZE)
        if len(frames) != CHUNK_SIZE:
            break
        data = np.array([f - 128 for f in frames], dtype=np.int8)
        del frames
        fft = pyfftw.interfaces.numpy_fft.fft(data)
        fft = np.abs(fft[:CHUNK_SIZE/2])
        avgdata += fft
        del data
        del fft
    return (np.argmax(avgdata[1:]) * spacing) + (spacing / 2)


for f in range(100, 1000, 10):
    with FakeSin(f, length=0.05) as orig:
        ffted = get_top_freq(orig, pbar=False)
        print("Freq: {} FFT: {} | Multiplier: {} Difference: {}".format(round(f, 2), round(ffted, 2), round(ffted/f, 2), round(ffted-f, 2)))

    #plot = plt.figure(1)
    #plt.plot([(i*spacing)+spacing for i in range(len(avgdata[1:1000//spacing]))], list(avgdata[1:1000//spacing]), "r")
    #plt.xlabel("Frequency (Hz)")
    #plt.ylabel("Intensity (abs(fft[freq]))")
    #plt.title("FFT Analysis")
    #plt.show(1)
