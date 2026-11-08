# Security Policy

## Supported versions

Only the latest released version of First60 receives security fixes.
Pre-release (0.1.0, unreleased) code is under active development; report
issues and they will be fixed before the v0.1.0 tag.

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | Yes, once released |
| < 0.1.0 | Development only   |

## Reporting a vulnerability

Do not open a public issue for a security vulnerability. Email
security@techaurah.com with a description of the issue, the steps to
reproduce it, and the version affected. We will acknowledge the report,
investigate, and agree a fix and disclosure plan with you before any
public mention.

## What First60 will never do

- Send a message to anyone without an explicit write-mode gate
  (direct, dry-run or approval) and an audit row.
- Cold-message anyone. First60 only replies to people who contacted the
  business first, plus follow-ups to those same conversations.
- Make phone calls, or give medical or trade advice. Emergency terms in
  a business pack trigger a fixed safety template and a human handoff.
- Store credentials. The demo runs with zero credentials, and the
  optional LLM responder reads its endpoint settings from environment
  variables only.

## Scope note

First60 is text-only in v0.1.0. Platform-native senders (Instagram,
WhatsApp, email) are v0.2 candidates, each behind that platform's
official API and policy review. Unofficial-client sending is out of
scope permanently.
