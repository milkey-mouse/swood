from __future__ import print_function
import sys

if sys.version_info.major < 3 or (sys.version_info.major == 3 and sys.version_info.minor < 4):
    print("Sorry, swood.exe requires at least Python 3.4 to run correctly.")
    sys.exit(1)

from setuptools import setup
import importlib.util
import importlib
import platform

import os
import io

try:
    import pip
except ImportError:
    print("Installing pip...")
    import ensurepip
    ensurepip.bootstrap()
    importlib.invalidate_caches()
    import pip


def install_package(pkg):
    print("Installing {}...".format(pkg))
    tmp_stdout = sys.stdout
    sys.stdout = io.StringIO()
    try:
        pip.main(["install", pkg])
    except SystemExit as e:
        stdout_str = sys.stdout.getvalue()
        sys.stdout = tmp_stdout
        if e.code != 0:
            print("pip failed to install {}.\nYou may need a working C compiler to continue.\npip stdout:".format(pkg))
            print(stdout_str)
            raise ImportError
        else:
            importlib.invalidate_caches()


def get_flags():
    sse4 = False
    avx2 = False
    try:
        # something feels very wrong about running assembly in python
        # most of this taken from https://github.com/workhorsy/py-cpuinfo

        # the docs say platform.machine() can be unreliable
        sixtyfour = sys.maxsize == (2 ** 63) - 1

        def asm_func(restype=None, argtypes=(), byte_code=[]):
            byte_code = bytes.join(b'', byte_code)
            address = None
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
            func, address = asm_func(
                ctypes.c_uint64 if sixtyfour else ctypes.c_uint32, (), byte_code)
            # Call the byte code like a function
            retval = func()
            size = ctypes.c_size_t(len(byte_code))
            # Free the function memory segment
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
                return b"\x66\xB8\x01\x00"  # mov eax,0x1"
            else:
                return (b"\x31\xC0"         # xor ax,ax
                        b"\x40")            # inc ax

        ecx = run_asm(eax(),
                      b"\x0f\xa2"         # cpuid
                      b"\x89\xC8"         # mov ax,cx
                      b"\xC3")            # ret

        ebx = run_asm(
            b"\xB8\x01\x00\x00\x80"  # mov ax,0x80000001
            b"\x0f\xa2"         # cpuid
            b"\x89\xD8"         # mov ax,bx
            b"\xC3")            # ret

        sse4 = is_bit_set(ecx, 19) or is_bit_set(ecx, 20)

        # because a midi synthesizer definitely needs to support server-grade
        # hardware
        avx2 = is_bit_set(ebx, 5)
    except Exception:
        pass
    return (sse4, avx2)

install = False
simd = False

if len(sys.argv) > 1 and "install" in sys.argv:
    pkgs = [package.project_name.lower()
            for package in pip.get_installed_distributions()]

    if "pillow-simd" in pkgs:
        print("pillow-simd is already installed. swood will install with SIMD support.")
        install = False
        simd = True
    if platform.machine() in ("i386", "x86_64") and os.name in ("posix", "nt"):
        try:
            import ctypes
            sse4, avx2 = get_flags()
            if avx2:
                print(
                    "Your processor supports AVX2. swood will install with SIMD support.")
                os.environ["CFLAGS"] = "-mavx2"
                install = True
                simd = True
            elif sse4:
                print(
                    "Your processor supports SSE4. swood will install with SIMD support.")
                install = True
                simd = True
        except:
            simd = False

    # we need to install numpy first because pyfftw needs it and pip has bad dependency resolution
    # and we need to set this flag because pyFFTW uses a deprecated API
    # apparently
    os.environ["CFLAGS"] = "-DNPY_NO_DEPRECATED_API=NPY_1_7_API_VERSION"

    for pkg in ("numpy", "pyfftw"):
        if pkg not in pkgs:
            install_package(pkg)

    if install:
        try:
            install_package("pillow-simd")
        except ImportError:
            print("SIMD support failed to install. swood will run slower.")
            simd = False

reqs = ['mido', 'numpy', 'tqdm', 'pyfftw']

if not simd:
    reqs.append('pillow')

setup(
    name='swood',
    version='1.0.4',
    description='Make music with any sound',
    long_description='Are you tired of manually pitch-adjusting every sound for your shitposts? Toil no more with auto-placement of sound samples according to a MIDI!',
    url='https://meme.institute/swood',
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

    install_requires=reqs,

    entry_points={
        'console_scripts': [
            'swood=swood:run_cmd',
        ],
    },
)
