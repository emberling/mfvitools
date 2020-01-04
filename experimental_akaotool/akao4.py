import functools
from sequence import Sequence, Event, Format
        
akao4 = Format(
    name = "AKAO4 Generic",
    note_min = 0,
    note_max = 0xC3,
    duration_table = [0xC0, 0x60, 0x40, 0x48, 0x30, 0x20, 0x24, 0x18, 0x10, 0x0C, 0x08, 0x06, 0x04, 0x03]
    duration_as_modulo = True,
    rest_before_tie = False,
    timing_constant = 39,
    has_percussion = False,
    has_alt_volume = False)

### C4: Volume
#future note: when implementing conversion from two-volume to one-volume formats, there is no need to do anything here! instead, unroll the sequence and adjust volume events by proportions appropriate for current velocity level
#when implementing register_command, allow empty byte and verb fields to register in only one direction
akao4.register_command(
    type = "volume"
    byte = 0xC4, bytelength = 2
    verb = "v", paramcount = 1
    value = (partial(from_bitfield_scaled, 1, 0x7F), partial(to_bitfield_scaled, 1, 0x7F))
    polarity = (partial(from_bitfield, 1, 0x80), partial(to_bitfield, 1, 0x80)))
    
akao4.register_command_out(
    type = "volume"
    byte = 0xC4, bytelength = 2
    verb = "v", paramcount = 1
    value = partial(to_bitfield_scaled, 1, 0x7F))
    
### C5: Volume Fade
akao4.register_command(
    type = "volume"
    byte = 0xC5, bytelength = 3
    verb= "v", paramcount = 2
    duration = (partial(from_byte, 1), partial(to_byte, 1))
    value = (partial(from_bitfield_scaled, 2, 0x7F), partial(to_bitfield_scaled, 2, 0x7F))
    polarity = (partial(from_bitfield, 1, 0x80), partial(to_bitfield, 1, 0x80)))
    
akao4.register_command_out(
    type = "volume"
    byte = 0xC5, bytelength = 3
    verb = "v", paramcount = 2
    duration = (partial(from_byte, 1), partial(to_byte, 1))
    value = partial(to_bitfield_scaled, 1, 0x7F))
    
### C6: Pan
akao4.register_command(
    type = "pan"
    byte = 0xC6, bytelength = 2
    verb = "p", paramcount = 1
    value = (partial(from_bitfield_scaled, 1, 0x7F), partial(to_bitfield_scaled, 1, 0x7F))
    polarity = (partial(from_bitfield, 1, 0x80), partial(to_bitfield, 1, 0x80)))
    
akao4.register_command_out(
    type = "pan"
    byte = 0xC6, bytelength = 2
    verb = "p", paramcount = 1
    value = partial(to_bitfield_scaled, 1, 0x7F))
    
### C7: Pan Fade
akao4.register_command(
    type = "volume"
    byte = 0xC5, bytelength = 3
    verb= "v", paramcount = 2
    duration = (partial(from_byte, 1), partial(to_byte, 1))
    value = (partial(from_bitfield_scaled, 2, 0x7F), partial(to_bitfield_scaled, 2, 0x7F))
    polarity = (partial(from_bitfield, 1, 0x80), partial(to_bitfield, 1, 0x80)))
    
akao4.register_command_out(
    type = "volume"
    byte = 0xC5, bytelength = 3
    verb = "v", paramcount = 2
    duration = (partial(from_byte, 1), partial(to_byte, 1))
    value = partial(to_bitfield_scaled, 1, 0x7F))
    
### DC: Program Change
akao4.register_command(
    type = "program"
    byte = 0xDC, bytelength = 2
    verb = "@", paramcount = 1
    value = (partial(from_byte, 1), partial(to_byte, 1)))
    
akao4.register_command_in(
    type = "program"
    byte = None, bytelength = None
    verb = "|", paramcount = 1
    value = partial(from_progchange, 1))
    