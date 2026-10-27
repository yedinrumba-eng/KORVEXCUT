"""Which frames one reader reads in a row (spec S1.5b row 1, `render/reads.py`)."""

import pytest

from kcut.render.reads import ReadRun, plan_reads


class TestPlanReads:
    def test_reads_nothing_asked_nothing_read(self) -> None:
        assert plan_reads([]) == []

    def test_reads_frames_in_order_are_one_reader(self) -> None:
        assert plan_reads([10, 11, 12, 13]) == [ReadRun(10, 13, [10, 11, 12, 13])]

    def test_reads_one_frame_is_one_run_of_one(self) -> None:
        assert plan_reads([7]) == [ReadRun(7, 7, [7])]

    def test_reads_a_step_up_to_the_gap_stays_in_the_run_and_a_bigger_one_starts_another(
        self,
    ) -> None:
        assert plan_reads([0, 8, 16]) == [ReadRun(0, 16, [0, 8, 16])]
        assert plan_reads([0, 9]) == [ReadRun(0, 0, [0]), ReadRun(9, 9, [9])]

    def test_reads_the_gap_is_a_parameter(self) -> None:
        assert plan_reads([0, 3, 6], max_gap=2) == [ReadRun(0, 0, [0]), ReadRun(3, 3, [3]),
                                                   ReadRun(6, 6, [6])]  # fmt: skip
        assert plan_reads([0, 20], max_gap=20) == [ReadRun(0, 20, [0, 20])]

    def test_reads_a_jump_back_starts_another_reader(self) -> None:
        assert plan_reads([10, 11, 5, 6]) == [ReadRun(10, 11, [10, 11]), ReadRun(5, 6, [5, 6])]

    def test_reads_slow_motion_repeats_a_frame_inside_one_run(self) -> None:
        assert plan_reads([10, 10, 11, 11, 12]) == [ReadRun(10, 12, [10, 10, 11, 11, 12])]

    def test_reads_fast_motion_skips_frames_inside_one_run(self) -> None:
        run = plan_reads([90, 92, 94, 96])[0]
        assert (run.first, run.last, run.picks) == (90, 96, [90, 92, 94, 96])

    def test_reads_the_remap_of_the_example_is_two_runs(self) -> None:
        frames = [*range(0, 30), *(90 + 2 * k for k in range(30))]
        first, second = plan_reads(frames)
        assert (first.first, first.last, len(first.picks)) == (0, 29, 30)
        assert (second.first, second.last, len(second.picks)) == (90, 148, 30)

    def test_reads_every_frame_asked_comes_out_once_and_in_order(self) -> None:
        frames = [5, 5, 6, 40, 41, 41, 2, 3, 3, 100]
        runs = plan_reads(frames)
        assert [pick for run in runs for pick in run.picks] == frames
        assert all(run.first == run.picks[0] and run.last == run.picks[-1] for run in runs)

    @pytest.mark.parametrize("frames", [[1, 2, 3], [3, 1, 2], [0, 100, 200], [4, 4, 4]])
    def test_reads_a_run_never_goes_backwards_or_leaps(self, frames: list[int]) -> None:
        for run in plan_reads(frames):
            steps = [b - a for a, b in zip(run.picks, run.picks[1:], strict=False)]
            assert all(0 <= step <= 8 for step in steps)
