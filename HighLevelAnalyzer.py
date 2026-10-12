
from saleae.analyzers import HighLevelAnalyzer, AnalyzerFrame, ChoicesSetting

# Instructions for AT86RF233 -- note there is also RAM mode, not included here
READ_REG = b'\x80'
WRITE_REG = b'\xC0'
READ_BUFFER = b'\x20'
WRITE_BUFFER = b'\x60'

# Registers
SET_RADIO_STATE = 0x02

# Radio Commands
RADIO_COMMANDS = {0x03: 'OFF', 0x06: 'RX', 0x09: "TX"}

# Radio status
RADIO_STATUS = {0x06: "RX", 0x08: 'OFF', 0x09: "TX", 0x1F: "Transitioning"}

INTERRUPT_BITS = {
    0x01: "PLL_LOCK",
    0x02: "PLL_UNLOCK",
    0x04: "RX_START",
    0x08: "TRX_END",  # completion of frame reception
    0x10: "CCA_ED_DONE",
    0x20: "AMI",
    0x40: "TRX_UR",
    0x80: "BAT_LOW",
}


def bytes_formatted(data: bytes | list[int] | int) -> str:
    # prints data without converting to ascii
    if isinstance(data, int):
        return f"{data:02x}"
    else:
        return " ".join(f"{b:02x}" for b in data)


class HLA_AT86RF233_SPI(HighLevelAnalyzer):

    result_types = {
        'Read Register': {
            'format': 'Read Register {{data.register}}  Value {{data.data}}'
        },
        'Write Register': {
            'format': 'Write Register {{data.register}}  Value {{data.data}}'
        },
        'Read Radio State': {'format': 'Read Radio State: {{data.data}}'},
        'Set Radio State': {'format': 'Set Radio State: {{data.data}}'},
        'Set Channel': {'format': 'Set channel {{data.data}}'},
        'Check ED': {'format': 'Check ED: {{data.data}} dB'},
        'Other': {'format': '{{data.message}}'},
        'Transmit': {'format': "Transmit data: {{data.data}}"},
        'Receive': {'format': "Receive data: {{data.data}}"}
    }

    def __init__(self):
        self.data = []
        self.radio_channel = 0

    def decode(self, frame: AnalyzerFrame):
        # SPI frame types are: enable, result, and disable
        if frame.type == 'enable':
            self.data = []

        elif frame.type == 'result':
            # keep adding incoming data
            self.data.append(frame)

        elif frame.type == 'disable':
            # we've got the whole packet, so now process and output the analyzer frame
            if len(self.data):
                return self.parse_message(self.data)

        return []

    def parse_message(self, data):
        start_time = data[0].start_time
        end_time = data[-1].end_time
        command = int.from_bytes(data[0].data['mosi'])

        # reading from frame buffer
        if command == 0x20:
            bytes_list = b''.join(f.data['miso'] for f in data[2:])
            rx_data = f"ch {self.radio_channel}: {bytes_formatted(bytes_list)}"
            return AnalyzerFrame('Receive', start_time, end_time, {'data': rx_data})

        # writing to frame buffer
        elif command == 0x60:
            bytes_list = b''.join(f.data['mosi'] for f in data[2:])
            tx_data = f"ch {self.radio_channel}: {bytes_formatted(bytes_list)}"
            return AnalyzerFrame('Transmit', start_time, end_time, {'data': tx_data})

        # writing register
        elif command & 0b11000000 == 0b11000000:
            if len(data) != 2:
                print("Invalid packet length")
            register = command & 0b00111111
            value = data[1].data['mosi'][0]

            if register == 0x02:  # radio status
                message = RADIO_COMMANDS.get(value, value)
                return AnalyzerFrame('Set Radio State', start_time, end_time, {'data': message})
            elif register == 0x05:  # set radio power
                return AnalyzerFrame('Other', start_time, end_time, {'message': f"Set radio power = {value}"})
            elif register == 0x07:  # start ED measurement
                return AnalyzerFrame('Other', start_time, end_time, {'message': "Start ED measurement"})
            elif register == 0x0B:  # set SFD
                return AnalyzerFrame('Other', start_time, end_time, {'message': f"Set SFD = {bytes_formatted(value)}"})
            elif register == 0x0E:  # set interrupts
                if value == 0x00:  # disable all interrupts
                    return AnalyzerFrame('Other', start_time, end_time, {'message': "Disable interrupts"})
                else:
                    result = ", ".join(name for mask, name in INTERRUPT_BITS.items() if value & mask)
                    return AnalyzerFrame('Other', start_time, end_time, {'message': f"Set interrupts: {result}"})
            elif register == 0x08:  # channel frequency
                channel = int(value & 0b00011111)  # bottom five bits are the channel
                self.radio_channel = channel
                if int(value & 0b10000000) == 0b10000000:  # manual clear-channel start
                    pass
                return AnalyzerFrame('Set Channel', start_time, end_time, {'data': str(channel)})

            else:
                return AnalyzerFrame('Write Register', start_time, end_time, {'register': bytes_formatted(register), 'data': bytes_formatted(value)})

        # reading register
        elif command & 0b11000000 == 0b10000000:
            if len(data) != 2:
                print(f'Received wrong-length packet to register read: {len(data)}')
                return False
            register = command & 0b00111111
            value = data[1].data['miso'][0]

            if register == 0x01:  # various statuses
                message = RADIO_STATUS.get(value, value)
                return AnalyzerFrame('Read Radio State', start_time, end_time, {'data': message})
            elif register == 0x06:  # RSSI, a random number, and CRC validity
                rssi = value & 0b00011111
                rssi_dbm = -94 + (3 * rssi)  # from datasheet
                crc_valid = value & 0b10000000 == 0b10000000
                msg = f"RSSI = {rssi_dbm} dB, "
                msg += f"CRC valid" if crc_valid else "CRC INVALID"
                return AnalyzerFrame('Other', start_time, end_time, {'message': msg})
            elif register == 0x07:  # check Energy Detect level
                if value == 0xff:
                    return AnalyzerFrame('Other', start_time, end_time, {'message': "Checked ED: (not started yet)"})
                else:
                    value_dbm = value - 94  # from datasheet
                    return AnalyzerFrame('Check ED', start_time, end_time, {'data': f"{value_dbm} dBm"})
            elif register == 0x0F:  # reading interrupts clears the flag (and is required to do so)
                if value == 0x00:
                    return AnalyzerFrame('Other', start_time, end_time, {'message': f"No interrupts set"})
                else:
                    result = ", ".join(name for mask, name in INTERRUPT_BITS.items() if value & mask)
                    return AnalyzerFrame('Other', start_time, end_time, {'message': f"Interrupts pending: {result}"})
            else:
                return AnalyzerFrame('Read Register', start_time, end_time, {'register': bytes_formatted([register]), 'data': bytes_formatted([value])})

        # SRAM read
        elif command & 0b11100000 == 0b00000000:
            bytes_list = b''.join(f.data['miso'] for f in data[2:])
            rx_data = bytes_formatted(bytes_list)
            return AnalyzerFrame('Other', start_time, end_time, {'message': f"SRAM read: {rx_data}"})

        elif command & 0b11100000 == 0b01000000:
            bytes_list = b''.join(f.data['mosi'] for f in data[2:])
            tx_data = bytes_formatted(bytes_list)
            return AnalyzerFrame('Other', start_time, end_time, {'message': f"SRAM write: {tx_data}"})

        else:
            return None