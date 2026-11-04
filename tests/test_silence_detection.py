from record_transcript_resume.silence_detection import SilenceTracker


def test_silence_tracker_counts_initial_silence_and_resets_on_sound() -> None:
    tracker = SilenceTracker()
    tracker.reset(now=100.0)

    tracker.observe(0.001, now=200.0)
    assert tracker.silent_for(now=700.0) == 600.0

    tracker.observe(0.02, now=701.0)
    assert tracker.silent_for(now=702.0) == 1.0
    tracker.observe(0.002, now=703.0)
    assert tracker.silent_for(now=1301.0) == 600.0


def test_silence_tracker_counts_time_when_loopback_supplies_no_frames() -> None:
    tracker = SilenceTracker()
    tracker.reset(now=10.0)
    assert tracker.silent_for(now=610.0) == 600.0
