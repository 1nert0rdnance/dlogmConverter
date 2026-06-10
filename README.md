# DJI LUT Converter

A Python script that batch-applies a `.cube` LUT to DJI drone footage using FFmpeg, with a live terminal dashboard showing encode progress, speed, system resource usage, and compression ratios.

Built for DJI D-Log M → Rec.709 conversion but works with any `.cube` LUT and any `.MP4` source files.

![Python](https://img.shields.io/badge/python-3.8%2B-blue) ![Platform](https://img.shields.io/badge/platform-Windows-lightgrey) ![FFmpeg](https://img.shields.io/badge/requires-FFmpeg-orange)

---

## Features

- Batch-processes all `.MP4` files in the script's directory
- Auto-detects any `.cube` LUT file in the same folder — no hardcoded filename
- Choose between **H.264**, **H.265**, or **AV1** output at runtime
- Live sticky footer dashboard with:
  - Per-file and overall progress bars
  - Encode speed (fps, speed multiplier, bitrate)
  - CPU and RAM usage (requires `psutil`)
- Scrolling log panel above the dashboard showing real-time per-file status
- Handles terminal resize cleanly without corrupting the layout
- Compression ratio summary table on completion
- Detailed FFmpeg error reporting — if a file fails, the reason is captured and shown
- Output files saved to a `processed/` subfolder with original filenames preserved
- Source metadata (creation time, GPS, etc.) copied to output for correct gallery ordering

## Requirements

- Python 3.8+
- [FFmpeg](https://ffmpeg.org/download.html) — must be in your system `PATH`
- `psutil` *(optional)* — enables CPU and RAM monitoring

Install the optional dependency:
```
pip install psutil
```

## Usage

1. Drop `DJI_Lut_Applicator.py` and your `.cube` LUT file into the same folder as your `.MP4` files.

```
📁 your-footage-folder/
├── DJI_Lut_Applicator.py
├── DJI_DLogM_to_Rec709.cube
├── DJI_20260531_172251_0058_D.MP4
├── DJI_20260531_172311_0059_D.MP4
└── ...
```

2. Run the script:
```
python DJI_Lut_Applicator.py
```

3. Select your output codec when prompted:
```
  [1]  H.264              — faster encode, universal compatibility
  [2]  H.265              — smaller files (~40%), plays on most modern devices
  [3]  AV1 Next-Gen Archive — highest space savings, ideal for deep storage
```

4. Processed files appear in a `processed/` subfolder.

## Codec comparison

| | H.264 | H.265 | AV1 |
|---|---|---|---|
| Encode speed | Fast | ~2× slower | Very slow |
| Output size | Largest | ~30–40% smaller | ~50–60% smaller |
| Compatibility | Universal | Android 5+, iOS 11+, modern players | Chrome, Firefox, Android 10+, VLC |
| CRF | 18 | 24 | 26 |
| Best for | Quick turnaround, sharing | Daily use, phone galleries | Long-term archival storage |

**Recommended:** H.265 for phone galleries and general sharing (Pixel phones, Google Photos, VLC all handle it fine). AV1 for archival where encode time isn't a concern.

> **Note:** AV1 encoding via `libaom-av1` is significantly slower than H.264/H.265 — expect 5–10× longer encode times on CPU. This is a limitation of the software encoder, not the script.

## Notes

- If multiple `.cube` files are present, the script picks the first one alphabetically. Keep one `.cube` per folder to avoid ambiguity.
- Output is always 8-bit `yuv420p` for maximum device compatibility.
- FFmpeg's `lut3d` filter is CPU-only — GPU encoding is not used since the bottleneck is the LUT processing step, not the encode.
- If a file fails to encode, the script captures the FFmpeg error output and displays the reason in the final summary.

## License

MIT
