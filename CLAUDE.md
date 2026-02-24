# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Custom Wine runner for JM Studio (3DMakerPro 3D scanner software) on Linux, built for use with Bottles. The Wine build includes patches for USB scanner access (wineusb0.sys), V4L2 camera capture (qcap), and UVC Extension Unit queries.

## Build Commands

Build the runner:
```bash
./build-runner.sh
```

Install into Bottles:
```bash
tar xzf wine-jmstudio.tar.gz -C ~/.var/app/com.usebottles.bottles/data/bottles/runners/
```

## Architecture

- **`build-runner.sh`** — Build script that compiles libusb and the custom Wine fork (`poita66/wine`, branch `test/all-prs`) in WoW64 mode (`--enable-archs=i386,x86_64`), then packages the result as a `wine-jmstudio.tar.gz` tarball
- **`bottle.yml`** — Bottles configuration file users can import to set up a bottle with the custom runner
- Wine is built with WoW64 mode (single 64-bit build handles 32-bit Windows apps natively)
- Wine patches are LGPL-2.1+; JM Studio itself is proprietary
