// A catchment's wards as short text: the first few by overlap, then a count of the rest.
export function formatWards(wards, max = 3) {
  if (!wards || wards.length === 0) return "";
  const shown = wards.slice(0, max).join(", ");
  return wards.length > max ? `${shown} and ${wards.length - max} more` : shown;
}
