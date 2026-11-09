# Offline classification rules

## User policy

On 2026-11-08 the user chose to retain their existing domain groups and give
mainland-China / Hong Kong **service regions** priority. Global products continue
to use domain groups regardless of publisher origin. Matching is deterministic
and offline at runtime. Unknown names and ambiguous placements remain for review.

Regional aliases include 🇨🇳 / China / 中国大陆 and HK / 🇭🇰 / Hong Kong / 香港.
`folders.regions` changes the target names; `regions` overrides individual bundle
IDs with CN, HK or GLOBAL. The narrow service-name cues cover local services
such as Railway12306, Meituan and Octopus. This is not a complete geographic
catalog and does not infer nationality or personal location.

## Public source verification

The developer inspected public App Store product pages and iTunes Lookup responses
on 2026-11-08. No device inventory was submitted for this verification.

- [DiDi China, App Store ID 554499054](https://apps.apple.com/us/app/didi-china-ride-hailing/id554499054)
  advertises rides in mainland China / Hong Kong. The
  [public lookup](https://itunes.apple.com/lookup?id=554499054&country=cn) returns
  bundle ID `com.xiaojukeji.didi`. The default primary-service rule is CN; a user
  can override the target when their own usage requires HK.
- [DiDi Rider, App Store ID 1362398401](https://apps.apple.com/us/app/didi-rider-affordable-rides/id1362398401)
  is a separate product. The
  [public lookup](https://itunes.apple.com/lookup?id=1362398401&country=us) returns
  `com.didi.global.passenger`. It uses ordinary transport-domain routing.

The ambiguous display name `DiDi` alone does not select a Chinese region rule.
Bundle IDs distinguish these variants. Unknown bundle IDs are not guessed from
publisher prefixes or display-name language.

## Full-review corrections (2026-11-09)

The user supplied real product bundle IDs; public primary sources establish the
service identities below. These are public app facts, not a personal device dump.
`GLOBAL` in this project's policy means outside the CN/HK local-service groups,
including services local to other markets.

- `nl.cz.app`: [CZ's app page](https://www.cz.nl/service-en-contact/cz-app)
  describes insurance cards, reimbursements and claims. It belongs to Health;
  the model's transport-operator explanation was incorrect.
- `com.go-jek.gopay`: [GoTo's launch announcement](https://www.gotocompany.com/en/news/press/goto-financial-launches-the-gopay-app-in-indonesia-expanding-its-reach-to-indonesians-from-all-levels-of-society)
  identifies GoPay as an Indonesian payments app. Route by Finance, outside CN/HK.
- `com.octopuscards.tourist`: [Octopus's tourist app](https://www.octopus.com.hk/dl/tourist-app/index.html)
  provides local Hong Kong payments and transit. Use HK even if previously in CN.
- `com.joybuy.jd`: [Joybuy's own description](https://about.joybuy.com/about/)
  identifies its European retail service. Chinese ownership does not imply CN routing.

Folder meanings should be supplied through local maps when inference is weak:
Weather, Home, Reading and Shopping are distinct from cloud storage, generic
utilities and publisher origin. Model confidence alone cannot establish those roles.

## Remaining limits

Home Screen snapshots do not supply complete service-region metadata. An existing
regional folder supplies an exact-bundle reference, not evidence for unrelated
apps sharing a publisher prefix. An app appearing in both regional groups needs
an explicit override. Pinned / unsupported folders remain protected.

Domain and region are independent. Region destinations are excluded from domain
voting, and known local services with no valid regional target remain unplaced.
Already-grouped regional exceptions are surfaced in `regional_review` while their
positions stay intact. Future broader reclassification requires an explicit policy.
