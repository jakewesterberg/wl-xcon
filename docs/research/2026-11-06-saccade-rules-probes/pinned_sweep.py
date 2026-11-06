import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tests"))
import test_saccade as T
from wl_xcon.saccade import Detector, Params, detect, thresholds, velocity

class Pinned(Detector):
    def __init__(self, eta):
        super().__init__()
        self.eta = eta
    def _refresh(self):
        self._eta_x, self._eta_y = self.eta

bad_free = bad_pinned = cases = 0
for seed in list(range(0, 60)) + [20261104]:
    rng = random.Random(seed)
    for _ in range(200):
        onset = rng.randint(150, 300)
        gaze, at = T._trace([(onset, rng.randint(2, 16), rng.uniform(1.0, 9.0), rng.uniform(-3.0, 3.0))], n=480, seed=rng.randint(0, 10**6))
        lost = T._lost(gaze, *{onset + rng.randint(-6, 12) for _ in range(rng.randint(1, 3))})
        batch = detect(lost, at)
        free = T._confirmations(lost, at)
        d = Pinned(thresholds(velocity(lost, at, Params()), Params()))
        pinned = [s for t, g in zip(at, lost) if (s := d.accept(t, g)) is not None]
        cases += 1
        if [s.start for _, s, _ in free] != [s.start for s in batch]:
            bad_free += 1
        if [s.start for s in pinned] != [s.start for s in batch]:
            bad_pinned += 1
            print("pinned differs", seed, onset, [(s.start, s.stop) for s in pinned], [(s.start, s.stop) for s in batch])
print("cases", cases, "free start lists differ", bad_free, "pinned differ", bad_pinned)
