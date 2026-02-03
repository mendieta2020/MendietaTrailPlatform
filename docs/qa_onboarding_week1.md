# QA Checklist: Onboarding Coach Wizard + PMC Explainer (Week 1)

## Onboarding Wizard
- [ ] New coach sees onboarding wizard after login.
- [ ] Step 1: “Conectar Strava” button opens the existing Strava OAuth flow.
- [ ] Step 2: Create athlete form submits with required fields only and shows success.
- [ ] Step 3: Template selector loads existing templates (or shows placeholder when none).
- [ ] Step 3: Assigning a template succeeds with a valid athlete + date.
- [ ] Step 4: Tour highlights PMC widget and Alerts list.
- [ ] “Saltar por ahora” advances without blocking in each step.
- [ ] “Finalizar onboarding” closes wizard and it does not reappear after reload.
- [ ] API errors show friendly messages with a next action.

## PMC Explainer
- [ ] PMC widget auto-opens the explainer only once per coach.
- [ ] Info icon on PMC widget reopens the explainer.
- [ ] Copy matches required guidance (CTL/ATL/TSB + interpretation).

## Regression Checks
- [ ] Dashboard loads without console errors.
- [ ] Alerts widget still loads and paginates.
