from enum import StrEnum


class TipStatus(StrEnum):
    DETECTED = "detected"  # seen, not yet acted on
    CONFIRMING = "confirming"  # waiting for confirmation (countdown)
    QUEUED = "queued"  # in the playback queue
    ACTIVE = "active"  # toy is firing now
    DONE = "done"  # completed
