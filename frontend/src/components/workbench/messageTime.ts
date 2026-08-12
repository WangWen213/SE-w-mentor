export function formatMessageTime(value: string): string {
  const parsed = value === "now" ? new Date() : new Date(value);
  const date = Number.isNaN(parsed.getTime()) ? new Date() : parsed;
  const year = date.getFullYear();
  const month = date.getMonth() + 1;
  const day = date.getDate();
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  return `${year}-${month}-${day} ${hours}:${minutes}`;
}
