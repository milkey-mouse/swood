import wave

from PIL import Image
import numpy as np
import pyfftw

pyfftw.interfaces.cache.enable()
        
class CalculatedFFT:
    def __init__(self, avgdata, spacing):
        self.avgdata = avgdata
        self.spacing = spacing


class Sample:
    def __init__(self, filename, binsize, volume=0.9, delete_raw_data=True):
        if binsize >= 512:
            self.binsize = binsize
        else:
            raise ComplainToUser("Bin size is too low. Absolute minimum is 512.")

        if volume > 0:
            self.volume = volume
        else:
            raise ComplainToUser("Volume canot be a negative number.")

        self.delete_raw = delete_raw_data  # delete raw data after FFT analysis
        self._maxfreq = None
        self._fft = None

        self.wav = self.parse_wav()

        volume_mult = 256 ** (4 - self.sampwidth)
        raw_data = (self.wav * (volume_mult * self.volume)).astype(np.int32).tobytes()
        self.img = Image.frombytes("I", (self.length, self.channels), raw_data, "raw", "I", 0, 1)

    def parse_wav(self):
        with wave.open(filename, "rb") as wavfile:
            try:
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
            except wave.Error:
                raise ComplainToUser("This WAV type is not supported. Try opening the file in Audacity and exporting it as a standard WAV.")

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