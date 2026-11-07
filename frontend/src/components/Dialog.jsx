import { useEffect, useRef } from "react";
import "./Dialog.css";

// A modal built on the browser's own <dialog> element, which keeps keyboard focus inside
// it and closes on Escape. Rendered only while open.
export default function Dialog({ title, description, onClose, children, width = 560 }) {
  const ref = useRef(null);

  useEffect(() => {
    const dialog = ref.current;
    dialog.showModal();
    return () => dialog.close();
  }, []);

  return (
    <dialog
      ref={ref}
      className="app-dialog"
      style={{ width: `min(${width}px, calc(100vw - 32px))` }}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClick={(e) => {
        if (e.target === ref.current) onClose(); // a click on the backdrop
      }}
    >
      <div className="app-dialog-body">
        <div className="app-dialog-header">
          <div>
            <h2 className="app-dialog-title">{title}</h2>
            {description && <p className="app-dialog-description">{description}</p>}
          </div>
          <button type="button" className="app-dialog-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>
        {children}
      </div>
    </dialog>
  );
}
