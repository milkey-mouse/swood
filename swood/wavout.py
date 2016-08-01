from numpy import zeros, int32, fromfile, dtype, full
from numpy import dtype as dtype_info
from . import complain

from collections import defaultdict
import wave


class UncachedWavFile:
    """Creates a single large array for the output and writes it to disk at the end."""
    def __init__(self, length, filename, framerate, channels=1, dtype=int32):
        self.channels = zeros((channels, length), dtype=dtype)
        self.framerate = framerate
        self.filename = filename

    def add_data(self, start, data, cutoffs=None):
        """Add sound data at a specified position.
        
        Args:
            start: How many samples into the output the data should start
            data: A NumPy array of data to add to the output.
            cutoffs: An array of integers that specifies where to cut off each channel. (optional)
        """
        if cutoffs is None:
            cutoffs = full(self.channels.shape[0], scaled.shape[1], dtype=int32)
        for chan in range(self.channels.shape[0]):
            length = min(self.channels.shape[
                         1] - start, data.shape[1], cutoffs[chan])
            self.channels[chan][
                start:start + length] += data[chan][:length].astype(self.channels.dtype)

    def save(self):
        """Write the output array to the file."""
        try:
            # open the file manually to catch I/O exceptions
            # as IOError instead of wave.Error
            with (open(self.filename, "wb") if isinstance(self.filename, str) else self.filename) as wavfile:
                with wave.open(wavfile, "w") as wav:
                    wav.setparams((self.channels.shape[0],  # channels
                                   self.channels.dtype.itemsize,  # sample width
                                   self.framerate,  # sample rate
                                   self.channels.shape[1],  # number of frames
                                   "NONE", "not compressed"))  # compression type (none are supported)
                    wav.writeframesraw(self.channels.flatten(order="F"))
        except IOError:
            raise complain.ComplainToUser(
                "Can't save output file '{}'.".format(self.filename))


class defaultdictkey(defaultdict):
    """Variation of collections.defaultdict that passes the key into the factory."""

    def __missing__(self, key):
        self[key] = self.default_factory(key)
        return self[key]


class CachedWavFile:

    def __init__(self, length, filename, framerate, channels=1, chunksize=32768, dtype=int32):
        # 32768 chunk size holds ~1/6 second at 192khz
        # and ~0.75 seconds at 44.1khz (cd quality)
        self.framerate = framerate
        self.channels = channels
        self.chunksize = chunksize

        self.dtype = dtype
        self.itemsize = dtype_info(self.dtype).itemsize
        self.chunkspacing = self.channels * self.chunksize * self.itemsize

        self.saved_to_disk = set()
        self.chunks = defaultdictkey(self.create_chunk)

        if isinstance(filename, str):
            self.wavfile = open(filename, "wb+")
            self._auto_close = true
        else:
            self.wavfile = filename
            self._auto_close = False

        self.wav = wave.Wave_write(self)
        self.wav.close = lambda: None
        self.wav.initfp(self.wavfile)

        self.wav.setparams((channels, self.itemsize, self.framerate,
                            0, "NONE", "not compressed"))
        self.wav._write_header(0)  # start at 0 length and patch header later
        self._header_length = self.wavfile.tell()

    def create_chunk(self, key):
        if key in self.saved_to_disk:
            return self.load_chunk(key)
        else:
            return zeros((self.channels, self.chunksize), dtype=self.dtype)

    def load_chunk(self, idx):
        raise NotImplementedError  # not needed for linear writes and I'm too lazy
        self.saved_to_disk.discard(idx)
        self.wavfile.seek(self._header_length + (self.chunkspacing * idx))
        raw_data = fromfile(self.wavfile, dtype=self.dtype,
                            count=self.channels * self.chunksize)
        return raw_data.reshape((self.channels, self.chunksize), order="F")

    def save_chunk(self, idx):
        self.wavfile.seek(self._header_length + (self.chunkspacing * idx))
        self.chunks[idx].flatten(order="F").tofile(self.wavfile)
        self.saved_to_disk.add(idx)
        del self.chunks[idx]

    def flush_cache(self, to_idx=None):
        # we should still sort the keys even though it's theoretically not needed
        # because sequential disk writes are faster on both SSDs and hard disks
        for idx in sorted(self.chunks.keys()):
            if to_idx is not None and idx >= to_idx:
                break
            else:
                self.save_chunk(idx)

    def add_data(self, start, data, cutoffs):
        data = data.astype(self.dtype)
        chunksize = self.chunksize
        chunk_start = start // chunksize
        chunk_offset = start - (chunk_start * chunksize)
        for chan in range(self.channels):
            current_chunk = chunk_start
            cutoff = min(cutoffs[chan], len(data[chan]))
            if cutoff + chunk_offset <= chunksize:
                self.chunks[current_chunk][chan][chunk_offset:chunk_offset + cutoff] += \
                    data[chan][:cutoff]
            else:
                self.chunks[current_chunk][chan][chunk_offset:] += \
                    data[chan][:chunksize - chunk_offset]
                bytes_remaining = cutoff - chunksize + chunk_offset
                current_chunk += 1
                while bytes_remaining >= chunksize:
                    self.chunks[current_chunk][chan] += \
                        data[chan][cutoff - bytes_remaining:
                                   cutoff - bytes_remaining + chunksize]
                    current_chunk += 1
                    bytes_remaining -= chunksize
                self.chunks[current_chunk][chan][:bytes_remaining] += \
                    data[chan][cutoff - bytes_remaining:cutoff]
        self.flush_cache(chunk_start)

    def save(self):
        self.flush_cache()
        self.wav._datawritten = (
            max(self.saved_to_disk) + 1) * self.chunkspacing
        self.wav._patchheader()
        if self._auto_close:
            self.wavfile.close()
