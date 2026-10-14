"""A stand-in text-to-speech engine, loaded through LNB_TTS_FACTORY."""

import numpy as np


class Engine:
    sample_rate = 24000

    def synthesize(self, text: str, voice: str) -> np.ndarray:
        return np.zeros(2400, dtype=np.float32)


def make(settings, models_dir):
    return Engine()
