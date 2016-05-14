from setuptools import setup, find_packages




# something feels very wrong about running assembly in python
# most of this taken from https://github.com/workhorsy/py-cpuinfo

print("Checking for SSE4 and AVX2 support...")
sse4 = False
avx2 = False
try:
    import platform
    import ctypes
    import os
    
    sixtyfour = (platform.architecture()[0] == '64bit')

    def eax():
        if sixtyfour:
            return (
                b"\x66\xB8\x01\x00" # mov eax,0x1"
            )
        else:
            return (
                b"\x31\xC0"         # xor ax,ax
                b"\x40"             # inc ax
            )
            
    def program_paths(program_name):
        paths = []
        exts = filter(None, os.environ.get('PATHEXT', '').split(os.pathsep))
        path = os.environ['PATH']
        for p in os.environ['PATH'].split(os.pathsep):
            p = os.path.join(p, program_name)
            if os.access(p, os.X_OK):
                paths.append(p)
            for e in exts:
                pext = p + e
                if os.access(pext, os.X_OK):
                    paths.append(pext)
        return paths
            
    selinux = False  
    if len(program_paths('sestatus')) > 0:
        selinux = (not run_and_get_stdout(['sestatus', '-b'], ['grep', '-i', '"allow_execheap"'])[1].strip().lower().endswith('on') or not run_and_get_stdout(['sestatus', '-b'], ['grep', '-i', '"allow_execmem"'])[1].strip().lower().endswith('on'))
            
    def asm_func(restype=None, argtypes=(), byte_code=[]):
            byte_code = bytes.join(b'', byte_code)
            address = None

            if platform.system().lower() == 'windows':
                # Allocate a memory segment the size of the byte code, and make it executable
                size = len(byte_code)
                MEM_COMMIT = ctypes.c_ulong(0x1000)
                PAGE_EXECUTE_READWRITE = ctypes.c_ulong(0x40)
                address = ctypes.windll.kernel32.VirtualAlloc(ctypes.c_int(0), ctypes.c_size_t(size), MEM_COMMIT, PAGE_EXECUTE_READWRITE)
                if not address:
                    raise Exception("Failed to VirtualAlloc")
                # Copy the byte code into the memory segment
                memmove = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t)(ctypes._memmove_addr)
                if memmove(address, byte_code, size) < 0:
                    raise Exception("Failed to memmove")
            else:
                # Allocate a memory segment the size of the byte code
                size = len(byte_code)
                address = ctypes.pythonapi.valloc(size)
                if not address:
                    raise Exception("Failed to valloc")
                # Mark the memory segment as writeable only
                if not selinux:
                    WRITE = 0x2
                    if ctypes.pythonapi.mprotect(address, size, WRITE) < 0:
                        raise Exception("Failed to mprotect")
                # Copy the byte code into the memory segment
                if ctypes.pythonapi.memmove(address, byte_code, size) < 0:
                    raise Exception("Failed to memmove")
                # Mark the memory segment as writeable and executable only
                if not selinux:
                    WRITE_EXECUTE = 0x2 | 0x4
                    if ctypes.pythonapi.mprotect(address, size, WRITE_EXECUTE) < 0:
                        raise Exception("Failed to mprotect")
            # Cast the memory segment into a function
            functype = ctypes.CFUNCTYPE(restype, *argtypes)
            fun = functype(address)
            return fun, address
            
    def run_asm(*byte_code):
        # Convert the byte code into a function that returns an int
        func, address = asm_func(ctypes.c_uint64 if sixtyfour else ctypes.c_uint64, (), byte_code)
        # Call the byte code like a function
        retval = func()
        size = ctypes.c_size_t(len(byte_code))
        # Free the function memory segment
        if platform.system().lower() == 'windows':
            MEM_RELEASE = ctypes.c_ulong(0x8000)
            ctypes.windll.kernel32.VirtualFree(address, size, MEM_RELEASE)
        else:
            # Remove the executable tag on the memory
            READ_WRITE = 0x1 | 0x2
            if ctypes.pythonapi.mprotect(address, size, READ_WRITE) < 0:
                raise Exception("Failed to mprotect")
            ctypes.pythonapi.free(address)
        return retval

    ecx = run_asm(
        eax(),
        b"\x0f\xa2"         # cpuid
        b"\x89\xC8"         # mov ax,cx
        b"\xC3"             # ret
    )

    def is_bit_set(reg, bit):
        mask = 1 << bit
        return reg & mask > 0
        
    sse4 = is_bit_set(ecx, 19) or is_bit_set(ecx, 20)

    
except Exception as e:
    print(e)
    print("Error checking for SSE4 support.")
    
print("sse4: {}".format(str(sse4).lower()))
print("avx2: {}".format(str(avx2).lower()))

setup(
    name='swood',
    version='0.9.8',
    description='With just one sample and a MIDI you too can make YTPMVs',
    long_description='Are you tired of manually pitch-adjusting every sound for your shitposts? Toil no more with auto-placement of sound samples according to a MIDI!',
    url='https://github.com/milkey-mouse/swood.exe',
    author='Milkey Mouse',
    author_email='milkeymouse@meme.institute',
    license='MIT',
    classifiers=[
        'Development Status :: 4 - Beta',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
    ],
    keywords='swood memes youtubepoop ytp ytpmvs',
    packages=["swood"],

    install_requires=['mido', 'numpy', 'Pillow', 'progressbar2', 'pyFFTW'],

    entry_points={
        'console_scripts': [
            'swood=swood:run_cmd',
        ],
    },
)
