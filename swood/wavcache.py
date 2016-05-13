import numpy as np

import wave

import complain


class CachedWavFile:
    pass


class UncachedWavFile:
    def __init__(self, length, filename, framerate, channels=1, dtype=np.int32):
        self.channels = np.zeros((channels, length), dtype=dtype)
        self.framerate = framerate
        self.filename = filename

    def add_data(self, start, data, channel=0):
        # cut it off at the end of the file in case of cache shenanigans
        length = min(self.channels.shape[1] - start, data.shape[1])
        if channel == -1:
            for chan in range(self.channels.shape[0]):
                self.channels[chan][start:start + length] += data[chan][:length]
        else:
            self.channels[channel][start:start + length] += data[:length]

    def save(self):
        try:
            with wave.open(self.filename, "wb") as wavfile:
                wavfile.setparams((self.channels.shape[0], self.channels.dtype.itemsize, self.framerate, self.channels.shape[1], "NONE", "not compressed"))
                wavfile.writeframesraw(self.channels.reshape(self.channels.size, order="F"))
        except IOError:
            raise complain.ComplainToUser("Error saving output file '{}'.".format(self.filename))
