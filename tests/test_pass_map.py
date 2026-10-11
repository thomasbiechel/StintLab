"""Pass-Map-Reel: Zeitachse schnell, um Manöver herum langsam."""

from stintlab.reels.pass_map import FAST, FPS, SLOW, frame_times, slow_weight


def test_slow_weight_is_one_at_the_pass_and_zero_far_away():
    assert slow_weight(100.0, [100.0]) == 1.0
    assert slow_weight(140.0, [100.0]) == 0.0
    assert 0 < slow_weight(105.0, [100.0]) < 1


def test_frames_are_dense_around_the_pass():
    times = frame_times(80.0, 120.0, [100.0])
    near = [t for t in times if abs(t - 100.0) < 1]
    far = [t for t in times if 80.0 <= t < 82.0]
    assert len(near) / 2 > len(far) / 2 * 3         # mehr Bilder pro Echtzeit-Sekunde am Manöver
    assert abs((times[1] - times[0]) - FAST / FPS) < 1e-9
    assert SLOW < FAST
