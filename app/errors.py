class PublicError(Exception):
    """A failure whose message is written for the learner and may be shown as-is."""


class NoTextLayer(PublicError):
    """The PDF has pages but no selectable text: a scan. A vision model can transcribe it."""
