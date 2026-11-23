export function normalizeLookupInput(value: string): string {
  return value.trim().normalize('NFC');
}

export function normalizeLookupKey(value: string): string {
  return normalizeLookupInput(value.toLowerCase());
}
