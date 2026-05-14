const AUTH_PHONE_HINT_KEY = 'authPhoneHint';

export function readAuthPhoneHint() {
  try {
    return localStorage.getItem(AUTH_PHONE_HINT_KEY) || '';
  } catch {
    return '';
  }
}

export function writeAuthPhoneHint(phone) {
  try {
    const normalized = String(phone || '').trim();
    if (normalized) localStorage.setItem(AUTH_PHONE_HINT_KEY, normalized);
  } catch {
    // Ignore storage failures; the user menu can fall back to phone_last4.
  }
}

export function clearAuthPhoneHint() {
  try {
    localStorage.removeItem(AUTH_PHONE_HINT_KEY);
  } catch {
    // Ignore storage failures.
  }
}
