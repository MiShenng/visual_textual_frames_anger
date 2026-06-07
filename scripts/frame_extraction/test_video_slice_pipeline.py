from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageFilter

from video_slice_pipeline import (
    FrameInfo,
    SegmentInfo,
    VideoRow,
    choose_videos,
    compute_phash,
    hamming_distance,
    segment_adjacent_frames,
    to_segment_infos,
    variance_of_laplacian,
)


class VideoSlicePipelineTests(unittest.TestCase):
    def test_choose_videos_is_reproducible(self) -> None:
        candidates = [
            VideoRow(
                row_index=index,
                selected_from="keep",
                platform="douyin",
                platform_video_id=str(index),
                author_name=f"author-{index}",
                title=f"title-{index}",
                description="",
                published_at="",
                matched_queries="",
                video_path=f"/tmp/{index}.mp4",
                source_row={},
            )
            for index in range(10)
        ]
        selected_a = choose_videos(candidates, sample_size=4, seed=42, process_all=False)
        selected_b = choose_videos(candidates, sample_size=4, seed=42, process_all=False)
        self.assertEqual([item.platform_video_id for item in selected_a], [item.platform_video_id for item in selected_b])

    def test_segment_adjacent_frames_uses_threshold(self) -> None:
        frames = [
            FrameInfo(0, 0.0, "/tmp/0.jpg", "0.jpg", "0f", int("0f", 16), 1.0, 100, 100),
            FrameInfo(1, 1.0, "/tmp/1.jpg", "1.jpg", "0e", int("0e", 16), 2.0, 100, 100),
            FrameInfo(2, 2.0, "/tmp/2.jpg", "2.jpg", "ff", int("ff", 16), 3.0, 100, 100),
        ]
        segments = segment_adjacent_frames(frames, fps=1.0, phash_threshold=1)
        self.assertEqual([len(segment) for segment in segments], [2, 1])

    def test_representative_frame_is_sharpest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            frame_a = root / "frame_a.jpg"
            frame_b = root / "frame_b.jpg"
            Image.new("RGB", (64, 64), color="gray").save(frame_a)
            sharp = Image.new("L", (64, 64), color=0)
            for x in range(64):
                sharp.putpixel((x, x), 255)
            sharp = sharp.convert("RGB")
            sharp.save(frame_b)

            frames = [
                FrameInfo(0, 0.0, str(frame_a), frame_a.name, "00", 0, 1.0, 64, 64),
                FrameInfo(1, 1.0, str(frame_b), frame_b.name, "00", 0, 9.0, 64, 64),
            ]
            representatives_dir = root / "representatives"
            segments = to_segment_infos([frames], representatives_dir, root, fps=1.0)
            self.assertEqual(segments[0].representative_frame_index, 1)
            self.assertTrue((representatives_dir / "segment_0000_rep.jpg").exists())

    def test_sharpness_detects_blur_difference(self) -> None:
        base = Image.new("L", (64, 64), color=0)
        for x in range(16, 48):
            for y in range(16, 48):
                base.putpixel((x, y), 255)
        blurred = base.filter(ImageFilter.GaussianBlur(radius=3))
        self.assertGreater(variance_of_laplacian(base), variance_of_laplacian(blurred))

    def test_phash_distance_for_identical_image_is_zero(self) -> None:
        image = Image.new("RGB", (64, 64), color="white")
        left_int, _ = compute_phash(image)
        right_int, _ = compute_phash(image.copy())
        self.assertEqual(hamming_distance(left_int, right_int), 0)


if __name__ == "__main__":
    unittest.main()
