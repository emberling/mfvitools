#!/usr/bin/env python3
import sys, os, itertools

DEBUG_WRITE_FULL_HEX = False
CONFIG_NOTE_LENGTH_COMPENSATION = True

def clean_end():
    print("Processing ended.")
    input("Press enter to close.")
    quit()
    
def write_hex(bin):
    s = ""
    for b in bin:
        s += f"{b:02X} "
    return s.strip()
    
def specify_note_duration(note, dur):
    target_note_table = [0xC0, 0x60, 0x40, 0x48, 0x30, 0x20, 0x24, 0x18, 0x10, 0x0C, 0x08, 0x06, 0x04, 0x03]
    ff6_duration_table = ["1", "2", "3", "4.", "4", "6", "8.", "8", "12", "16", "24", "32", "48", "64"]
    key = {target_note_table[i]: ff6_duration_table[i] for i in range(len(target_note_table))}
    
    if not dur:
        return ""
        
    solution = []
    if dur in target_note_table:
        solution = [dur]
    target_note_table = [t for t in target_note_table if t <= dur]
    if not solution:
        for c in itertools.combinations(target_note_table, 2):
            if sum(c) == dur:
                solution = c
                break
    # if CONFIG_EXPAND_NOTES_TO_THREE and not solution:
        # for c in itertools.combinations(target_note_table, 3):
            # if sum(c) == dur:
                # solution = c
                # break
    if solution:
        text = ""
        for i, s in enumerate(solution):
            text += "^" if i else f"{note}"
            text += f"{key[s]}"
    else:
        text = f"&{dur}{note}"
    
    return text
    
command_length_table_SFC = {
    1: [0xFB],
    2: [0xF3, 0xFC],
    3: [0xF0, 0xF1, 0xF2, 0xF4, 0xF5, 0xF7, 0xF8, 0xF9, 0xFA, 0xFE],
    4: [0xF6]
    }
command_length_table_S2C = {
    1: [0xFB],
    2: [0xF3, 0xFC],
    3: [0xF0, 0xF1, 0xF2, 0xF4, 0xF5, 0xF6, 0xF7, 0xF8, 0xF9, 0xFA, 0xFE],
    4: []
    }
command_length_table = command_length_table_SFC

def handle_pattern(ptr):
    loc = ptr
    pdata = b""
    line = ""
    while True:
        #print(f"DEBUG: reading sequence at {loc:04X}")
        cmd = data[loc]
        if cmd == 0xFD:    # end pattern
            pdata = data[ptr:loc+1]
            break  
        elif cmd in range(0x60):    # note with parameters
            line += handle_full_note(data[loc:loc+4])
            loc += 4
        elif cmd in range(0x80, 0xE0):    # note without parameters
            line += handle_note(data[loc] - 0x80, state_delta, state_length, state_velocity)
            loc += 1
        elif cmd == 0xFF:    # meta commands
            line += handle_meta_command(data[loc+1], data[loc+2])
            loc += 3
        elif cmd in command_length_table[1]:    # 1 byte commands
            line += handle_command(cmd, bytes([data[loc]]))
            loc += 1
        elif cmd in command_length_table[2]:    # 2 byte commands
            line += handle_command(cmd, data[loc:loc+2])
            loc += 2
        elif cmd in command_length_table[3]:    # 3 byte commands & unknown
            line += handle_command(cmd, data[loc:loc+3])
            loc += 3
        elif cmd in command_length_table[4]:    # 4 byte commands
            line += handle_command(cmd, data[loc:loc+4])
            loc += 4
        elif cmd in range(0x60, 0x80):    # unknown
            print(f"unknown bytecode {write_hex(data[loc:loc+4])}")
            line += f"'{write_hex(data[loc:loc+4])}'"
            loc += 4
        else:    # unknown
            print(f"unknown bytecode {data[loc]:02X}")
            line += f"'{data[loc]:02X}'"
            loc += 1
    if DEBUG_WRITE_FULL_HEX:
        line = f"## {write_hex(pdata)}\n" + line
    return line
            
def get_note_key(key):
    note_table = ["c", "c+", "d", "d+", "e", "f", "f+", "g", "g+", "a", "a+", "b"]
    if key < 0:
        return "^"
    return note_table[key % 12]
    
def handle_full_note(code):
    return " " + handle_note(code[0], code[1], code[2], code[3])
    
def handle_note(key, delta, length, velocity):
    global state_octave, state_delta, state_length, state_last_key, state_velocity, state_output_volume, state_slur, state_retrigger, state_remainder
    
    key += pattern_transpose
    
    octave = (key // 12)
    note = get_note_key(key)
    
    before_this_note_text = ""
    after_this_note_text = ""
    if state_last_key == key and state_remainder >= 0 and not state_retrigger:
        note = "^"
    if state_slur and state_remainder < 0:
        before_this_note_text += ')'
        state_slur = False
    if length > delta:
        state_last_key = key
        if not state_slur:
            before_this_note_text += '('
            state_slur = True
    else:
        state_last_key = -1
        if state_slur:
            after_this_note_text += ')'
            state_slur = False
    state_retrigger = False
    
    state_length = length
    state_delta = delta
    state_remainder = max(-1, length - delta)
    if CONFIG_NOTE_LENGTH_COMPENSATION and length - delta <= 3:
        if length / delta >= 0.75:
            length = delta
    length = min(length, delta)
    
    note_text = before_this_note_text + specify_note_duration(note, length) + after_this_note_text
    if delta - length:
        note_text += specify_note_duration("r", delta - length)
        
    if octave == state_octave:
        octave_text = ""
    elif octave == state_octave + 1:
        octave_text = "<"
        state_octave += 1
    elif octave == state_octave - 1:
        octave_text = ">"
        state_octave -= 1
    else:
        octave_text = f"o{octave} "
        state_octave = octave
        
    output_volume = int(velocity * (1 + state_volume) / 128)
    if output_volume != state_output_volume:
        volume_text = f"v{output_volume}"
        state_output_volume = output_volume
    else:
        volume_text = ""
    state_velocity = velocity
    
    return octave_text + volume_text + note_text
    
def handle_command(cmd, code):   
    global state_volume, state_octave, state_retrigger, state_remainder, state_last_key
    note = "^"
    if cmd == 0xF1:    # track volume
        state_volume = code[2]
        text = ""
    elif cmd == 0xF2:    # pan
        text = f"p{code[2]}"
    elif cmd == 0xF3:    # rest
        text = ""
    elif cmd == 0xF6 and format == "S2C":    # detune
        text = f"k{code[2]-0x80}"
        note = get_note_key(state_last_key)
        #if not code[1]:
        #    state_retrigger = True
    elif cmd == 0xF7:    # program change
        used_programs.add(code[2])
        text = f"'Prog{code[2]:02X}'"
    elif cmd == 0xFB:    # loop start
        loopid = len(used_loops)
        state_loops.append(loopid)
        used_loops.add(loopid)
        state_octave = -1
        text = f"'Loop{loopid:02}'"
    elif cmd == 0xFC:    # loop end
        if state_loops:
            loopid = state_loops.pop()
            if code[1]:
                placeholders[f"'Loop{loopid:02}'"] = f"[{code[1]}"
                text = "]"
            else:
                placeholders[f"'Loop{loopid:02}'"] =  "$"
                text = ";\n"
        else:
            text = ""
    else:
        text = f"'CMD {write_hex(code)}' "
    try:
        if len(code) >= 3 or cmd == 0xF3:
            text += specify_note_duration(note, code[1])
            state_remainder = max(-1, state_remainder - code[1])
        return text
    except UnboundLocalError:
        print(f"ERROR: UnboundLocalError in handle_command {write_hex(code)}")
        return f"'ULE {write_hex(code)}'"
    
    
def handle_meta_command(cmd, param):
    if cmd == 0x01:    # EFB
        return f"%b0,{param}"
    elif cmd == 0x03:    # enable echo
        return "%e1"
    elif cmd == 0x04:    # disable echo
        return "%e0"
    elif cmd == 0x0B:    # ADSR sustain rate (R)
        return f"%r{param}"
    else:
        return f"'META {cmd:02X}:{param}'"
        
if __name__ == "__main__":
    print("mfvitools Neverland SFC/S2C to MML converter")
    
    if len(sys.argv) >= 2:
        fn = sys.argv[1]
    else:
        print("Enter Neverland SPC filename..")
        fn = input(" > ").replace('"','').strip()
        
    try:
        with open(fn, 'rb') as f:
            spc = f.read()
    except IOError:
        print("Error reading file {}".format(fn))
        clean_end()
        
    spc = spc[0x100:]
    mml = []
    
    print()
    for loc in range(0x10000):
        format = None
        if spc[loc:loc+3] == b"SFC":
            format = "SFC"
        elif spc[loc:loc+3] == b"S2C":
            format = "S2C"
            command_length_table = command_length_table_S2C
        if format:
            name = spc[loc+4:loc+16]
            timecode = spc[loc+3]
            print(f"Possible match found: {format} at 0x{loc:04X} - {name}")
            print("Type 'n' to skip, or press enter to accept")
            entry = input(" > ").lower()
            if entry and entry[0] == "n":
                continue
            else:
                break
    if not format:
        print("No sequence found. Exiting.")
        clean_end()
        
    if format == "SFC":
        data = spc
        head = loc
    else:
        data = spc[loc:]
        head = 0
    used_programs = set()
    used_loops = set()
    placeholders = {}
    
    tracks = []
    for t in range(8):
        tracks.append(int.from_bytes(data[head + 0x20 + t*2 : head + 0x20 + t*2 + 2], "little"))
    
    # tempo (est.)
    # BERSERKER 0x35 (53) ~= 190bpm ~= 315.8 ms/beat ~= 6.58 ms/tick
    # PRAYER BELLS 0x4a (74) ~= 135bpm ~= 444.4 ms/beat ~= 9.26 ms/tick
    # PRIPHEA (L2) 0x64 (100) ~= 100bpm ~= 600 ms/beat ~= 12.5 ms/tick
    # CALMING DAYS 0x76 (118) ~= 90bpm ~= 666.7 ms/beat ~= 13.89 ms/tick
    # estimate: timecode * 6 = ms/beat
    tempo = int((1 / (timecode * 6)) * 1000 * 60)
    
    for track in range(8):
        mml.append(f"{{Track {track+1}}}")
        if track == 0:
            mml.append(f"t{tempo}")
        pattern_loc = tracks[track]
        
        state_octave = -1
        state_volume = 0
        state_program = 0
        state_delta = 0
        state_length = 0
        state_remainder = -1
        state_velocity = 0
        state_output_volume = 0
        state_last_key = -1
        state_loops = []
        state_slur = False
        state_retrigger = False
        
        while pattern_loc <= len(data) - 3:
            pattern_transpose = 0
            if data[pattern_loc] == 0xFF:
                mml.append(";\n")
                break
            if data[pattern_loc] >= 0x80:
                pattern_transpose = data[pattern_loc] - 0x80
                #print(f"DEBUG: transposing next pattern by {pattern_transpose}")
                pattern_loc += 1
            #print(f"DEBUG: reading pattern at {pattern_loc:04X}")
            pattern_ptr = int.from_bytes(data[pattern_loc:pattern_loc + 2], "big")
            mml.append(f"{{'{pattern_ptr:X}'}}" + handle_pattern(pattern_ptr))
            pattern_loc += 2
            
    for k, v in placeholders.items():
        for i, line in enumerate(mml):
            mml[i] = line.replace(k, v)
            
    prepend = [""]
    for i, p in enumerate(used_programs):
        prepend.append(f"#WAVE 0x{0x20+i:02X} 0x00    # program {p:02X}")
    prepend.append("")
    for i, p in enumerate(used_programs):
        prepend.append(f"#def Prog{p:02X}= |{i:X} %k12")
    prepend.append("\n#cdef ( %l1\n#cdef ) %l0\n")
    mml = prepend + mml
    
    fn = fn.rpartition('.')[0] + '.mml'
    try:
        with open(fn, 'w') as f:
            f.write("\n".join(mml))
    except IOError:
        print("Error writing file {}".format(fn))
        clean_end()
        
    clean_end()