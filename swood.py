import matplotlib.pyplot as plt
import numpy as np
import pyfftw
import wave
import sys

#pyfftw.interfaces.cache.enable()

with wave.open("440.wav", "r") as orig:
    Fs = int(orig.getframerate())
    data = np.array([f - 128 for f in orig.readframes(orig.getnframes())], dtype=np.int8)
    n = len(data)
    k = np.arange(n)
    T = n/Fs
    frq = k/T
    frq = frq[range(int(n/2))]

    Y = abs(pyfftw.interfaces.numpy_fft.fft(data))**2
    which = Y[1:].argmax() + 1
    thefreq = which*Fs/len(data)
    print("The freq is %f Hz." % (thefreq))
    #sys.exit()

    plot = plt.figure(1)
    plt.plot(Y, range(len(Y)), "r")
    plt.xlabel("Frequency (Hz)")
    plt.ylabel("Intensity (abs(fft[freq]))")
    plt.title("FFT Analysis")
    plt.show(1)
