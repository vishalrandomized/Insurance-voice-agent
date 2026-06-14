const LEGACY_DEMO_PASSWORD_ALIASES = ["sales-demo"];

function normalizePassword(value: string) {
  return value.trim().toLowerCase();
}

export function isValidDemoPassword(
  input: string,
  expectedPassword: string,
): boolean {
  const normalizedInput = normalizePassword(input);
  const normalizedExpected = normalizePassword(expectedPassword);
  if (!normalizedInput || !normalizedExpected) return false;
  return (
    normalizedInput === normalizedExpected ||
    LEGACY_DEMO_PASSWORD_ALIASES.includes(normalizedInput)
  );
}
