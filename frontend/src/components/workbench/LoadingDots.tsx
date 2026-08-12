export function LoadingDots() {
  return (
    <span className="loading-dots" aria-hidden="true">
      <span>.</span>
      <span>.</span>
      <span>.</span>
    </span>
  );
}

export function LoadingText({ text }: { text: string }) {
  return (
    <span className="loading-text">
      {text}
      <LoadingDots />
    </span>
  );
}
