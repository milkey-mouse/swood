class CachedWavFile:  # Stores serialized data
    def __init__(self, length, dtype=np.int32, binsize=8192):
        self.binsize = binsize
        self.savedchunks = 0
        self.length = math.ceil(length / binsize) * binsize
        self.dtype = dtype
        self.chunks = collections.defaultdict(lambda: np.zeros((self.binsize, ), dtype=self.dtype))

    def __getitem__(self, key):
        if isinstance(key, int):
            if key < 0 or key >= self.length:
                raise IndexError()
            else:
                return self.chunks[key / self.binsize][key % self.binsize]
        elif isinstance(key, slice):
            startchunk = math.floor(slice.start / self.binsize)
            stopchunk = math.ceil(slice.stop / self.binsize)
            offset = slice.start - (startchunk * self.binsize)
            length = slice.stop - slice.start
            if startchunk == stopchunk:
                return self.chunks[startchunk][offset:offset + length]
            else:
                ret = []
                ret.extend(self.chunks[startchunk][offset])
            for i in range(startchunk, stopchunk + 1):
                if i in self.chunks:
                    for b in self.chunks[i][max(offset, self.binsize):]:
                        if offset > 0:
                            offset -= 1
                        elif length > 0:
                            length -= 1
                            yield b
                        else:
                            break
                else:
                    for _ in range(self.binsize):
                        if offset > 0:
                            offset -= 1
                        elif length > 0:
                            length -= 1
                            yield 0
                        else:
                            break
                            
