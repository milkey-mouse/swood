from time import sleep
import sys
import os

sys.path.insert(0, os.path.realpath("../../swood"))
import swood

def find_program(prog):
    for path in os.environ["PATH"].split(os.pathsep):
        vlc_location = os.path.join(path.strip('"'), prog)
        if os.path.isfile(fpath):
            return vlc_location, args
    return None

def play_audio(clip):
    import subprocess
    if os.name == "nt":
        if os.path.isfile("C:/Program Files (x86)/VideoLAN/VLC/vlc.exe"):
            return subprocess.Popen(["C:/Program Files (x86)/VideoLAN/VLC/vlc.exe", clip, "vlc://quit"])
        elif find_program("vlc.exe"):
            return subprocess.Popen([find_program("vlc.exe"), clip, "vlc://quit"])
        elif os.path.isfile("C:/Program Files (x86)/Windows Media Player/wmplayer.exe"):
            return subprocess.Popen(["C:/Program Files (x86)/Windows Media Player/wmplayer.exe", clip, "/Play", "/Close"])
        elif find_program("wmplayer.exe"):
            return subprocess.Popen([find_program("wmplayer.exe"), clip, "/Play", "/Close"])
        else:
            raise FileNotFoundError("Can't find an audio player.")

running_player = None

def run(midi, *args, play=False):
    global running_player
    print("~~~~~~~~~~ Testing '{}' ~~~~~~~~~~".format(midi))
    out = "outputs/" + midi + ".wav"
    swood.run_cmd(["samples/doot.wav", "midis/" + midi + ".mid", out, "--no-pbar", *args])
    if play:    
        if not os.path.isfile(out):
            return
        if running_player:
            os.remove(out)
            running_player.wait()
        running_player = play_audio(out)

if sys.argv[1] == "playall":
    try:
        run("beethoven", play=True)
        run("dummy", play=True)
        run("pitchbend", play=True)
    finally:
        import glob
        for wav in glob.iglob("outputs/*.wav"):
            os.remove(wav)
elif sys.argv[1] == "all":
    run("beethoven")
    run("dummy")
    run("pitchbend")
elif sys.argv[1] == "bend":
    run("pitchbend")