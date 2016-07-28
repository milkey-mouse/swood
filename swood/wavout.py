from numpy import zeros, int32
from . import complain
import collections
import wave


class UncachedWavFile:  # basic huge array to file

    def __init__(self, length, filename, framerate, channels=1, dtype=int32):
        self.channels = zeros((channels, length), dtype=dtype)
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
                    nframes = len(data) // (self._sampwidth * self._nchannels)
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

    def __init__(self, length, filename, framerate, channels=1, chunksize=65536, dtype=int32):
        # 65536 chunk size holds ~1/3 second at 192khz
        # and ~1.5 seconds at 44.1khz (cd quality)
        self.framerate = framerate
        self.dtype = dtype
        self.channels = channels
        self.chunksize = chunksize

        self.chunkspacing = self.channels * self.chunksize * self.dtype.itemsize

        self.saved_to_disk = set()
        self.chunks = collections.defaultdict(self.create_chunk)

        if isinstance(filename, str):
            self.wavfile = open(filename, "wb+")
            self._auto_close = true
        else:
            self.wavfile = filename
            self._auto_close = false

        self.wav = wave.Wave_write(self)
        self.wav.initfp(self.wavfile)
        wav.setparams((channels, self.dtype.itemsize,
                       self.framerate, 0, "NONE", "not compressed"))
        wav._write_header(0)  # start at 0 length and patch header later
        self._header_length = self.wavfile.tell()

    def create_chunk(self):
        # todo: check self.saved_to_disk and use np.fromfile to load
        return zeros((self.channels, self.chunksize), dtype=self.dtype)

    def save_chunk(self, idx):
        self.wavfile.seek(self._header_length + (self.chunkspacing * idx))
        chunk = self.chunks[idx]
        chunk.reshape(chunk.size, order="F").tofile(self.wavfile)
        del self.chunks[idx]
        self.saved_to_disk.add(idx)

    def flush_cache(self, to_idx=None):
        # we should still sort the keys even though it's theoretically not needed
        # because sequential disk writes are faster on both SSDs and hard disks
        for idx in sorteddict.keys():
            if to_idx is not None and idx <= to_idx:
                break
            else:
                self.save_chunk(idx)
        dict.clear()

    def add_data(self, start, data, cutoffs):
        chunksize = self.chunksize
        chunk_offset = (start % chunksize)
        chunk_start = start // chunksize
        for chan in range(self.channels):
            chandata = data[chan]
            if cutoffs[chan] + chunk_offset <= chunksize:
                self.chunks[chunk_start][chan][chunk_offset:chunk_offset + cutoffs[chan]] = \
                    chandata[:cutoffs[chan]]
            else:
                self.chunks[chunk_start][chan][chunk_offset:] = \
                    chandata[:chunksize - chunk_offset]
                bytes_remaining = cutoffs[chan] - chunksize + chunk_offset
                chunk_start += 1
                while bytes_remaining >= chunksize:
                    self.chunks[chunk_start][chan] = \
                        chandata[-bytes_remaining:-bytes_remaining + chunksize]
                    chunk_start += 1
                self.chunks[chunk_start][chan][:bytes_remaining] = \
                    chandata[-bytes_remaining:]

    def save(self):
        self.flush_cache()
        if self._auto_close:
            self.wavfile.close()
