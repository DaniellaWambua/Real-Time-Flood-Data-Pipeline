// Quoted CSV cells; a leading = + - @ is prefixed so spreadsheet apps never run a value as a formula
function csvCell(value) {
  let text = value == null ? "" : String(value);
  if (/^[=+\-@]/.test(text)) text = `'${text}`;
  return `"${text.replace(/"/g, '""')}"`;
}

// Build a CSV from a header row and data rows, and hand it to the browser as a download
export function downloadCsv(baseName, header, rows) {
  const lines = [header, ...rows].map((row) => row.map(csvCell).join(","));
  const blob = new Blob([lines.join("\r\n")], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${baseName}-${new Date().toISOString().slice(0, 10)}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}
