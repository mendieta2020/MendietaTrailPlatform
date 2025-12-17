// Event bus mínimo para desacoplar el cliente HTTP del routing/UI.

const logoutSubscribers = new Set();

export function subscribeOnLogout(cb) {
  logoutSubscribers.add(cb);
  return () => logoutSubscribers.delete(cb);
}

export function emitLogout(reason = 'auth_failed') {
  for (const cb of logoutSubscribers) {
    try {
      cb({ reason });
    } catch {
      // ignore
    }
  }
}
