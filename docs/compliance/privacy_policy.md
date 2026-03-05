# Privacy Policy — Quantoryn

**Effective date**: 2026-03-05
**Last updated**: 2026-03-05
**Contact**: privacy@quantoryn.com

---

## 1. What Quantoryn is

Quantoryn is a scientific coaching operating system for endurance sports organisations.
It connects structured training plans created by coaches with completed activities delivered
by athlete wearables and third-party provider APIs, and applies evidence-based analytics to
close the coaching feedback loop.

Quantoryn is **not a social network**. Data collected by the platform is used exclusively
for coaching analytics within the organisation (coach + athletes) that owns it.

---

## 2. Who this policy applies to

This policy applies to:

- **Coaches** who create and manage organisations on the platform.
- **Athletes** (alumnos) whose training data is managed within a coach's organisation.
- **Visitors** to the Quantoryn web application.

---

## 3. Data we collect

### 3.1 Data provided directly

| Data | Who provides it | Purpose |
|---|---|---|
| Name, email, city | Coach (on behalf of athlete) | Athlete profile and contact |
| Weight, height, date of birth | Coach (on behalf of athlete) | Physiological calculations (VO₂max, training zones) |
| Training plans, structured workouts | Coach | Plan vs Real reconciliation |
| Payment records | Coach | Organisation billing tracking |
| Physiological markers (FC máx, FTP, VAM) | Coach | Canonical load and zone calculations |

### 3.2 Data received from third-party providers

When an athlete connects a third-party account (e.g. Strava), Quantoryn receives:

| Data type | Source | Purpose |
|---|---|---|
| Activity metadata (sport, start time, duration, distance, elevation) | Provider API | Training load calculation, Plan vs Real reconciliation |
| GPS / polyline data | Provider API | Map visualisation (stored, not transmitted further) |
| Heart rate and power metrics | Provider API | Canonical load (TSS/TRIMP) computation |
| Raw activity payload (JSON) | Provider API | Audit trail and future re-processing |
| Athlete profile (name, profile photo from provider) | Provider OAuth handshake | Identity linking |

The athlete's provider account is connected explicitly by the coach with the athlete's
consent. Athletes may disconnect at any time through the platform.

### 3.3 Data collected automatically

| Data | Source | Purpose |
|---|---|---|
| OAuth state and nonce tokens | Browser redirect | Anti-replay CSRF protection during OAuth flow |
| Structured operation logs (event name, provider, outcome) | Application | Security monitoring and incident investigation |

Quantoryn does **not** use cookies for advertising, tracking, or analytics beyond what is
necessary for session management.

---

## 4. Data storage

| Store | Technology | Data held |
|---|---|---|
| Primary database | PostgreSQL (Railway-managed) | All domain data: athletes, plans, activities, OAuth credentials |
| Cache / broker | Redis (Railway-managed) | OAuth nonces (15-min TTL), Celery task queue |
| Static files | WhiteNoise / Railway volume | Application assets only — no personal data |

All data is stored within the same cloud region as the application deployment.
Data is **not** replicated to or stored in third-party analytics or advertising services.

---

## 5. OAuth token handling

OAuth access tokens and refresh tokens obtained from third-party providers (e.g. Strava)
are stored in the PostgreSQL database in the `OAuthCredential` table, one row per
(athlete, provider) pair.

- Tokens are **never written to application logs**.
- Tokens are transmitted exclusively over HTTPS.
- Token expiry is tracked and used to prompt renewal.
- Tokens are deleted or zeroed when an athlete disconnects a provider integration.

**TODO (planned)**: Field-level encryption of stored tokens at rest
(`p1/encrypt-oauth-tokens-at-rest`).

---

## 6. Multi-tenant data isolation

Every data record in Quantoryn is scoped to a **coach organisation** (the tenant).
An athlete's data is accessible only to the coach organisation that manages them.
No coach can read, write, or query another organisation's data — this is enforced at the
database query level on every request, not just at the UI layer.

---

## 7. Third-party data sharing

Quantoryn does **not**:

- Sell athlete data to any third party.
- Share athlete data outside the coach organisation boundary.
- Use athlete data for advertising or profiling.
- Transfer data to analytics platforms (e.g. Google Analytics, Segment).

The only third parties that receive data are the **provider APIs** (e.g. Strava) during the
OAuth token exchange and activity fetch — this is initiated by the athlete's own connection
request.

---

## 8. Data retention

Activity data is retained for as long as the athlete's record is active within the
organisation. When a coach deletes an athlete's record, associated activity data is
cascade-deleted from the primary database.

**Formal retention schedule**: TODO — a per-data-type retention schedule with automated
deletion will be published in a future update (`p1/data-retention-policy`).

---

## 9. Data deletion requests

Athletes or coaches may request deletion of all personal data by emailing
**privacy@quantoryn.com** with the subject line "Data Deletion Request".

We will action deletion requests within **30 days** of verification.

**Programmatic deletion API**: TODO — a self-service deletion endpoint is planned
(`p1/data-deletion-request-api`).

---

## 10. Your rights

Depending on your jurisdiction, you may have the right to:

- Access the personal data held about you.
- Correct inaccurate data.
- Request deletion of your data.
- Object to or restrict certain processing.
- Receive a copy of your data in a portable format.

To exercise any of these rights, contact **privacy@quantoryn.com**.

---

## 11. Changes to this policy

We will update this policy when our data practices change. The "Last updated" date at the
top of this document will reflect the most recent revision.

---

## 12. Contact

**Privacy enquiries**: privacy@quantoryn.com
**Mailing address**: [TODO: Legal entity address]
