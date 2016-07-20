import numpy as np
from . import complain
import wave


class UncachedWavFile:  # basic huge array to file

    def __init__(self, length, filename, framerate, channels=1, dtype=np.int32):
        self.channels = np.zeros((channels, length), dtype=dtype)
        self.framerate = framerate
        self.filename = filename

    def add_data(self, start, data, cutoffs):
        for chan in range(self.channels.shape[0]):
            length = min(self.channels.shape[
                         1] - start, data.shape[1], cutoffs[chan])
            self.channels[chan][
                start:start + length] += data[chan][:length].astype(self.channels.dtype)

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
                                   "NONE", "not compressed"))  # compression type (none are supported)
                    wav.writeframesraw(self.channels.reshape(self.channels.size,
                                                             order="F"))
        except IOError:
            raise complain.ComplainToUser(
                "Can't save output file '{}'.".format(self.filename))


class CachedWavFile:

    def __init__(self, length, filename, framerate, channels=1, chunksize=65536, dtype=np.int32):
        # 65536 chunk size holds ~1/3 second at 192khz
        # and ~1.5 seconds at 44.1khz (cd quality)
        self.channels = channels
        self.chunksize = chunksize
        self.framerate = framerate
        self.saved_to_disk = set()
        self.chunks = {}
        #np.zeros((self.channels, self.chunksize), dtype=dtype)

        if isinstance(self.filename, str):
            self.wavfile = open(filename, "wb+")
        else:
            self.wavfile = filename

        # write the WAV header to the file
        with wave.Wave_write(self) as wav:
            wav.initfp(wavfile)
            wav.setparams((self.channels.shape[0],  # channels
                           self.channels.dtype.itemsize,  # sample width
                           self.framerate,  # sample rate
                           self.channels.shape[1],  # number of frames
                           "NONE", "not compressed"))  # compression type (none are supported)
            wav._write_header(0)  # start at 0 length

    def add_data(self, start, data, cutoffs):
        for chan in range(self.channels.shape[0]):
            length = min(self.channels.shape[1] - start,
                         data.shape[1], cutoffs[chan])
            self.channels[chan][start:start + length] += \
                data[chan][:length].astype(self.channels.dtype)

    def flush_cache(self):

    def save_chunk(self, idx):
        self.wavfileself.chunks[idx]
        del self.chunks[idx]

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
                                   "NONE", "not compressed"))  # compression type (none are supported)
                    wav.writeframesraw(self.channels.reshape(self.channels.size,
                                                             order="F"))
        except IOError:
            raise complain.ComplainToUser(
                "Can't save output file '{}'.".format(self.filename))
