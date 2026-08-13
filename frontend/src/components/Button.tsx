import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode;
  variant?: "default" | "dark" | "danger" | "link";
  size?: "default" | "small";
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    children,
    className = "",
    variant = "default",
    size = "default",
    type = "button",
    ...props
  },
  ref,
) {
  const classes = ["btn", variant !== "default" ? variant : "", size].filter(Boolean);
  return (
    <button ref={ref} className={[...classes, className].join(" ")} type={type} {...props}>
      {children}
    </button>
  );
});
