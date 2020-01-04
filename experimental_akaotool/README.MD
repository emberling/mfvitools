# akaotool

An unfinished, inactive project that's been sitting around on my hard drive for a while.
It requires some extra third-party python libraries from pip, i don't remember what (wx for sure)

The goal was to have an all-in-one tool for browsing, extracting, importing, and converting Square SNES game music. Most of that didn't get done, but enough got done that the tool can still be occasionally useful.

to use, run akaotool_gui.exe

Things that work, more or less:
- Detects all music sequences in the ROM
- Browse music sequences and look at their sample loadouts
- Extract raw music sequences
- Detects all "instrument" samples in the ROM (not sound effect BRRs)
- Browse samples and view their metadata, including some useful tuning info
- Audition samples (barely works - monophonic and no looping. ST3 keyboard layout)
- View list of songs that use a sample
- Save names for songs and samples

Things that extremely don't work:
- saving always writes to a specific filename, i think it's out_test.smc
- this is because in many cases, saving mangles the entire ROM
- yeah
- maybe just .. look, don't touch
- I don't remember fully but I think editing pitch, envelope, loop, and sample loadouts are safe? Anything that doesn't affect the rom size. Some of those may not actually save, but they shouldn't break the ROM i think.

games supported:
- Final Fantasy 6
- Final Fantasy 5
- Secret of Mana
- Chrono Trigger
- Romancing SaGa 3
- Radical Dreamers

supporting additional games using AKAO3/AKAO4 engines is just a matter of tracking down a few locations in the ROM and adding them to dat/gameinfo.txt