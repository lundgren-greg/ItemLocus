# Privacy

ItemLocus is designed so that a household can look for misplaced belongings without building a surveillance archive of the people who live there. This document is the intended policy. The software does not exist yet; when it does, the implementation should match these rules.

## Local first

Detection, embeddings, the last-seen store, and answers run on hardware the household controls. There is no cloud service in the default configuration. Any optional cloud language model is off until a person turns it on, is labeled clearly, and should send text only by default — not images.

## What is stored

For each enrolled item, ItemLocus is planned to keep:

- A name the household chose
- Local enrollment embeddings derived from photographs the household provided
- The last-seen room or zone, time, and confidence
- An **object-only crop** of the item

Enrollment photographs and crops stay on the local machine. Retention is limited and configurable. A person should be able to delete an item, a crop, or the entire store, and to pause processing.

The system should strip location metadata from kept stills and should not write street addresses or precise coordinates into exports.

## What is not stored

- Faces or person crops
- Continuous raw video (recording, if any, stays with Frigate or the household's existing recorder)
- Camera views from rooms that have not been opted in
- Masked regions (for example a bed), which should be excluded before inference
- Sensitive categories: medicine and related gear, nudity, identity documents, mail, passwords, or other private screens and papers. If a frame cannot be classified safely, it is dropped

ItemLocus will not offer face recognition or people tracking.

## Consent and cameras

- Each camera is off for ItemLocus until someone in the household opts it in.
- Bathrooms and bedrooms stay off by default.
- When the system is used to support someone else, including a person living with dementia or other memory loss, the household should agree on who can query, who can see crops, and how to pause or wipe the system. Dignity and the ability to say no matter as much as the feature set.
- Fixed cameras in a home are more intrusive than a device a person chooses to wear. The first version uses fixed cameras only; that choice should be made deliberately.

## Queries and sharing

Answers include a short location, a time, and an object crop, or an honest "I'm not sure." The query UI should not show a live video wall. Optional image-free export hooks, if added later, would share last-seen *facts* (item, room, time, confidence) without images; they are not part of the first version.

## This is not medical or legal advice

ItemLocus is not a medical device. This policy describes product intent. It is not legal advice about recording laws, consent, or data protection in any particular place. Households are responsible for following the rules that apply to them.
