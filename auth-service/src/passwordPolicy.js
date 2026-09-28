/**
 * Documented, teaches-a-human password policy (Reto 5).
 *
 * Constants are exported so the policy is self-describing and testable.
 */
export const PASSWORD_POLICY = {
  minLength: 8,
  requireUppercase: true,
  requireLowercase: true,
  requireDigit: true,
};

export function validarPoliticaPassword(plain) {
  if (typeof plain !== 'string' || plain.length === 0) {
    return 'La contraseña es obligatoria';
  }
  if (plain.length < PASSWORD_POLICY.minLength) {
    return `La contraseña debe tener al menos ${PASSWORD_POLICY.minLength} caracteres`;
  }
  if (PASSWORD_POLICY.requireUppercase && !/[A-Z]/.test(plain)) {
    return 'La contraseña debe incluir al menos una mayúscula';
  }
  if (PASSWORD_POLICY.requireLowercase && !/[a-z]/.test(plain)) {
    return 'La contraseña debe incluir al menos una minúscula';
  }
  if (PASSWORD_POLICY.requireDigit && !/[0-9]/.test(plain)) {
    return 'La contraseña debe incluir al menos un número';
  }
  return null;
}
