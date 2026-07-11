# Changelog

## 0.1.6 - 2026-07-11

- Preserved real timestamp gaps from IAD files so measurement-stop periods are not compressed.
- Kept no-value samples as blank values instead of filling or interpolating nearby temperatures.
- Improved timestamped scaled-physical CHA parsing, including int16 raw records with no-value sentinels.
- Updated original IPEmotion CSV grouping to honor each channel's own .X time column when plotting and averaging.
- Broke graph lines across missing samples or large time gaps so disconnected measurements are shown as blanks.
## 0.1.5 - 2026-07-05

- Fixed unsigned 16-bit physical IAD channels so temperature channels no longer convert to inflated values.
- Kept partially missing channels in averaging lists while hiding channels that are entirely No value.
- Skipped averaging output for channels with no numeric samples in the selected range.
- Restored Korean UI labels that were corrupted during local edits.

## 0.1.4 - 2026-07-04

- Added a no-zip release mode that builds PyInstaller in noarchive mode and can skip package zip creation.
- Updated installer validation to accept extracted standard library files instead of base_library.zip.
- Documented copying the whole release folder for company DRM environments that block zip access.

## 0.1.3 - 2026-07-04

- Added an installation launcher that clears PYTHONHOME and PYTHONPATH before starting the PyInstaller app.
- Added installer checks for the embedded Python standard library archive to catch incomplete extraction or quarantined files.
- Included launch.cmd in release packages and updated install notes for company PCs.

## 0.1.2 - 2026-07-04

- Improved IAD extraction for logger exports that contain ZIP local headers without a central directory.
- Fixed physical int16 CHA scaling by handling CHA headers and signed raw offsets correctly.
- Added support for scaled physical CHA records stored as timestamp plus raw value pairs.
- Inferred output sample rate from converted time data when metadata sampleRate is misleading.
- Skipped media channels during numeric conversion.

## 0.1.1 - 2026-06-27

- Changed fixed 10-minute/5-minute averaging mode so graph double-click sets a single baseline and << / >> applies the selected fixed range.
- Kept user-defined mode as two graph double-clicks for selecting a custom averaging range.
- Added an app-wide exit button to the main window.

## 0.1.0 - 2026-06-21

- Added IAD import and conversion to CSV/Excel.
- Added UTF-16 IRD XML parsing and CHA channel conversion.
- Added channel metadata extraction including units, sampling rate, and conversion formula.
- Added GUI flow for file import, channel plotting, averaging range selection, preview popup, and Excel export.
- Added graph zoom, pan, and double-click averaging range selection.
- Added ambient-temperature adjusted average output column.
- Added source file and averaging time comments to exported Excel.
