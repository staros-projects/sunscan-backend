# SunScan backend release notes

The version is `BACKEND_API_VERSION` in `app/main.py`. The app reads it from `GET /sunscan/stats` (`backend_api_version`).

## 2.1.1 (2026-09-19)

First packaged release of the 2.1 series: `sunscan_backend_source.zip` also contains everything listed under 2.1.0.

### Fixed

- **The spectral line was missing from the watermark of single scans.** Only the H-epsilon, helium and continuum images said what they show; every other image of a scan carried the date alone, whatever the line. The label of the line tag (for instance `Ca II H line - 3968 Å`) is now written after the date on the surface, colour, negative, prominence and Doppler images, as it already was on stacks and animations. The colour images of the H-epsilon and helium processings get it too.
  - A scan without a tag, or with a tag which is not a line (`other`), keeps the date alone.
  - The watermark is written when a scan is processed: process an older scan again to get the line on its images.
- **Images of the previous line stayed after a tag change.** Processing a scan again after changing its tag rewrote the images of the new line but left the ones it does not produce: the negative image when the new line is not a hydrogen line, the colour image when it has no colour (Fe I, Fe X, Fe XIV, a tag which is not a line). They are now removed by the processing, once the scan is rebuilt. Every other image is left alone, the H-epsilon ones included.
- Double space in the Ca II H label (`3968  Å`), which also showed in the watermark of the stacks.

### Changed

- Stacks and animations now return `observation_date` in `GET /sunscan/stacked` and `GET /sunscan/animated`: the mean time of the scans for a stack, which is the time written on its images, and the first scan for an animation. It is `null` for the ones created before 2.1.0.
- SpectroSolHub: a stack is sent with this same date (it used to be the middle between its first and last scan, which differs from the watermark from 3 scans on) and with the observer name given when it was stacked.

## 2.1.0 (2026-09-19)

Published on the `dev` branch only, never packaged on its own.

### Added

- **H-epsilon from Ca II H scans.** The H-epsilon line (3970.08 Å) sits in the red wing of Ca II H, so a Ca II H scan now also produces `sunscan_hepsilon` (surface), `sunscan_hepsilon_color` and `sunscan_hepsilon_protus` (prominences). The line is confirmed from the spectrum itself, not only from the tag, so a Ca II K scan tagged Ca II H by mistake produces nothing more. Costs about 4 s per Ca II H scan; every other output is unchanged.
- **Upload to SpectroSolHub** of scans, stacks and animations (`/spectrosolhub/*` routes), with the login kept on the SunScan. Every item then reports a `hub_status`.
- **Line tags on stacks and animations**, taken from their scans when they are created, and changeable afterwards like the tag of a scan.
- **Filters on the lists**: `tag`, `status`, `date_from`, `date_to` and `hub_status` on `GET /sunscan/scans`, `tag` and `hub_status` on the stacks and the animations.
- **Progress of stackings and animations** on the `job_progress_<job_id>` WebSocket channel and `GET /sunscan/process/job/{job_id}`, for the requests giving a `job_id`.
- **PiSugar 3 repair**: `GET /power/pisugar/status` detects a battery board stuck in its bootloader and `POST /power/pisugar/repair` reflashes its firmware, now bundled in `app/firmware`.

### Fixed

- The creation date of stacks and animations comes from the name of their directory instead of its modification time, which changed whenever a file was added to it.

## 2.0.0 (2026-09-18)

### Added

- **Web gallery**: browse, preview, download and delete scans, stacks, animations and snapshots from a browser. Downloads are streamed as a zip built on the fly, nothing is written on the SD card.
- **Processing progress**: the steps of a scan being processed are reported on the `scan_progress_<key>` WebSocket channel and by `POST /sunscan/scan/process/status/`.
- **Joining a WiFi network from the hotspot** (`/network/*` routes), on Raspberry Pi OS Bookworm and later.

### Changed

- **Reconstruction about twice as fast**, with identical images.
- **Fewer dropped frames while scanning**: the SER file is written by a dedicated thread, the backend runs with a raised CPU and disk priority, WiFi power saving and the periodic system maintenance are turned off.
- The camera mode is selected by its size and bit depth instead of its index, which changes between libcamera versions.
- The hotspot is restricted to WPA2, which some phones need to be able to join it.

## Earlier versions

See the git history.
