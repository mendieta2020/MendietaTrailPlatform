import client from './client'

export const createReport = (membershipId, { period_days, coach_message }) =>
  client.post(`/api/coach/athletes/${membershipId}/report/`, { period_days, coach_message })

export const sendReportEmail = (membershipId, token, { recipient_email }) =>
  client.post(`/api/coach/athletes/${membershipId}/report/${token}/email/`, { recipient_email })
