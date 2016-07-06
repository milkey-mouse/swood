import numpy as np
from . import complain
import wave


class CachedWavFile:
    pass

    
class UncachedWavFile:
    def __init__(self, length, filename, framerate, channels=1, dtype=np.int32):
        self.channels = np.zeros((channels, length), dtype=dtype)
        self.framerate = framerate
        self.filename = filename

    def add_data(self, start, data, cutoffs):
        for chan in range(self.channels.shape[0]):
            #print(self.channels.shape[1] - start)
            #print(data.shape[1])
            #print(cutoffs[chan])
            length = min(self.channels.shape[1] - start, data.shape[1], cutoffs[chan])
            self.channels[chan][start:start + length] += data[chan][:length].astype(self.channels.dtype)

    def save(self):
        # we can't use a with statement with wave.open here
        # because wave.open throws a really weird error I can't catch
        try:
            with (open(self.filename, "wb") if isinstance(self.filename, str) else self.filename) as wavfile:
                with wave.Wave_write(self) as wav:
                    wav.initfp(wavfile)
                    wav.setparams((self.channels.shape[0],  # channels
                                   self.channels.dtype.itemsize,  # sample width
                                   self.framerate,  # sample rate
                                   self.channels.shape[1],  # number of frames
                                   "NONE", "not compressed"))  # compression type
                    wav.writeframesraw(self.channels.reshape(self.channels.size, order="F"))
        except IOError:
            raise complain.ComplainToUser("Can't save output file '{}'.".format(self.filename))
