# SunScan backend release notes

The version is `BACKEND_API_VERSION` in `app/main.py`. The app reads it from `GET /sunscan/stats` (`backend_api_version`).

## 2.1.7 (2026-10-01)

### Fixed

- **Scans whose images differ in size could not be stacked.** A scan processed without the autocrop keeps the whole swept area, so the size of its images depends on the length of the scan (2102×956 and 2132×1787 for two scans of 1028 and 1891 frames of the same Sun); scans processed with different autocrop sizes differ too. The stacking summed the images pixel by pixel and failed with `stacking_failed` (HTTP 500, `operands could not be broadcast together`).
  - When the images of the selected scans differ in size, each one is now cropped around its solar disk to a common square of about 1.4 disk diameters (1144 px for a disk of 816), then aligned and summed as before. The images of the scans also stacked with the surface (continuum, H epsilon) get the same crop.
  - Scans of the same size, the usual case with the autocrop, are untouched: their stacks are identical to 2.1.6.
  - When the disk can not be found on one of the scans, the stacking answers the new error `disk_not_found` (HTTP 409, with the number and the folder of the scan in `detail`) instead of a 500. See `docs/erreurs-stack.md` for the error keys the app can show.

## 2.1.6 (2026-09-29)

### Fixed

- **The folders of `storage/` are created again when they are missing.** Any of them (`scans`, `snapshots`, `stacking`, `animations`, `tmp`, and `storage/` itself) can be deleted by hand, over SFTP or from the Linux desktop, while the backend runs; and a fresh image has none of them, each one appeared with its first use. Part of the code assumed they were there:
  - a scan started without `storage/scans` stopped the capture thread: no more frames and no more scans until the backend restarted;
  - a snapshot without `storage/snapshots` closed the live socket, and the snapshot still pending, every reconnection of the app closed it again;
  - a stacking or a listing without `storage/` answered 500, and so did `POST /sunscan/update` without `storage/tmp` (on a fresh image, until the web gallery had cached a thumbnail);
  - `GET /snapshots`, `GET /sunscan/snapshots/delete/all/` and the gallery (`/gallery/list/...`) answered 404 or 500 instead of an empty folder.
  - Every folder is now created with its parents where it is needed: when a scan, a snapshot, a stack or an animation is written, when a section is listed, and `storage/` itself when the backend starts. Nothing changes for the folders which exist, and a folder deleted during a recording still loses that scan.

## 2.1.5 (2026-09-28)

### Fixed

- **The SunScan left its hotspot on its own after `POST /network/hotspot`.** The saved home networks are kept by design, and a background monitor joins one when the box is on its hotspot with nobody connected and the network is in range (a box booted in the field, brought back home). It ran too after the app had asked for the hotspot, at home with the WiFi in range: its next check could come seconds after the switch, before the phone had joined the hotspot, and the box went straight back to the WiFi. It also went back each time the phone dropped the hotspot for two minutes, which phones do with a network without internet.
  - After `POST /network/hotspot` the SunScan now stays on the hotspot until the next boot or the next `POST /network/wifi/connect`. The flag is kept in memory only: a reboot goes back to the home network when it is in range, as the app announces. `GET /network/status` gives it as `hotspot_hold`.
  - After any switch to the hotspot (hotspot asked, current network forgotten, failed connection), the automatic return waits five minutes, so the phone has time to join the hotspot and, after a failed connection, to read the result.

## 2.1.4 (2026-09-21)

### Changed

- **The Linux desktop of the Raspberry Pi is off by default.** Nothing on the SunScan needs it: the device is driven from the phone, and the display manager, the compositor, the panel and the file manager only took memory (about 70 MB measured on a Pi 4) and 1 to 3 % of a core. Each time the backend starts it sets the Pi to boot without the desktop, so an installed SunScan loses it at the second boot after the update.
  - A desktop which is already running is never stopped by the backend itself: the backend restarts far more often than the Pi does, and stopping the session would close the applications of whoever is working on the Pi. Only the next boots change.
  - Nothing else is modified: the automatic login of the display manager is left as it is, and the backend is a system service, unaffected by the desktop going up or down.
  - With the desktop off, the HDMI screen shows the text console and VNC does not answer, since it needs the desktop.

### Added

- **Routes to turn the Linux desktop on and off**, so it can be brought back to work on the Pi itself, from the app or with `curl`. See `docs/bureau-linux.md`.
  - `GET /sunscan/desktop` gives `supported` (false on a Raspberry Pi OS Lite image), `running`, `at_boot` and the systemd `state` of the display manager.
  - `POST /sunscan/desktop` takes `running` and / or `at_boot`, both optional, the one left out is not changed. `running` starts or stops the desktop for the current boot; `at_boot` chooses whether it starts with the Pi, and keeps that choice out of the application folder (`~/.config/sunscan/desktop_at_boot`), so an update does not overwrite it. Without that flag, a boot on the desktop set by hand (`raspi-config`, `systemctl set-default`) is reverted when the backend starts.
  - The answer is the state read after the switch. Starting or stopping is refused during the recording of a scan (409 `recording`), since starting the desktop loads the CPU and the SD card; asking for `at_boot` alone is still accepted. 501 `unsupported` without a desktop installed.
  - Stopping closes every application opened on the desktop, unsaved work included: the app asks for confirmation first.
- **`GET /camera/set-monobin-mode/{mode}`** selects a monochrome binning mode directly (0 RGB, 1 R, 2 G, 3 B), instead of cycling through the four with `/camera/toggle-monobin-mode/`. 422 for any other value. The cycling route is unchanged.

## 2.1.3 (2026-09-20)

### Added

- **H-epsilon images of the stacks and animations of Ca II H scans.** A Ca II H scan produces H-epsilon images since 2.1.0, but stacking or animating Ca II H scans left them out (reported by a user). When every scan of the selection has them, the stack now also produces:
  - `stacked_hepsilon_N_raw` and `stacked_hepsilon_N_sharpen` (surface, png and jpg), and the colour images `stacked_hepsilon_color_N_raw.jpg` and `stacked_hepsilon_color_N_sharpen.jpg`;
  - `stacked_hepsilon_protus_N_raw` (prominences, png and jpg), not sharpened, as on a single scan;
  - the previews `stacked_hepsilon_preview.jpg` and `stacked_hepsilon_protus_preview.jpg`.
  - The H-epsilon images of the scans are aligned with the distortion maps computed on the Ca II H surface, as the continuum is. Their watermark carries the H-epsilon line (`Hε line - 3970.08 Å`), not the Ca II H tag of the stack.
  - One scan without H-epsilon images in the selection (processed before 2.1.0, a Ca II K scan tagged Ca II H, or the line too close to the edge of the spectrum) and the stack has none: process that scan again first. Every other image of a stack is unchanged, byte for byte.
  - The new images are listed in `images` of `GET /sunscan/stacked`, and can be sent to SpectroSolHub (`hepsilon_sharpen`, `hepsilon_raw`, `hepsilon_color_sharpen`, `hepsilon_color_raw`, `hepsilon_protus_raw`, line H-epsilon).
  - Animations get them too: `animated_hepsilon.gif` and `animated_hepsilon_protus.gif` from scans, and from stacks `animated_hepsilon.gif`, `animated_hepsilon_sharpen.gif` and `animated_hepsilon_protus.gif`, when every source has the images. The date written on the frames comes with the H-epsilon line. They are listed in `images` of `GET /sunscan/animated` and can be sent to SpectroSolHub (`hepsilon`, `hepsilon_sharpen`, `hepsilon_protus`).

### Fixed

- `stacked_img_count` of `GET /sunscan/stacked` was wrong for a stack of 10 scans or more: only one digit of the number was read from the file names.

## 2.1.2 (2026-09-19)

### Fixed

- **The raw colour image of a stack was sharpened.** A stack comes in two versions, raw and sharpened, but `stacked_color_N_raw.jpg` was the same image as `stacked_color_N_sharpen.jpg`: the sharpening wrote into the image it was given, so the raw stack was already sharpened when the colour images were made. The raw colour image is now made from the raw stack.
  - Every other image of a stack is unchanged, pixel for pixel: surface and continuum, raw and sharpened, and the negative, which is built on the sharpened stack as the negative of a single scan is.
  - The images of single scans are unchanged too.
  - Stacks already created are not rebuilt: stack the scans again to get the raw colour image.

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
