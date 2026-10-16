# Standard Library
import logging

log = logging.getLogger('beambar.voice')

SAMPLE_RATE = 8000
FRAMES_PER_CHUNK = 4096


class VoiceCapture:
    def __init__(self):
        self.stream = None

    def start(self, on_chunk):
        # Loaded on first use, so a missing audio library never stops the app from starting.
        import sounddevice as sd

        self.stop()

        def callback(indata, frames, time_info, status):
            if status:
                log.debug('mic status: %s', status)
            on_chunk(bytes(indata))

        self.stream = sd.RawInputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype='int16', blocksize=FRAMES_PER_CHUNK, callback=callback
        )
        self.stream.start()

    def stop(self):
        if self.stream is None:
            return
        try:
            self.stream.stop()
            self.stream.close()
        finally:
            self.stream = None

    @property
    def active(self):
        return self.stream is not None
