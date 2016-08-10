from numpy import zeros, int32, fromfile, full, ndarray
from numpy import dtype as dtype_info
from collections import defaultdict
from . import complain
import mmap
import wave
import os


class UncachedWavFile:
    """Creates a single large array for the output and writes it to disk at the end."""

    def __init__(self, length, filename, framerate, channels=1, dtype=int32):
        self.channels = zeros((channels, length), dtype=dtype)
        self.framerate = framerate
        self.filename = filename

    def add_data(self, start, data, cutoffs=None):
        """Add sound data at a specified position.

        Args:
            start: How many samples into the output the data should start.
            data: A NumPy array of data to add to the output.
            cutoffs: An array of integers that specifies where to cut off each channel. (optional)
        """
        if cutoffs is None:
            cutoffs = full(self.channels.shape[
                           0], scaled.shape[1], dtype=int32)
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


def CachedWavFile(*args, **kwargs):
    """Tries to create a MemMapWavFile and falls back to ChunkedWavFile."""

    # Windows doesn't like mmap'ing as non-admin
    if os.name == "nt":
        try:
            import ctypes
            if ctypes.windll.shell32.IsUserAnAdmin() == 0:
                return ChunkedWavFile(*args, **kwargs)
        except:
            pass

    try:
        return MemMapWavFile(*args, **kwargs)
    except PermissionError:
        return ChunkedWavFile(*args, **kwargs)
    except (Exception, e):
        # Probably has more obscure errors here so just ignore them
        return ChunkedWavFile(*args, **kwargs)  # shh bby is ok


class MemMapWavFile:
    """Uses memory mapped arrays to easily cache WAV files."""

    def __init__(self, length, filename, framerate, channels=1, dtype=int32):
        # this was so much simpler to write than ChunkedWavFile
        # really wish i learned about memmap before writing it
        if isinstance(filename, str):
            self.wavfile = open(filename, "wb+")
            self._auto_close = True
        else:
            self.wavfile = filename
            self._auto_close = False

        wav = wave.Wave_write(self)
        wav.close = lambda: None
        wav.initfp(self.wavfile)
        wav.setparams((channels, dtype_info(dtype).itemsize,
                       framerate, length, "NONE", "not compressed"))
        wav._write_header(length)
        del wav
        self.wavfile.flush()
        self.wav_memmap = mmap.mmap(self.wavfile.fileno(),
                                    length * dtype_info(dtype).itemsize,
                                    access=mmap.ACCESS_WRITE)
        self.channels = ndarray((channels, length), dtype,
                                self.wav_memmap, self.wavfile.tell(), order="F")
        self.framerate = framerate
        self.filename = filename

    def add_data(self, start, data, cutoffs=None):
        """Add sound data at a specified position.

        Args:
            start: How many samples into the output the data should start.
            data: A NumPy array of data to add to the output.
            cutoffs: An array of integers that specifies where to cut off each channel. (optional)
        """
        if cutoffs is None:
            cutoffs = full(self.channels.shape[
                           0], scaled.shape[1], dtype=int32)
        for chan in range(self.channels.shape[0]):
            length = min(self.channels.shape[
                         1] - start, data.shape[1], cutoffs[chan])
            self.channels[chan][
                start:start + length] += data[chan][:length].astype(self.channels.dtype)

    def save(self):
        del self.wav_mmap  # the way to close a memmap is to delete it
        if self._auto_close:
            self.wavfile.close()


class defaultdictkey(defaultdict):
    """Variation of collections.defaultdict that passes the key into the factory."""

    def __missing__(self, key):
        self[key] = self.default_factory(key)
        return self[key]


class ChunkedWavFile:
    """Uses chunks of data to efficiently write a WAV file to disk without storing a large array."""

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
        self.chunks = defaultdictkey(self._create_chunk)

        if isinstance(filename, str):
            self.wavfile = open(filename, "wb+")
            self._auto_close = True
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

    def _create_chunk(self, key):
        """Create a new chunk filled with zeros, or load one from disk."""
        if key in self.saved_to_disk:
            return self._load_chunk(key)
        else:
            return zeros((self.channels, self.chunksize), dtype=self.dtype)

    def _load_chunk(self, idx):
        """Load a chunk from disk into the cache."""
        raise NotImplementedError  # not needed for linear writes and it's broken
        self.saved_to_disk.discard(idx)
        self.wavfile.seek(self._header_length + (self.chunkspacing * idx))
        raw_data = fromfile(self.wavfile, dtype=self.dtype,
                            count=self.channels * self.chunksize)
        return raw_data.reshape((self.channels, self.chunksize), order="F")

    def _save_chunk(self, idx):
        """Write a chunk to disk and remove it from the cache."""
        self.wavfile.seek(self._header_length + (self.chunkspacing * idx))
        self.chunks[idx].flatten(order="F").tofile(self.wavfile)
        self.saved_to_disk.add(idx)
        del self.chunks[idx]

    def flush_cache(self, to_idx=None):
        """Save all (or all up to a certain index) chunks in memory to disk and remove them fron the cache."""
        # we should still sort the keys even though it's theoretically not needed
        # because sequential disk writes are faster on both SSDs and hard disks
        for idx in sorted(self.chunks.keys()):
            if to_idx is not None and idx >= to_idx:
                break
            else:
                self._save_chunk(idx)

    def fill_empty_chunks(self):
        """Fill all the unwritten chunks with zeros.

        This isn't strictly necessary, as on POSIX and Windows seek()ing past
        the end of a file fills the unwritten part with zeros. Unfortunately,
        doing so is still undefined behavior and should be avoided. This function
        iterates over the unwritten chunks, filling them with zeros."""
        for chunk_idx in range(max(self.saved_to_disk)):
            if chunk_idx not in self.saved_to_disk:
                # the chunk won't exist but it will create it full of zeros &
                # save it
                self._save_chunk(chunk_idx)

    def add_data(self, start, data, cutoffs):
        """Add sound data at a specified position.

        Args:
            start: How many samples into the output the data should start.
            data: A NumPy array of data to add to the output.
            cutoffs: An array of integers that specifies where to cut off each channel. (optional)
        """
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
        """Flush the cache of chunks to disk, patch the WAV header with the new length, and close the file."""
        self.flush_cache()
        self.fill_empty_chunks()
        self.wav._datawritten = (
            max(self.saved_to_disk) + 1) * self.chunkspacing
        self.wav._patchheader()
        if self._auto_close:
            self.wavfile.close()
