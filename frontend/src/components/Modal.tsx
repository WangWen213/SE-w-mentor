import { useEffect, useRef } from "react";

import { Button } from "./Button";

interface ModalProps {
  open: boolean;
  title: string;
  children: React.ReactNode;
  onClose: () => void;
}

export function Modal({ open, title, children, onClose }: ModalProps) {
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) {
      return undefined;
    }
    closeRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose, open]);

  if (!open) {
    return null;
  }

  return (
    <div aria-labelledby="mentor-modal-title" aria-modal="true" className="modal" role="dialog">
      <div className="modal-box">
        <div className="modal-title" id="mentor-modal-title">
          {title}
        </div>
        <div className="modal-info">{children}</div>
        <div className="modal-actions">
          <Button ref={closeRef} variant="dark" onClick={onClose}>
            关闭
          </Button>
        </div>
      </div>
    </div>
  );
}
