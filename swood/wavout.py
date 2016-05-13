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

    def add_data(self, start, data):
        # cut it off at the end of the file in case of cache shenanigans
        length = min(self.channels.shape[1] - start, data.shape[1])
        for chan in range(self.channels.shape[0]):
            self.channels[chan][start:start + length] += data[chan][:length]

    def save(self):
        # we can't use a with statement with wave.open here
        # because wave.open throws a really weird error I can't catch
        try:
            with open(self.filename, "wb") as wavfile:
                with wave.Wave_write(self) as wav:
                    wav.initfp(wavfile)
                    wav.setparams((self.channels.shape[0], #channels
                                   self.channels.dtype.itemsize, #sample width
                                   self.framerate, #sample rate
                                   self.channels.shape[1], #number of frames
                                   "NONE", "not compressed")) #compression type
                    wav.writeframesraw(self.channels.reshape(self.channels.size, order="F"))
        except IOError:
            raise complain.ComplainToUser("Can't save output file '{}'.".format(self.filename))
