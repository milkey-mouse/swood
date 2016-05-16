from __future__ import print_function
import sys

if sys.version_info.major < 3 or (sys.version_info.major == 3 and sys.version_info.minor < 4):
    print("Sorry, swood.exe requires at least Python 3.4 to run correctly.")
    sys.exit(1)
    
import platform

from setuptools import setup
import importlib
import warnings
import ctypes
import os

try:
    import pip
except ImportError:
    print("Please download and install pip to set up swood.exe.")

warnings.filterwarnings("ignore")

def get_flags():
    sse4 = False
    avx2 = False
    try:
        # something feels very wrong about running assembly in python
        # most of this taken from https://github.com/workhorsy/py-cpuinfo
        
        sixtyfour = sys.maxsize > 2**32 #the docs say platform.machine() can be unreliable
                
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
                    WRITE = 0x2
                    if ctypes.pythonapi.mprotect(address, size, WRITE) < 0:
                        raise Exception("Failed to mprotect")
                    # Copy the byte code into the memory segment
                    if ctypes.pythonapi.memmove(address, byte_code, size) < 0:
                        raise Exception("Failed to memmove")
                    # Mark the memory segment as writeable and executable only
                    WRITE_EXECUTE = 0x2 | 0x4
                    if ctypes.pythonapi.mprotect(address, size, WRITE_EXECUTE) < 0:
                        raise Exception("Failed to mprotect")
                # Cast the memory segment into a function
                functype = ctypes.CFUNCTYPE(restype, *argtypes)
                fun = functype(address)
                return fun, address
                
        def run_asm(*byte_code):
            # Convert the byte code into a function that returns an int
            func, address = asm_func(ctypes.c_uint64 if sixtyfour else ctypes.c_uint32, (), byte_code)
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

        def is_bit_set(reg, bit):
            mask = 1 << bit
            return reg & mask > 0
            
        def eax():
            if sixtyfour:
                return b"\x66\xB8\x01\x00" # mov eax,0x1"
            else:
                return (b"\x31\xC0"         # xor ax,ax
                        b"\x40"             # inc ax
                )
            
        ecx = run_asm(
            eax(),
            b"\x0f\xa2"         # cpuid
            b"\x89\xC8"         # mov ax,cx
            b"\xC3"             # ret
        )
            
        sse4 = is_bit_set(ecx, 19) or is_bit_set(ecx, 20)
        
        ebx = run_asm(
                b"\xB8\x01\x00\x00\x80" # mov ax,0x80000001
                b"\x0f\xa2"         # cpuid
                b"\x89\xD8"         # mov ax,bx
                b"\xC3"             # ret
            )
            
        avx2 = is_bit_set(ebx, 5)
    except Exception:
        pass
    return (sse4, avx2)

simd = False
if len(sys.argv) > 1 and sys.argv[1] == "install":
    pkgs = [package.project_name.lower() for package in pip.get_installed_distributions()]
    if "pillow-simd" in pkgs:
        print("Pillow-SIMD is already installed. swood will install with SIMD support.")
        simd = True
    elif os.name() not in ("posix", "mac"):
        print("This system may not be able to build pillow-simd. SIMD support is disabled.")
        if os.name() == "nt":
            #use wheel
        else:
            print("With the right prerequisites, you may be able to build it:")
            print("https://github.com/uploadcare/pillow-simd/blob/3.2.x-simd/winbuild/build.rst")
        simd=False
    elif platform.machine() not in ("i386", "x86_64"):
        simd = False
    else:
        sse4, avx2 = get_flags()
        if avx2:
            print("Your processor supports AVX2. swood will install with SIMD support.")
            os.environ["CFLAGS"] = "-mavx2"
            simd = True
        elif sse4:
            print("Your processor supports SSE4. swood will install with SIMD support.")
            simd = True
        
    if simd:
        if "pillow" in pkgs:
            print("############################################################")
            print("Pillow will be replaced by pillow-simd, which takes advantage of certain CPU features.")
            print("To revert this change, simply run `pip uninstall pillow-simd` then `pip install pillow`.")
            print("############################################################")
            print("Removing Pillow...")
            try:
                pip.main(["uninstall", "pillow", "-y", "-q"])
            except SystemExit:
                pass
        if "pil" in pkgs:
            print("############################################################")
            print("PIL will be replaced by pillow-simd, which takes advantage of certain CPU features.")
            print("To revert this change, simply run `pip uninstall pillow-simd` then `pip install PIL`.")
            print("(Though you really should be using Pillow instead: http://python-pillow.org/)")
            print("############################################################")
            print("Removing PIL...")
            try:
                pip.main(["uninstall", "pil", "-y", "-q"])
            except SystemExit:
                pass
                
    if "numpy" not in pkgs:
        print("Installing NumPy...")
        os.environ["CFLAGS"] = "-DNPY_NO_DEPRECATED_API=NPY_1_7_API_VERSION" # pyFFTW uses a deprecated API apparently
        try:
            pip.main(["install", "numpy", "-q"])
        except SystemExit:
            pass
            
    if "pyfftw" not in pkgs:
        print("Installing PyFFTW...")
        try:
            pip.main(["install", "pyfftw", "-q"])
        except SystemExit:
            pass

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

    install_requires=['mido', 'numpy', 'progressbar2', 'pyfftw', 'pillow-simd' if simd else 'pillow'],

    entry_points={
        'console_scripts': [
            'swood=swood:run_cmd',
        ],
    },
)
