import functools

class Format:
    def __init__(
            name = "Generic Format",
            note_min = 0,
            note_max = 0xD1,
            duration_table = [0xc0, 0x60, 0x40, 0x48, 0x30, 0x20, 0x24, 0x18, 0x10, 0x0c, 0x08, 0x06, 0x04, 0x03]
            duration_as_modulo = True,
            rest_before_tie = False,
            timing_constant = 36,
            has_percussion = False,
            has_alt_volume = False):
        self.name = name
        self.note_min = note_min
        self.note_max = note_max
        self.duration_table = duration_table
        self.rest_before_tie = rest_before_tie
        self.timing_constant = timing_constant
        self.has_percussion = has_percussion
        self.has_alt_volume = has_alt_volume
        
        self.byte_commands = {}
        self.mml_commands = {}
        self.event_types = {}
        
    def register_command(type, byte, bytelength, verb, paramcount, eparams=None, **kwargs):
        in_kw, out_kw = {}, {}
        for k, v in kwargs.items():
            in_kw[k] = v[0]
            out_kw[k] = v[1]
        self.register_command_in(type, byte, bytelength, verb, paramcount, eparams, **in_kw)
        self.register_command_out(type, byte, bytelength, verb, paramcount, eparams, **out_kw)
        
    def register_command_in(type, byte, bytelength, verb, paramcount, eparams=None, **kwargs):
        if eparams is None:
            eparams = kwargs.keys()
        #register for binary - skip if not defined
        if byte is not None:
            self.byte_commands[(byte, bytelength)] = lambda b: parse_byte(b, eparams, **kwargs)
        #register for mml - skip if not defined
        if verb is not None:
            self.mml_commands[(verb, paramcount)] = lambda v: parse_verb(v, eparams, **kwargs)
            
    def register_command_out(type, byte, bytelength, verb, paramcount, eparams=
    None, **kwargs):
        if eparams is None:
            eparams = kwargs.keys()
        self.event_types[(type, eparams)] = (lambda e: write_byte(e, byte, bytelength, **kwargs), lambda e: write_mml(e, verb, paramcount, **kwargs)
            
            
        