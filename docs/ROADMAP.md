# Roadmap

ItemLocus is in planning. This document describes the intended first product (the MVP), later work, risks, and non-goals. Nothing here is implemented yet.

## Minimum viable product

A local add-on that sits on [Frigate](https://frigate.video/) when available, or on RTSP or snapshot cameras when it is not, lets someone enroll a few personal items from photographs, keeps a last-seen room, time, and object-only crop for each item, and answers "Where are my keys?" in a simple web or phone UI and through Home Assistant Assist. It includes a large-text, high-contrast mode and an honest "not sure" path. There is no cloud in the default configuration.

### Milestones

1. **Ingest and rooms.** Consume Frigate MQTT events and snapshots when Frigate is present, or periodic RTSP or ONVIF stills when it is not. Map each camera (and, where possible, each Frigate zone) to a named room or area. Honor privacy masks. Drop person and face crops. No cloud. Cameras are off for ItemLocus until they are opted in.
2. **Enrollment.** Name an item, add a handful of photographs (about 3–10), store local embeddings, and list or delete items. Support more than one instance of a similar object (two key rings, two remotes) with distinct names.
3. **Last-seen writer.** Use open-vocabulary detection plus embedding match to update a last-seen record: room or zone, timestamp, confidence, and an object-only crop. Configurable retention and deletion.
4. **Query.** A simple web and phone page, plus a Home Assistant Assist intent. Return place, time, and crop. Low confidence, or no sighting within the retention window, produces "I'm not sure," never an invented location.
5. **Caregiver and accessibility pass.** Large text and high contrast. Clear control over who can query and who can see crops. Pause and wipe. Large tap targets, readable type, and no meaning that depends on color alone.

A later slice, not part of the MVP: consistent identity across several cameras, distinguishing "still visible" from "last seen," fully offline voice wake, optional wearable or first-person input, and optional **image-free** export hooks so another household tool could subscribe to last-seen *facts* (item name, room, time, confidence) without receiving images. Those hooks are future work only; ItemLocus stays a standalone project.

## Risks

- **Small and hidden objects.** Keys, rings, and similar items are often too small, shiny, or covered (in a drawer, pocket, bag, or under paper) for a typical ceiling or corner camera. The product must say this clearly. Guidance on camera placement is part of the work, not an afterthought.
- **Look-alikes.** Two similar key rings or remotes will confuse re-identification. Enrollment must allow separate items, and the UI must show the crop so a person can disagree with the match.
- **Harm from a wrong answer.** For someone living with memory loss, a confident wrong room is worse than "I don't know." Thresholds, wording, and calibration matter as much as the model. See [AI integration](AI-INTEGRATION.md#confidence-and-honest-answers).
- **Consent and dignity.** Always-on cameras in a home, especially when set up to support someone else, need household agreement, excluded rooms, and a way to pause or wipe the system. Bathrooms and bedrooms stay off by default. Fixed cameras are more intrusive than a device a person chooses to wear; the documentation should treat that difference seriously.
- **Domain gap.** Close-up enrollment photos may not match a wide, dim, top-down camera frame. Enrollment guidance and, later, in-situ snapshots can reduce this gap.
- **Compute.** Open-vocabulary models and embeddings are heavier than a basic motion detector. A small always-on box may need an accelerator, or may only process Frigate event snapshots rather than every frame.
- **Brand and integration.** Integrate with Frigate; do not use the Frigate name or logo in a way that implies official status.

## Non-goals

- Not a new network video recorder, and not a Frigate fork. Recording, motion detection, and video retention stay with Frigate or the household's existing recorder.
- Not face recognition, person tracking, or visitor logs. ItemLocus must not store face or person crops.
- Not a medical device, and no clinical or diagnostic claims.
- No cloud inference in the default path. Any cloud option is off until a person turns it on, and should send as little data as possible.
- Not Bluetooth, UWB, or RFID tags. They can complement ItemLocus later; they are a different product.
- Not a wearable or first-person camera in the MVP.
- Not outdoor, property-wide mapping, multi-site inventories, or a catalog of furniture.
- No use of sensitive image categories (medicine and related gear, nudity, identity documents, or other private data) as examples, tests, or features.

## Status of this plan

Documentation only. Implementation of any milestone needs a later, explicit go-ahead.
