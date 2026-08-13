import { useEffect, useRef } from "react";

interface DrawerProps {
  open: boolean;
  title: string;
  children: React.ReactNode;
  onClose: () => void;
}

export function Drawer({ open, title, children, onClose }: DrawerProps) {
  const drawerRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!open) {
      return undefined;
    }
    drawerRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose, open]);

  return (
    <>
      <div className={`drawer-backdrop ${open ? "open" : ""}`} />
      <aside
        ref={drawerRef}
        aria-hidden={!open}
        aria-labelledby="mentor-drawer-title"
        aria-modal="true"
        className={`drawer ${open ? "open" : ""}`}
        role="dialog"
        tabIndex={-1}
      >
        <div className="drawer-head">
          <div className="drawer-title" id="mentor-drawer-title">
            {title}
          </div>
          <button aria-label="关闭项目记忆详情" className="drawer-close" onClick={onClose} type="button">
            ×
          </button>
        </div>
        {children}
      </aside>
    </>
  );
}
