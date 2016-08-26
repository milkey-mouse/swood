#!/usr/local/bin/python
import swood.sample, swood.soundfont, swood.render, swood.midiparse
from time import perf_counter

ascii_art = "                                 .___                    __    \n  ________  _  ______   ____   __| _/_____ _____ _______|  | __\n /  ___/\\ \\/ \\/ /  _ \\ /  _ \\ / __ |/     \\\\__  \\\\_  __ \\  |/ /\n \\___ \\  \\     (  <_> |  <_> ) /_/ |  Y Y  \\/ __ \\|  | \\/    < \n/____  >  \\/\\_/ \\____/ \\____/\\____ |__|_|  (____  /__|  |__|_ \\\n     \\/                           \\/     \\/     \\/           \\/\n"

print(ascii_art)

print("Loading sample... ", end="")
start=perf_counter()
sample = swood.sample.Sample("samples/doot.wav")
print("Done in {}s".format(round(perf_counter() - start, 2)))

soundfont = swood.soundfont.DefaultFont(sample)
renderer = swood.render.NoteRenderer(soundfont, True)

print("Rendering MIDI scale... ", end="")
elapsed = 0
for notenum in range(36, 97):
    note = swood.midiparse.Note(pitch=notenum, instrument=soundfont.instruments[1][0])
    note.finalize(0)  # since it's in fullclip mode, note length doesn't matter
    start=perf_counter()
    renderer.render_note(note)
    elapsed += (perf_counter() - start)
print("Done in {}s (avg. {}s/note)".format(round(elapsed, 2), round(elapsed/60, 2)))
