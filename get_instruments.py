"""Scrapes the General MIDI Wikipedia article for a list of
instrument types and outputs a list of instrument tuples.
Needs the 'wikipedia' library.
"""

import wikipedia
import string

print("instruments = [")

gmidi = wikipedia.page("General MIDI")
last_header = "broken lol"
for line in gmidi.content.split("\n"):
    if len(line) > 0 and line[0] in string.digits:
        try:
            parts = line.split()
            if last_header == "percussion":
                if int(parts[0]) < 81:
                    print("    ({}, \"{}\"),".format(parts[0], " ".join(parts[1:])))
                elif int(parts[0]) == 81:
                    print("    ({}, \"{}\")".format(parts[0], " ".join(parts[1:])))
                    print("]")
                    break
            else:
                if int(parts[0]) < 128:
                    print("    ({}, \"{}\", \"{}\"),".format(parts[0], " ".join(parts[1:]), last_header))
                elif int(parts[0]) == 128:
                    print("    ({}, \"{}\", \"{}\")".format(parts[0], " ".join(parts[1:]), last_header))
                    print("]")
                    print()
                    print("percussion = [")
        except:
            pass
    elif line.startswith("="):
        last_header = " ".join(line.split()[1:-1]).lower()