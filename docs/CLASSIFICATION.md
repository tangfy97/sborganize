# Make categories useful

[Home](../README.md) · [Configuration example](examples/config.toml) · [Policy guide](POLICY.md)

Classify by the app's primary purpose, not its publisher, language or icon color.
Names can be ambiguous: BankID is identity verification, CZ is health insurance,
Nomad is an eSIM service, and a lounge-access app is travel rather than banking.

## A practical domain vocabulary

- `🏦💰`: banks, payment wallets, credit cards and investment accounts.
- `🧾💸`: energy/telecom bills, data plans, parking payments and spending rewards.
- `🛍️🍔📦`: shopping, groceries, food ordering and parcel delivery.
- `💬`: messages, calls and social communication.
- `🚆🚗`: maps, trains, buses and cars, including international rail.
- `✈️🧳`: flights, airports, lounges, hotels and trip booking.
- `📺🎬🎵`: news, television, movies, music and live entertainment.
- `🤖`: AI assistants, separate from news and entertainment.
- `📝🔐`: notes, mail, calendar, identity and authentication.
- `📚☁️`: reading, education, translation, cloud storage and document resources.
- `📸🎞️`: photos, cameras and media creation/editing.
- `🏠🛠️`: home devices, housing, repair services and pet care.
- `🩺🏃`: fitness, health and healthcare.
- `🌦️`: weather. A cloud emoji must not confuse weather with file storage.
- `🛠️⚙️`: general utilities, browsers and network tools.
- `🧪`: development/test apps.

These are examples, not an automatically imposed universal layout. Someone else's
frequent apps or preferred category boundaries may differ.

## Regional services and deliberate exceptions

Mainland-China and Hong Kong local shopping, government and transport can retain
separate `🇨🇳` and `🇭🇰` groups. Global tools use their domain regardless of
publisher origin. Other local markets also use ordinary domains in this policy.

If you want banks/payments and bills together across regions, add exact bundle-ID
category and GLOBAL region overrides. Keep bank and billing folders adjacent in
an explicit policy. That preference takes precedence over an older region-first
classification. It does not move unrelated local shopping into finance.

```toml
[folders.map]
Finance = "🏦💰"
Expenses = "🧾💸"

[categories]
"com.example.bank" = "Finance"
"com.example.energy" = "Expenses"

[regions]
"com.example.bank" = "GLOBAL"
"com.example.energy" = "GLOBAL"
```

Use real bundle IDs from your own local scan. These are placeholders.

## Why an app may stay for review

Rules deliberately have limited knowledge. Unknown purpose, several plausible
folders, absent destinations, protected content or uncertain regional claims
leave an app unresolved. Model confidence does not override those protections.

A saved, explicit per-app policy is the repeatable path for a fully reviewed
layout. It records every decision, including niche apps and your own prototypes,
and packs folder pages sequentially. See [public identity research](research/classification.md).
