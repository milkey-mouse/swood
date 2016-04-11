from setuptools import setup, find_packages
from codecs import open
from os import path

setup(
    name='swood',
    version='0.9.2',
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
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
    ],
    keywords='shitposting memes youtubepoop ytp ytpmvs',
    packages=find_packages(exclude=['contrib', 'docs', 'tests']),

    py_modules=["swood"],

    install_requires=['mido', 'numpy', 'Pillow', 'progressbar2', 'pyFFTW'],

    entry_points={
        'console_scripts': [
            'swood=swood:run_cmd',
        ],
    },
)
