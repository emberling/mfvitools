#!/usr/bin/env python3
VERSION = "beta 1.1.2"

DEBUG_STEP_BY_STEP = False
DEBUG_LOOP_VERBOSE = False
DEBUG_JUMP_VERBOSE = False
DEBUG_STATE_VERBOSE = False
DEBUG_PERC_VERBOSE = False
DEBUG_WRITE_VERBOSE = False

import sys, itertools, copy, string, os, math

def ifprint(text, condition, **kwargs):
    if condition:
        print(text, **kwargs)
        
class Format:
    def __init__(self, sort_as, id, display_name):
        self.id = id
        self.display_name = display_name
        self.sort_as = sort_as
        
        #placeholders
        self.scanner_loc = 0
        self.scanner_data = "ph"
        self.sequence_loc = 0
        self.header_type = 0
        
        self.brr_table_size = 0x100
        self.brr_table = 0
        self.tuning_table = 0
        self.env_table = 0
        self.tuning_type = "double"
        
        self.note_table = []
        self.duration_table = []
        self.bytecode = {}
        
        self.loop_start = []
        self.loop_end = []
        self.end_track = []
        self.octave_up = []
        self.octave_down = []
        self.hard_jump = []
        self.volta_jump = []
        self.loop_break = []
        self.conditional_jump = []
        
        #defaults
        self.sequence_relative = True
        self.percussion_table_loc = None
        self.program_map_loc = None
        self.use_expression = False
        self.tempo_scale = 1
        self.tempo_mode = "simple"
        self.low_octave_notes = []
        self.note_increment_custom_duration = False
        self.note_sort_by_duration = False
        self.dynamic_note_duration = False
        self.first_note_id = 0
        self.loops_store_octave = False
        self.zero_loops_infinite = False
        self.program_base = 0x20
        self.max_loop_stack = 4
        self.base_octave = 5
        
class PercussionDef:
    def __init__(self, prg, key, pan, smp=None):
        self.prg = prg
        self.key = key
        self.pan = pan
        if smp is None:
            self.prg_raw = prg
        else:
            self.prg_raw = smp
        
    def write(self):
        octave = self.key // 12
        note = note_symbol_by_id[self.key % 12]
        
        if format.tuning_type == "suzuki":
            brrid = sample_mappings[self.prg_raw]
        else:
            brrid = self.prg
            
        if self.prg >= format.program_base:
            prgid = self.prg - 0x20
            prgtext = f"|{prgid:1X}"
            if self.prg not in program_defs:
                #sample_defs[self.prg] = f"#WAVE 0x{self.prg:02X} 0x00"
                extract_brr(self.prg, brrid)
                sample_defs[self.prg] = create_program_declaration(self.prg, brrid)
                program_defs[self.prg] = f"#def {prgid:1X}i=   |{prgid:1X}"
                volume_defs[self.prg] = f"#def {prgid:1X}v=   v100" + "\n" + \
                                        f"#def {prgid:1X}f= v1,100"
        else:
            if self.prg >= 10:
                prgtext = f"@0x{self.prg:02X}"
            else:
                prgtext = f"@{self.prg}"
            if self.prg not in program_defs:
                extract_brr(self.prg, brrid)
                sample_defs[self.prg] = "#" + create_program_declaration(self.prg, brrid)
                program_defs[self.prg] = f"#def {self.prg}@i=   @{self.prg}"
                volume_defs[self.prg] = f"#def {self.prg}@v=   v100" + "\n" + \
                                        f"#def {self.prg}@f= v1,100"
                
        return  f"{octave}{note} {prgtext} p{self.pan}"
        
#######################
#### command types ####
#######################

class Code:
    def __init__(self, length, symbol, params=[], collapse_empty=False, type="generic", **kwargs):
        self.type = type
        
        self.length = length
        self.symbol = symbol
        self.params = params
        self.collapse_empty = collapse_empty
        self.dest = None
        self.percid = None
        self.kwargs = kwargs
        
    def write(self, cmd, _):
        text = self.symbol
        for i, param in enumerate(self.params):
            if self.collapse_empty and not param(cmd):
                continue
            if "count_param" in self.kwargs and param(cmd) <= 2:
                continue
            #print(f"{cmd[0]:02X}: param {param}")
            text += f"{param(cmd)}"
            if len(self.params) > i+1:
                text += ","
        return text

    def get(self, cmd, keyword):
        try:
            return self.params[self.kwargs[keyword]-1](cmd)
        except (KeyError, AttributeError):
            print(f"warning: couldn't access keyword {keyword} in {' '.join([f'{b:02X}' for b in cmd])}")
            return None
            
class Note(Code):
    def __init__(self, noteid, dur):
        self.type = "note"
        
        self.dur = dur
        self.note = format.note_table[noteid]
        self.percid = noteid if noteid < 12 else None
        
        self.length = 1 if dur else 2
        self.symbol = self.note + dur if dur else self.note + '&'
        self.params = [] if dur else( [Increment(1)] if format.note_increment_custom_duration else [P(1)])
        self.dest = None
      
    def write(self, cmd, loc):
        note = self.note
        if loc in forced_percussion_notes:
            note = forced_percussion_notes[loc]
        if self.params:
            dur = self.params[0](cmd)
            return specify_note_duration(note, dur)
        else:
            return note + self.dur
            
class RudraNote(Note):
    def __init__(self, noteid, idx):
        self.type = "note"
        note = format.note_table[noteid]
        self.idx = idx
        self.percid = noteid if noteid < 12 else None
        if idx == 7:
            self.note = note
            self.length = 2
            self.symbol = note + '&'
            self.params = [P(1)]
            self.dest = None
        else:
            self.note = note
            self.length = 1
            self.symbol = note
            self.params = []
            self.dest = None
            
    def write(self, cmd, loc):
        note = self.note
        if loc in forced_percussion_notes:
            note = forced_percussion_notes[loc]
        if self.params:
            dur = self.params[0](cmd)
        else:
            try:
                dur = dynamic_note_durations[loc]
            except KeyError:
                print(f"{loc:04X}: warning: no duration info for note {cmd[0]:02X} ({self.symbol})")
                dur_table = [d for d in format.duration_table if isinstance(d, int)]
                dur = dur_table[self.idx]
        text = specify_note_duration(note, dur)
        return text
        
class DoubleCode(Code):
    def __init__(self, length, first_symbol, second_symbol, first_params=[], second_params=[], collapse_empty=False, type="generic", **kwargs):
        Code.__init__(self, length, first_symbol + second_symbol, params=second_params, **kwargs)
        self.first_symbol = first_symbol
        self.second_symbol = second_symbol
        self.first_params = first_params
        self.second_params = second_params
        
    def write(self, cmd, _):
        text = self.first_symbol
        for i, param in enumerate(self.first_params):
            if self.collapse_empty and not param(cmd):
                continue
            #print(f"{cmd[0]:02X}: param {param}")
            text += f"{param(cmd)}"
            if len(self.first_params) > i+1:
                text += ","
        text += self.second_symbol
        for i, param in enumerate(self.second_params):
            if self.collapse_empty and not param(cmd):
                continue
            #print(f"{cmd[0]:02X}: param {param}")
            text += f"{param(cmd)}"
            if len(self.second_params) > i+1:
                text += ","
        return text
        
class Comment(Code):
    def write(self, cmd, _):
        params_resolved = [p(cmd) for p in self.params]
        if self.collapse_empty:
            params_resolved = [p for p in self.params if p]
        text = "{'" + self.symbol.format(*params_resolved) + "'}"
        return text
        
class Jump(Code):
    def __init__(self, length, symbol, dest=None, **kwargs):
        Code.__init__(self, length, symbol, **kwargs)
        self.type = "jump"
        self.dest = dest
        
    def write(self, cmd, loc):
        iterations = None
        try:
            unshifted = self.dest(cmd)
            dest = shift(unshifted)
        except TypeError: #suzuki 1-byte loop break
            if loc in implicit_jump_targets:
                dest = implicit_jump_targets[loc]
            else:
                dest = 0
            if loc in suzuki_volta_counts:
                iterations = suzuki_volta_counts[loc]
            else:
                iterations = 0
                
        try:
            target = jumps[dest]
        except KeyError:
            print(f"{loc:04X}: couldn't find jump destination {dest:04X} ({unshifted:04X})")
            target = 0
        self.params.append(Fixed(target))
        if self.length == 1: #suzuki 1-byte loop break
            ifprint(f"1-byte loop break: {iterations}x -> {target}", DEBUG_LOOP_VERBOSE)
            
            text = f"{self.symbol}{iterations},{target}"
        else:
            text = Code.write(self, cmd, loc)
        self.params.pop()
        return text
        
class ProgramCode(Code):
    def __init__(self, length, **kwargs):
        Code.__init__(self, length, "@", **kwargs)
        self.type = "program"
        
    def write(self, cmd, loc):
        progval = self.params[0](cmd)
        prog = None
        macro_id = f"{progval}@"
        if progval >= format.program_base:
            prog = progval - format.program_base
            text = f"|{prog:1X}"
            macro_id = f"{prog:1X}"
        elif progval >= 10:
            text = f"@0x{progval:02X}"
        else:
            text = f"@{progval}"
            
        if progval not in program_defs:
            if prog is not None:
                extract_brr(prog+0x20, progval)
                sample_defs[prog+0x20] = create_program_declaration(prog+0x20, progval)
                #sample_defs[prog+0x20] = f"#WAVE 0x{prog+0x20:02X} 0x00"
                program_defs[prog+0x20] = f"#def {prog:1X}i=   |{prog:1X}"
                octave_defs[prog+0x20] = f"#def {prog:1X}o=   o{format.base_octave}"
                volume_defs[prog+0x20] = f"#def {prog:1X}v=   v100" + "\n" + \
                                         f"#def {prog:1X}f= v1,100"
            else:
                extract_brr(progval, progval)
                sample_defs[progval] = "#" + create_program_declaration(progval, progval)
                program_defs[progval] = f"#def {progval}@i=   @{progval}"
                octave_defs[progval] = f"#def {progval}@o=   o{format.base_octave}"
                volume_defs[progval] = f"#def {progval}@v=   v100" + "\n" + \
                                       f"#def {progval}@f= v1,100"
                
        if CONFIG_USE_PROGRAM_MACROS:
            text = f"\n'{macro_id}i'"
            if loc in program_locs:
                program, octave, volume = program_locs[loc]
            text += ' '
        return text
            
    def get(self, cmd, keyword=''):
        progval = self.params[0](cmd)
        if sample_mappings: #suzuki
            return progval
        elif progval >= format.program_base:
            return progval - format.program_base + 0x20 #for ff4
        else:
            return progval

class ProgramCodeBySample(ProgramCode):
    def write(self, cmd, loc):
        smpval = self.params[0](cmd)
        progval = sample_mappings[smpval]
        #print(f"read sample {smpval:02X} -> is mapped to program {progval:02X}")
        prog = None
        macro_id = f"{progval}@"
        if progval >= format.program_base:
            prog = convert_program(progval) - 0x20
            text = f"|{prog:1X}"
            macro_id = f"{prog:1X}"
        elif progval >= 10:
            text = f"@0x{progval:02X}"
        else:
            text = f"@{progval}"
            
        if progval not in program_defs:
            if prog is not None:
                #sample_defs[prog+0x20] = f"#WAVE 0x{prog+0x20:02X} 0x00"
                extract_brr(prog+0x20, progval)
                sample_defs[prog+0x20] = create_program_declaration(prog+0x20, progval)
                program_defs[prog+0x20] = f"#def {prog:1X}i=   |{prog:1X}"
                octave_defs[prog+0x20] = f"#def {prog:1X}o=   o{format.base_octave}"
                volume_defs[prog+0x20] = f"#def {prog:1X}v=   v100" + "\n" + \
                                         f"#def {prog:1X}f= v1,100"
            else:
                extract_brr(progval, progval)
                sample_defs[progval] = "#" + create_program_declaration(progval, progval)
                program_defs[progval] = f"#def {progval}@i=   @{progval}"
                octave_defs[progval] = f"#def {progval}@o=   o{format.base_octave}"
                volume_defs[progval] = f"#def {progval}@v=   v100" + "\n" + \
                                       f"#def {progval}@f= v1,100"
                
        if CONFIG_USE_PROGRAM_MACROS:
            text = f"\n'{macro_id}i'"
            if loc in program_locs:
                program, octave, volume = program_locs[loc]
            text += ' '
        return text
            
class OctaveCode(Code):
    def __init__(self, length, symbol, **kwargs):
        Code.__init__(self, length, symbol, **kwargs)
        self.type = "octave"
        if "octave_param" in kwargs:
            self.octave_param = kwargs["octave_param"] - 1
        else:
            self.octave_param = 0
        
    def write(self, cmd, loc):
        if CONFIG_USE_OCTAVE_MACROS:
            octave = self.params[self.octave_param](cmd)
            
            if loc in octave_locs:
                progval = octave_locs[loc][0]
            else:
                progval = None
            text = write_octave_macro(progval, octave, loc)
        else:
            text = Code.write(self, cmd, loc)
        return text
            
def write_octave_macro(progval, octave, loc=0):    
    if octave is None:
        return ""
    if progval in sample_mappings: #suzuki
        progval = convert_program(sample_mappings[progval])
    elif sample_mappings and progval is not None:
        print(f"program mapping for sample {progval:02X} not found")
    if progval is None:
        macro_id = "??"
        print(f"warning: unknown program in octave change at {loc:04X}")
    elif progval >= 0x20:
        macro_id = f"{progval-0x20:1X}"
    else:
        macro_id = f"{progval}@"
        
    rel = octave - 5
    text = f"'{macro_id}o"
    if rel:
        text += f"{'+' if rel > 0 else '-'}o{abs(rel)}"
    text += "'"
    return text
            
class VolumeCode(Code):
    def __init__(self, length, symbol, **kwargs):
        Code.__init__(self, length, symbol, **kwargs)
        self.type = "volume"
        if "volume_param" in kwargs:
            self.volume_param = kwargs["volume_param"] - 1
        else:
            self.volume_param = 0
            
    def write(self, cmd, loc):
        if CONFIG_USE_VOLUME_MACROS:
            volume = self.params[self.volume_param](cmd)
            if "env_param" in self.kwargs:
                env = self.params[self.kwargs["env_param"]-1](cmd)
            else:
                env = None
            if self.collapse_empty and not env:
                env = None
                
            if loc in volume_locs:
                progval = volume_locs[loc][0]
                volume = volume_locs[loc][1]
            else:
                progval = None
            text = write_volume_macro(progval, volume, env=env, loc=loc)
        else:
            text = Code.write(self, cmd, loc)
        return text
        
def write_volume_macro(progval, volume, env=None, loc=0):
    if volume is None:
        return ""
    env_text = "" if env is None else f"{env},"
    if progval in sample_mappings: #suzuki
        progval = convert_program(sample_mappings[progval])
    elif sample_mappings and progval is not None:
        print(f"program mapping for sample {progval:02X} not found")
    if progval is None:
        macro_id = "??"
        print(f"warning: unknown program in volume change at {loc:04X}")
    elif progval >= 0x20:
        macro_id = f"{progval-0x20:1X}"
    else:
        macro_id = f"{progval}@"
    vol = f"{volume / 100:.2f}".lstrip('0')
    text = f"'{macro_id}{'f' if env else 'v'}*v{env_text}{vol}'"
    return text
    
class ExpressionCode(VolumeCode):
    def __init__(self, length, symbol, **kwargs):
        Code.__init__(self, length, symbol, **kwargs)
        self.type = "expression"
        if "expression_param" in kwargs:
            self.expression_param = kwargs["expression_param"] - 1
            self.volume_param = 0
        else:
            self.expression_param = 0
            self.volume_param = 0

class Percussion(Code):
    def __init__(self, length, on, **kwargs):
        Code.__init__(self, length, "{P" + ("+" if on else "-") + "}", **kwargs)
        if on:
            self.type = "PercOn"
        else:
            self.type = "PercOff"
        
class NoteTable(Code):
    def __init__(self, length, symbol, **kwargs):
        Code.__init__(self, length, symbol, **kwargs)
        self.type = "dur_table"

    def _evaluate(self, cmd):
        return [param(cmd) for param in self.params]
        
    def write(self, cmd, _):
        text = f"\n{{'Note table: "
        for dur in self._evaluate(cmd):
            text += f"{dur} "
        text = text.strip() + "'}\n"
        return text

    def get(self, cmd, _ = None):
        return self._evaluate(cmd)
        
class NoteTableShort(NoteTable):
    def _evaluate(self, cmd):
        rawval = self.params[0](cmd)
        
        note_values = [0xC0, 0x90, 0x60, 0x48, 0x40, 0x30, 0x24, 0x20,
                       0x18, 0x12, 0x10, 0x0C, 0x08, 0x06, 0x04, 0x03]
        note_table = []
        for i in range(0,16):
            if rawval & (1 << (15 - i)):
                note_table.append(note_values[i])
        
        return note_table
            
#########################
#### parameter types ####
#########################

def P(pos):
    def readp(cmd):
        return cmd[pos]
    return readp
    
def Multi(pos, length):
    def readp(cmd):
        num = cmd[pos:pos+length]
        return int.from_bytes(num, "little")
    return readp
    
def Scaled(pos, scale):
    def readp(cmd):
        return min(0xFF, int(cmd[pos] * scale))
    return readp
    
def TempoScale(pos):
    def readp(cmd):
        if format.tempo_mode == "suzuki":
            tempo = int(60000000 / (125 * cmd[pos] * 48))
        else:
            tempo = int(cmd[pos] * format.tempo_scale)
            if format.tempo_mode == "fm":
                tempo += (int(tempo * 0x14) >> 8)
        return min(0xFF, tempo)
    return readp
    
def LfoScale(pos):
    def readp(cmd):
        return min(0xFF, int(cmd[pos] / 4) + 192)
    return readp

def SixBitFloorScaled(pos, floor, scale): #rudra vibrato
                                          #just locking it on bidirectional
                                          #instead of figuring out its modes
    def readp(cmd):
        val = cmd[pos] & 0x00111111
        return min(0xFF, floor + round(val * scale))
    return readp
    
def Increment(pos):
    def readp(cmd):
        val = cmd[pos]
        if format.zero_loops_infinite and val == 0:
            return 0
        return val + 1
    return readp
    
def Signed(pos):
    def readp(cmd):
        num = cmd[pos]
        if num >= 0x80:
            num -= 0x100
        return num
    return readp
    
def ScaledSigned(pos, scale):
    def readp(cmd):
        num = cmd[pos]
        if num >= 0x80:
            num -= 0x100
        return min(0xFF, int(num * scale))
    return readp
    
def ShiftedSigned(pos, delta):
    def readp(cmd):
        num = cmd[pos]
        if num >= 0x80:
            num -= 0x100
        num += delta
        if abs(num) > 0xFF:
            print(f"{pos:04X}: {' '.join([f'{b:02X}' for b in cmd])} delta {delta}: warning: shifted value {num} out of range")
        return num
    return readp
    
def Fixed(val):
    def readp(cmd):
        return val
    return readp
    
#### format definitions ####

general_note_table = ["c", "c+", "d", "d+", "e", "f", "f+", "g", "g+", "a", "a+", "b"]
note_symbol_by_id = {i: n for i, n in enumerate(general_note_table)}

formats = {}

## ## ## AKAO1 ## ## ##

        # FINAL FANTASY IV #
formats["ff4"] = Format("01", "ff4", "AKAO1 / Final Fantasy IV")
formats["ff4"].scanner_loc = 0x900
formats["ff4"].scanner_data = b"\x20\xC0\xCD\xCF\xBD\xE8\x00\x5D" + \
                              b"\xAF\xC8\xE0\xD0\xFB\xA2\x8A\x8F"
formats["ff4"].sequence_loc = 0x2100
formats["ff4"].brr_table = 0x1F00
formats["ff4"].brr_table_size = 0x200
formats["ff4"].tuning_table = 0x10000
formats["ff4"].tuning_type = "single"
formats["ff4"].sequence_relative = False
formats["ff4"].header_type = 1 
formats["ff4"].tempo_scale = (60000 / 216) / 256
formats["ff4"].note_table = ["c", "c+", "d", "d+", "e", "f", "f+", "g", "g+", "a", "a+", "b", "r", "^"]
formats["ff4"].duration_table = ["1", "2.", "2", "4.", "3", "4", "8.", "6", "8", "12", "16", "24", "32", "48", "64"]
formats["ff4"].bytecode = {
    0xD2: Code(4, "t", params=[Multi(1,2), TempoScale(3)], collapse_empty=True, env_param=1),
    0xD3: Comment(2, "nop {}", params=[P(1)]),
    0xD4: Code(2, "%v", params=[P(1)]),
    0xD5: DoubleCode(3, "%b0,", "%f0,", first_params=[P(1)], second_params=[P(2)]),
    0xD6: Comment(4, "PitchSlideMode delay={} len={} depth={}", params=[P(1), P(2), Signed(3)]),
    0xD7: Code(4, "v", params=[P(1), P(2), LfoScale(3)]),
    0xD8: Code(4, "m", params=[P(1), P(2), LfoScale(3)]),
    0xD9: Code(4, "{PansweepWithDelay}p", params=[P(1), P(2), P(3)]),
    0xDA: OctaveCode(2, "o", params=[P(1)], octave_param=1),
    0xDB: ProgramCode(2, params=[P(1)]),
    0xDC: Comment(2, "VolEnvMode {}", params=[P(1)]),
    0xDD: Code(2, "%r", params=[P(1)]), #GAIN release -> ADSR sustain rate
    0xDE: Comment(2, "Duration {}%", params=[P(1)]),
    0xDF: Code(2, "%c", params=[P(1)]),
    0xE0: Code(2, "[", params=[Increment(1)], collapse_empty=True, count_param=1),
    0xE1: Code(1, "<"),
    0xE2: Code(1, ">"),
    0xE3: Comment(1, "nop"),
    0xE4: Comment(1, "nop"),
    0xE5: Comment(1, "nop"),
    0xE6: Comment(1, "PitchSlideOff"),
    0xE7: Code(1, "v"),
    0xE8: Code(1, "m"),
    0xE9: Code(1, "p"),
    0xEA: Code(1, "%e1"),
    0xEB: Code(1, "%e0"),
    0xEC: Code(1, "%n1"),
    0xED: Code(1, "%n0"),
    0xEE: Code(1, "%p1"),
    0xEF: Code(1, "%p0"),
    0xF0: Code(1, "]"),
    0xF1: Code(1, ";"),
    0xF2: VolumeCode(4, "v", params=[Multi(1,2), Scaled(3, .5)], env_param=1, volume_param=2, collapse_empty=True),
    0xF3: Code(4, "p", params=[Multi(1,2), Scaled(3, .5)], env_param=1, collapse_empty=True),
    0xF4: Jump(3, ";", dest=Multi(1,2)),
    0xF5: Jump(4, "j", params=[P(1)], dest=Multi(2,2), volta_param=1),
    0xF6: Comment(1, "?"),
    0xF7: Code(1, ";"),
    0xF8: Code(1, ";"),
    0xF9: Code(1, ";"),
    0xFA: Code(1, ";"),
    0xFB: Code(1, ";"),
    0xFC: Code(1, ";"),
    0xFD: Code(1, ";"),
    0xFE: Code(1, ";"),
    0xFF: Code(1, ";")
    }
formats["ff4"].loop_start = [0xE0]
formats["ff4"].loop_end = [0xF0]
formats["ff4"].end_track = [0xF1, 0xF7, 0xF8, 0xF9, 0xFA, 0xFB, 0xFC, 0xFD, 0xFE, 0xFF]
formats["ff4"].octave_up = [0xE1]
formats["ff4"].octave_down = [0xE2]
formats["ff4"].hard_jump = [0xF4]
formats["ff4"].volta_jump = [0xF5]
formats["ff4"].program_base = 0x40

## ## ## AKAO2 ## ## ##

        # ROMANCING SAGA #
formats["rs1"] = Format("02", "rs1", "AKAO2 / Romancing SaGa")
formats["rs1"].scanner_loc = 0x900
formats["rs1"].scanner_data = b"\x20\xC0\xCD\xfF\xBD\xE8\x00\x5D" + \
                              b"\xAF\xC8\xF0\xD0\xFB\x1A\x02\xE8"
formats["rs1"].sequence_loc = 0x2100
formats["rs1"].sequence_relative = False
formats["rs1"].brr_table = 0x2000
formats["rs1"].env_table = 0x1F80
formats["rs1"].tuning_table = 0x1F40
formats["rs1"].tuning_type = "single"
formats["rs1"].header_type = 1 
formats["rs1"].tempo_scale = (60000 / 216) / 256
formats["rs1"].note_table = ["c", "c+", "d", "d+", "e", "f", "f+", "g", "g+", "a", "a+", "b", "r", "^"]
formats["rs1"].duration_table = ["1", "2.", "2", "3", "4.", "4", "6", "8.", "8", "12", "16", "24", "32", "48", "64"]
formats["rs1"].bytecode = {
    0xD2: Code(2, "t", params=[TempoScale(1)]),
    0xD3: Code(3, "t", params=[P(1), TempoScale(2)], env_param=1),
    0xD4: VolumeCode(2, "v", params=[Scaled(1, .5)], volume_param=1),
    0xD5: VolumeCode(3, "v", params=[P(1), Scaled(2, .5)], env_param=1, volume_param=2),
    0xD6: Code(2, "p", params=[P(1)]),
    0xD7: Code(3, "p", params=[P(1), P(2)], env_param=1),
    0xD8: Code(2, "%v", params=[P(1)]),
    0xD9: Code(3, "%v", params=[P(1), P(2)], env_param=1),
    0xDA: Code(2, "%k", params=[Signed(1)]),
    0xDB: Comment(4, "PitchSlideMode len={}? delay={}? depth={}", params=[P(1), P(2), Signed(3)]),
    0xDC: Comment(1, "PitchSlideOff"),
    0xDD: Code(4, "m", params=[P(2), P(3), LfoScale(1)]), #guessing - vgmtrans has this wrong but i'm not sure what's right. 2nd param byte is definitely delay. DD is vibrato, not tremolo.
    0xDE: Code(1, "m"),
    0xDF: Code(4, "v", params=[P(2), P(3), LfoScale(1)]),
    0xE0: Code(1, "v"),
    0xE1: Code(2, "%c", params=[P(1)]),
    0xE2: Code(1, "%n1"),
    0xE3: Code(1, "%n0"),
    0xE4: Code(1, "%p1"),
    0xE5: Code(1, "%p0"),
    0xE6: DoubleCode(3, "%b0,", "%f0,", first_params=[P(1)], second_params=[P(2)]),
    0xE7: Code(1, "%e1"),
    0xE8: Code(1, "%e0"),
    0xE9: Code(3, "p0,", params=[P(1), P(2)]),
    0xEA: Code(1, "p"),
    0xEB: OctaveCode(2, "o", params=[P(1)], octave_param=1),
    0xEC: Code(1, "<"),
    0xED: Code(1, ">"),
    0xEE: Code(2, "[", params=[Increment(1)], collapse_empty=True, count_param=1),
    0xEF: Code(1, "]"),
    0xF0: Jump(4, "j", params=[P(1)], dest=Multi(1,2), volta_param=1),
    0xF1: Jump(3, ";", dest=Multi(1,2)),
    0xF2: Code(1, "%l1"),
    0xF3: ProgramCode(2, params=[P(1)]),
    0xF4: Comment(2, "VolEnvMode {}", params=[P(1)]),
    0xF5: Code(1, "%l0"),
    0xF6: Jump(3, ":", dest=Multi(1,2)),
    0xF7: Code(2, "k", params=[Signed(1)]),
    0xF8: Code(1, ";"),
    0xF9: Code(1, ";"),
    0xFA: Code(1, ";"),
    0xFB: Code(1, ";"),
    0xFC: Code(1, ";"),
    0xFD: Code(1, ";"),
    0xFE: Code(1, ";"),
    0xFF: Code(1, ";"),
    }
formats["rs1"].loop_start = [0xEE]
formats["rs1"].loop_end = [0xEF]
formats["rs1"].end_track = [0xF8, 0xF9, 0xFA, 0xFB, 0xFC, 0xFD, 0xFE, 0xFF]
formats["rs1"].octave_up = [0xEC]
formats["rs1"].octave_down = [0xED]
formats["rs1"].hard_jump = [0xF1]
formats["rs1"].volta_jump = [0xF0]
formats["rs1"].conditional_jump = [0xF6]

## ## ## AKAO3 ## ## ##

        # FINAL FANTASY MYSTIC QUEST #
formats["ffmq"] = Format("03", "ffmq", "AKAO3 / Final Fantasy Mystic Quest")
formats["ffmq"].scanner_loc = 0x300
formats["ffmq"].scanner_data = b"\x20\xC0\xCD\xFF\xBD\xE8\x00\x5D" + \
                              b"\xAF\xC8\xF0\xD0\xFB\x1A\x02\x1A"
formats["ffmq"].sequence_loc = 0x1D00
formats["ffmq"].brr_table = 0x1C00
formats["ffmq"].env_table = 0x1B80
formats["ffmq"].tuning_table = 0x1B00
formats["ffmq"].tuning_type = "double"
formats["ffmq"].header_type = 2
formats["ffmq"].tempo_scale = (60000 / 216) / 256
formats["ffmq"].note_table = ["c", "c+", "d", "d+", "e", "f", "f+", "g", "g+", "a", "a+", "b", "^", "r"]
formats["ffmq"].duration_table = ["1", "2.", "2", "3", "4.", "4", "6", "8.", "8", "12", "16", "24", "32", "48", "64"]
formats["ffmq"].bytecode = {
    0xD2: VolumeCode(2, "v", params=[Scaled(1, .5)], volume_param=1),
    0xD3: VolumeCode(3, "v", params=[P(1), Scaled(2, .5)], env_param=1, volume_param=2),
    0xD4: Code(2, "p", params=[Scaled(1, .5)]),
    0xD5: Code(3, "p", params=[P(1), Scaled(2, .5)], env_param=1),
    0xD6: Code(3, "m", params=[P(1), Signed(2)]),
    0xD7: Code(4, "m", params=[P(1), P(2), P(3)]),
    0xD8: Code(1, "m"),
    0xD9: Code(4, "v", params=[P(1), P(2), P(3)]),
    0xDA: Code(1, "v"),
    0xDB: Code(3, "p0,", params=[P(1), P(2)]),
    0xDC: Code(1, "p"),
    0xDD: Code(2, "%c", params=[P(1)]),
    0xDE: Code(1, "%n1"),
    0xDF: Code(1, "%n0"),
    0xE0: Code(1, "%p1"),
    0xE1: Code(1, "%p0"),
    0xE2: Code(1, "%e1"),
    0xE3: Code(1, "%e0"),
    0xE4: OctaveCode(2, "o", params=[P(1)], octave_param=1),
    0xE5: Code(1, "<"),
    0xE6: Code(1, ">"),
    0xE7: Code(2, "%k", params=[Signed(1)]),
    0xE8: Code(2, "m", params=[Signed(1)]),
    0xE9: Code(2, "k", params=[Signed(1)]),
    0xEA: ProgramCode(2, params=[P(1)]),
    0xEB: Code(2, "%a", params=[P(1)]),
    0xEC: Code(2, "%y", params=[P(1)]),
    0xED: Code(2, "%s", params=[P(1)]),
    0xEE: Code(2, "%r", params=[P(1)]),
    0xEF: Code(1, "%y"),
    0xF0: Code(2, "[", params=[Increment(1)], collapse_empty=True, count_param=1),
    0xF1: Code(1, "]"),
    0xF2: Code(1, ";"),
    0xF3: Code(2, "t", params=[TempoScale(1)]),
    0xF4: Code(3, "t", params=[P(1), TempoScale(2)], env_param=1),
    0xF5: Code(2, "%v", params=[P(1)]),
    0xF6: Code(3, "%v", params=[P(1), P(2)], env_param=1),
    0xF7: DoubleCode(3, "%b0,", "%f0,", first_params=[P(1)], second_params=[P(2)]),
    0xF8: Code(2, "%x", params=[P(1)]),
    0xF9: Jump(4, "j", params=[P(1)], dest=Multi(2,2), volta_param=1),
    0xFA: Jump(3, ";", dest=Multi(1,2)),
    0xFB: Jump(3, ":", dest=Multi(1,2)),
    0xFC: Code(1, ";"),
    0xFD: Code(1, ";"),
    0xFE: Code(1, ";"),
    0xFF: Code(1, ";")
    }
formats["ffmq"].loop_start = [0xF0]
formats["ffmq"].loop_end = [0xF1]
formats["ffmq"].end_track = [0xF2, 0xFC, 0xFD, 0xFE, 0xFF]
formats["ffmq"].octave_up = [0xE5]
formats["ffmq"].octave_down = [0xE6]
formats["ffmq"].hard_jump = [0xFA]
formats["ffmq"].volta_jump = [0xF9]
formats["ffmq"].conditional_jump = [0xFB]

        # FINAL FANTASY V #
formats["ff5"] = copy.deepcopy(formats["ffmq"])
formats["ff5"].sort_as = "04"
formats["ff5"].id = "ff5"
formats["ff5"].display_name = "AKAO3 / Final Fantasy V, Hanjuku Hero"
formats["ff5"].scanner_loc = 0x300
formats["ff5"].scanner_data = b"\x20\xC0\xCD\xFF\xBD\xE8\x00\x5D" + \
                              b"\xAF\xC8\xF0\xD0\xFB\x1A\xEB\xE8"
formats["ff5"].header_type = 3
formats["ff5"].volta_jump = []
formats["ff5"].loop_break = [0xF9]

        # SEIKEN DENSETSU 2 #
formats["sd2"] = copy.deepcopy(formats["ff5"])
formats["sd2"].sort_as = "05"
formats["sd2"].id = "sd2"
formats["sd2"].display_name = "AKAO3 / Seiken Densetsu 2 (Secret of Mana)"
formats["sd2"].scanner_loc = 0x300
formats["sd2"].scanner_data = b"\x20\xC0\xCD\xFF\xBD\xE8\x00\x5D" + \
                              b"\xAF\xC8\xF0\xD0\xFB\xE8\x00\x8D"
formats["sd2"].sequence_loc = 0x1B00
formats["sd2"].brr_table = 0x1A00
formats["sd2"].env_table = 0x1980
formats["sd2"].tuning_table = 0x1900
formats["sd2"].tuning_type = "double"
formats["sd2"].bytecode[0xFC] = Comment(1, "LoopRestart")
formats["sd2"].bytecode[0xFD] = Comment(2, "IgnoreMVol prg={}", params=[P(1)])
formats["sd2"].end_track = [0xF2, 0xFE, 0xFF]

## ## ## AKAO4 ## ## ##

        # ROMANCING SAGA 2 #
formats["rs2"] = Format("06", "rs2", "AKAO4 / Romancing SaGa 2")
formats["rs2"].scanner_loc = 0x310
formats["rs2"].scanner_data = b"\x00\x8D\x0C\x3F\x5C\x06\x8D\x1C" + \
                              b"\x3F\x5C\x06\x8D\x2C\x3F\x5C\x06"
formats["rs2"].sequence_loc = 0x1D00
formats["rs2"].brr_table = 0x1C00
formats["rs2"].env_table = 0x1B80
formats["rs2"].tuning_table = 0x1B00
formats["rs2"].tuning_type = "double"
formats["rs2"].header_type = 4
formats["rs2"].tempo_scale = (60000 / 216) / 256
formats["rs2"].note_table = ["c", "c+", "d", "d+", "e", "f", "f+", "g", "g+", "a", "a+", "b", "^", "r"]
formats["rs2"].duration_table = ["1", "2", "3", "4.", "4", "6", "8.", "8", "12", "16", "24", "32", "48", "64"]
formats["rs2"].bytecode = {
    0xC4: VolumeCode(2, "v", params=[Scaled(1, .5)], volume_param=1),
    0xC5: VolumeCode(3, "v", params=[P(1), Scaled(2, .5)], env_param=1, volume_param=2),
    0xC6: Code(2, "p", params=[Scaled(1, .5)]),
    0xC7: Code(3, "p", params=[P(1), Scaled(2, .5)], env_param=1),
    0xC8: Code(3, "m", params=[P(1), Signed(2)]),
    0xC9: Code(4, "m", params=[P(1), P(2), P(3)]),
    0xCA: Code(1, "m"),
    0xCB: Code(4, "v", params=[P(1), P(2), P(3)]),
    0xCC: Code(1, "v"),
    0xCD: Code(3, "p0,", params=[P(1), P(2)]),
    0xCE: Code(1, "p"),
    0xCF: Code(2, "%c", params=[P(1)]),
    0xD0: Code(1, "%n1"),
    0xD1: Code(1, "%n0"),
    0xD2: Code(1, "%p1"),
    0xD3: Code(1, "%p0"),
    0xD4: Code(1, "%e1"),
    0xD5: Code(1, "%e0"),
    0xD6: OctaveCode(2, "o", params=[P(1)], octave_param=1),
    0xD7: Code(1, "<"),
    0xD8: Code(1, ">"),
    0xD9: Code(2, "%k", params=[Signed(1)]),
    0xDA: Code(2, "m", params=[Signed(1)]),
    0xDB: Code(2, "k", params=[Signed(1)]),
    0xDC: ProgramCode(2, params=[P(1)]),
    0xDD: Code(2, "%a", params=[P(1)]),
    0xDE: Code(2, "%y", params=[P(1)]),
    0xDF: Code(2, "%s", params=[P(1)]),
    0xE0: Code(2, "%r", params=[P(1)]),
    0xE1: Code(1, "%y"),
    0xE2: Code(2, "[", params=[Increment(1)], collapse_empty=True, count_param=1),
    0xE3: Code(1, "]"),
    0xE4: Code(1, "%l1"),
    0xE5: Code(1, "%l0"),
    0xE6: Code(1, "%g1"),
    0xE7: Code(1, "%g0"),
    0xE8: Code(2, "&", params=[P(1)]),
    0xE9: Code(2, "s0,", params=[P(1)]),
    0xEA: Code(2, "s1,", params=[P(1)]),
    0xEB: Code(1, ";"),
    0xEC: Code(1, ";"),
    0xED: Code(1, ";"),
    0xEE: Code(1, ";"),
    0xEF: Code(1, ";"),
    0xF0: Code(2, "t", params=[TempoScale(1)]),
    0xF1: Code(3, "t", params=[P(1), TempoScale(2)], env_param=1),
    0xF2: Code(2, "%v", params=[P(1)]),
    0xF3: Code(3, "%v", params=[P(1), P(2)], env_param=1),
    0xF4: DoubleCode(3, "%b0,", "%f0,", first_params=[P(1)], second_params=[P(2)]),
    0xF5: Code(2, "%x", params=[P(1)]),
    0xF6: Jump(4, "j", params=[P(1)], dest=Multi(2,2), volta_param=1),
    0xF7: Jump(3, ";", dest=Multi(1,2)),
    0xF8: Code(1, "u1"),
    0xF9: Code(1, "u0"),
    0xFA: Code(1, "%i"),
    0xFB: Code(1, ";"),
    0xFC: Code(1, ";"),
    0xFD: Code(1, ";"),
    0xFE: Code(1, ";"),
    0xFF: Code(1, ";")
    }
formats["rs2"].loop_start = [0xE2]
formats["rs2"].loop_end = [0xE3]
formats["rs2"].end_track = [0xEB, 0xEC, 0xED, 0xEE, 0xEF, 0xFB, 0xFC, 0xFD, 0xFE, 0xFF]
formats["rs2"].octave_up = [0xD7]
formats["rs2"].octave_down = [0xD8]
formats["rs2"].hard_jump = [0xF7]
formats["rs2"].loop_break = [0xF6]

        # LIVE A LIVE #
formats["lal"] = copy.deepcopy(formats["rs2"])
formats["lal"].sort_as = "07"
formats["lal"].id = "lal"
formats["lal"].display_name = "AKAO4 / Live A Live"
formats["lal"].scanner_data = b"\x00\x8D\x2C\x3F\x14\x06\x8D\x3C" + \
                              b"\x3F\x14\x06\x8D\x5D\xE8\x1B\x3F"
formats["lal"].bytecode[0xFB] = Jump(3, ":", dest=Multi(1,2))
formats["lal"].conditional_jump = [0xFB]
formats["lal"].end_track = [0xEB, 0xEC, 0xED, 0xEE, 0xEF, 0xFC, 0xFD, 0xFE, 0xFF]
                  
        # FINAL FANTASY VI #
formats["ff6"] = copy.deepcopy(formats["lal"])
formats["ff6"].sort_as = "08"
formats["ff6"].id = "ff6"
formats["ff6"].display_name = "AKAO4 / Final Fantasy VI"
formats["ff6"].scanner_data = b"\x00\x8D\x0C\x3F\x48\x06\x8D\x1C" + \
                              b"\x3F\x48\x06\x8D\x2C\x3F\x48\x06"
formats["ff6"].tempo_scale = 1
formats["ff6"].bytecode[0xC4] = VolumeCode(2, "v", params=[P(1)], volume_param=1)
formats["ff6"].bytecode[0xC5] = VolumeCode(3, "v", params=[P(1), P(2)], env_param=1, volume_param=2)
formats["ff6"].bytecode[0xC6] = Code(2, "p", params=[P(1)])
formats["ff6"].bytecode[0xC7] = Code(3, "p", params=[P(1), P(2)], env_param=1)
formats["ff6"].bytecode[0xF4] = Code(2, "%x", params=[P(1)])
formats["ff6"].bytecode[0xF5] = Jump(4, "j", params=[P(1)], dest=Multi(2,2), volta_param=1)
formats["ff6"].bytecode[0xF6] = Jump(3, ";", dest=Multi(1,2))
formats["ff6"].bytecode[0xF7] = Code(3, "%b", params=[P(1), P(2)], env_param=1)
formats["ff6"].bytecode[0xF8] = Code(3, "%f", params=[P(1), P(2)], env_param=1)
formats["ff6"].bytecode[0xF9] = Code(1, "u1")
formats["ff6"].bytecode[0xFA] = Code(1, "u0")
formats["ff6"].bytecode[0xFB] = Code(1, "%i")
formats["ff6"].bytecode[0xFC] = Jump(3, ":", dest=Multi(1,2))
formats["ff6"].end_track = [0xEB, 0xEC, 0xED, 0xEE, 0xEF, 0xFD, 0xFE, 0xFF]
formats["ff6"].hard_jump = [0xF6]
formats["ff6"].loop_break = [0xF5]
formats["ff6"].conditional_jump = [0xFC]

        # FRONT MISSION #
formats["fm"] = copy.deepcopy(formats["ff6"])
formats["fm"].sort_as = "09"
formats["fm"].id = "fm"
formats["fm"].display_name = "AKAO4 / Front Mission"
formats["fm"].scanner_data = b"\xC7\xE8\x00\x8D\x2C\x3F\x05\x07" + \
                             b"\x8D\x3C\x3F\x05\x07\xCD\x40\xD5"
formats["fm"].sequence_loc = 0x2100
formats["fm"].brr_table = 0x1F00
formats["fm"].env_table = 0x2080
formats["fm"].tuning_table = 0x2000
formats["fm"].tuning_type = "double"
formats["fm"].percussion_table_loc = 0xF220
formats["fm"].use_expression = True
formats["fm"].tempo_scale = (60000 / 252) / 256
formats["fm"].tempo_mode = "fm"
formats["fm"].bytecode[0xF9] = Comment(2, "F9 {}", params=[P(1)])
formats["fm"].bytecode[0xFA] = Jump(4, ":", dest=Multi(2,2))
formats["fm"].bytecode[0xFB] = Percussion(1, True)
formats["fm"].bytecode[0xFC] = Percussion(1, False)
formats["fm"].bytecode[0xFD] = ExpressionCode(2, "{e}", params=[P(1)], expression_param=1)
formats["fm"].end_track = [0xEB, 0xEC, 0xED, 0xEE, 0xEF, 0xFE, 0xFF]
formats["fm"].conditional_jump = [0xFA]

        # CHRONO TRIGGER #
formats["ct"] = copy.deepcopy(formats["fm"])
formats["ct"].sort_as = "10"
formats["ct"].id = "ct"
formats["ct"].display_name = "AKAO4 / Chrono Trigger"
formats["ct"].scanner_data = b"\xBB\x8D\x2C\x3F\xA3\x07\x8D\x3C" + \
                             b"\x3F\xA3\x07\xCD\x40\xD5\x6E\xF1"
formats["ct"].bytecode[0xF9] = Comment(2, "CpuSetValue {}", params=[P(1)])

## ## ## SUZUKI ## ## ##

        # SEIKEN DENSETSU 3 #
formats["sd3"] = Format("11", "sd3", "SUZUKI / Seiken Densetsu 3 (Trials of Mana)")
formats["sd3"].scanner_loc = 0x310
formats["sd3"].scanner_data = b"\xFF\xBD\x3F\x0A\x03\x8F\x00\xF6" + \
                              b"\x8F\x02\xF7\xC4\xF4\xC4\xF5\xE4"
formats["sd3"].sequence_loc = 0x2100
formats["sd3"].program_map_loc = 0x5F80
formats["sd3"].brr_table = 0x5F00
formats["sd3"].env_table = 0x6040
formats["sd3"].tuning_table = 0x6080
formats["sd3"].tuning_type = "suzuki"
formats["sd3"].header_type = 5
formats["sd3"].sequence_relative = False
formats["sd3"].tempo_scale = 1
formats["sd3"].tempo_mode = "suzuki"
formats["sd3"].note_sort_by_duration = True
formats["sd3"].note_increment_custom_duration = True
formats["sd3"].program_base = 0x8
formats["sd3"].loops_store_octave = True
formats["sd3"].max_loop_stack = 10
formats["sd3"].note_table = ["c", "c+", "d", "d+", "e", "f", "f+", "g", "g+", "a", "a+", "b", "r", "^"]
formats["sd3"].duration_table = ["1", "2.", "2", "4.", "4", "8.", "6", "8", "12", "16", "24", "32", "64", None]
formats["sd3"].bytecode = {
    0xC4: Code(1, "<"),
    0xC5: Code(1, ">"),
    0xC6: OctaveCode(2, "o", params=[P(1)], octave_param=1),
    0xC7: Comment(1, "nop"),
    0xC8: Code(2, "%c", params=[P(1)]),
    0xC9: Code(1, "%n1"),
    0xCA: Code(1, "%n0"),
    0xCB: Code(1, "%p1"),
    0xCC: Code(1, "%p0"),
    0xCD: Code(2, "s0", params=[P(1)]),
    0xCE: Code(2, "s1", params=[P(1)]),
    0xCF: Code(2, "k", params=[Signed(1)]),
    0xD0: Code(1, ";"),
    0xD1: Code(2, "t", params=[TempoScale(1)]),
    0xD2: Code(2, "[", params=[P(1)], collapse_empty=True, count_param=1),
    0xD3: Code(2, "[", params=[P(1)], collapse_empty=True, count_param=1),
    0xD4: Code(2, "[", params=[P(1)], collapse_empty=True, count_param=1),
    0xD5: Code(1, "]"),
    0xD6: Jump(1, "j"),
    0xD7: Code(1, "$"),
    0xD8: Code(1, "%y"),
    0xD9: Code(2, "%a", params=[P(1)]),
    0xDA: Code(2, "%d", params=[P(1)]),
    0xDB: Code(2, "%s", params=[P(1)]),
    0xDC: Code(2, "%r", params=[P(1)]),
    0xDD: Comment(2, "Duration {}%", params=[P(1)]),
    0xDE: ProgramCodeBySample(2, params=[P(1)]),
    0xDF: Comment(2, "NoiseClock Rel {}", params=[P(1)]),
    0xE0: VolumeCode(2, "v", params=[P(1)], volume_param=1),
    0xE1: Comment(1, "E1"), #unknown length
    0xE2: VolumeCode(2, "v", params=[P(1)], volume_param=1),
    0xE3: Comment(1, "VolRel {}", params=[P(1)]),
    0xE4: VolumeCode(3, "v", params=[P(1), P(2)], env_param=1, volume_param=2),
    0xE5: Comment(3, "m", params=[P(1), Signed(2)]),
    0xE6: Comment(1, "PortaToggle"),
    0xE7: Code(2, "p", params=[Scaled(1, .5)]),
    0xE8: Code(3, "p", params=[P(1), Scaled(2, .5)], env_param=1),
    0xE9: Comment(3, "TODO PanLFO rate={} depth={}", params=[P(1), P(2)]),
    0xEA: Comment(1, "PanLFOReset"),
    0xEB: Code(1, "p"),
    0xEC: Code(2, "%k", params=[P(1)]),
    0xED: Code(2, "m", params=[P(1)]),
    0xEE: Percussion(1, True),
    0xEF: Percussion(1, False),
    0xF0: Code(3, "m0,", params=[P(1), P(2)]),
    0xF1: Code(4, "m", params=[P(1), P(2), P(3)]),
    0xF2: Comment(2, "TempoRel {}", params=[P(1)]),
    0xF3: Code(1, "m"),
    0xF4: Code(3, "v0,", params=[P(1), P(2)]),
    0xF5: Code(4, "v", params=[P(1), P(2), P(3)]),
    0xF6: Code(1, "<"),
    0xF7: Code(1, "v"),
    0xF8: Code(1, "%l1"),
    0xF9: Code(1, "%l0"),
    0xFA: Code(1, "%e1"),
    0xFB: Code(1, "%e0"),
    0xFC: Comment(2, "PlaySfxLo {}", params=[P(1)]),
    0xFD: Comment(2, "PlaySfxHi {}", params=[P(1)]),
    0xFE: Code(1, "<"),
    0xFF: Code(1, "<")
    }
formats["sd3"].loop_start = [0xD2, 0xD3, 0xD4]
formats["sd3"].loop_end = [0xD5]
formats["sd3"].end_track = [0xD0]
formats["sd3"].octave_up = [0xC4, 0xF6, 0xFE, 0xFF]
formats["sd3"].octave_down = [0xC5]
formats["sd3"].loop_break = [0xD6]
        
        # ROMANCING SAGA 3 #
formats["rs3"] = copy.deepcopy(formats["ct"])
formats["rs3"].sort_as = "12"
formats["rs3"].id = "ct"
formats["rs3"].display_name = "AKAO4 / Romancing SaGa 3"
formats["rs3"].scanner_data = b"\xBC\x8D\x2C\x3F\x97\x07\x8D\x3C" + \
                              b"\x3F\x97\x07\xCD\x40\xD5\x68\xF1"
formats["rs3"].sequence_loc = 0x2300
formats["rs3"].brr_table = 0x2100
formats["rs3"].env_table = 0x2280
formats["rs3"].tuning_table = 0x2200
formats["rs3"].tuning_type = "double"
formats["rs3"].tempo_scale = 1
formats["rs3"].tempo_mode = "simple"
formats["rs3"].bytecode[0xF4] = ExpressionCode(2, "{e}", params=[P(1)], expression_param=1)
formats["rs3"].bytecode[0xF7] = Code(2, "%b0,", params=[P(1)])
formats["rs3"].bytecode[0xF8] = Code(2, "%f0,", params=[P(1)])
formats["rs3"].bytecode[0xFD] = Comment(2, "PlaySfx {}", params=[P(1)])

        # BANDAI SATELLAVIEW #
formats["bs"] = copy.deepcopy(formats["rs3"])
formats["bs"].sort_as = "13"
formats["bs"].id = "ct"
formats["bs"].display_name = "AKAO4 / BS - DynamiTracer, Treasure Conflix, Koi ha Balance, Radical Dreamers"
formats["bs"].scanner_data = b"\xC4\x8D\x2C\x3F\x1F\x08\x8D\x3C" + \
                             b"\x3F\x1F\x08\xCD\x40\xD5\x6E\xF1"
formats["bs"].sequence_loc = 0x2500
formats["bs"].brr_table = 0x2300
formats["bs"].env_table = 0x2480
formats["bs"].tuning_table = 0x2400
formats["bs"].tuning_type = "double"
formats["bs"].bytecode[0xFD] = Comment(2, "FD {}", params=[P(1)])
formats["bs"].bytecode[0xFE] = Comment(1, "FE")
formats["bs"].end_track = [0xEB, 0xEC, 0xED, 0xEE, 0xEF, 0xFF]

        # BAHAMUT LAGOON #
formats["bl"] = copy.deepcopy(formats["sd3"])
formats["bl"].sort_as = "14"
formats["bl"].id = "bl"
formats["bl"].display_name = "SUZUKI / Bahamut Lagoon"
formats["bl"].scanner_loc = 0x310
formats["bl"].scanner_data = b"\xFF\xBD\x3F\x11\x03\x8F\x00\xF6" + \
                             b"\x8F\x02\xF7\xC4\xF4\xC4\xF5\xE4"
formats["bl"].program_map_loc = 0x5780
formats["bl"].brr_table = 0x5700
formats["bl"].env_table = 0x5840
formats["bl"].tuning_table = 0x5880
formats["bl"].tuning_type = "suzuki"
formats["bl"].header_type = 6
formats["bl"].program_base = 0x8
formats["bl"].note_increment_custom_duration = False
formats["bl"].bytecode[0xD2] = Comment(2, "TimerFreq {}", params=[P(1)])
formats["bl"].bytecode[0xD3] = Comment(2, "TimerFreq Rel {}", params=[P(1)])
formats["bl"].bytecode[0xE0] = Comment(2, "RestRelease {}", params=[P(1)])
formats["bl"].bytecode[0xF6] = Comment(2, "F6 {}", params=[P(1)])
formats["bl"].bytecode[0xFC] = Code(1, "<")
formats["bl"].bytecode[0xFD] = Code(1, "<")
formats["bl"].bytecode[0xFE] = Comment(1, "FE")
formats["bl"].bytecode[0xFF] = Comment(1, "FF")
formats["bl"].loop_start = [0xD4]
formats["bl"].octave_up = [0xC4, 0xFC, 0xFD]
                     
        # FRONT MISSION : GUN HAZARD #
formats["gh"] = copy.deepcopy(formats["bs"])
formats["gh"].sort_as = "15"
formats["gh"].id = "gh"
formats["gh"].display_name = "AKAO4 / Front Mission: Gun Hazard"
formats["gh"].scanner_data = b"\xC4\x8D\x2C\x3F\x40\x07\x8D\x3C" + \
                             b"\x3F\x40\x07\xCD\x40\xD5\x6E\xF8"
formats["gh"].sequence_loc = 0x2300
formats["gh"].brr_table = 0x2100
formats["gh"].env_table = 0x2280
formats["gh"].tuning_table = 0x2200
formats["gh"].tuning_type = "double"
formats["gh"].percussion_table_loc = 0xF920
formats["gh"].bytecode[0xEB] = Comment(2, "EB {}", params=[P(1)])
formats["gh"].bytecode[0xFD] = Code(1, ";")
formats["gh"].bytecode[0xFE] = Code(1, ";")
formats["gh"].end_track = [0xEC, 0xED, 0xEE, 0xEF, 0xFD, 0xFE, 0xFF]

        # SUPER MARIO RPG #
formats["smrpg"] = copy.deepcopy(formats["bl"])
formats["smrpg"].sort_as = "16"
formats["smrpg"].id = "smrpg"
formats["smrpg"].display_name = "SUZUKI / Super Mario RPG"
formats["smrpg"].scanner_loc = 0x310
formats["smrpg"].scanner_data = b"\xFF\xBD\x3F\x1A\x03\x8F\x00\xF6" + \
                                b"\x8F\x02\xF7\xC4\xF4\xC4\xF5\xE4"
formats["smrpg"].program_map_loc = 0x4780
formats["smrpg"].brr_table = 0x4700
formats["smrpg"].env_table = 0x4840
formats["smrpg"].tuning_table = 0x4880
formats["smrpg"].tuning_type = "suzuki"
formats["smrpg"].program_base = 0xA
formats["smrpg"].bytecode[0xFC] = Comment(4, "FC {} {} {}", params=[P(1), P(2), P(3)])
formats["smrpg"].bytecode[0xFD] = Code(1, "<")
formats["smrpg"].bytecode[0xFE] = Comment(1, "FE")
formats["smrpg"].bytecode[0xFF] = Code(1, "<")
formats["smrpg"].octave_up = [0xC4, 0xFD, 0xFF]
                       
## ## ## ????? ## ## ##

        # RUDRA NO HIHOU #
formats["rnh"] = Format("17", "rnh", "Rudra no Hihou (Treasure of the Rudras)")
formats["rnh"].scanner_loc = 0x300
formats["rnh"].scanner_data = b"\x5D\x3E\xF4\xF0\xFC\xF8\xF4\x30" + \
                              b"\x03\x1F\x85\x03\x1F\x05\x03\xBA"
formats["rnh"].sequence_loc = 0x100 #dynamic location
formats["rnh"].brr_table = 0x1C00
formats["rnh"].env_table = 0x1F60
formats["rnh"].tuning_table = 0x1E40
formats["rnh"].tuning_type = "rudra"
formats["rnh"].header_type = 7
formats["rnh"].use_expression = True
formats["rnh"].tempo_scale = 1 #unknown
formats["rnh"].note_table = ["c", "c+", "d", "d+", "e", "f", "f+", "g", "g+", "a", "a+", "b", "c", "c+", "d", "d+", "e", "f", "f+", "g", "g+", "a", "a+", "b", "^", "r"]
formats["rnh"].duration_table = [0xC0, 0x60, 0x48, 0x30, 0x24, 0x18, 0x0C, None]
formats["rnh"].low_octave_notes = range(0x30,0x90)
formats["rnh"].dynamic_note_duration = True
formats["rnh"].first_note_id = 0x30
formats["rnh"].zero_loops_infinite = True
formats["rnh"].base_octave = 6
formats["rnh"].bytecode = {
    0x00: Code(1, ";"),
    0x01: Code(2, "%x", params=[P(1)]),
    0x02: Code(2, "%v", params=[Scaled(1, 2)]),
    0x03: ExpressionCode(2, "{e}", params=[Scaled(1, .5)], expression_param=1),
    0x04: DoubleCode(3, "%b0,", "%f0,", first_params=[P(1)], second_params=[P(2)]),
    0x05: Comment(1, "05"),
    0x06: Code(2, "t", params=[TempoScale(1)]),
    0x07: Code(3, "t", params=[P(1), TempoScale(2)], env_param=1),
    0x08: Comment(2, "08 {}", params=[P(1)]),
    0x09: NoteTableShort(3, "{L}", params=[Multi(1,2)]),
    0x0A: NoteTable(8, "{L}", params=[P(1), P(2), P(3), P(4), P(5), P(6), P(7)]),
    0x0B: Code(2, "%k", params=[ShiftedSigned(1, -36)]),
    0x0C: VolumeCode(2, "v", params=[Scaled(1, .5)], volume_param=1),
    0x0D: VolumeCode(3, "v", params=[P(1), Scaled(1, .5)], env_param=1, volume_param=2),
    0x0E: Code(2, "p", params=[Scaled(1, .5)]),
    0x0F: Code(3, "p", params=[P(1), Scaled(1, .5)], env_param=1),
    0x10: ProgramCode(2, params=[P(1)]),
    0x11: Code(2, "k", params=[ScaledSigned(1, .1)]),
    0x12: Code(2, "%a", params=[P(1)]),
    0x13: Code(2, "%y", params=[P(1)]),
    0x14: Code(2, "%s", params=[P(1)]),
    0x15: Code(2, "%r", params=[P(1)]),
    0x16: Comment(1, "%y"),
    0x17: Comment(2, "AltTuning {}", params=[P(1)]),
    0x18: Comment(2, "18 {}", params=[P(1)]),
    0x19: Code(4, "m", params=[P(1), Scaled(2, 4), SixBitFloorScaled(3, 192, 21)]),
    0x1A: Code(1, "m"),
    0x1B: Code(4, "v", params=[P(1), Scaled(2, 4), SixBitFloorScaled(3, 192, 21)]),
    0x1C: Code(1, "v"),
    0x1D: Code(3, "p0,", params=[Scaled(1, 2), Scaled(2, 1)]),
    0x1E: Code(1, "p"),
    0x1F: Code(1, "%n1"),
    0x20: Code(1, "%n0"),
    0x21: Code(1, "%p1"),
    0x22: Code(1, "%p0"),
    0x23: Code(1, "%e1"),
    0x24: Code(1, "%e0"),
    0x25: Comment(2, "PortaMode rate={}", params=[P(1)]),
    0x26: Comment(1, "PortaOff"),
    0x27: Comment(2, "27 {}", params=[P(1)]),
    0x28: Comment(1, "28"),
    0x29: Code(3, "m", params=[P(1), ScaledSigned(2, .5)]),
    0x2A: Code(2, "[", params=[Increment(1)], collapse_empty=True, count_param=1),
    0x2B: Comment(3, "2B {} {}", params=[P(1), P(2)]),
    0x2C: Comment(4, "2C {} {} {}", params=[P(1), P(2), P(3)]),
    0x2D: Comment(3, "2D {} {}", params=[P(1), P(2)]),
    0x2E: Code(1, "]"),
    0x2F: Jump(4, "j", params=[P(1)], dest=Multi(2,2), volta_param=1),
    }
formats["rnh"].loop_start = [0x2A]
formats["rnh"].loop_end = [0x2E]
formats["rnh"].end_track = [0x00]
formats["rnh"].volta_jump = [0x2F]

####################
#### procedures ####
####################

def shift(loc):
    loc -= shift_amount
    while loc < 0:
        loc += 0x10000
    return loc

def convert_program(src_prg):
    #format.program_base
    prg = src_prg
    while prg >= 0x10:
        prg -= 0x10
    return prg + 0x20
    
def specify_note_duration(note, dur):
    target_note_table = [0xC0, 0x60, 0x40, 0x48, 0x30, 0x20, 0x24, 0x18, 0x10, 0x0C, 0x08, 0x06, 0x04, 0x03]
    key = {target_note_table[i]: formats["ff6"].duration_table[i] for i in range(len(target_note_table))}
    
    solution = []
    if dur in target_note_table:
        solution = [dur]
    target_note_table = [t for t in target_note_table if t <= dur]
    if not solution:
        for c in itertools.combinations(target_note_table, 2):
            if sum(c) == dur:
                solution = c
                break
    if CONFIG_EXPAND_NOTES_TO_THREE and not solution:
        for c in itertools.combinations(target_note_table, 3):
            if sum(c) == dur:
                solution = c
                break
    if solution:
        text = ""
        for i, s in enumerate(solution):
            text += "^" if i else f"{note}"
            text += f"{key[s]}"
    else:
        text = f"&{dur}{note}"
    
    return text
        
def register_notes():
    if format.note_sort_by_duration == True: #suzuki
        multiplier = len(format.note_table)
        for i, dur in enumerate(format.duration_table):
            for j, note in enumerate(format.note_table):
                #if dur:
                format.bytecode[i * multiplier + j + format.first_note_id] = Note(j, dur)
                #else:
                #    format.bytecode[i * multiplier + j + format.first_note_id] = CustomNote(j)
    else:
        multiplier = len(format.duration_table)
        for i, note in enumerate(format.note_table):
            for j, dur in enumerate(format.duration_table):
                if format.dynamic_note_duration == True: #rudra
                    format.bytecode[i * multiplier + j + format.first_note_id] = RudraNote(i, j)
                else: #akao
                    format.bytecode[i * multiplier + j + format.first_note_id] = Note(i, dur)
           
def register_percussion_note(prg=0x2F, key=69, pan=64, symbol=None, id=None, smp=None):
    if symbol is None:
        if id is None:
            return
        else:
            symbol = note_symbol_by_id[id]
    
    percussion_defs[symbol] = PercussionDef(prg, key, pan, smp=smp)
    ifprint(f"Defined percussion {symbol} as {percussion_defs[symbol].write()}", DEBUG_PERC_VERBOSE)

def calculate_forced_percussion():    
    potential_symbols = string.ascii_lowercase[7:]
    if len(forced_percussion_locs) > len(potential_symbols):
        potential_symbols += [c + '+' for c in string.ascii_lowercase[7:]]
        if len(forced_percussion_locs) > len(potential_symbols):
            potential_symbols += [c + '-' for c in string.ascii_lowercase[7:]]
            if len(forced_percussion_locs) > len(potential_symbols):
                potential_symbols += [c + '-' for c in string.ascii_lowercase[:7]]
    symbol_idx = 0
    
    defs = []
    program = None
    for (prg, oct, keyid), locs in sorted(forced_percussion_locs.items()):
        if prg != program:
            defs.append(f"## auto percussion  0x{prg:02X}")
            program = prg
        key = note_symbol_by_id[keyid]
        symbol = potential_symbols[symbol_idx]
        defs.append(f'#drum "{symbol}"= {oct}{key}')
        for loc in locs:
            forced_percussion_notes[loc] = symbol
        
        symbol_idx += 1
    return defs

def create_program_declaration(slot, brrid):
    if not CONFIG_EXTRACT_BRR:
        return f"#WAVE 0x{slot:02X} 0x00"
    else:
        addr = int.from_bytes(inst_data_addr[brrid*4 : brrid*4 + 2], "little")
        loop = int.from_bytes(inst_data_addr[brrid*4 + 2: brrid*4 + 4], "little")
        looptext = (loop - addr).to_bytes(2, "little").hex().upper()
        if format.tuning_type == "single":
            pitchtext = f"{inst_data_pitch[brrid]:02X}00"
        elif format.tuning_type == "double":
            pitchtext = inst_data_pitch[brrid*2 : brrid*2 + 2].hex()
        elif format.tuning_type == "suzuki":
            print(f"DEBUG: tuning data for {slot:02X} {brrid:02X} is {inst_data_pitch[brrid*2:brrid*2+2].hex().upper()}")
            coarse = inst_data_pitch[brrid*2+1]
            coarse -= 0x100 if coarse >= 0x80 else 0
            fine = inst_data_pitch[brrid*2] / 256
            sign = "+" if coarse >= 0 else ""
            pitchtext = f"{sign}{coarse + fine:.3f}"
        elif format.tuning_type == "rudra":
            pitchscale = int.from_bytes(inst_data_pitch[brrid*2 : brrid*2 + 2], "big", signed=True)
            pitchscale = (pitchscale / 65536) + 1
            if pitchscale > 1:
                pitchscale = (pitchscale - 1) * 2 + 1
            semitones = (math.log(pitchscale, 10) / math.log(2, 10) * 12) - 3
            sign = "+" if semitones > 0 else ""
            pitchtext = f"{sign}{semitones:.3f}"
        if format.env_table:
            adsrtext = inst_data_adsr[brrid*2 : brrid*2 + 2].hex().upper()
        else:
            adsrtext = "F 7 7 0"
        
        brrfile = fn.rpartition('.')[0] + f"_{slot:02X}.brr"
        return f"#BRR 0x{slot:02X} 0x00; {brrfile}, {looptext}, {pitchtext}, {adsrtext}"
 
def extract_brr(slot, brrid):
    if CONFIG_EXTRACT_BRR:
        brr = bytearray()
        loc = 0x100 + int.from_bytes(inst_data_addr[brrid*4 : brrid*4 + 2], "little")
        print(f"DEBUG: extracting BRR {slot:02X} / {brrid:02X} at {loc:04X}")
        while True:
            try:
                brr += orig_bin[loc:loc+9]
            except IndexError:
                print(f"DEBUG: end of file without END bit ({loc:05X})")
                break
            if orig_bin[loc] & 1:   # END bit
                print(f"DEBUG: end bit at {loc:04X}")
                break
            loc += 9
        
        brr = len(brr).to_bytes(2, "little") + brr
        brrfile = fn.rpartition('.')[0] + f"_{slot:02X}.brr"
        try:
            with open(brrfile, "wb") as f:
                f.write(brr)
            print(f"Wrote sample {slot:02X} to file {brrfile}")
        except OSError:
            print(f"ERROR: unable to write sample {slot:02X} ({brrfile})")
            
# # # # # HEADER # # # # #

def parse_header(data, loc=0):
    tracks = {}
    end = None
    header_start = 0
    
    if format.header_type == 1: ### ff4, rs1 ###
        header_length = 0x10
        shift_amt = format.sequence_loc - 0x100
        header = data[loc:loc+header_length]
        for i in range(8):
            ii = i*2
            track_start = int.from_bytes(header[ii:ii+2], "little")
            if track_start > 0:
                tracks[i] = track_start
                
    elif format.header_type == 2: ### ffmq ###
        header_length = 0x12
        header = data[loc:loc+header_length]
        shift_amt = int.from_bytes(header[0:2], "little") - header_length
        end = int.from_bytes(header[0x10:0x12], "little")
        for i in range(8):
            ii = i*2
            track_start = int.from_bytes(header[ii:ii+2], "little")
            if track_start != end:
                tracks[i] = track_start
                
    elif format.header_type == 3: ### ff5, sd2 ###
        header_length = 0x14
        header = data[loc:loc+header_length]
        shift_amt = int.from_bytes(header[0:2], "little") - header_length
        end = int.from_bytes(header[0x12:0x14], "little")
        for i in range(8):
            ii = (i+1)*2
            track_start = int.from_bytes(header[ii:ii+2], "little")
            if track_start != end:
                tracks[i] = track_start
                
    elif format.header_type == 4: ### akao4 ###
        header_length = 0x24
        header = data[loc:loc+header_length]
        shift_amt = int.from_bytes(header[0:2], "little") - header_length
        end = int.from_bytes(header[0x2:0x4], "little")
        for i in range(16):
            ii = (i+2)*2
            track_start = int.from_bytes(header[ii:ii+2], "little")
            if track_start != end:
                if i < 8 or ( (i-8) in tracks and track_start != tracks[i-8] ): 
                    tracks[i] = track_start
        
        #akao4 percussion
        if percussion_data:
            for i in range(12):
                ii = i*3
                prg, key, pan = percussion_data[ii:ii+3]
                if key:
                    register_percussion_note(prg, key, pan, id=i)
            
    elif format.header_type in (5, 6): ### suzuki ###
        shift_amt = format.sequence_loc - 0x100
        if program_map_data:
            for i in range(0x80):
                if program_map_data[i] < 0xFF:
                    sample_mappings[i] = program_map_data[i]
                    program_mappings[program_map_data[i]] = i
                    if i >= format.program_base:
                        print(f"sample {i:02} / 0x{i:02X} <--> program {sample_mappings[i]:02X} (orig), {convert_program(sample_mappings[i]):02X} (mml)")
            
        perc_loc = loc+0x10 if format.header_type == 5 else loc
        i = perc_loc
        perc_count = 0
        while True:
            if data[i] == 0xFF:
                break
            else:
                id, smp, key, vol, pan = data[i:i+5]
                i += 5
                perc_count += 1
                if key:
                    if smp in sample_mappings:
                        ifprint(f"registering perc {smp:02X} -> {sample_mappings[smp]:02X} -> {convert_program(sample_mappings[smp]):02X}", DEBUG_PERC_VERBOSE)
                        register_percussion_note(convert_program(sample_mappings[smp]), key, pan//2, id=id, smp=smp)
                    else:
                        register_percussion_note(0, key, pan//2, id=id, smp=smp)
        perc_length = perc_count * 5 + 1
        
        track_loc = loc if format.header_type == 5 else loc+perc_length
        for i in range(8):
            ii = i*2
            track_start = int.from_bytes(data[track_loc+ii:track_loc+ii+2], "little")
            if track_start:
                tracks[i] = track_start
        
        header_length = perc_length + 0x10
                
        
    elif format.header_type == 7: ### rnh ###
        header_length = 0x12
        if spc_mode:
            #finding the sequence start is a bit of a hack..
            #may not work as consistently on spcs ripped from mid song
            #or on unusually formed sequences (i'm assuming 0A as the first
            #command after the header)
            edl = data[0x1007D]
            sequence_pos = 0xFFFF
            for i in range(8): #track read pointers
                ii = i*2
                pos = int.from_bytes(data[0x1F+ii:0x1F+ii+2], "little")
                sequence_pos = min(pos, sequence_pos)
            #look for 0A or 09 (note table, usually first thing in sequence)
            found = False
            for i in range(sequence_pos-2, 0xA000, -1):
                if data[i] in [0x09, 0x0A]:
                    # 17 bytes before the 09/OA should be <= 8
                    # 18 before = EDL
                    if data[i-0x12] == edl and data[i-0x11] <= 8 and data[i-0x11] > 0:
                        print(f"found rudra sequence starting at {i:04X}")
                        header_start = i-0x12
                        header = data[header_start:header_start+header_length]
                        found = True
                        break
            if not found:
                print("sequence scanner method 1 failed, trying another (may false positive)")
                for i in range(sequence_pos-2, 0xA000, -1):
                    if data[i] == 0x0B:
                        # 17 bytes before the 0B should be <= 8
                        # 18 before = EDL
                        if data[i-0x12] == edl and data[i-0x11] <= 8 and data[i-0x11] > 0:
                            print(f"found rudra sequence starting at {i:04X}")
                            header_start = i-0x12
                            header = data[header_start:header_start+header_length]
                            found = True
                            break                
            if not found:
                print("sequence scanner method 2 failed, trying another (likely to false positive)")
                for i in range(sequence_pos-18, 0xA000, -1):
                    # first check theoretical EDL if this is a header
                    if data[i] != edl:
                        continue
                    unknown = data[i+1]
                    if unknown > 8:
                        continue
                    echo_offset = 0xED00 - (edl * 0x800)
                    # look for any collection of 16 bytes that might be a header
                    headerish = True
                    test_rom_offset = int.from_bytes(data[i+2:i+4], "little") - 18
                    for j in range(8):
                        word = int.from_bytes(data[i + 2 + j*2:i + 4 + j*2], "little")
                        word = word - test_rom_offset + i
                        while word > 0x10000:
                            word -= 0x10000
                        while word < 0:
                            word += 0x10000
                        if word < i + 18 or word > echo_offset:
                            headerish = False
                            break
                    if headerish:
                        header = data[i:i+header_length]
                        header_start = i
                        print(f"found rudra sequence starting at {i:04X}")
                        found = True
            if not found:
                print(f"couldn't find rudra sequence. try extracting it first")
                clean_end()
        else:
            header_start = 0
            header = data[0:header_length]
            
            
        edl = header[0]
        echo_buffer_size = edl * 0x800
        end = 0xED00 - echo_buffer_size
        first_track = 0xFFFF
        for i in range(1,9):
            ii = i*2
            track_start = int.from_bytes(header[ii:ii+2], "little")
            first_track = min(first_track, track_start)
            tracks[i-1] = track_start
        shift_amt = first_track - header_length


    tracks_shifted = {}
    for k, v in tracks.items():
        v -= shift_amt
        while v < 0:
            v += 0x10000
        tracks_shifted[v] = k+1
        
    print(f"tracks found: (raw address) {' '.join([f'{t:04X}' for t in tracks.values()])}")
    print(f"                 (adjusted) {' '.join([f'{t:04X}' for t in list(tracks_shifted)])}")
    
    return tracks_shifted, shift_amt, end, header_start, header_length
    
# # # # # TRACE # # # # #

def trace_segments(data, segs):

    def add_jump(dest, volta_warn=False):
        nonlocal jump_counter
        if dest not in jumps:
            jumps[dest] = f"{seg_counter}{jump_counter:02}"
            ifprint(f"registered jump target at {dest:04X}, id {jumps[dest]}", DEBUG_JUMP_VERBOSE)
            jump_counter += 1
            
            if volta_warn:
                print(f"({format.id}/volta): jump target ${jumps[dest]} may be unsafe due to format differences.\n{' '*(len(format.id)+10)}be prepared to correct it manually!")
        
    def adjusted_volume():
        try:
            return int(volume * (expression / 0x7F))
        except TypeError:
            return None
            
    def rel_octave_set(targ):
        nonlocal octave_rel, rel_octave_delta
        if format.low_octave_notes:
            while octave_rel > targ:
                octave_rel -= 1
                rel_octave_delta -= 1
            while octave_rel < targ:
                octave_rel += 1
                rel_octave_delta += 1
        
    def finalize(append_before=None):    
        if rel_octave_delta > 0:
            append_before += "<" * abs(rel_octave_delta)
        elif rel_octave_delta < 0:
            append_before += ">" * abs(rel_octave_delta)
            
        if append_before:
            if loc in append_before_items:
                if append_before_items[loc] != append_before:
                    print(f"{loc:04X}: warning: ambiguous prepend ({append_before_items[loc]}) ({append_before})")
            append_before_items[loc] = append_before
                
    # traverse data starting from header pointers
    # goals:
    # - establish end of file when not specified
    # - track and store jump targets
    # - track and store conditional scaling values
    print(f"tracing segments. pointers are offset by {shift_amount:X}.")
    
    flowctrl_cmds = format.loop_start + format.loop_end + format.hard_jump + format.loop_break + format.volta_jump + format.conditional_jump + [k for k, v in format.bytecode.items() if '$' in v.symbol]
    
    segs = list(segs)
    eof = 0
    seg_counter = 0
    already_traced_segs = []
    for seg in segs:
        if seg in already_traced_segs: continue
        already_traced_segs.append(seg)
        seg_counter += 1
        #reset state variables
        loop_stack = []
        octave = 5 if format.low_octave_notes else None
        octave_rel = 0
        prev_octave = None
        volume = None
        expression = 0x7F
        program = None
        force_octave_set = False
        force_volume_set = False
        block_volume_cmds = []
        block_octave_cmds = []
        block_flowctrl_cmds = []
        block_octave_rel = {}
        volume_set = False
        octave_set = False
        jump_counter = 1
        percussion = False
        percussion_marked = False
        percussion_state = None
        force_perc_state = False
        dur_table = []
        if format.dynamic_note_duration:
            dur_table = [d for d in format.duration_table if isinstance(d, int)]
        
        this_trace_segs = [seg]
        loc = seg
        print(f"tracing segment {loc:04X}...")
        while True:
            append_before = ""
        
            #read control byte
            cmd = data[loc]
            cmdinfo = format.bytecode[cmd]
            ifprint(f"read {cmd:02X} at {loc:04X} -- it's {cmdinfo.length} long \"{cmdinfo.symbol}\"", DEBUG_STEP_BY_STEP, end="")
            cmd = data[loc:loc+cmdinfo.length]
            ifprint(" -- " + " ".join([f"{b:02X}" for b in cmd]), DEBUG_STEP_BY_STEP)

            if loc + len(cmd) > eof:
                eof = loc + len(cmd)
            
            next_loc = loc + cmdinfo.length
            
            force_perc_state = False
            #handle forced percussion
            if forced_percussion_prgs:
                if cmdinfo.type == "program":
                    if cmdinfo.get(cmd) != program:
                        force_perc_state = "on" if cmdinfo.get(cmd) in forced_percussion_prgs else "off"
                if program in forced_percussion_prgs:
                    if cmdinfo.type == "note" and cmdinfo.percid is not None:
                        if (program, octave, cmdinfo.percid) not in forced_percussion_locs:
                            forced_percussion_locs[(program, octave, cmdinfo.percid)] = set()
                        forced_percussion_locs[(program, octave, cmdinfo.percid)].add(loc)
                                                
            #handle percussion
            if "PercOn" in cmdinfo.type or force_perc_state == "on":
                percussion = True
                percussion_state = None
                ifprint(f"{loc:04X}: PercOn - {' '.join([f'{b:02X}' for b in cmd])} - p {percussion} ps {percussion_state} pm {percussion_marked}", DEBUG_PERC_VERBOSE)
            elif "PercOff" in cmdinfo.type or force_perc_state == "off":
                percussion = False
                percussion_state = None
                if percussion_marked:
                    percussion_ends.add(loc)
                    percussion_marked = False
                ifprint(f"{loc:04X}: PercOff - {' '.join([f'{b:02X}' for b in cmd])} - p {percussion} ps {percussion_state} pm {percussion_marked}", DEBUG_PERC_VERBOSE)
            if percussion:
                if loc in percussion_states:
                    ops = percussion_states[loc]
                else:
                    ops = None
                ifprint(f"{loc:04X}: {cmdinfo.symbol} - {' '.join([f'{b:02X}' for b in cmd])} - p {percussion} ps {percussion_state} ops {ops} pm {percussion_marked}", DEBUG_PERC_VERBOSE)
                if cmdinfo.percid is not None:
                    ifprint("perc: Is a percussion note", DEBUG_PERC_VERBOSE)
                    if not percussion_marked:
                        ifprint("perc: Mark is inactive, activating", DEBUG_PERC_VERBOSE)
                        percussion_starts.add(loc)
                        percussion_marked = True
                    if percussion_state is None:
                        ifprint("perc: State is inactive, resetting", DEBUG_PERC_VERBOSE)
                        percussion_resets.add(loc)
                    elif loc in percussion_states and percussion_state is not None and percussion_states[loc] != percussion_state:
                        ifprint("perc: State is ambiguous, resetting", DEBUG_PERC_VERBOSE)
                        percussion_resets.add(loc)
                    percussion_states[loc] = percussion_state
                    percussion_state = cmdinfo.percid
                    if program not in forced_percussion_prgs:
                        if note_symbol_by_id[cmdinfo.percid] not in percussion_defs:
                            register_percussion_note(id=cmdinfo.percid)
                        perc_prg = percussion_defs[note_symbol_by_id[cmdinfo.percid]].prg_raw
                        if perc_prg != program:
                            program = perc_prg
                else:
                    if percussion_marked:
                        ifprint("perc: Not a percussion note, mark is active, deactivating", DEBUG_PERC_VERBOSE)
                        percussion_ends.add(loc)
                        percussion_marked = False
                        
            #track states
            rel_octave_delta = 0
            
            if cmdinfo.type == "program":
                if cmdinfo.get(cmd) != program:
                    program = cmdinfo.get(cmd)
                    force_octave_set = len(block_flowctrl_cmds)
                    force_volume_set = len(block_flowctrl_cmds)
                ifprint(f"{loc:04X}: set program to {program:02X}", DEBUG_STATE_VERBOSE)
                if loc in program_locs:
                    if program_locs[loc][1] != octave:
                        if program_locs[loc][1] is None:
                            program_locs[loc][1] = octave
                        elif octave is not None:
                            print(f"{loc:04X}: ambiguous octave on program set ({program_locs[loc][1]}) ({octave})")
                    if program_locs[loc][2] != adjusted_volume():
                        if program_locs[loc][2] is None:
                            program_locs[loc][2] = adjusted_volume()
                        elif adjusted_volume() is not None:
                            print(f"{loc:04X}: ambiguous volume on program set ({program_locs[loc][2]}) ({adjusted_volume()})")
                else:
                    program_locs[loc] = [program, octave, adjusted_volume()]
                octave_rel = 0
            elif cmdinfo.type == "volume":
                volume = cmdinfo.get(cmd, 'volume_param')
                block_volume_cmds.append((loc, adjusted_volume()))
                volume_set = True
                ifprint(f"{loc:04X}: set volume to {volume} ({adjusted_volume()})", DEBUG_STATE_VERBOSE)
                #volume_locs[loc] = program
            elif cmdinfo.type == "expression":
                expression = cmdinfo.get(cmd, 'expression_param')
                block_volume_cmds.append((loc, adjusted_volume()))
                volume_set = True
                ifprint(f"{loc:04X}: set expression to {expression} ({adjusted_volume()})", DEBUG_STATE_VERBOSE)
            elif cmdinfo.type == "octave":
                octave = cmdinfo.get(cmd, 'octave_param')
                block_octave_cmds.append(loc)
                octave_set = True
                ifprint(f"{loc:04X}: set octave to {octave}", DEBUG_STATE_VERBOSE)
            elif cmd[0] in format.octave_up and octave:
                block_octave_rel[loc] = cmd
                octave += 1
            elif cmd[0] in format.octave_down and octave:
                block_octave_rel[loc] = cmd
                octave -= 1

            if cmd[0] in flowctrl_cmds:
                block_flowctrl_cmds.append(loc)
                
            #handle static block on active block start
            if "note" in cmdinfo.type and 'r' not in cmdinfo.symbol:
                if force_volume_set is not False:
                    if not volume_set:
                        volume_set = True
                        try:
                            block_volume_cmds.append((block_flowctrl_cmds[force_volume_set], volume))
                        except IndexError:
                            block_volume_cmds.append((loc, volume))
                if force_octave_set is not False:
                    if not octave_set and not percussion:
                        octave_set = True
                        try:
                            block_octave_cmds.append(block_flowctrl_cmds[force_octave_set])
                        except IndexError:
                            block_octave_cmds.append(loc)
                if CONFIG_USE_VOLUME_MACROS:
                    for vloc, vol in block_volume_cmds:
                        volume_locs[vloc] = program, vol
                if CONFIG_USE_OCTAVE_MACROS:
                    for oloc in block_octave_cmds:
                        octave_locs[oloc] = program, octave
                #handle alligator redundancy
                if CONFIG_REMOVE_REDUNDANT_OCTAVES:
                    for roloc, _ in block_octave_rel.items():
                        if octave_set or percussion:
                            if roloc not in redundant_items:
                                redundant_items[roloc] = True
                        else:
                            redundant_items[roloc] = False
                        
                #reset static-block counters
                block_flowctrl_cmds = []
                block_volume_cmds = []
                block_octave_cmds = []
                block_octave_rel = {}
                volume_set = False
                octave_set = False
                force_octave_set = False
                force_volume_set = False
                
            #handle weird rudra duration stuff
            if format.dynamic_note_duration:
                if "dur_table" in cmdinfo.type:
                    new_dur_table = cmdinfo.get(cmd, "dur_table")
                    for i, d in enumerate(new_dur_table):
                        if i >= 7:
                            print(f"{loc:04X}: warning: likely duration table overflow (length {len(new_dur_table)}")
                            break
                        dur_table[i] = d
                elif "note" in cmdinfo.type:
                    if loc in dynamic_note_durations and dynamic_note_durations[loc] != dur_table[cmdinfo.idx]:
                        print(f"{loc:04X}: ambiguous note duration ({dynamic_note_durations[loc]:02X}) ({dur_table[cmdinfo.idx]:02X})")
                    elif cmdinfo.length == 1:
                        dynamic_note_durations[loc] = dur_table[cmdinfo.idx]
                
            #handle loops
            do_jump = False
            if cmd[0] in format.loop_start:
                startloc, iterations, counter = [loc + cmdinfo.length, cmdinfo.get(cmd, "count_param"), 1]
                rel_octave_set(0)
                loop_stack.append( [startloc, iterations, counter, octave] )
                if format.loops_store_octave:
                    force_octave_set = len(block_flowctrl_cmds)
                ifprint(f"{loc:04X}: loop started with {iterations} iterations", DEBUG_LOOP_VERBOSE)
                if len(loop_stack) > format.max_loop_stack:
                    print("warning: loop stack above {format.max_loop_stack}, behavior may become inaccurate")
                    loop_stack.pop(0)
                elif len(loop_stack) > 4:
                    print("warning: loop stack is {len(loop_stack)} - unsupported by target engine. Correct manually.")
                if iterations == 0 and format.zero_loops_infinite:
                    replace_items[loc] = "$"
            elif cmd[0] in format.loop_end:
                if not loop_stack:
                    print("warning: segment terminated by loop end")
                    finalize(append_before=append_before)
                    break
                else:
                    startloc, iterations, counter, loop_oct = loop_stack[-1]
                    rel_octave_set(0)
                    loop_ends[startloc] = loc + cmdinfo.length
                    if iterations == 0 and format.zero_loops_infinite:
                        print("ending segment via infinite loop")
                        replace_items[loc] = ";"
                        finalize(append_before=append_before)
                        break
                    if counter >= iterations:
                        ifprint(f"{loc:04X}: loop ended at {iterations} iterations", DEBUG_LOOP_VERBOSE)
                        loop_stack.pop()
                    else:
                        counter += 1
                        ifprint(f"looping back to {startloc:04X} for {counter}rd iteration", DEBUG_LOOP_VERBOSE)
                        finalize(append_before=append_before)
                        loc = startloc
                        loop_stack[-1][2] = counter
                        if format.loops_store_octave:
                            octave = loop_oct
                        continue
            elif cmd[0] in format.loop_break or cmd[0] in format.volta_jump:
                rel_octave_set(0)
                if loop_stack:
                    startloc, iterations, counter, loop_oct = loop_stack[-1]
                    if cmdinfo.length == 1:
                        volta_count = iterations
                        suzuki_volta_counts[loc] = volta_count
                    else:
                        volta_count = cmdinfo.get(cmd, "volta_param")
                    #print(f"{loc:04X}: volta on {volta_count}, currently {counter}")
                    if counter == volta_count:
                        #print(f"jumping to volta at {shift(cmdinfo.dest(cmd)):04X}")
                        do_jump = True
                        if cmd[0] in format.loop_break and volta_count > 1:
                            loop_stack.pop()
                        
            #do stuff if it's a jump or end
            if cmd[0] in format.end_track:
                ifprint(f"{loc:04X}: hard end", DEBUG_JUMP_VERBOSE)
                finalize(append_before=append_before)
                break
            if cmd[0] in format.hard_jump or do_jump:
                if cmd[0] in format.loop_break and cmdinfo.length == 1: #suzuki
                    next_loc = loop_ends[startloc]
                    implicit_jump_targets[loc] = next_loc
                else:
                    next_loc = shift(cmdinfo.dest(cmd))
                ifprint(f"Found hard jump to {next_loc:04X} ({next_loc:04X})", DEBUG_JUMP_VERBOSE)
                add_jump(next_loc, cmd[0] in format.volta_jump)
                rel_octave_set(0)
                if cmd[0] in format.hard_jump:
                    if next_loc in this_trace_segs:
                        ifprint(f"We've been here before. Ending segment", DEBUG_JUMP_VERBOSE)
                        finalize(append_before=append_before)
                        break
                    else:
                        this_trace_segs.append(next_loc)
            elif cmd[0] in format.conditional_jump:
                rel_octave_set(0)
                target = shift(cmdinfo.dest(cmd))
                segs.append(target)
                add_jump(target)
                
            #handle octave-baked-into-note state (rudra)
            if cmd[0] in format.low_octave_notes:    
                rel_octave_set(-1)
            elif "note" in cmdinfo.type:
                rel_octave_set(0)
                
            #move forward
            finalize(append_before=append_before)
            loc = next_loc
            if loc >= len(data):
                print("Segment terminated unexpectedly")
                break
    return eof
    
# # # # # WRITE # # # # #

def write_mml(data):
    
    def crlf(n=1):
        nonlocal line, new_text
        mml.append(line)
        while n > 1:
            mml.append("")
            n -= 1
        line = ""
        if new_text:
            mml.append(new_text)
            new_text = ""
        
    def ensure_percussion():
        nonlocal percussion_marked, new_text
        if not percussion_marked:
            new_text += '"'
            percussion_marked = True
            status.append("ForceP.on")
            
    def ensure_no_percussion():
        nonlocal percussion_marked, new_text
        if percussion_marked:
            new_text += '"'
            percussion_marked = False
            status.append("ForceP.end")
            
    mml = []
    line = ""
    loc = 0 + header_length
    percussion_marked = False
    percussion_end_state = False
    while loc < len(data):
        status = [] #debug info
        new_text = ""
        
        #text maintenance
        if len(line.rpartition('\n')[2]) >= 70:
            crlf()
            status.append("LF")
        
        if loc in percussion_ends:
            new_text += '"'
            percussion_marked = False
            percussion_end_state = False
            status.append("P.end")
            
        #check for targets at this location
        if loc in tracks:
            ensure_no_percussion()
            crlf()
            new_text += f"{{{tracks[loc]}}}"
            crlf()
            status.append("Track")
        if loc in jumps:
            ensure_no_percussion()
            crlf()
            new_text += f"${jumps[loc]}"
            status.append("Jump")
            
        #read control byte
        cmd = data[loc]
        cmdinfo = format.bytecode[cmd]
        cmd = data[loc:loc+cmdinfo.length]
        
        #write volume/octave macros if not a volume/octave command
        if loc in volume_locs:
            if "volume" not in cmdinfo.type and "expression" not in cmdinfo.type:
                new_text += write_volume_macro(*volume_locs[loc], loc=loc)
                status.append("vol")
        if loc in octave_locs:
            if "octave" not in cmdinfo.type:
                new_text += write_octave_macro(*octave_locs[loc], loc=loc)
                status.append("oct")

        #percussion
        if loc in percussion_starts:
            new_text += '"'
            percussion_marked = True
            percussion_end_state = True
            status.append("P.on")
        if loc in percussion_resets:
            ensure_percussion()
            new_text += " !!!o "
            status.append("P.reset")
        
        if percussion_marked != percussion_end_state:
            percussion_marked = percussion_end_state
            new_text += '"'
            status.append("P.adjust")
        
        #write command to mml
        if loc in append_before_items:
            new_text += append_before_items[loc]
            status.append("append")
        if loc in replace_items:
            new_text += replace_items[loc]
            status.append("replace")
        elif loc not in redundant_items or not redundant_items[loc]:
            new_text += cmdinfo.write(cmd, loc)

        if cmd[0] in format.hard_jump:
            crlf()
            
        #advance
        status = ('(' + ', '.join(status) + ')') if status else ""
        ifprint(f"{loc:04X}: writing {' '.join([f'{b:02X}' for b in cmd])} as {new_text}    {status}", DEBUG_WRITE_VERBOSE)
        line += new_text
        
        loc += cmdinfo.length
    
    crlf()
    return mml
        
def clean_end():
    print("Processing ended.")
    input("Press enter to close.")
    os._exit(0)
    
############
### MAIN ###
############

if __name__ == "__main__":
        
    print(f"mfvitools general binary-to-MML converter")
    print(f"                    version {VERSION}")
    print(f"                    created by emberling")
    print()
    
    if len(sys.argv) >= 2:
        fn = sys.argv[1]
    else:
        print("Enter data filename..")
        print("Accepts either raw data or SPC dump")
        fn = input(" > ").replace('"','').strip()
        
    try:
        with open(fn, 'rb') as f:
            bin = f.read()
    except IOError:
        print(f"Error reading file {fn}")
        clean_end()
        
    format = None
    spc_mode = False
    
    if len(bin) >= 0x10000:
        spc_mode = True
        print(f"Using SPC mode...")
        for fid, fmt in formats.items():
            #print(f" scanning at {fmt.scanner_loc:X} for {fmt.scanner_data}")
            #print(f" found {bin[fmt.scanner_loc:fmt.scanner_loc+len(fmt.scanner_data)]}")
            if bin[fmt.scanner_loc:fmt.scanner_loc+len(fmt.scanner_data)] == fmt.scanner_data:
                format = fmt
                print(f"Detected format '{fid}'")
                break
        if not format:
            print(f"Could not automatically detect format")
            
    if not format:
        print("Select a format:")
        print()
        format_list = sorted(formats.items(), key=lambda x:x[1].sort_as)
        for fid, fmt in format_list:
            print(f"{fmt.sort_as:2}: ({fid}) {fmt.display_name}")
        print()
        while not format:
            entry = input(">").strip()
            try:
                format = format_list[int(entry)-1][1]
            except (KeyError, ValueError):
                try:
                    format = formats[entry]
                except KeyError:
                    print("Invalid format entry '{entry}'")
    
    CONFIG_IGNORE_FIRST_BYTES = 0
    CONFIG_EXTRACT_BRR = False
    CONFIG_USE_PROGRAM_MACROS = True
    CONFIG_USE_VOLUME_MACROS = True
    CONFIG_USE_OCTAVE_MACROS = True
    CONFIG_EXPAND_NOTES_TO_THREE = False
    CONFIG_REMOVE_REDUNDANT_OCTAVES = True
    CONFIG_DEF_SORT_MODE = "program"
    forced_percussion_prgs = set()
    
    #attempt to autodetect 2-byte rom header (akao4 only, for ff6hacking song data page compatibility)
    if not spc_mode and "AKAO4" in format.display_name:
        header_words = []
        for i in range(19):
            header_words.append(bin[i*2:i*2+2])
        # 26 00 is never the extra header and often the first word of the real header
        if header_words[0] == b"\x26\x00":
            pass #no rom header
        elif header_words[1] == b"\x26\x00":
            CONFIG_IGNORE_FIRST_BYTES = 2
        # look for matching & offset track8/track16 pointers
        if header_words[18] == header_words[10] and header_words[10] != header_words[2]:
            CONFIG_IGNORE_FIRST_BYTES = 2
    if CONFIG_IGNORE_FIRST_BYTES:
        print(f"detected extra {CONFIG_IGNORE_FIRST_BYTES}-byte header. use option 'h0' if this is incorrect")
        
    while True:
        print("Enter any additional configuration options (? for help):")
        print()
        entry = input(">").strip()
        if entry and entry[0] == '?':
            print("    b - extract BRR samples from SPC, if possible")
            print("    dp - sort definitions by program number, excluding #WAVE (default)")
            print("    dt - sort definitions by definition type")
            print("    dw - sort definitions by program number, including #WAVE")
            print("    hXX - ignore the first XX bytes (hex) of the input file")
            print("    mp - disable converting program changes to macros")
            print("    mv - disable converting volume changes to macros")
            print("    mo - disable converting octave set commands to macros")
            print("    o - preserve all octave up/down commands, even if redundant")
            print("    pXX - treat notes with program XX (hex) as percussion notes")
            print("    t - use ties instead of & for rendering three-byte notes")
            print()
            print("for example, if you want something closer to a byte-accurate conversion while sacrificing")
            print("convenience features, and you know your data file includes the two-byte length")
            print("header present in AKAO ROM data rips, you could enter:")
            print("  h2 o mp mv mo")
            print()
            continue
    
        options = entry.split(' ')
        options_hex_int = ['h', 'p']
        options_str = ['d', 'm']
        for option in options:
            if not len(option):
                continue
            val = None
            if option[0] in options_hex_int:
                try:
                    val = int(option[1:], 16)
                except ValueError:
                    print(f"invalid parameter '{option[1:]}' for option {option[0]}")
                    continue
            elif option[0] in options_str:
                val = option[1:]
            
            if option[0] == 'b':
                CONFIG_EXTRACT_BRR = True
            if option[0] == 'd':
                if val == 't':
                    CONFIG_DEF_SORT_MODE = "type"
                    print(f"{option}: sort definitions by type")
                elif val == 'p':
                    CONFIG_DEF_SORT_MODE = "program"
                    print(f"{option}: sort definitions by program")
                elif val == 'w':
                    CONFIG_DEF_SORT_MODE = "wave"
                    print(f"{option}: sort definitions and sample table entries by program")
            elif option[0] == 'h':
                CONFIG_IGNORE_FIRST_BYTES = val
                print(f"{option}: ignoring 0x{val:X} bytes")
            elif option[0] == 'm':
                if val == 'p':
                    CONFIG_USE_PROGRAM_MACROS = False
                    print(f"{option}: program change macros disabled")
                elif val == 'v':
                    CONFIG_USE_VOLUME_MACROS = False
                    print(f"{option}: volume change macros disabled")
                elif val == 'o':
                    CONFIG_USE_OCTAVE_MACROS = False
                    print(f"{option}: octave setting macros disabled")
                else:
                    print(f"{option}: unrecognized sub-option '{val}'")
            elif option[0] == 'o':
                CONFIG_REMOVE_REDUNDANT_OCTAVES = False
                print(f"{option}: preserving all octave up and down commands")
            elif option[0] == 'p':
                forced_percussion_prgs.add(val)
                print(f"{option}: adding program 0x{val:02X} notes as percussion notes")
            elif option[0] == 't':
                CONFIG_EXPAND_NOTES_TO_THREE = True
                print(f"{option}: using ties instead of & for three-byte note durations")
        print()
        break
        
    origin = format.sequence_loc if spc_mode else 0 + CONFIG_IGNORE_FIRST_BYTES
    register_notes()
    
    jumps = {}
    sample_defs = {}
    program_defs = {}
    octave_defs = {}
    volume_defs = {}
    program_locs = {}
    octave_locs = {}
    volume_locs = {}
    loop_ends = {}
    implicit_jump_targets = {}
    suzuki_volta_counts = {}
    dynamic_note_durations = {}
    note_tables = {}
    append_before_items = {}
    inst_data_addr = b""
    inst_data_pitch = b""
    inst_data_adsr = b""
    inst_data_brr = {}
    orig_bin = b""
    program_map_data = b""
    program_mappings = {}
    sample_mappings = {}
    percussion_data = b""
    percussion_starts = set()
    percussion_ends = set()
    percussion_resets = set()
    percussion_states = {}
    percussion_defs = {}
    forced_percussion_locs = {}
    forced_percussion_notes = {}
    replace_items = {}
    redundant_items = {}
    
    if spc_mode:
        if format.percussion_table_loc is not None:
            percussion_data = bin[format.percussion_table_loc:format.percussion_table_loc+0x24]
        if format.program_map_loc is not None:
            program_map_data = bin[format.program_map_loc:format.program_map_loc+0x80]
        if CONFIG_EXTRACT_BRR:
            inst_data_addr = bin[format.brr_table:format.brr_table+format.brr_table_size]
            inst_data_pitch = bin[format.tuning_table:format.tuning_table + 0x60]
            if format.env_table:
                inst_data_adsr = bin[format.env_table:format.env_table + 0x60]
            print(inst_data_addr.hex())
    
    orig_bin = bin
    bin = bin[origin:]
    tracks, shift_amount, end, header_start, header_length = parse_header(bin)
    
    if header_start: #rudra
        bin = bin[header_start:end]
    elif format.sequence_relative: #akao3, akao4
        bin = bin[:shift(end)]
    end = trace_segments(bin, tracks)
    if not format.sequence_relative: #akao1, akao2
        bin = bin[:end]
    
    forced_percussion_defs = calculate_forced_percussion()
    mml = write_mml(bin)
    
    #prepend definitions
    prepend = [f"##created with sqspcmml {VERSION}"]
    if CONFIG_DEF_SORT_MODE == "type":
        prepend += [""] + [v for k,v in sorted(sample_defs.items())]
        if CONFIG_USE_PROGRAM_MACROS:
            prepend += [""] + [v for k,v in sorted(program_defs.items())]
        if CONFIG_USE_OCTAVE_MACROS:
            prepend += [""] + [v for k,v in sorted(octave_defs.items())]
        if CONFIG_USE_VOLUME_MACROS:
            prepend += [""] + [v for k,v in sorted(volume_defs.items())]
    else:
        if CONFIG_DEF_SORT_MODE != "wave":
            prepend += [""] + [v for k,v in sorted(sample_defs.items())]
        used_prgvals = set(list(sample_defs.keys()) + list(program_defs.keys()) + list(octave_defs.keys()) + list(volume_defs.keys()))
        for p in sorted(used_prgvals):
            prepend += [""]
            if CONFIG_DEF_SORT_MODE == "wave" and p in sample_defs:
                prepend.append(sample_defs[p])
            if p in program_defs:
                prepend.append(program_defs[p])
            if p in octave_defs:
                prepend.append(octave_defs[p])
            if p in volume_defs:
                prepend.append(volume_defs[p])
    if percussion_defs:
        prepend += [""]
        for k, v in sorted(percussion_defs.items()):
            prepend += [f'#drum "{k}"= {v.write()}']
    if forced_percussion_defs:
        prepend += [""] + forced_percussion_defs
            
    mml = prepend + mml
    ###
    
    fn = fn.rpartition('.')[0]
    try:
        with open(fn + ".mml", 'w') as mmlf:
            for line in mml:
                mmlf.write(line + "\n")
    except IOError:
        print("Error writing {}.mml".format(fn))
    
    clean_end()