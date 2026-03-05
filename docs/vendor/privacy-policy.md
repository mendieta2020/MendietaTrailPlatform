# Privacy Policy — Quantoryn

**Effective date**: 2026-03-05
**Last updated**: 2026-03-05
**Privacy contact**: privacy@quantoryn.com
**Location**: Córdoba, Argentina

---

## 1. Who we are

Quantoryn is an endurance training platform for coaching organisations. We provide coaches
with tools to plan, monitor, and analyse athlete training. We are not a consumer service.
Access to the platform is mediated by a coach organisation — individual athletes do not
create independent accounts.

---

## 2. Data we collect

### 2.1 Data provided by the coach organisation

When a coach registers an athlete on the platform, they provide:

- Athlete name, email address, and city
- Date of birth, height, weight
- Physiological markers: maximum heart rate, resting heart rate, functional threshold power (FTP), VO₂ max estimate
- Training history and coaching notes

This data is entered directly by the coach and is used exclusively for training plan
construction and analytics within that organisation.

### 2.2 Data received from connected activity providers

When a coach connects an athlete's account to an external provider (Strava, and in future
Garmin, COROS, Polar, Suunto, Wahoo), Quantoryn receives activity data via OAuth and
webhooks:

- Activity metadata: sport type, start time, duration, distance, elevation gain/loss
- Physiological streams: heart rate, power, cadence, pace/speed
- GPS data: coordinates and altitude (when stream access is granted)
- Raw provider payload: stored verbatim for audit and re-processing

The athlete's provider account is connected by the coach with the athlete's explicit consent.
Athletes may revoke this connection at any time.

### 2.3 Technical data collected automatically

- OAuth state and nonce tokens (temporary, 15-minute TTL)
- Structured operation logs (event name, provider, outcome — never PII or credentials)
- Standard web server request logs

---

## 3. How we use data

| Data type | Purpose | Shared externally? |
|---|---|---|
| Athlete profile | Training plan construction, physiological calculations | No |
| Activity data | Plan vs Real reconciliation, load analytics, injury risk | No |
| GPS and streams | Terrain-aware analytics, heatmaps, pacing analysis | No |
| Raw provider payload | Audit trail, future re-processing | No |
| Logs | Security monitoring, incident investigation | No |

We do not use athlete data for advertising. We do not sell, transfer, or share athlete
data with any third party outside the coach's organisation.

---

## 4. Data storage

All data is stored on infrastructure managed by Quantoryn:

| Store | Technology | Purpose |
|---|---|---|
| Primary database | PostgreSQL | All domain data: athletes, plans, activities, credentials |
| Cache / task queue | Redis | OAuth nonces (15-min TTL), async task processing |

Data is stored in the cloud region where the application is deployed.
No data is transmitted to advertising platforms, analytics services, or data brokers.

---

## 5. OAuth tokens and credentials

When an athlete connects a provider account:

- Access tokens and refresh tokens are stored in the database
- Tokens are transmitted exclusively over HTTPS
- Tokens are never written to application logs
- Token expiry is tracked and used to trigger renewal prompts
- Tokens are deleted when an athlete disconnects their provider account

Token storage encryption at rest is planned as a near-term improvement.

---

## 6. Multi-tenant isolation

Every data record is scoped to a coach organisation. A coach can access data only for
athletes within their own organisation. This isolation is enforced at the database query
level on every request — it is not a UI-only control.

Cross-organisation data access is architecturally impossible.

---

## 7. Data retention

Activity data is retained for as long as the athlete record is active in the organisation.
When an athlete record is deleted by the coach, associated activity data, credentials, and
integration records are deleted by cascade.

A formal per-field data retention schedule is in development and will be published at
`docs/compliance/privacy_policy.md` when complete.

---

## 8. Data deletion requests

Athletes and coaches may request deletion of all personal data by contacting us at
**privacy@quantoryn.com** with the subject "Data Deletion Request".

We will acknowledge the request within 48 hours and complete deletion within 30 days of
identity verification.

A self-service data deletion endpoint is planned.

---

## 9. Your rights

You have the right to:

- Access the personal data held about you
- Correct inaccurate data
- Request deletion of your data
- Object to or restrict processing
- Receive your data in a portable format

To exercise any of these rights, contact **privacy@quantoryn.com**.

---

## 10. Changes to this policy

We will update this policy when our data practices change. The effective date at the top of
this document reflects the most recent revision.

---

## 11. Contact

**Privacy enquiries**: privacy@quantoryn.com
**Full compliance documentation**: `docs/compliance/privacy_policy.md`
