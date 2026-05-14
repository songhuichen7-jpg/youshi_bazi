const AUTH_SESSION_HINT_KEY = 'authSessionHint';

export function hasAuthSessionHint() {
  try {
    return localStorage.getItem(AUTH_SESSION_HINT_KEY) === '1';
  } catch {
    return true;
  }
}

export function setAuthSessionHint() {
  try {
    localStorage.setItem(AUTH_SESSION_HINT_KEY, '1');
  } catch {
    // Ignore storage errors and fall back to cookie bootstrap.
  }
}

export function clearAuthSessionHint() {
  try {
    localStorage.removeItem(AUTH_SESSION_HINT_KEY);
  } catch {
    // Ignore storage errors and fall back to cookie bootstrap.
  }
}
