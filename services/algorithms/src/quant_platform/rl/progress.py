"""Stdout progress reporting for long CPU training runs (server logs / nohup).

stable-baselines3 is imported inside the factory so this module stays
import-safe without the ``[rl]`` extra, matching the rest of ``rl/``.
"""

from __future__ import annotations

import sys
import time
from collections import deque


def _fmt(seconds: float) -> str:
    total = int(max(0.0, seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}"


def make_progress_callback(total_timesteps: int, every: int, eval_cb=None, stream=None):
    """One flushed status line per ``every`` steps: %, elapsed, ETA, rewards.

    Line-based on purpose (no ``\\r``): the server runs training under nohup and
    the log file must stay readable. ``eval_cb`` is an optional SB3
    ``EvalCallback``; when given, the best validation score so far is appended.
    """
    from stable_baselines3.common.callbacks import BaseCallback

    stream = stream or sys.stdout
    every = max(1, int(every))
    total = max(1, int(total_timesteps))

    class ProgressCallback(BaseCallback):
        def __init__(self) -> None:
            super().__init__(verbose=0)
            self._start = time.time()
            self.rewards: deque[float] = deque(maxlen=100)

        def _on_training_start(self) -> None:
            self._start = time.time()
            self._report()

        def _on_step(self) -> bool:
            for info in self.locals.get("infos") or []:
                episode = info.get("episode")
                if episode is not None:
                    self.rewards.append(float(episode["r"]))
            if self.num_timesteps % every == 0 or self.num_timesteps >= total:
                self._report()
            return True

        def _report(self) -> None:
            n = self.num_timesteps
            elapsed = time.time() - self._start
            eta = elapsed / n * (total - n) if n else 0.0
            mean = f"{sum(self.rewards) / len(self.rewards):+.2f}" if self.rewards else "n/a"
            best = ""
            if eval_cb is not None:
                value = getattr(eval_cb, "best_mean_reward", None)
                if value is not None and value > float("-inf"):
                    best = f" | best_val {value:+.2f}"
            print(
                f"[{n}/{total} {100.0 * n / total:5.1f}%]"
                f" elapsed {_fmt(elapsed)} eta {_fmt(eta)}"
                f" | ep_rew100 {mean}{best}",
                file=stream,
                flush=True,
            )

    return ProgressCallback()
