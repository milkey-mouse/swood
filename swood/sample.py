from PIL import Image
import numpy as np
from . import complain
import pyfftw
import wave

pyfftw.interfaces.cache.enable()


class CalculatedFFT:
    def __init__(self, avgdata, spacing):
        self.avgdata = avgdata
        self.spacing = spacing


class Sample:
    def __init__(self, filename, binsize, volume=0.8, delete_raw_data=True):
        self.binsize = binsize

        if binsize < 2:
            raise complain.ComplainToUser("FFT bin size must be at least 2.")

        self.delete_raw = delete_raw_data  # delete raw data after FFT analysis
        self._maxfreq = None
        self._fft = None

        self.wav = self.parse_wav(filename)

        max_amplitude = float(max(max(abs(min(chan)), abs(max(chan))) for chan in self.wav))
        self.volume = 256 ** 4 / (max_amplitude * 2) * volume
        self.img = Image.frombytes("I",
                                   (self.length, self.channels),
                                   self.wav.astype(np.int32).tobytes(),
                                   "raw", "I", 0, 1)
        # Pillow recommends those last args because of a bug in the raw parser
        # See http://pillow.readthedocs.io/en/3.2.x/reference/Image.html?highlight=%22raw%22#PIL.Image.frombuffer

    def parse_wav(self, filename):
        try:
            with wave.open(filename, "rb") as wavfile:
                self.sampwidth = wavfile.getsampwidth()
                self.framerate = wavfile.getframerate()
                self.channels = wavfile.getnchannels()
                self.length = wavfile.getnframes()

                if self.sampwidth == 1:
                    self.size = np.int8
                elif self.sampwidth == 2:
                    self.size = np.int16
                elif self.sampwidth == 3 or self.sampwidth == 4:
                    self.size = np.int32
                else:
                    raise wave.Error

                wav = np.zeros((self.channels, self.length), dtype=self.size)
                for i in range(0, self.length):
                    frame = wavfile.readframes(1)
                    for chan in range(self.channels):
                        wav[chan][i] = int.from_bytes(frame[self.sampwidth * chan:self.sampwidth * (chan + 1)], byteorder="little", signed=True)
                return wav
        except IOError:
            raise complain.ComplainToUser("Error opening WAV file at path '{}'.".format(filename))
        except wave.Error:
            raise complain.ComplainToUser("This WAV type is not supported. Try opening the file in Audacity and exporting it as a standard WAV.")

    @property
    def fft(self):
        if not self._fft:
            if self.binsize % 2 != 0:
                print("Warning: Bin size must be a multiple of 2, correcting automatically")
                self.binsize += 1
            spacing = float(self.framerate) / self.binsize
            avgdata = np.zeros(self.binsize // 2, dtype=np.float64)
            for chan in range(self.channels):
                for i in range(0, self.wav.shape[1], self.binsize):
                    data = np.array(self.wav[chan][i:i + self.binsize], dtype=self.size)
                    if len(data) != self.binsize:
                        continue
                    fft = pyfftw.interfaces.numpy_fft.fft(data)
                    fft = np.abs(fft[:self.binsize // 2])
                    avgdata += fft
                    del data
                    del fft
            if max(avgdata) == 0:
                print("Warning: Bin size is too large to analyze sample; dividing by 2 and trying again")
                self.binsize = self.binsize // 2
                self._fft = self.fft
            else:
                if self.delete_raw:
                    del self.wav
                self._fft = CalculatedFFT(avgdata, spacing)
        return self._fft

    @property
    def maxfreq(self):
        if not self._maxfreq:
            self._maxfreq = (np.argmax(self.fft.avgdata[1:]) * self.fft.spacing) + (self.fft.spacing / 2)
        return self._maxfreq

    def __len__(self):
        return self.length
