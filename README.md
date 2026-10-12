
  # SPI Sniffer for Atmel AT86RF233
  
This extension interprets SPI traffic flowing to and from the Atmel AT86RF233, which is an 802.15.4 radio.

## Capabilities
The extension interprets and nicely displays the following:
- Register reads/writes for channel selection, radio state, RSSI, CRC check, ED check, and some others.
- Frame buffer reads/writes (i.e. sent and received payloads) -- these are displayed as provided by the chip, meaning without the preamble and SFD but with the CRC (assuming the master bothers to read it out -- which it might not).  It's prefixed by `ch [channel number]:` so you know which channel messages are being sent/received on.
- Supports early frame buffer read/write termination, wherein the master de-asserts the CS line before reading or writing the entire buffer (as supported by the chip in some cases).

## Limitations
- Like the chip itself, this extension uses the CS line enable/disable to delimit transactions.  This requires that you a) have a CS signal and that b) it goes low before and high after each transaction.  If you don't have a CS signal or leave it low all the time, the SPI analyzer might read it properly but this extension won't parse the individual commands properly.
- Many registers are not interpreted into human-readable text -- in these cases the register number and read/written value are shown
- "SRAM" random-access read/write of the frame buffer is supported but somewhat dumb and untested

## For Developers (How It Works)
When CS goes low, incoming bytes are added into `self.data`.  When CS goes high again, `self.data` is sent to `parse_message()` to be parsed.  That function uses the high bits of the first byte to determine what kind of command is being sent, and goes from there.

I use the CS line as a packet delimiter because:
1. This is how the chip does it.
2. I'm too lazy to write a state machine that handles every case if CS is missing.
3. It's needed to support premature abort of frame buffer read/write by de-asserting the CS line.  Without CS, there's no easy way for us to know that the read is over because the buffer length byte sent by the radio != the number of bytes read out.

We don't hold a lot of state between transactions, but we do keep track of the radio channel.  This allows us to prefix sent/received data with the channel number, which can be useful for channel-hopping applications.

## Boilerplate from Saleae

1. Build your extension by updating the Python files for your needs
2. Create a public Github repo and push your code 
3. Update this README
4. Open the Logic app and publish your extension
5. Create a Github release
6. Debug your hardware like you've never done before :)

  