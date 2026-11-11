# ItemLocus

ItemLocus is a local-first, open-source project that helps people find everyday belongings at home. It works with existing security cameras to remember where items such as keys, tools, wallets, remotes, or glasses were last seen, and to answer questions like **"Where are my keys?"**

This repository is in **planning**, with one exception: a small **photo-only test prototype** (see [Try the photo test](#try-the-photo-test)) that works from a few still photos. There is no camera, Frigate, or RTSP integration yet.

## Who it is for

- People living with dementia or other forms of memory loss who want a respectful, practical way to find things they have set down
- Caregivers and family members who are asked "where did I put it?" many times a day
- Anyone who has trouble keeping track of belongings, whether that is occasional forgetfulness or a more persistent challenge

The project aims to support independence and reduce time spent searching. It is **not** a medical device, and it does not diagnose or treat any condition.

## Design principles

- **Local first.** Detection, memory, and answers run on hardware you control. There is no cloud service in the default configuration.
- **Privacy by default.** Cameras are opt-in one at a time. The system stores an object crop, a room or zone name, a time, and a confidence score — not faces, not people, and not a continuous video archive of the household.
- **Honest answers.** If the system is not confident, it says it is not sure. A wrong room, stated with certainty, is worse than "I don't know."
- **Reuse what you already have.** ItemLocus is not a new video recorder. It is designed to sit alongside [Frigate](https://frigate.video/) when you have it, or to take RTSP or snapshot feeds from ordinary cameras when you do not.
- **Fixed cameras first.** The first version watches rooms, not a wearable camera on a person. A wearable mode may be explored later; it is not part of the initial product.

## Project status

| Area | Status |
| --- | --- |
| Public documentation | In progress (this repository) |
| Photo-only test prototype (enroll items, ask where they are, from a few still photos; CLI and localhost page) | Exists, experimental; real-model path not yet validated. No camera integration. See [docs/PHOTO-TEST.md](docs/PHOTO-TEST.md) |
| Camera-based item enrollment, detection, and last-seen store | Not started |
| Query UI and voice assistant | Not started |
| Builds, packages, or releases | None — no implementation work until the docs are accepted and a later milestone is approved |

See [docs/ROADMAP.md](docs/ROADMAP.md) for planned milestones, risks, and non-goals. See [docs/AI-INTEGRATION.md](docs/AI-INTEGRATION.md) for the planned AI architecture. See [docs/PRIVACY.md](docs/PRIVACY.md) for privacy rules. See [CONTRIBUTING.md](CONTRIBUTING.md) if you want to help.

## Try the photo test

A way to try the idea today with a few photos of your rooms. Everything runs on your computer; **nothing is uploaded anywhere**. The only network use is the one-time download of model weights by the model libraries on first run (roughly 1.2 GB for the default OWLv2 detector and CLIP embedder; allow a few minutes). Details, limits, and licences are in [docs/PHOTO-TEST.md](docs/PHOTO-TEST.md).

Windows PowerShell, from the repository root (Python 3.10 or newer):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
# Optional, for an NVIDIA GPU: install CUDA PyTorch first (see the comment in requirements.txt)
pip install -r requirements.txt
```

Put room photos in `photos\`, optionally one sub-folder per room (`photos\kitchen\`, `photos\office\`). Use photos without people where you can; if a person is detected, that region is blacked out in the saved copy. Avoid photographing medicine, documents, or screens.

```powershell
python -m itemlocus ingest photos                    # room = sub-folder name; or: --room kitchen
python -m itemlocus enroll "house keys" --query keys --ref keys-closeup.jpg
python -m itemlocus enroll "wallet"                  # text-only: no reference photo
python -m itemlocus find "where are my house keys?"  # add --json or --verbose for scores
python -m itemlocus serve                            # then open http://127.0.0.1:8765/
```

`find` prints the room, confidence, and box, and writes an object-only crop to `data\crops\`. Below the confidence threshold it says it is not sure. Photos, the database, and crops are stored under `data\` (ignored by git). Use `--photos-dir` / `--data-dir` or the `ITEMLOCUS_PHOTOS` / `ITEMLOCUS_DATA` environment variables to change locations, `--device cpu|cuda` to force a device, and `--detector yoloworld` for the optional faster detector.

`serve` binds to 127.0.0.1 only and refuses other addresses.

To run the tests (no models or GPU needed): `pip install -r requirements-dev.txt` then `python -m pytest`.

## How it is planned to work

```mermaid
flowchart LR
    cams[Home cameras] --> ingest[Ingest]
    frigate[Frigate events] --> ingest
    ingest --> detect[Detect and match]
    enroll[Enrolled item photos] --> detect
    detect --> store[Last-seen store]
    store --> query[Query]
    query --> ui[Web or phone UI]
    query --> assist[Home Assistant Assist]
```

1. **Connect cameras.** Prefer Frigate's event and snapshot API when Frigate is already running. Otherwise, accept RTSP streams or periodic stills from ONVIF or RTSP cameras. Each camera is mapped to a named room or zone, such as "kitchen" or "workbench."
2. **Enroll items.** A person or caregiver takes a few photographs of an item, gives it a name ("the house keys", "the red toolbox"), and ItemLocus stores a local visual embedding. No cloud training step.
3. **Watch for last seen.** When a camera view may contain an enrolled item, ItemLocus tries to detect it and match it to the enrollment. On a confident match it updates a last-seen record: room or zone, time, confidence, and a crop of the object only.
4. **Ask.** From a simple web or phone page, or by voice through Home Assistant Assist, someone asks "Where are my keys?" The reply is a short sentence, a time, and the crop — or a clear "I'm not sure."

Bathrooms and bedrooms should stay off unless a household deliberately turns them on. Privacy masks should hide beds and other excluded regions. See [docs/PRIVACY.md](docs/PRIVACY.md).

## What this is not

ItemLocus is not a replacement NVR, a face-recognition system, a people tracker, a medical product, or a tag-based finder (such as Bluetooth trackers). Those tools can be useful in their own ways; they are out of scope here. A longer list is in the [roadmap](docs/ROADMAP.md#non-goals).

## Hardware, in brief

The intended first target is a home computer or small server that can already run Frigate, with an optional accelerator (for example a Coral, Hailo, Intel iGPU or NPU, NVIDIA GPU, or Apple Silicon). Open-vocabulary detection and embeddings need more memory than a basic motion recorder; a typical recommendation is 16 GB of RAM. A Raspberry Pi is not the planned sole host for the first models. Camera placement and a clear view of counters, tables, and benches matter more than camera brand. Details are in [docs/AI-INTEGRATION.md](docs/AI-INTEGRATION.md#hardware-tiers).

## Contributing

Documentation improvements, issue reports, and careful discussion of privacy and accessibility are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request. In short:

- Keep the project generic and public. Do not commit household-specific paths, names, addresses, camera inventories, or anyone's photographs.
- Do not include images of faces, people, medicine or related gear, nudity, identity documents, or other private material — not even as examples.
- Use respectful language about dementia, memory loss, aging, and disability. Write *with* the people who may use this, not about them as a problem to be managed.
- Prefer local, inspectable approaches over cloud defaults.
- Confirm the contributor terms and sign off your commits as described in [CONTRIBUTING.md](CONTRIBUTING.md).

Code contributions are not open yet, because there is no application code. When implementation begins, this section will describe how to run tests, the license of any bundled models, and the review process.

## License

Copyright (C) 2026 the ItemLocus author (github.com/lundgren-greg).

ItemLocus is free software: you can redistribute it and/or modify it under the terms of the [GNU Affero General Public License v3.0](LICENSE) as published by the Free Software Foundation.

"Frigate" is a trademark of Frigate, Inc. ItemLocus plans to integrate with Frigate; it is not an official Frigate project.
